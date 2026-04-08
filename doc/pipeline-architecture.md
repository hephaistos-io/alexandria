# Pipeline Architecture

A conceptual guide to how Alexandria moves data between services using a message-driven pipeline.

---

## 1. Message Queues and AMQP

### The problem with direct HTTP calls

The simplest way to connect two services is a direct HTTP call: service A finishes work, calls service B's REST endpoint, waits for a response. This works at small scale, but it creates tight coupling:

- If service B is down, service A either fails or has to implement its own retry logic.
- If service B is slow, service A blocks waiting for it.
- If you want service C to also receive the same data, you have to change service A's code.
- You can only scale both services together — you can't run three instances of B for every one instance of A without a load balancer in between.

A **message queue** solves this by putting a buffer between producers and consumers. Service A publishes a message to the queue and immediately moves on. Service B reads from the queue whenever it is ready. The two services never talk to each other directly.

This gives you:
- **Temporal decoupling** — producer and consumer don't need to be running at the same time.
- **Flow control** — if consumers fall behind, messages accumulate in the queue rather than causing backpressure or dropped work.
- **Fan-out** — multiple consumers can read the same message without changing the producer.
- **Observability** — queue depth is a real-time signal of how far behind consumers are.

### What is AMQP?

**AMQP** (Advanced Message Queuing Protocol) is the wire protocol that RabbitMQ speaks. You do not need to understand the protocol itself in detail, but knowing the vocabulary helps.

RabbitMQ structures messaging around three concepts:

**Exchanges** receive messages from publishers. The exchange applies routing logic and forwards messages to one or more queues. The exchange never stores messages — it only routes them.

**Queues** store messages until a consumer reads and acknowledges them. Queues are durable (survive broker restarts) or transient (lost on restart). Messages sit in a queue until a consumer is ready to process them.

**Bindings** connect an exchange to a queue, with an optional routing key. When a message arrives at an exchange, the exchange checks its bindings to decide which queues to deliver to.

A publisher always targets an exchange (even when using the default exchange). A consumer always reads from a queue. The exchange sits between them as the routing layer.

### Exchange types

**Direct exchange** — routes a message to queues whose binding key exactly matches the message's routing key. Use this when you want one consumer type per message type. The default exchange (empty string `""`) is a special direct exchange that routes by queue name — convenient for simple point-to-point cases.

**Fanout exchange** — broadcasts every message to all bound queues, ignoring the routing key entirely. Use this when multiple independent consumers need to process the same data. Adding a new consumer only requires declaring a new queue and binding it — no changes to the publisher.

**Topic exchange** — routes based on wildcard pattern matching against the routing key (e.g. `logs.error.*` or `news.#`). Use this when you need selective routing across a namespace of message types. Alexandria does not currently use topic exchanges, but they are the natural next step if the pipeline grows more conditional routing requirements.

---

## 2. The Pipeline Pattern

Alexandria chains services into a linear pipeline where each stage consumes from one queue, does work, and publishes results to the next queue (or exchange). This is the **pipe-and-filter** architectural pattern applied to distributed services.

The shape of the full article pipeline is:

```
RSS Feeds (multiple sources)
        |
        |  [article-fetcher-*]  (one instance per feed)
        v
  [ articles.rss ]  <-- durable queue
        |
        |  [article-scraper]  fetches full HTML, extracts text
        v
  < articles.scraped >  <-- fanout exchange
        |               |
        v               v
 [articles.raw]  [articles.training]
        |               |
        |  [ner-tagger]  |  [article-store]
        v               v
 [articles.tagged]  [PostgreSQL]  (raw article storage for labelling)
        |
        |  [entity-resolver]  links mentions to Wikidata
        v
 [articles.resolved]
        |
        |  [role-classifier]  zero-shot entity role NLI
        v
 [articles.role-classified]
        |
        |  [topic-tagger]  zero-shot topic classification
        v
  < articles.classified >  <-- fanout exchange
        |                    |
        v                    v
[articles.classified.store]  [articles.classified.relation]
        |                              |
        |  [label-updater]             |  [relation-extractor]
        v                              v
   [PostgreSQL]                     [Neo4j]
   (auto-labels)               (entity relations graph)


Conflict data pipeline (parallel, independent):

OSINT / UCDP / GDELT fetchers
        |
        v
 [conflict_events.raw]
        |
        |  [conflict-store]
        v
   [PostgreSQL]
   (conflict events)
        |
        |  [event-detector]  (polls DB, writes back)
        v
   [PostgreSQL]
   (named events)


Natural disaster pipeline (parallel, independent):

NASA EONET API
        |
        |  [nasa-eonet-fetcher]  (polls every 30 min)
        v
 [natural_disasters.raw]
        |
        |  [disaster-store]  (entrypoint inside article-store)
        v
   [PostgreSQL]
   (natural disasters)
```

