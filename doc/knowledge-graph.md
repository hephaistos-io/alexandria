# Knowledge Graph — Concepts and Design

This document explains the graph database layer in Alexandria: why it exists,
how it is designed, and how data flows into it from plain article text.

The intended reader knows SQL and relational databases well but has not worked
with graph databases before.

---

## 1. What is a Knowledge Graph?

A knowledge graph is a database that stores facts as a network of connected
entities rather than as rows in tables.

The three building blocks are:

- **Node** — a thing in the world. In Alexandria, every resolved entity
  (a country, person, organisation) is a node. Nodes can carry properties:
  `qid`, `name`, `entity_type`.

- **Edge** (also called a relationship) — a connection between two nodes. An
  edge has a direction (from node A to node B) and can carry properties of its
  own: `relation_type`, `base_strength`, `article_count`, timestamps.

- **Property** — a named value attached to a node or edge. This is analogous
  to a column in SQL; the difference is that not every node or edge needs the
  same set of properties.

A single "fact" in the graph is often called a **triple**: (subject, predicate,
object) — for example (Russia, attacks, Ukraine). That maps directly to
(node A, edge, node B).

### Why a graph database instead of a relational table?

You could store relations in a PostgreSQL table:

```sql
CREATE TABLE relations (
    source_qid  TEXT,
    target_qid  TEXT,
    relation_type TEXT,
    base_strength FLOAT,
    ...
);
```

This works fine for simple queries like "give me all relations involving Russia".
It becomes awkward when you want to traverse the network: "find all entities
that are within two hops of Russia and also connected to China". In SQL, each
hop is another JOIN, and the query grows combinatorially. In a graph database,
traversal is the primitive operation — the engine is optimised for it.

The practical rule of thumb:

| Situation | Better fit |
|---|---|
| Simple lookups, aggregates, reporting | PostgreSQL |
| Traversal, path-finding, multi-hop queries | Neo4j / graph DB |
| You already have Postgres and queries are shallow | Stay in Postgres |
| Relations between entities are the primary subject | Graph DB |

Alexandria uses **both**: PostgreSQL holds articles, events, entities, and
operational metadata; Neo4j holds only the relation graph, where the
connections themselves are what you want to query and display.

### Neo4j specifically

Neo4j is the most widely deployed graph database. Its query language (Cypher,
covered in section 5) reads like ASCII art for graphs: `(a)-[r]->(b)`. It is
a property graph database, meaning nodes and edges carry arbitrary key-value
properties — distinct from RDF triple stores which have a stricter data model.

Alexandria runs Neo4j Community Edition (the free tier). Community Edition
lacks some Enterprise features, one of which matters to us: the `exp()` math
function is not reliably available in all Community versions. That constraint
directly shapes the decay design in section 3.

---

## 2. Graph Schema Design

### Entity nodes

Every node in Alexandria has a single Neo4j label: `Entity`. The label is
roughly analogous to a table name — it lets Neo4j quickly filter nodes by
type during queries.

Properties on each `Entity` node:

| Property | Description |
|---|---|
| `qid` | Wikidata QID (e.g. `Q159`). This is the stable, canonical identifier. |
| `name` | Human-readable name at the time of first creation. |
| `entity_type` | Coarse type string from the NER tagger (e.g. `GPE`, `ORG`, `PER`). |

The `qid` property has a **uniqueness constraint** applied at startup:

```cypher
CREATE CONSTRAINT entity_qid IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.qid IS UNIQUE
```

This does two things. First, it prevents duplicate nodes (the same country
cannot appear twice with different internal IDs). Second, Neo4j automatically
creates a B-tree index on constrained properties, so `MERGE (e:Entity {qid: $qid})`
becomes an index lookup rather than a full scan of every node in the database.

### Relation edges

All edges use a single Neo4j relationship type: `RELATION`. The semantic
relation — what kind of connection this is — is stored as a **property** called
`relation_type`, not as the Neo4j type itself.

Properties on each `RELATION` edge:

