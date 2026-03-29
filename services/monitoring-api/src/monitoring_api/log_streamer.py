"""LogStreamer — tails Docker container logs and feeds them into an asyncio queue.

Architecture
------------
Docker's log API is synchronous (backed by the `requests` library). We can't
call it from an async handler without blocking the event loop. The solution is
a polling loop that runs in a dedicated thread per container.

Each thread polls for new log lines every POLL_INTERVAL seconds using
`container.logs(since=last_ts)`. Between polls the thread sleeps on a
`threading.Event` — this is a *cancellable* sleep: calling `event.set()` wakes
all threads immediately so they can exit cleanly.

Why polling instead of streaming?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The previous version used `container.logs(stream=True, follow=True)` which
returns a blocking generator that yields bytes forever. The problem:
`asyncio.to_thread()` can cancel the *Task* wrapping the function, but it
CANNOT interrupt the underlying thread — Python threads can't be forcibly
killed. So every WebSocket disconnect left zombie threads blocking on the
Docker socket. After a few reconnects the default ThreadPoolExecutor was
exhausted and the `/api/status` endpoint deadlocked.

Polling with a 2-second interval solves this: threads check a stop flag
between polls and exit within 2 seconds of being asked to stop. The trade-off
is slightly delayed log delivery, but 2 seconds is fine for a monitoring UI.

Thread -> Queue -> WebSocket
         (async bridge)
"""

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Guard import: docker SDK may not be present in all environments.
try:
    import docker  # noqa: F401 — imported to test availability

    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False

# How often each thread polls Docker for new log lines (seconds).
POLL_INTERVAL = 2.0

# Sentinel object placed in the queue when a container's poll loop ends.
_STREAM_DONE = object()


def _poll_container(
    container,  # docker.models.containers.Container
    service_name: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
) -> None:
    """Blocking function: polls log lines from one container and enqueues them.

    Runs in a thread. Reads new logs every POLL_INTERVAL seconds using the
    `since` parameter to only fetch lines we haven't seen yet. Exits cleanly
    when stop_event is set.

    Args:
        container: Docker SDK container object.
        service_name: Compose service label used as the "service" field.
        queue: asyncio.Queue that the WebSocket handler reads from.
        loop: Running event loop — needed for call_soon_threadsafe.
        stop_event: Set by stop() to signal this thread to exit.
    """
    # Start by reading the last 50 historical lines.
    last_ts = None

    try:
        # Initial batch: get recent history.
        raw = container.logs(tail=50, timestamps=True)
        last_ts = _process_log_bytes(raw, service_name, queue, loop)

        # Poll for new lines until told to stop.
        # stop_event.wait(POLL_INTERVAL) is a cancellable sleep — it returns
        # True immediately if the event is set, or False after the timeout.
        while not stop_event.wait(POLL_INTERVAL):
            try:
                kwargs: dict = {"timestamps": True}
                if last_ts is not None:
                    kwargs["since"] = last_ts

                raw = container.logs(**kwargs)
                new_ts = _process_log_bytes(raw, service_name, queue, loop)
                if new_ts is not None:
                    last_ts = new_ts
            except Exception as exc:
                logger.warning("Error polling logs for %s: %s", service_name, exc)

    except Exception as exc:
        logger.warning("Log polling failed for %s: %s", service_name, exc)
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, _STREAM_DONE)