The natural-disaster branch is deliberately shaped like the conflict branch: one fetcher,
one raw queue, one writer, one table. It is not wired into `event-detector`, the NLP
pipeline, or the article heatmap — disasters and conflicts are kept as separate map layers
rather than fused. See `natural-disasters.md` for the full rationale.

Each service in this graph:
1. Knows only about its input queue and its output exchange or queue.
2. Does not know what comes before or after it.
3. Can crash, restart, or scale independently without affecting other stages.

This independence is what makes the pattern powerful. The NER tagger does not care whether there is one article-scraper or ten. The article-scraper does not care whether the NER tagger is currently down. Messages pile up in the queue, and processing resumes when the consumer recovers.

It also enables language agnosticism. Every service communicates via JSON over AMQP. A future service could be written in Go, Rust, or Java and slot into the same pipeline by reading and writing to the same queues — nothing in the protocol is Python-specific.

---

## 3. The Fanout Pattern

At two points in the pipeline, a service needs to send the same data to multiple independent consumers:

- `article-scraper` publishes to `articles.scraped` (fanout), which feeds both the NLP pipeline (`articles.raw`) and the training data store (`articles.training`).
- `topic-tagger` publishes to `articles.classified` (fanout), which feeds both the label-updater (`articles.classified.store`) and the relation-extractor (`articles.classified.relation`).

The critical property of a fanout exchange is that **each bound queue gets its own independent copy of every message**. The NER tagger consuming from `articles.raw` does not affect the article-store consuming from `articles.training`. Each queue has its own read pointer and its own acknowledgement state.

Without a fanout exchange, you would have two options, both worse:
1. The publisher sends to both queues manually. Now the publisher has to know about all its consumers, and adding a consumer requires changing the publisher.
2. Consumers coordinate to share messages from a single queue. This requires complex partitioning logic and breaks the independence guarantee.

**When to use fanout vs direct:** use a fanout exchange when you have multiple consumers that each need the full stream of messages independently. Use a direct exchange (or the default exchange) when there is one consumer type and you want simple point-to-point delivery, or when you want competing consumers (multiple instances of the same service sharing work from one queue).

---

## 4. Reliability Patterns

A message queue is only reliable if you configure it correctly. There are two distinct failure scenarios: broker restarts, and consumer crashes.

### Durable queues and persistent messages

A **durable queue** survives a RabbitMQ broker restart. The queue's existence and its undelivered messages are written to disk. If you declare a queue without `durable=True`, a broker restart erases it along with everything in it.

A **persistent message** is written to disk by the broker before it acknowledges receipt from the publisher. If the broker crashes mid-flight, persistent messages survive. If you publish without `delivery_mode=pika.DeliveryMode.Persistent`, messages are held only in memory and are lost on crash.

Both settings are required together. A durable queue with non-persistent messages still loses in-flight messages on crash. Persistent messages into a non-durable queue means the queue itself disappears. In Alexandria every queue is declared durable and every message is published persistent — you can see this pattern consistently across all publisher files.

Note: "written to disk" does not mean immediately flushed. RabbitMQ batches disk writes for performance. For truly zero-loss semantics you need publisher confirms (the broker explicitly acknowledges that it wrote to disk before the publisher proceeds). Alexandria does not use publisher confirms — the tradeoff is that a broker crash at exactly the wrong moment could lose the in-flight batch. For an OSINT pipeline this is an acceptable risk: duplicate articles are filtered by deduplication logic, and a missed article is not catastrophic.

### The always-ACK pattern

When a consumer receives a message, RabbitMQ waits for an **acknowledgement (ACK)** before removing the message from the queue. If the consumer crashes before ACKing, RabbitMQ redelivers the message to another consumer — this is the core durability guarantee.

However, this creates a subtle problem for certain failure modes. Consider what happens when the article-scraper receives a URL that returns a 404, or the NER tagger receives malformed JSON. If the consumer NACKs (negative acknowledgement) or crashes mid-processing, RabbitMQ redelivers the message. The same broken message comes back, fails again, and loops forever — a **poison message** that blocks the queue.

Alexandria avoids this by ACKing unconditionally in the `finally` block:

```python
try:
    payload = json.loads(body)
    self._on_message(payload)
except Exception:
    logger.exception("Failed to process message: ...")
finally:
    channel.basic_ack(delivery_tag=method.delivery_tag)
```

The message is consumed regardless of whether processing succeeded. Failed articles are logged but discarded. The reasoning is explicit in the code comments: "failed extractions (404, timeout, empty content) won't succeed on retry, so leaving them unacked would poison the queue."