| Property | Description |
|---|---|
| `relation_type` | The semantic type: `attacks`, `allied_with`, `trades_with`, etc. |
| `base_strength` | Highest NLI confidence score ever observed for this edge (0–1 range). |
| `first_seen` | Datetime when this edge was first written. |
| `last_seen` | Datetime when the most recent article evidencing this edge was processed. |
| `article_count` | How many articles have contributed evidence for this edge. |
| `last_article_url` | URL of the most recent evidencing article (useful for audit). |

### Why `relation_type` is a property, not a Neo4j label

This is a common source of confusion for people coming from other data models.

In Neo4j, relationship types (like `RELATION`, or hypothetically `ATTACKS`,
`TRADES_WITH`) are **schema-level constants**. The `MERGE` clause — Neo4j's
upsert mechanism — requires you to name the relationship type statically in the
query. You cannot write:

```cypher
-- This does NOT work in Cypher
MERGE (a)-[r:$dynamic_type]->(b)
```

The type name must be a literal. This means if you want to add a new relation
type to Alexandria you would need to modify the query itself and redeploy the
service — clearly unworkable for a system where relation types are managed in
the database at runtime.

Storing `relation_type` as a property on a generic `RELATION` edge is the
standard pattern for dynamic type sets. The trade-off is that you lose the
ability to use Neo4j's native type-based filtering (which would read
`MATCH (a)-[:ATTACKS]->(b)`) and must instead use a property filter
(`WHERE r.relation_type = 'attacks'`). For the scale Alexandria operates at,
this cost is negligible.

### The upsert pattern: MERGE + ON CREATE / ON MATCH

The core write query in `neo4j_writer.py`:

```cypher
MERGE (a:Entity {qid: $source_qid})
ON CREATE SET a.name = $source_name, a.entity_type = $source_type
MERGE (b:Entity {qid: $target_qid})
ON CREATE SET b.name = $target_name, b.entity_type = $target_type
MERGE (a)-[r:RELATION {relation_type: $relation_type}]->(b)
ON CREATE SET
    r.base_strength = $confidence,
    r.first_seen = datetime(),
    r.last_seen = datetime(),
    r.article_count = 1,
    r.last_article_url = $article_url
ON MATCH SET
    r.base_strength = CASE WHEN $confidence > r.base_strength
        THEN $confidence ELSE r.base_strength END,
    r.last_seen = datetime(),
    r.article_count = r.article_count + 1,
    r.last_article_url = $article_url
```

`MERGE` is to Cypher what `INSERT ... ON CONFLICT DO UPDATE` is to SQL. It
finds an existing node or edge that matches the given pattern; if none exists,
it creates one. The `ON CREATE` block runs only when the record is new; `ON
MATCH` runs only when it already existed.

This gives Alexandria idempotent writes: processing the same article twice will
increment `article_count` a second time but will not create duplicate nodes or
edges. In a message-driven pipeline where retries are a fact of life, this
property is valuable.

The `base_strength` update uses a `CASE` expression rather than a simple
assignment: it only replaces the stored value if the new observation is
stronger. This preserves the historical peak confidence — the strongest signal
ever seen for this relationship — which is more meaningful than the most recent
score (which might come from a shorter, less informative article).

---

## 3. Temporal Decay

### The problem

News articles describe the world at a point in time. A ceasefire signed in
January is no longer evidence of active conflict in June. A graph that simply
accumulates edges without accounting for time will show stale relationships
with the same prominence as current ones — which is misleading for an OSINT
tool that is meant to reflect the present situation.

Temporal decay is the mechanism that causes old, unreinforced edges to fade
while recent ones stay prominent.

### The formula

```
display_strength = base_strength * article_count^α * exp(-λ * hours_since_last_seen)
```

Each term has a distinct role:

**`base_strength`** is the anchor. It is the highest NLI confidence ever
observed for this edge. A single very-high-confidence observation sets a high
ceiling; low-confidence observations can only boost the count, they cannot
lower the base.

