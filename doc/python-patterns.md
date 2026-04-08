# Python Patterns in Alexandria

This document explains the Python idioms and design patterns used throughout this
codebase. It assumes you know another language (JavaScript, Java, Go) and are
learning Python-specific ways of thinking. The examples are drawn directly from
the services in this repo.

---

## 1. Protocol vs ABC — Two Ways to Define Interfaces

Python has two distinct mechanisms for expressing "this thing must have these
methods." They differ in *when* the contract is enforced and *whether
inheritance is required*.

### ABC (Abstract Base Class) — nominal typing

`ABC` comes from the `abc` module. A class that inherits from `ABC` and
decorates methods with `@abstractmethod` **cannot be instantiated** unless all
abstract methods are implemented. The contract is enforced at construction time,
not call time.

From `services/article-fetcher/src/article_fetcher/base.py`:

```python
from abc import ABC, abstractmethod
from article_fetcher.models import Article

class DataFetcher(ABC):
    @abstractmethod
    def fetch(self) -> list[Article]:
        """Fetch the latest articles from this source."""
        ...

    @abstractmethod
    def origin_name(self) -> str:
        """Short identifier for the news outlet, e.g. 'bbc_world'."""
        ...
```

If you write `class MyFetcher(DataFetcher):` and forget to implement `fetch`,
Python raises `TypeError: Can't instantiate abstract class MyFetcher` the moment
you call `MyFetcher()`. You find out immediately, at the point of construction,
not buried in a stack trace when the method is eventually called.

Every concrete fetcher (`RssFetcher`, `AlJazeeraFetcher`, `GdeltFetcher`) must
inherit from `DataFetcher` — the relationship is explicit and required. That is
nominal typing: the class *names* its parent, and the parent enforces the rules.

### Protocol — structural typing (duck typing, formalised)