def _process_log_bytes(
    raw: bytes,
    service_name: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> datetime | None:
    """Parse a batch of Docker log bytes and enqueue each line.

    Returns the timestamp of the last line processed (for use as `since` in
    the next poll), or None if no lines were found.
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    latest_dt: datetime | None = None

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Docker prepends a timestamp when timestamps=True:
        #   "2026-03-21T10:15:00.123456789Z some log message"
        ts_prefix, _, remainder = line.partition(" ")

        entry = _parse_log_line(remainder, service_name, ts_prefix)
        loop.call_soon_threadsafe(queue.put_nowait, entry)

        # Track the latest Docker timestamp for the `since` parameter.
        dt = _parse_docker_ts_as_datetime(ts_prefix)
        if dt is not None:
            latest_dt = dt

    return latest_dt


def _parse_log_line(text: str, service_name: str, docker_ts: str) -> dict:
    """Parse a single log line into a structured dict.

    If the text is valid JSON (i.e. the service uses our JsonFormatter), we
    return it as-is (already has ts/level/service/logger/message fields).

    If it's not JSON (third-party output, Python tracebacks, etc.), we wrap
    it in a minimal envelope so the frontend always receives the same shape.
    """
    try:
        parsed = json.loads(text)
        # Validate it has the fields we expect from our JsonFormatter.
        if isinstance(parsed, dict) and "message" in parsed:
            return parsed
        # It's JSON but not our format — wrap it.
        return _wrap_raw(text, service_name, docker_ts)
    except (json.JSONDecodeError, ValueError):
        return _wrap_raw(text, service_name, docker_ts)


def _wrap_raw(text: str, service_name: str, docker_ts: str) -> dict:
    """Wrap a non-JSON log line in our standard envelope."""
    ts = _parse_docker_ts(docker_ts) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "ts": ts,
        "level": "info",
        "service": service_name,
        "message": text,
    }


def _parse_docker_ts(ts: str) -> str | None:
    """Normalise Docker's nanosecond-precision timestamp to our format.

    Docker gives us e.g. "2026-03-21T10:15:00.123456789Z". We truncate the
    sub-second part to 0 digits for a clean ISO 8601 output.
    Returns None if the string is empty or unparseable.
    """
    dt = _parse_docker_ts_as_datetime(ts)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_docker_ts_as_datetime(ts: str) -> datetime | None:
    """Parse Docker's timestamp into a datetime object.

    Used both for formatting (in _parse_docker_ts) and for tracking the
    `since` parameter in the polling loop.
    """
    if not ts:
        return None
    try:
        base = ts.split(".")[0].rstrip("Z")
        return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


class LogStreamer:
    """Manages concurrent log polling for all Alexandria containers.

    Usage:
        streamer = LogStreamer(docker_client)
        async for entry in streamer.stream():
            await websocket.send_json(entry)

    The stream() method is an async generator. It yields dicts (one per log
    line) until stop() is called or all containers stop producing logs.

    Key difference from the previous streaming approach: threads here EXIT
    cleanly when stop() is called, because they poll with a cancellable sleep
    instead of blocking on follow=True.
    """

    def __init__(self, docker_client) -> None:
        self._docker_client = docker_client
        self._stop_event = threading.Event()
        # Dedicated thread pool so log-polling threads don't compete with
        # the default executor used by /api/status for Docker SDK calls.
        self._executor = ThreadPoolExecutor(max_workers=12, thread_name_prefix="log-poll")
        self._futures: list = []

    async def stream(self):  # -> AsyncIterator[dict]
        """Async generator that yields log entry dicts from all containers."""
        if not _DOCKER_AVAILABLE:
            yield {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "error",
                "service": "monitoring-api",
                "message": "Docker SDK not available",
            }
            return

        raw_client = self._docker_client.get_raw_client()
        if raw_client is None:
            yield {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "error",
                "service": "monitoring-api",
                "message": "Docker socket unavailable",
            }
            return

        try:
            containers = raw_client.containers.list(
                all=False,
                filters={
                    "label": (
                        f"{self._docker_client.COMPOSE_PROJECT_LABEL}"
                        f"={self._docker_client.project_name}"
                    )
                },
            )
        except Exception as exc:
            logger.warning("Failed to list containers for log streaming: %s", exc)
            yield {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "error",
                "service": "monitoring-api",
                "message": f"Failed to list containers: {exc}",
            }
            return

        # Filter out containers whose logs aren't useful in the pipeline terminal:
        #   - "base": build-only container, never runs
        #   - "frontend": Vite dev server output (HMR, module resolution) is noisy
        #   - "monitoring-api": own request/poll logs create feedback loops
        _EXCLUDED_SERVICES = {"base", "frontend", "monitoring-api"}
        containers = [
            c
            for c in containers
            if (c.labels or {}).get(self._docker_client.COMPOSE_SERVICE_LABEL)
            not in _EXCLUDED_SERVICES
        ]

        if not containers:
            yield {
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": "info",
                "service": "monitoring-api",
                "message": "No running containers found",
            }
            return

        logger.info("Polling logs from %d containers", len(containers))

        queue: asyncio.Queue[dict | object] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Submit each container's poll loop to our dedicated thread pool.
        for container in containers:
            service_name = (container.labels or {}).get(
                self._docker_client.COMPOSE_SERVICE_LABEL, container.name
            )
            future = self._executor.submit(
                _poll_container, container, service_name, queue, loop, self._stop_event
            )
            self._futures.append(future)

        active_streams = len(self._futures)

        try:
            while active_streams > 0:
                item = await queue.get()
                if item is _STREAM_DONE:
                    active_streams -= 1
                else:
                    yield item
        except asyncio.CancelledError:
            self.stop()
            raise
        finally:
            self.stop()

    def stop(self) -> None:
        """Signal all polling threads to exit and shut down the thread pool.

        Sets the stop event (wakes all threads from their sleep immediately),
        then shuts down the executor. Threads will exit within one poll cycle.
        """
        self._stop_event.set()
        self._executor.shutdown(wait=False)
        self._futures = []