**`article_count^α`** is the corroboration boost. An edge mentioned in ten
different articles is more credible than one mentioned once. The exponent `α`
(alpha) controls how aggressively multiple articles boost the score:

- `α = 0`: count is ignored (`count^0 = 1` always). Every edge is treated
  equally regardless of how many articles support it.
- `α = 0.5` (the default): square-root scaling. 4 articles give a 2x boost,
  9 articles give a 3x boost. The boost grows but flattens out.
- `α = 1`: linear scaling. 10 articles give a 10x boost. Rare articles are
  heavily penalised relative to well-covered ones.

The default of 0.5 is a conservative middle ground: corroboration matters, but
a single high-confidence edge still competes with a moderately-evidenced one.

**`exp(-λ * hours)`** is the decay term. This is the standard exponential
decay function borrowed from physics (radioactive decay, population dynamics —
it appears wherever something fades at a rate proportional to its current
value). `λ` (lambda) is the decay rate:

- A larger `λ` means faster decay. At `λ = 0.1`, an edge loses half its
  strength in roughly 7 hours.
- A smaller `λ` means slower decay. At `λ = 0.001`, the half-life is about
  29 days.

The half-life formula comes directly from setting the decay term to 0.5 and
solving: `t_half = ln(2) / λ ≈ 0.693 / λ`. This is the same formula used for
radioactive isotopes and pharmacokinetics — exponential decay is exponential
decay regardless of domain.

For news monitoring, `λ = 0.01` gives a half-life of about 70 hours (roughly
3 days), which is a reasonable default: a conflict reported three days ago is
still relevant, but one from three weeks ago should fade unless there are fresh
articles.

### Why this is computed in Python, not Cypher

The obvious place to apply decay would be inside the Cypher query:

```cypher
-- Conceptually what you might want
RETURN r.base_strength * exp(-0.01 * hours_elapsed) AS display_strength
```

Neo4j Enterprise Edition supports the `exp()` function in Cypher. Neo4j
Community Edition (what Alexandria uses) does not guarantee its availability.
Rather than tie the system to an Enterprise licence, the decay calculation is
done in Python after fetching the raw edge data. The Cypher query returns
`base_strength`, `last_seen`, and `article_count`; Python then computes
`display_strength` for each edge before the API returns the result.

The practical cost is that filtering by `display_strength` cannot happen inside
the database — all edges must be fetched and then filtered in memory. At
Alexandria's current scale (hundreds to low thousands of edges) this is
acceptable. If the graph grew to millions of edges, pushing the calculation
into the database or materialising the decay score periodically would become
necessary.

---

## 4. Directed vs Undirected Relations

### The problem with symmetric relations

"Russia attacks Ukraine" has an obvious direction: Russia is the aggressor,
Ukraine the target. Reversing it would state something different.

"Germany allied with France" does not have a meaningful direction. The
alliance is mutual — if Germany is allied with France, France is allied with
Germany. These are the same fact.

If you stored both directions in the graph, you would have two edges:
- `(Germany)-[:RELATION {relation_type: "allied_with"}]->(France)`
- `(France)-[:RELATION {relation_type: "allied_with"}]->(Germany)`

This is redundant and causes problems: querying "how many articles mention
the Germany-France alliance" would double-count, and displaying the graph would
show two arrows where one line suffices.

### How Alexandria handles it

The `relation_types` table in PostgreSQL has a `directed` boolean column.
When `directed = false`, the relation is symmetric and gets special handling
in both the extractor and the writer.

**During extraction** (`extractor.py`): for undirected relation types, the NLI
model is tested in both orderings — "Germany allied_with France" and "France
allied_with Germany". The score reported is `max(forward_score, reverse_score)`.
The best score from either direction represents the confidence that the
relationship exists at all.