`Protocol` comes from `typing`. A class that implements all the methods of a
Protocol satisfies it **without inheriting from it**. This is Python's
formalised version of duck typing ("if it walks like a duck and quacks like a
duck, it is a duck").

From `services/article-fetcher/src/article_fetcher/dedup.py`:

```python
from typing import Protocol

class SeenUrls(Protocol):
    def contains(self, url: str) -> bool: ...
    def add(self, url: str) -> None: ...
```

The two backends — `RedisSeenUrls` and `InMemorySeenUrls` — satisfy this
Protocol, but neither inherits from it:

```python
class RedisSeenUrls:     # no parent class
    def contains(self, url: str) -> bool: ...
    def add(self, url: str) -> None: ...

class InMemorySeenUrls:  # no parent class
    def contains(self, url: str) -> bool: ...
    def add(self, url: str) -> None: ...
```

A type checker (mypy, Pyright, your IDE) will verify that any value passed as
`SeenUrls` has the right shape, but Python itself never checks it at runtime.

### Why Protocol was chosen for dedup, and ABC for fetchers

The comment in `base.py` explains the reasoning directly: "Why ABC and not
Protocol: we own all implementations, and ABC gives us runtime enforcement."

The fetchers are internal — every implementation lives in this codebase, and
we want to catch missing implementations as early as possible (at instantiation,
not at call time).

The dedup backends are more loosely coupled. If someone adds a third-party
cache that happens to expose `.contains()` and `.add()`, it can be used as a
`SeenUrls` without modification. Protocol is also useful here because the two
backends have genuinely different inheritance hierarchies — one uses `redis`,
the other uses the standard library. Forcing them to share a parent would add a
dependency that doesn't exist in the real relationship.

**Rule of thumb:** use ABC when you own all implementations and want enforcement
at construction time. Use Protocol when you want structural compatibility without
requiring inheritance — especially when the implementors come from different
libraries or teams.

---

## 2. Dataclasses — Generating Boilerplate You'd Write By Hand

In Java or Go you routinely write constructors, `toString()`, and equality
methods by hand. Python's `@dataclass` decorator generates all of these from
the field declarations.

From `services/article-fetcher/src/article_fetcher/models.py`:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Article:
    source: str
    origin: str
    title: str
    url: str
    summary: str
    published: datetime | None
    fetched_at: datetime
```

`@dataclass` generates:

- `__init__` — accepts all fields as arguments, assigns them to `self`
- `__repr__` — returns a readable string like `Article(source='rss', origin='bbc_world', ...)`
- `__eq__` — two `Article` instances are equal if all their fields are equal

You get these for free. You do not have to write them.

### Field defaults

To give a field a default value, use an `=` assignment:

```python
@dataclass
class ClassificationLabelCreate:
    name: str
    description: str
    color: str = "#76A9FA"   # default used when color is not provided
```

Fields with defaults must come after fields without defaults — same rule as
function arguments. This is enforced at class-definition time, not at call time.

For mutable defaults (lists, dicts), use `field(default_factory=...)`:

```python
from dataclasses import dataclass, field

@dataclass
class Result:
    items: list[str] = field(default_factory=list)
```

Do not write `items: list[str] = []`. Python evaluates the default once at
class definition time, so all instances would share the same list object. This
is a well-known Python footgun. `default_factory` creates a new list per
instance.

### `asdict()` for serialisation

The `dataclasses.asdict()` function recursively converts a dataclass (and any
nested dataclasses) into a plain dict. FastAPI can serialise a dict to JSON
automatically.

From `services/monitoring-api/src/monitoring_api/server.py`:

```python
return {
    "containers": [dataclasses.asdict(c) for c in containers],
    "queues":     [dataclasses.asdict(q) for q in queues],
    "exchanges":  [dataclasses.asdict(e) for e in exchanges],
}
```

### When to use dataclass vs dict vs Pydantic model

- **`dict`** — unstructured data you don't control (raw JSON payloads, DB rows
  before you know the shape). No type checking, no attribute access, no IDE
  autocomplete.
- **`@dataclass`** — structured internal data you own. The `Article` and
  `ConflictEvent` models in this project are dataclasses because we construct
  them ourselves and want typed, named attributes.
- **Pydantic `BaseModel`** — data crossing an API boundary (HTTP request bodies,
  config from environment). Pydantic validates types at runtime and produces
  clear error messages when data doesn't match the schema. `LabelUpdate`,
  `CreateRoleType`, and the other request-body models in `server.py` are
  Pydantic models for exactly this reason.

### Frozen dataclasses

Adding `frozen=True` makes instances immutable:

```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float
```

Frozen instances are hashable (can be used as dict keys or set members). If you
try to assign to a field after construction, Python raises `FrozenInstanceError`.

---

## 3. Context Managers — Guaranteed Cleanup

A context manager is the Python pattern for "do something, then always clean
up, even if an exception was raised." In Go this is `defer`; in Java it's
`try-with-resources`.

### The `with` statement

```python
with open("file.txt") as f:
    data = f.read()
# File is closed here — even if read() raised an exception.
```

Any class that implements `__enter__` and `__exit__` can be used in a `with`
statement. `__enter__` runs at the top, `__exit__` runs at the bottom (always).

### `@contextmanager` — writing one without a class

The `contextlib.contextmanager` decorator lets you write a context manager as a
generator function. The code before `yield` is `__enter__`; the code after is
`__exit__`.

```python
from contextlib import contextmanager

@contextmanager
def managed_connection(url: str):
    conn = connect(url)
    try:
        yield conn
    finally:
        conn.close()

with managed_connection("postgres://...") as conn:
    conn.execute("SELECT 1")
```

The `finally` block guarantees `conn.close()` runs even if an exception is
raised inside the `with` block.

### `@asynccontextmanager` — the async version

FastAPI replaced the older `@app.on_event("startup")` / `@app.on_event("shutdown")`
hooks with a single `lifespan` context manager. Code before the `yield` is
startup; code after is shutdown.

From `services/monitoring-api/src/monitoring_api/server.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    state["docker"] = DockerClient(project_name=config["docker_project"])
    state["db"] = DbClient(database_url=config["database_url"])
    # ...more clients...

    logger.info("Monitoring API started")
    yield
    # --- Shutdown ---
    if state["rabbitmq"] is not None:
        await state["rabbitmq"].aclose()
    if state["graph"] is not None:
        state["graph"].close()
    logger.info("Monitoring API stopped")

app = FastAPI(title="Alexandria Monitoring API", lifespan=lifespan)
```

The `yield` is where the application runs. Anything after it is guaranteed to
execute on shutdown — whether the server exits cleanly, is interrupted by
SIGTERM, or crashes. This is the correct place to close database connections,
RabbitMQ channels, and other persistent resources.

### Why this matters

Without guaranteed cleanup:
- Database connections accumulate until the server runs out of pool slots.
- File handles are held open and prevent the OS from flushing writes.
- RabbitMQ channels are left open, preventing clean consumer deregistration.

Context managers make resource lifetimes explicit and bounded. They are the
standard Python answer to "how do I ensure this gets cleaned up."

---

## 4. Threading in Python — The GIL and When Threading Helps

### The GIL

CPython (the standard Python interpreter) has a Global Interpreter Lock. At any
moment, only one thread can execute Python bytecode. Threads take turns; they
cannot run simultaneously on multiple CPU cores.

This means threading does **not** speed up CPU-bound work (computation,
parsing, number-crunching). If you have two threads computing Fibonacci numbers,
they serialise — one waits while the other runs.

### Why threading still works for I/O-bound tasks

When a thread performs I/O — reading from a socket, waiting for a database
response, sleeping — it releases the GIL. Other threads can run while the
first thread waits. This is why threading is useful for:

- Network requests (HTTP, database queries, RabbitMQ)
- File reads
- Sleep-based delays

The role-classifier service uses a single thread that blocks on ML inference
for 20–60 seconds per article. Threading allows a separate background thread
to refresh role types from the database during that window.

### `threading.Timer` — one-shot scheduled callbacks

`threading.Timer(seconds, fn)` creates a thread that sleeps for `seconds` then
calls `fn`. It is a lightweight way to schedule work without an async runtime
or a scheduler library.

From `services/role-classifier/src/role_classifier/__main__.py`:

```python
import threading

def _schedule_role_type_refresh(
    classifier: RoleClassifier,
    database_url: str,
    interval_seconds: int,
) -> None:
    def refresh() -> None:
        try:
            role_types = load_role_types(database_url)
            if role_types:
                classifier.update_role_types(role_types)
        except Exception:
            logger.exception("Role type refresh failed")
        # Reschedule regardless of success.
        _schedule_role_type_refresh(classifier, database_url, interval_seconds)

    timer = threading.Timer(interval_seconds, refresh)
    timer.daemon = True
    timer.start()
```

Each `refresh()` call reschedules itself at the end, creating a recurring loop.
The `timer.daemon = True` line marks the thread as a daemon thread.

### Daemon threads

A daemon thread is one the Python interpreter is allowed to kill when all
non-daemon threads exit. The main thread is non-daemon. If the main process
finishes (or is interrupted), daemon threads are killed automatically — you do
not need to explicitly stop them.

Non-daemon threads prevent the process from exiting until they finish. If you
forget to stop a non-daemon background thread, your service will appear to hang
on shutdown.

Use daemon threads for background maintenance tasks (cache refreshes, heartbeat
pings, metrics flushing) that should not block shutdown. Use non-daemon threads
for work that must complete before the process exits (final flush of a write
buffer, clean queue drain).

### Threading vs multiprocessing vs asyncio

| Use case | Tool |
|---|---|
| I/O-bound concurrency, simple | `threading` |
| CPU-bound parallelism (bypasses GIL) | `multiprocessing` |
| Many concurrent I/O operations, event-driven server | `asyncio` |
| ML inference (already releases GIL via C extensions) | Either threading or multiprocessing depending on memory |

Alexandria uses threading for background maintenance (Timer), and asyncio for
the HTTP-facing monitoring API. The ML services (role-classifier, ner-tagger)
use synchronous threading because the underlying native C libraries release the
GIL during inference anyway.

---

## 5. async/await and the Event Loop

### What asyncio is

`asyncio` is Python's standard library for cooperative multitasking on a single
thread. Instead of threads taking turns, you write code with `async def` and
`await` keywords that explicitly yield control back to the event loop at every
I/O point.

The event loop is a scheduler. It keeps a list of coroutines that are ready to
run. When a coroutine `await`s something (a network response, a timer, another
coroutine), it suspends and the loop runs the next ready coroutine. No threads,
no GIL contention.

This model handles thousands of concurrent connections efficiently because most
of the time those connections are waiting for I/O, not computing.

### Why FastAPI is async

FastAPI is built on Starlette, which uses asyncio. Route handlers declared with
`async def` are coroutines — the framework `await`s them. While one handler is
waiting for a database response, the event loop services other requests.

```python
@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

### The sync/async boundary problem

The Docker SDK used by monitoring-api is synchronous — it uses the `requests`
library internally, which blocks the calling thread. Calling it directly inside
an `async def` handler would block the entire event loop: no other requests
could be handled until Docker responds.

The solution is `run_in_executor`, which offloads the synchronous call to a
thread pool and returns an awaitable:

```python
@app.get("/api/status")
async def status() -> dict:
    loop = asyncio.get_event_loop()

    # Docker SDK is sync — run in a thread so we don't block the loop.
    containers = await loop.run_in_executor(
        None, docker_client.get_containers
    )

    # DB client is also sync.
    db_stats = await loop.run_in_executor(None, db_client.get_stats)
```

`None` as the first argument means "use the default ThreadPoolExecutor." The
event loop remains free to handle other requests while the thread executes the
blocking call.

This is the canonical pattern for calling synchronous code (database drivers
that don't support asyncio, legacy libraries, C extensions) from within an
async context.

### `asyncio.gather` — running multiple coroutines concurrently

```python
queues, exchanges = await asyncio.gather(
    rabbitmq_client.get_queues(),
    rabbitmq_client.get_exchanges(),
)
```

`gather` runs both coroutines concurrently and waits for both to complete.
Where sequential `await` would take `T1 + T2` time, `gather` takes `max(T1, T2)`.
This is the async equivalent of spawning two threads and joining them.

---

## 6. Error Handling Patterns

### The always-ACK pattern

In messaging systems, a message is either acknowledged (ACK) or
not-acknowledged (NACK). An unacknowledged message stays in the queue and will
be redelivered. This is correct for transient errors (database temporarily
unreachable) but wrong for permanent errors (malformed JSON, schema violation).

A malformed message will never become valid. Leaving it unacknowledged poisons
the queue — it blocks all subsequent messages and eventually fills the queue.

From `services/article-store/src/article_store/consumer.py`:

```python
def _handle_delivery(self, channel, method, properties, body):
    try:
        payload = json.loads(body)
        self._on_message(payload)
    except Exception:
        logger.exception(
            "Failed to process message: %s",
            body[:200].decode("utf-8", errors="replace"),
        )
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)
```

The `finally` block ensures ACK runs whether or not an exception was raised.
This is deliberate: non-retryable failures are logged and discarded. The message
is gone, but the queue keeps flowing.

The role-classifier uses a refinement of this: it lets connection errors
propagate (so the reconnect loop in `start()` can catch them) while ACKing on
all other exceptions:

```python
def _handle_delivery(self, channel, method, properties, body):
    try:
        payload = json.loads(body)
        self._on_message(payload)
    except (
        pika.exceptions.StreamLostError,
        pika.exceptions.AMQPConnectionError,
    ):
        raise   # Let the reconnect loop handle these.
    except Exception:
        logger.exception("Failed to process message: ...")

    channel.basic_ack(delivery_tag=method.delivery_tag)
```

Note that the ACK is outside the `try/except` here, not in a `finally` block.
This means connection exceptions propagate before the ACK is sent — the message
will be redelivered after reconnect.

### Exception hierarchies

Python exceptions inherit from `BaseException`. The two branches you care about:

- `Exception` — all "normal" errors: `ValueError`, `TypeError`, `IOError`,
  `KeyError`, etc. `except Exception:` catches all of these.
- `BaseException` — includes `Exception` plus `SystemExit`, `KeyboardInterrupt`,
  and `GeneratorExit`. These are signals that the process should exit or a
  generator should be closed. Almost never catch these.

**Bare `except:`** (no class specified) catches `BaseException`, including
`KeyboardInterrupt`. This prevents Ctrl+C from working. Never write bare
`except:` unless you have a compelling reason and immediately re-raise or exit.

**`except Exception:`** catches everything that is not a shutdown signal.
This is appropriate when you want to log an error and continue — like the
message consumers above. It is still broader than ideal; narrowing to specific
exception types when you know what can go wrong makes code easier to reason
about.

### `try/finally` for unconditional teardown

The `finally` clause runs whether the `try` block succeeds, raises, or is
interrupted. This is the right tool for "this must always happen":

```python
consumer = MessageConsumer(rabbitmq_url, on_message=_on_message)
try:
    consumer.start()
finally:
    consumer.close()     # Runs even if start() raises or is interrupted.
    publisher.close()
```

From `services/role-classifier/src/role_classifier/__main__.py`. If the service
is interrupted by SIGTERM or a keyboard interrupt, the `finally` block still
runs and closes the connections cleanly.

---

## 7. Connection Management

### Why long-lived connections break

Network connections are not permanent. They break due to:

- **Heartbeat timeouts** — the broker kills connections that haven't sent a
  heartbeat frame within the timeout window. RabbitMQ's default is 60 seconds.
- **Network partitions** — load balancer resets, container restarts, VPN drops.
- **Server-side idle connection cleanup** — some databases close connections
  that have been idle for too long.

This is why you cannot open a connection at startup and assume it will be there
indefinitely.

### Reconnect on failure with retry

The role-classifier's consumer keeps a reconnect loop because ML inference can
block the thread for up to 60 seconds, during which pika cannot send heartbeats.
The broker drops the connection. On the next `start_consuming()` call, pika
raises `StreamLostError`.

From `services/role-classifier/src/role_classifier/consumer.py`:

```python
RECONNECT_DELAY_SECONDS = 5
MAX_RECONNECT_ATTEMPTS = 10

def _reconnect(self) -> None:
    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        logger.warning(
            "Reconnecting to RabbitMQ (attempt %d/%d)",
            attempt,
            MAX_RECONNECT_ATTEMPTS,
        )
        time.sleep(RECONNECT_DELAY_SECONDS)
        try:
            self._connect()
            logger.info("Reconnected to RabbitMQ successfully")
            return
        except pika.exceptions.AMQPConnectionError:
            if attempt == MAX_RECONNECT_ATTEMPTS:
                raise

def start(self) -> None:
    while True:
        try:
            self._channel.start_consuming()
        except (
            pika.exceptions.StreamLostError,
            pika.exceptions.AMQPConnectionError,
        ) as exc:
            logger.warning("Connection lost (%s), reconnecting", exc)
            self._reconnect()
```

The reconnect uses a fixed delay rather than exponential backoff here — 5
seconds between attempts is appropriate for a local Docker network where
the broker is expected to come back quickly.

For connections to external services with variable recovery times, exponential
backoff with jitter is the standard pattern: `delay = min(cap, base * 2**attempt + random()`.

### Connect-per-operation vs connection pooling

The article-store's `consumer.py` opens one connection at startup and reuses
it for every message. This is appropriate for a message consumer because the
connection is the main purpose of the service — it must be live at all times.

The monitoring-api's `DbClient` (and most of the other DB clients) use a
connect-per-operation pattern: open a connection, run the query, close it. This
is simpler but has higher overhead per request. The psycopg library's default
behavior handles the connection efficiently at the OS level (via TCP connection
reuse in the kernel), and query frequency is low enough that this is not a
bottleneck.

**Connection pooling** (a pool of pre-opened connections shared across
requests) is the right answer when:
- Queries are frequent and connection setup overhead is measurable.
- You have many concurrent requests.
- The database imposes a hard connection limit.

Libraries like `psycopg_pool` or SQLAlchemy's pool provide this. It is not used
here because the monitoring-api query rate is low and each client is
single-threaded.

---

## 8. Type Hints — Documentation That Tools Can Check

### What they are

Type hints are annotations on variables and function signatures that describe
the expected types. Python ignores them at runtime — they have no effect on
execution. Their value is entirely for tooling: IDEs, type checkers like mypy,
and anyone reading the code.

```python
def fetch(self) -> list[Article]:
    ...

def contains(self, url: str) -> bool:
    ...
```

Without type hints, a reader of `fetch()` does not know what the function
returns without reading the implementation. With type hints, the contract is
stated explicitly in the signature.

### Common forms

**Union types** — a value can be one of several types. In Python 3.10+ the
preferred syntax uses `|`:

```python
published: datetime | None     # either a datetime, or None
docker_client: DockerClient | None = None
```

`X | None` is equivalent to `Optional[X]` from `typing`. Both are valid;
`X | None` is preferred in Python 3.10+.

**Built-in generics** — Python 3.9+ allows using the built-in types directly
as generics:

```python
list[Article]         # a list of Article objects
dict[str, str]        # a dict with str keys and str values
list[dict]            # a list of dicts (untyped dict values)
Callable[[dict], None]  # a function taking dict, returning None
```

Before Python 3.9 you needed `from typing import List, Dict` and wrote
`List[Article]`. The lowercase forms are now preferred.

**Protocol as a type hint** — in `runner.py`, `FetchLoop` accepts both
`DataFetcher` (ABC) and `SeenUrls` (Protocol) as constructor arguments:

```python
def __init__(
    self,
    fetcher: DataFetcher,
    on_message: Callable[[Article], None],
    seen_urls: SeenUrls | None = None,
) -> None:
```

`seen_urls: SeenUrls | None = None` means: accept any object that implements
`SeenUrls` (has `.contains()` and `.add()`), or `None` (default to in-memory).

### Runtime behaviour

Type hints are not enforced at runtime. If you call `fetch()` and it returns a
string instead of `list[Article]`, Python will not raise an error — the type
hint is not a runtime contract. Only a type checker run as a separate tool
(mypy, Pyright) will catch that mismatch.

This is a meaningful difference from statically typed languages. The type
system here is advisory for humans and tools, not enforced by the interpreter.

**`cast()`** (from `typing`) is a way to tell the type checker "trust me, this
is X" without performing any actual check:

```python
from typing import cast
x = cast(list[str], some_function())  # No runtime effect; just a type hint.
```

Use it sparingly — it is telling the type checker to stop checking, which
defeats the purpose.

### Where Pydantic differs

Pydantic's `BaseModel` *does* enforce types at runtime during construction.
When FastAPI receives an HTTP request and constructs a `LabelUpdate` from the
JSON body, Pydantic validates that `labels` is a list of strings. If it is not,
FastAPI returns a 422 response automatically.

This is a key reason to use Pydantic at API boundaries and dataclasses for
internal data: Pydantic gives you runtime validation on untrusted input, while
dataclasses give you lightweight structured data for internal use where you
trust the construction site.