This is the right call for work that is not idempotently retryable. For work where retries would succeed (e.g. a transient database error), you would instead NACK with `requeue=True`, or use a dead-letter queue to park failed messages for inspection.

### prefetch_count and why it matters

By default, RabbitMQ will push as many messages to a consumer as it can, regardless of whether the consumer has finished processing previous ones. For a fast consumer this is fine. For a slow consumer — one that makes HTTP requests, runs ML inference, or writes to a database — buffering multiple messages means:

- The consumer holds messages in memory that it cannot process yet.
- Other consumer replicas sit idle even though there is work to do.
- If the consumer crashes, all buffered (but unacked) messages need to be redelivered.

`channel.basic_qos(prefetch_count=1)` tells RabbitMQ: "do not send me another message until I have ACKed the current one." With `prefetch_count=1`, each consumer replica holds exactly one message at a time. Work is distributed fairly across replicas. This is the standard pattern for slow or CPU-bound consumers.

---

## 5. The Heartbeat Problem

This is the most operationally tricky aspect of using pika in a pipeline with slow or blocking operations. Understanding it will save hours of debugging.

### What heartbeats are

AMQP connections include a **heartbeat** mechanism. The broker and client each send a small "are you still there?" frame at regular intervals. If one side stops receiving heartbeats, it assumes the other side has crashed and closes the connection. The default RabbitMQ heartbeat interval is 60 seconds — both sides send a frame every 60 seconds, and the connection is considered dead if no frame is received within 2× the interval.

### Why pika's BlockingConnection cannot send heartbeats during work

Pika's `BlockingConnection` is single-threaded. It processes network I/O (including heartbeat frames) only when the event loop is running — specifically, only when you call `connection.process_data_events()` or `connection.sleep()`, or when `start_consuming()` is blocked waiting for messages.

When your callback is executing (running ML inference, waiting for an HTTP response, writing to a database), pika's event loop is not running. No heartbeats are sent. If this takes longer than the heartbeat deadline, RabbitMQ closes the connection from its side. The next time pika tries to do anything with the connection — send a message, ACK a delivery — it raises `StreamLostError`.

This is a genuine footgun. The code looks correct, the connection was valid when you started, and then it fails silently during a long operation.

### The three mitigations used in Alexandria

**1. Long heartbeat timeout (600 seconds)**

The NER tagger and topic-tagger set `params.heartbeat = 600` before connecting. This gives 10 minutes before RabbitMQ considers the connection dead. For ML inference that takes 1-30 seconds per article, this is sufficient margin.

The tradeoff: a genuinely dead connection takes longer to detect. For a consumer that processes messages one at a time and ACKs immediately, this is fine — the next ACK will fail fast anyway.

**2. `connection.sleep()` instead of `time.sleep()`**

The article-fetcher needs to wait between polling cycles (e.g. 60 or 900 seconds between feed checks). If it calls `time.sleep(900)`, pika's event loop is frozen for 15 minutes. Heartbeats are not sent. RabbitMQ kills the connection.

The fix is to call `self._connection.sleep(seconds)` instead. This is pika's own sleep implementation, which processes I/O events (including heartbeat frames) in a loop while waiting. The result is that the connection stays alive during idle periods.

**3. Connect-per-publish for the article-scraper**

The article-scraper has a different structure: it is primarily a consumer (blocking in `start_consuming()`) but it also needs to publish after each scrape. It holds both a consumer connection and a publisher connection.

The consumer connection is fine — `start_consuming()` keeps the event loop running and heartbeats are processed normally. The publisher connection is the problem: it sits idle during scraping (HTTP fetch, HTML parsing, etc.) and will eventually time out.

The article-scraper solves this differently from the NER tagger: it uses a **connect-per-publish** pattern. Each call to `publish()` opens a fresh connection, declares the exchange, publishes the message, and closes the connection. There is no long-lived publisher connection to time out. The overhead of a TCP handshake per article is negligible compared to an HTTP fetch.

This is a valid alternative to the long-heartbeat approach and is simpler to reason about: there is no connection state to manage. The downside is latency cost per publish, which only matters if you are publishing at high volume.

The NER tagger and topic-tagger use a different approach: they hold a long-lived publisher connection (separate from their consumer connection) with `heartbeat=600`. The comments in `topic_tagger/publish.py` explain the tradeoff explicitly — the publisher connection sits idle during inference and will be killed if inference takes more than 600 seconds, at which point `StreamLostError` is caught and the connection is re-established before retrying.

The key insight: **a consumer connection and a publisher connection have different idle profiles**. The consumer connection is kept alive by `start_consuming()`. The publisher connection sits idle between messages. They need separate treatment.