**During storage** (`extractor.py`): the source/target assignment is
canonicalised by lexicographic QID ordering. Wikidata QIDs are strings like
`Q183` (Germany) and `Q142` (France). Since `"Q142" < "Q183"`, the edge is
always stored as `(Q142)-[allied_with]->(Q183)`, regardless of which order the
NLI test found stronger. This deterministic ordering means `MERGE` will always
find the existing edge rather than creating a duplicate.

For directed relations, no canonicalisation happens: `entity_a` is always the
source and `entity_b` is always the target, exactly as they appeared in the
text context.

The key insight is that "directed" and "undirected" are not properties of the
graph storage mechanism — all Neo4j edges have a direction. "Undirected" is a
modelling convention: you store one canonical direction and treat it as
direction-agnostic when querying and displaying.

---

## 5. Cypher Query Language

Cypher is Neo4j's declarative query language. Like SQL, you describe what you
want rather than how to find it. Unlike SQL, its syntax is designed to look
like the graph patterns you are matching.

### Core syntax

A node pattern uses parentheses: `(n:Label {property: value})`

A relationship pattern uses square brackets and arrows: `(a)-[r:TYPE]->(b)`

The two combined form a **path pattern**: `(a:Entity)-[r:RELATION]->(b:Entity)`

This reads: "find a node `a` with label `Entity`, connected by an outgoing
relationship `r` of type `RELATION`, to a node `b` also with label `Entity`."

### The four main clauses

**MATCH** — find patterns in the graph (analogous to `SELECT ... FROM ... JOIN`
in SQL):

```cypher
MATCH (a:Entity)-[r:RELATION]->(b:Entity)
WHERE r.relation_type = 'attacks'
RETURN a.name, b.name, r.base_strength
```

**MERGE** — upsert a node or relationship (find it if it exists, create it if
not). This is Alexandria's primary write mechanism.

**WHERE** — filter results, same concept as SQL `WHERE`.

**RETURN** — project the output columns, same concept as `SELECT`.

### How Cypher differs from SQL

The biggest conceptual shift is that relationships are first-class objects you
can traverse and inspect, not foreign key joins you write explicitly. In SQL,
joining `articles` to `entities` requires you to name both tables and the join
condition. In Cypher, you just write the path pattern and the engine figures
out the traversal.

The other difference is that Cypher has no concept of `NULL` propagation across
joins the way SQL does. A `MATCH` that finds no results simply returns no rows;
it does not produce `NULL`-padded rows the way a `LEFT JOIN` would.

### The key patterns used in Alexandria

**Node lookup (from `neo4j_writer.py`):**

```cypher
MERGE (a:Entity {qid: $source_qid})
```

