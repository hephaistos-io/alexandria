"""DockerClient — reads container status from the local Docker socket.

The Docker SDK communicates with the Docker daemon via a Unix socket at
/var/run/docker.sock. Inside a container you mount that socket as a volume
to give the container visibility into the host's Docker engine.

We filter to containers that belong to the Alexandria Compose project by
checking the 'com.docker.compose.project' label that Compose attaches
automatically. This avoids surfacing unrelated containers on the same host.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Guard import: docker SDK may not be importable in all environments.
# We catch ImportError so the rest of the app still starts without it.
try:
    import docker
    import docker.errors

    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False


@dataclass
class PipelineLabels:
    """Pipeline topology metadata parsed from 'alexandria.pipeline.*' Docker labels.

    These labels are set in docker-compose.yml on each service that participates
    in the data pipeline. The topology builder reads these to discover the graph
    without any hard-coded service names.

    Fields can be None when a label is absent — e.g. a pure store (postgres) has
    no inputs or outputs, only a role.
    """

    inputs: str | None  # e.g. "queue:articles.rss" or "queue:articles.raw"
    outputs: str | None  # e.g. "queue:articles.tagged" or "exchange:articles.scraped"
    stores: str | None  # e.g. "postgres" or "redis"
    role: str | None  # e.g. "store" — marks infrastructure nodes
    icon: str | None  # Material icon name for the frontend
    label: str | None  # Short display label (used by fetchers to show origin)
    sublabel: str | None  # Secondary display label (e.g. "HTML → content")
    accent: str | None  # Optional colour accent token (e.g. "error")


@dataclass
class ContainerStatus:
    name: str
    instance: int  # com.docker.compose.container-number (1-indexed, >1 when scaled)
    status: str
    health: str | None
    uptime_seconds: int | None
    restart_count: int


def _parse_uptime(started_at: str) -> int | None:
    """Return elapsed seconds since the container started.

    Docker gives us an ISO 8601 string like '2026-03-21T08:00:00.123456789Z'.
    Python's fromisoformat handles the format up to microseconds, but the
    Docker timestamp includes *nanoseconds* (9 decimal digits). We truncate
    to 6 digits before parsing.

    Returns None if parsing fails rather than crashing the whole request.
    """
    try:
        # Truncate sub-second part to 6 digits (microseconds) for fromisoformat.
        if "." in started_at:
            base, frac_and_tz = started_at.split(".", 1)
            # frac_and_tz looks like "123456789Z" — keep only 6 digits of fraction.
            frac = frac_and_tz.rstrip("Z")[:6]
            started_at = f"{base}.{frac}+00:00"
        else:
            started_at = started_at.replace("Z", "+00:00")

        started = datetime.fromisoformat(started_at)
        now = datetime.now(tz=UTC)
        return max(0, int((now - started).total_seconds()))
    except Exception:
        logger.warning("Could not parse container start time: %r", started_at)
        return None


def _get_health(attrs: dict) -> str | None:
    """Extract health status from container attrs, or None if no healthcheck."""
    try:
        return attrs["State"]["Health"]["Status"]
    except KeyError:
        return None


class DockerClient:
    """Reads Alexandria container statuses from the Docker socket.

    Instantiated once at app startup. The underlying docker.DockerClient
    is lazy — it does not open the socket until the first API call.
    """

    COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
    COMPOSE_SERVICE_LABEL = "com.docker.compose.service"

    def __init__(self, project_name: str = "alexandria") -> None:
        self._project_name = project_name
        self._client = None  # Opened lazily on first use.

    def _ensure_client(self) -> bool:
        """Open docker client if not already open. Returns False if unavailable."""
        if self._client is not None:
            return True
        if not _DOCKER_AVAILABLE:
            return False
        try:
            self._client = docker.from_env()
            return True
        except Exception as exc:
            logger.warning("Docker socket unavailable: %s", exc)
            return False

    def get_containers(self) -> list[ContainerStatus]:
        """Return status for all Alexandria containers.

        Returns an empty list (not an exception) if the Docker socket is
        unavailable — the monitoring page degrades gracefully.
        """
        if not self._ensure_client():
            return []

        try:
            containers = self._client.containers.list(
                all=True,
                filters={"label": f"{self.COMPOSE_PROJECT_LABEL}={self._project_name}"},
            )
        except Exception as exc:
            logger.warning("Failed to list containers: %s", exc)
            return []

        results: list[ContainerStatus] = []
        for c in containers:
            labels = c.labels or {}
            service_name = labels.get(self.COMPOSE_SERVICE_LABEL, c.name)

            # Skip the base image build container — it's not a runtime service.
            if service_name == "base":
                continue

            try:
                attrs = c.attrs
                container_number = int(labels.get("com.docker.compose.container-number", "1"))
                results.append(
                    ContainerStatus(
                        name=service_name,
                        instance=container_number,
                        status=c.status,
                        health=_get_health(attrs),
                        uptime_seconds=_parse_uptime(attrs["State"]["StartedAt"]),
                        restart_count=attrs.get("RestartCount", 0),
                    )
                )
            except Exception as exc:
                logger.warning("Error reading container %s: %s", c.name, exc)

        return results

    def get_raw_client(self):
        """Return the underlying docker.DockerClient, or None if unavailable.

        Used by LogStreamer to access the low-level container API for log
        streaming. Returns None if the Docker socket is not accessible.
        """
        if not self._ensure_client():
            return None
        return self._client

    @property
    def project_name(self) -> str:
        """Return the Compose project name used for container filtering."""
        return self._project_name

    def get_pipeline_labels(self) -> dict[str, PipelineLabels]:
        """Return pipeline topology labels keyed by service name.

        Reads all Alexandria containers and extracts 'alexandria.pipeline.*' labels
        from any container that has at least one such label. Services without any
        pipeline labels (e.g. rabbitmq, frontend) are excluded.

        Returns an empty dict if Docker is unavailable.
        """
        if not self._ensure_client():
            return {}

        try:
            containers = self._client.containers.list(
                all=True,
                filters={"label": f"{self.COMPOSE_PROJECT_LABEL}={self._project_name}"},
            )
        except Exception as exc:
            logger.warning("Failed to list containers for pipeline labels: %s", exc)
            return {}

        results: dict[str, PipelineLabels] = {}
        for c in containers:
            labels = c.labels or {}
            service_name = labels.get(self.COMPOSE_SERVICE_LABEL, c.name)

            # Collect only keys that start with our prefix.
            prefix = "alexandria.pipeline."
            pipeline_labels = {
                k[len(prefix):]: v
                for k, v in labels.items()
                if k.startswith(prefix)
            }

            # Skip services with no pipeline labels at all.
            if not pipeline_labels:
                continue

            results[service_name] = PipelineLabels(
                inputs=pipeline_labels.get("inputs"),
                outputs=pipeline_labels.get("outputs"),
                stores=pipeline_labels.get("stores"),
                role=pipeline_labels.get("role"),
                icon=pipeline_labels.get("icon"),
                label=pipeline_labels.get("label"),
                sublabel=pipeline_labels.get("sublabel"),
                accent=pipeline_labels.get("accent"),
            )

        return results