---

## 6. Reconnection and Resilience

### StreamLostError

`pika.exceptions.StreamLostError` is raised when pika tries to use a connection that the broker has already closed (typically due to a missed heartbeat, or a broker restart). It is distinct from `AMQPConnectionError`, which is raised when the initial TCP connection fails.

You will see this exception in two places:
- On `basic_publish()` — the connection was lost between the last publish and this one.
- On the next I/O operation after a long blocking period.

The handling pattern throughout Alexandria is: catch `StreamLostError`, reconnect, retry the operation once. If the retry fails, propagate the exception.

### Exponential backoff vs fixed delay

Alexandria uses a fixed delay (`RECONNECT_DELAY_SECONDS = 5`) rather than exponential backoff. For a deployment where the broker restarts (e.g. an upgrade), a fixed 5-second delay with 5 attempts gives 25 seconds of grace time, which is sufficient.

In a production system with unpredictable broker availability, exponential backoff (2s, 4s, 8s, 16s...) with jitter is preferred because it reduces thundering-herd reconnection storms when the broker comes back online and all consumers try to reconnect simultaneously. This is a known area for improvement.

### Connect-per-publish vs long-lived connections for publishers

There are two viable patterns for publishers:

**Long-lived connection:** establish once, reuse across many publishes, reconnect on error. Good for high-throughput publishers where reconnect overhead matters. Requires heartbeat management (either long timeout or background thread). Used by article-fetcher, NER tagger publisher, and topic-tagger publisher.

**Connect-per-publish:** open a fresh connection for each publish, close immediately after. Simple, no heartbeat concern, no reconnect state to track. Overhead is one TCP handshake per message. Good when publish frequency is low relative to processing time. Used by article-scraper publisher.

Both are correct. Choose based on publish frequency and how much idle time the publisher spends between messages.

---

## 7. Scaling

### How queue-based scaling works

One of the fundamental advantages of queue-based pipelines is that scaling a stage is independent of every other stage. If the NER tagger falls behind, you start more NER tagger instances. They all consume from the same `articles.raw` queue, and RabbitMQ distributes messages across them. No coordination, no configuration changes.

This works because:
1. Each message is delivered to exactly one consumer (competing consumers model).
2. With `prefetch_count=1`, no single consumer can hoard messages it has not processed yet.
3. ACKs happen per-message, so messages left unprocessed by a crashed replica are redelivered to healthy ones.

### KEDA autoscaling

In Kubernetes, **KEDA** (Kubernetes Event-Driven Autoscaling) watches RabbitMQ queue depth and automatically adjusts the number of consumer pod replicas. When the queue grows, KEDA scales up. When it drains, KEDA scales back down to zero.

The `prefetch_count=1` setting is essential for this to work fairly. Without it, one consumer replica could buffer many messages (consuming them from the broker's perspective, but not yet ACKed), leaving other replicas idle even though work is nominally available. With `prefetch_count=1`, each replica holds exactly one in-flight message at any time, and KEDA's queue-depth signal accurately reflects how much work still needs to be distributed.

The docker-compose.yml shows `role-classifier` and `topic-tagger` configured with `deploy.replicas: 2` — this is the local equivalent of telling the orchestrator to always run multiple instances for the slower ML inference stages.

### Why the conflict pipeline does not use queues for event detection

The `event-detector` service is notable because it does not consume from a queue. It polls the PostgreSQL database on a timer (`DETECTION_INTERVAL: "300"` — every 5 minutes), reads recent articles and conflict events, runs clustering logic, and writes results back to the same database.

This is intentional. Event detection is not triggered by individual messages — it is a batch process that makes sense of accumulated data. The right abstraction is a scheduled job reading from a database, not a stream consumer reacting to individual events. Not every service in a distributed system needs to be queue-driven.

---

## Summary of Design Decisions

| Decision | Rationale |
|---|---|
| All queues declared durable | Survive broker restarts |
| All messages published persistent | Survive broker restarts |
| Always-ACK in consumers | Avoid poison message loops for non-retryable failures |
| `prefetch_count=1` everywhere | Fair distribution, bounded in-flight work per replica |
| Separate consumer and publisher connections | Each has a different idle profile; mixing them creates heartbeat contention |
| `connection.sleep()` in article-fetcher | Keeps heartbeats alive during long idle periods |
| `heartbeat=600` in NER/topic-tagger | Tolerates ML inference time without connection loss |
| Connect-per-publish in article-scraper | Avoids heartbeat management for infrequent, slow publishers |
| Fanout exchanges at scraper and topic-tagger output | Multiple independent consumers without coupling to producer |