Find an `Entity` node with the given `qid`, or create one. The `$source_qid`
is a parameter (equivalent to a SQL prepared statement's `?` or `$1`).

**Full graph fetch (from `graph_client.py`):**

```cypher
MATCH (a:Entity)-[r:RELATION]->(b:Entity)
RETURN a.qid AS source_qid, a.name AS source_name, a.entity_type AS source_type,
       b.qid AS target_qid, b.name AS target_name, b.entity_type AS target_type,
       r.relation_type AS relation_type, r.base_strength AS base_strength,
       r.last_seen AS last_seen, r.first_seen AS first_seen,
       r.article_count AS article_count
ORDER BY r.base_strength DESC
```

This fetches every edge with both endpoint nodes in one query. The `AS` aliases
give the returned columns predictable names, just like SQL column aliases.

**Upsert with conditional update:**

```cypher
ON MATCH SET
    r.base_strength = CASE WHEN $confidence > r.base_strength
        THEN $confidence ELSE r.base_strength END
```

The `CASE` expression works identically to SQL's `CASE WHEN ... THEN ... ELSE
... END`. This keeps the historical peak confidence rather than blindly
overwriting it.

---

## 6. From Text to Graph: The Full Pipeline

Understanding any single component is easier once you see how data flows from
raw text to a graph edge.

### Step 1: Article arrives

An article is fetched, scraped, and NER-tagged by earlier pipeline stages. By
the time it reaches the relation-extractor, it carries:

- `title`: the article headline.
- `content`: the full article text.
- `entities`: a list of resolved entity objects, each with `wikidata_id`,
  `canonical_name`, `label` (type), and character offsets (`start`, `end`)
  indicating where in `content` this entity mention appears.

### Step 2: Sentence splitting

The extractor splits `content` into sentences using a simple boundary detector
(periods and newlines). Each sentence is recorded with its start and end
character offsets in the original text, so entity mentions can be mapped back
to sentences by comparing offsets.

This is intentionally simple — no NLP sentence splitter library is used — because
the goal is just to identify which entities are near each other in the text,
not to parse the sentences grammatically.

### Step 3: Building context windows

For every unique pair of resolved entities, the extractor checks whether their
character spans fall within the same sentence or in adjacent sentences (gap of
at most one sentence index). Pairs further apart than this are skipped.

This proximity constraint is important for two reasons. First, it is computationally
necessary: running the NLI model on every possible entity pair in a long article
would be expensive, and most of those pairs do not have a direct relationship
expressed in the text. Second, it reflects how language works: the sentence or
two surrounding a pair of entity mentions is where the relational language
between them almost always appears.

If the entities share a sentence, that sentence's text is the context window.
If they are in adjacent sentences, both sentences are concatenated. This
context window becomes the NLI **premise** — the text the model is told to
treat as given.

The final premise prepends the article title: `{title}. {context_text}`. The
title often names the parties and the event type even when a specific sentence
only names one.

### Step 4: NLI hypothesis scoring

Natural Language Inference (NLI) is a task where a model is given a **premise**
(something asserted to be true) and a **hypothesis** (a claim to evaluate) and
asked to classify the relationship as: entailment (the premise supports the
hypothesis), contradiction, or neutral.

Zero-shot classification repurposes NLI: the model scores a hypothesis even for
categories it was never explicitly trained on, by treating candidate labels as
hypotheses. Alexandria uses `MoritzLaurer/deberta-v3-base-zeroshot-v2.0`, which
was designed for this use case.

For each entity pair, the extractor builds a set of hypothesis strings — one
(or two, for undirected) per relation type. For relation type `attacks` with
description "attacked":

- Forward: `"In this context, Russia attacked Ukraine"`
- (Undirected would also test the reverse)

All hypotheses for a pair are sent to the model in a single batched call with
`multi_label=True`. Standard (single-label) NLI forces the model to pick one
winner; multi-label allows each hypothesis to be evaluated independently, which
is correct here because a pair can simultaneously trade with and be in conflict.

The model returns a confidence score (0–1) for each hypothesis. Scores above
the threshold (default 0.65) are kept.

### Step 5: Edge upsert into Neo4j

Each relation that passes the threshold is written to Neo4j via the upsert
query described in section 2. The directed/undirected canonicalisation (section
4) determines which entity becomes source and which becomes target before the
write.

The Neo4j writer is a long-lived object (created once at service startup) that
holds a driver with an internal connection pool. Writing each relation in its
own managed transaction means a failure on one edge does not roll back the
others from the same article.

### The complete journey

```
Article text
    |
    | sentence splitting + offset tracking
    v
Entity pairs with shared context windows
    |
    | NLI hypothesis scoring (one model call per pair, all relation types batched)
    v
Relations with confidence scores
    |
    | threshold filter + directed/undirected canonicalisation
    v
MERGE upsert into Neo4j
    |
    | ON CREATE: new edge with initial metadata
    | ON MATCH:  update base_strength (peak), last_seen, article_count
    v
Temporal relation graph
    |
    | Python decay: base * count^α * exp(-λ * hours)
    v
display_strength per edge (filtered, sorted, served via /api/graph/relations)
```

Each stage discards noise: unresolved entities (no QID) are dropped before
pairing; distant pairs are dropped before NLI; low-confidence hypotheses are
dropped before writing; decayed edges below `min_strength` are dropped before
the API response. The graph the UI receives shows only what the pipeline
considers confident and current.
