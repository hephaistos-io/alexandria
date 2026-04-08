# Event Detection in Alexandria

This document explains the concepts and algorithms behind Alexandria's event detector. The goal is to understand the *why* behind each design choice, not just the mechanics.

---

## 1. The Event Detection Problem

A news "event" is a real-world occurrence that generates coverage over time. The Iran nuclear deal. A military offensive in Sudan. A financial collapse in Argentina. Each event produces dozens or hundreds of articles from different outlets, written at different times, in different styles, with different emphases.

The challenge is that none of these articles say "I am about event X." You have to infer that grouping from the content.

Why is this hard?

**Vocabulary mismatch.** One article says "airstrike," another says "bombing," another says "military operation." They describe the same thing. Counting word occurrences won't connect them.

**Different angles, same event.** One article covers the humanitarian impact. Another covers the diplomatic response. A third focuses on a specific commander. They share almost no text, but they're covering the same story.

**Time spread.** Articles about a single event can arrive hours, days, or weeks apart. A naive system that only looks at recent articles misses the continuity.

**Scale and noise.** Most pairs of articles are unrelated. Any grouping system has to distinguish genuine clusters from coincidental co-occurrence of common words.

Alexandria's approach sidesteps the vocabulary problem entirely by working with entities instead of words.

---

## 2. Entity-Based Clustering

### The core insight

Before clustering, Alexandria's entity resolver runs over each article and identifies the real-world entities it mentions — people, organizations, places, concepts — and links them to Wikidata QIDs (stable identifiers like `Q796` for Iraq or `Q37922` for Yevgeny Prigozhin).

This means two articles can use completely different words and still be identified as covering the same subject, as long as they both reference the same real-world entities.

**Example:** An article titled "Wagner Group forces advance near Bakhmut" and one titled "Russia's private military contractors make gains in eastern Ukraine" would both resolve to entity QIDs for Wagner Group (Q104466893) and Ukraine (Q212). The surface text is different; the entity fingerprint overlaps substantially.

### Why not TF-IDF or embeddings?

Two common alternatives for document similarity are:

**TF-IDF (term frequency-inverse document frequency):** Measures how often distinctive words appear across a set of documents. Works well when articles use similar vocabulary. Breaks down across languages, synonyms, and paraphrase. Also sensitive to writing style — a verbose article and a brief one about the same event may score as dissimilar.

**Sentence embeddings:** Modern ML models (BERT, sentence-transformers) map text to a vector in high-dimensional space where semantically similar text ends up near each other. More robust than TF-IDF. But: requires a model, is computationally expensive to run on every pair, produces distances that are harder to interpret ("why did these two articles cluster?"), and can hallucinate similarity between thematically adjacent but factually separate events.

**Entity-based clustering** has three advantages for this use case:

1. **Interpretable.** You can look at a cluster and say "these articles are grouped because they all mention Iran (Q794), Saudi Arabia (Q851), and OPEC (Q7114)." You can explain the grouping.

2. **Stable across languages.** A French article and an English article that both mention the same politician will resolve to the same QID. The QID is language-neutral.

3. **No ML dependency in the core loop.** The clustering logic is pure Python using sets and counters. This makes it fast, debuggable, and easy to test.

The tradeoff: you depend on the entity resolver running successfully upstream. Articles without resolved entities cannot be clustered.

---

## 3. IDF Weighting

Sharing entities is a necessary condition for connection, but not a sufficient one. Two articles mentioning "United States" are not meaningfully connected — it's mentioned in half of all news. Two articles mentioning a specific Sudanese militia commander are almost certainly about the same story.

This is the intuition behind **Inverse Document Frequency (IDF)**.

### The formula

```
IDF(entity) = log(total_articles / articles_containing_entity)
```

Work through the numbers with a concrete dataset of 1,000 articles:

| Entity | Articles containing it | IDF |
|---|---|---|
| United States (Q30) | 400 | log(1000/400) = 0.92 |
| Russia (Q159) | 120 | log(1000/120) = 2.12 |
| Yevgeny Prigozhin (Q37922) | 8 | log(1000/8) = 4.83 |
| Specific militia commander | 2 | log(1000/2) = 6.21 |

The more articles contain an entity, the lower its IDF score. The rarer the entity, the higher the IDF — and the more informative it is as a connection signal.

This is the same principle used in search engines: common words like "the" or "is" carry no information; rare words that appear in only a few documents tell you something specific.

### The two thresholds

Alexandria uses two conditions for connecting a pair of articles:

1. They must share at least **2 entities** (MIN_SHARED_ENTITIES).
2. The IDF scores of those shared entities must sum to at least **2.0** (MIN_IDF_SUM).

Why both conditions? Each guards against a different failure mode.

**The count condition alone** would allow two articles to connect because they both mention "United States" and "government." That's noise, not signal. Common entities have low IDF, so the sum condition rejects this.

**The sum condition alone** would allow two articles to connect because one mentions a single highly specific entity — say, a named drone model used in an airstrike. One shared obscure entity could be coincidence. Requiring at least two shared entities demands a pattern, not a single data point.

Together, the conditions require: multiple shared entities, and at least some of them must be distinctive enough to carry real signal.

---

## 4. Graph-Based Clustering

### Articles as a graph

Once you have pairwise connection decisions, the problem becomes: how do you form groups?

Alexandria models articles as nodes in a graph. If two articles meet the shared-entity thresholds, an edge is drawn between them. Then groups are found by identifying **connected components** — sets of nodes where every node can be reached from every other node by following edges.

```
Article A — Article B — Article C
                |
            Article D — Article E

Article F (no edges — isolated)
```

In this graph, {A, B, C, D, E} is one connected component. Article F is isolated.

### BFS: Breadth-First Search

Finding connected components is a classic graph problem. Alexandria uses BFS (breadth-first search):

1. Pick any unvisited node.
2. Add all its neighbors to a queue.
3. Visit each neighbor, add their unvisited neighbors to the queue.
4. Repeat until the queue is empty — that's one component.
5. Find the next unvisited node and repeat.

BFS is simple and guaranteed to find all nodes reachable from a starting point, which is exactly what you need for components.

### Why not k-means or DBSCAN?

**k-means** requires you to specify `k` — the number of clusters — in advance. You don't know how many events are happening in a given week. It also requires a vector representation of each article, which brings you back to the embedding problem.

**DBSCAN** is density-based and doesn't require specifying `k`. It's widely used for text clustering. But it still requires a continuous distance metric between documents, and its epsilon (neighborhood radius) parameter is harder to tune than the discrete thresholds Alexandria uses. It can also be sensitive to the curse of dimensionality in high-dimensional embedding spaces.

**Connected components** has a natural advantage here: the edge condition is already well-defined (shared entities + IDF threshold). The cluster boundaries fall out directly from that definition. There are no hyperparameters about cluster shape or density. A cluster is just: all articles reachable from each other through the entity-overlap graph.

### The minimum cluster size filter

Isolated pairs (two articles) and single articles with no connections are filtered out. Only clusters with at least 3 articles become events.

This reduces noise from coincidental entity overlap. Two articles might share specific entities by chance — an editorial citing a report, for instance. Three or more articles covering the same entity combination is a much stronger signal that something is genuinely happening.

---

## 5. Heat and Lifecycle

Once you have a cluster of articles forming an event, you need to answer: how significant is this event right now? Is it breaking, fading, or long-dead?

### The heat formula

```
heat = sqrt(articles) × max(1, conflicts^0.3) × exp(-0.01 × hours_since_last_article)
```

Each term does a specific job.

**`sqrt(articles)` — volume with diminishing returns**

More articles means more coverage means more significance. But you don't want the score to scale linearly — a 100-article event should not score 100x a single-article event. Square root compresses the scale: 1 article → 1.0, 9 articles → 3.0, 100 articles → 10.0, 10,000 articles → 100.0. Large events still score higher, but not so much higher that they drown out medium events.

**`max(1, conflicts^0.3)` — conflict data as a signal boost**

When a conflict event from GDELT or UCDP data can be matched to the cluster's geography, it suggests the articles are covering real-world violence, not just political commentary. The conflict count is raised to the 0.3 power (a gentle compression, even more aggressive than square root) and the `max(1, ...)` wrapper ensures that an event with zero conflicts still multiplies by 1 instead of 0 — the conflict term boosts but never penalizes.

**`exp(-0.01 × hours)` — exponential decay**

News gets stale. An event that peaked 200 hours ago (over 8 days) should score much lower than one with fresh articles.

The function `exp(-λt)` is standard exponential decay. The constant λ = 0.01 means:

- After 0 hours: multiplier = 1.0 (full heat)
- After 69 hours (~3 days): multiplier ≈ 0.5 (half heat)
- After 138 hours (~6 days): multiplier ≈ 0.25 (quarter heat)
- After 230 hours (~10 days): multiplier ≈ 0.1 (10% heat)

The half-life (~69 hours) comes from solving `exp(-0.01 × t) = 0.5`, which gives `t = ln(2) / 0.01 ≈ 69.3`.

### Status transitions

Four statuses model the lifecycle of an event:

| Status | Meaning |
|---|---|
| `emerging` | New event, not yet confirmed as major |
| `active` | Significant, ongoing coverage |
| `cooling` | Was active, now fading |
| `historical` | Below significance threshold |

Transitions are driven by heat thresholds:

- Heat ≥ 5.0 → `active`
- Heat < 2.0 (and previously active) → `cooling`
- Heat < 0.5 → `historical` (from any state)

The key design choice is that **any state can transition directly to historical**. An event does not have to cool down gradually. If coverage stops completely — perhaps because a story was retracted, or simply never became significant — the decay term will push heat below 0.5 within about a week regardless of article count. This prevents zombie events from persisting indefinitely.

The reverse — a historical event re-emerging — is handled by the cluster-matching step (see section 6). If new articles form a cluster that matches an old event's entity fingerprint, the old event can be resurrected with updated heat.

---

## 6. Event Matching

The detector runs on a schedule. Each run produces fresh clusters from recent articles. The question becomes: is this cluster a new event, or a continuation of something already in the database?

### Jaccard similarity

For each new cluster, Alexandria computes its set of entity QIDs. It then compares that set to the entity QIDs stored for every existing (non-historical) event.

The comparison uses **Jaccard similarity**:

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

In words: the size of the intersection divided by the size of the union.

| Scenario | A | B | Jaccard |
|---|---|---|---|
| Identical sets | {Q1, Q2, Q3} | {Q1, Q2, Q3} | 3/3 = 1.0 |
| Good overlap | {Q1, Q2, Q3, Q4} | {Q1, Q2, Q3, Q5} | 3/5 = 0.6 |
| Weak overlap | {Q1, Q2, Q3} | {Q1, Q4, Q5, Q6} | 1/6 = 0.17 |
| No overlap | {Q1, Q2} | {Q3, Q4} | 0/4 = 0.0 |

The threshold is 0.3. A Jaccard score above 0.3 means the new cluster's entity profile overlaps substantially with the existing event's profile. The cluster is treated as new coverage of the same event rather than a new event.

Why 0.3 specifically? It's a judgment call. Lower thresholds would merge too aggressively — different stories in the same region might share a few country QIDs. Higher thresholds would miss genuine continuations where coverage has shifted focus slightly. 0.3 requires a meaningful shared core while tolerating the natural drift in which entities get mentioned as a story evolves.

### Conflict matching

Separately, conflict events (from structured data sources like GDELT) are linked to article clusters by country. The detector extracts country-level entities from each cluster — specifically GPE (geopolitical entity) entries whose Wikidata description contains the word "country" — and checks whether any conflict events in the database share that country.

This is a simpler lookup than Jaccard: it's just set intersection on country names, with case normalization. The reason for this separate path is that conflict data comes from a different source than articles and uses different identifiers. Country name is the most reliable common field.

---

## 7. Alternative Approaches

To understand the tradeoffs in Alexandria's design, it helps to know what was not chosen and why.

### Embedding-based clustering (HDBSCAN + sentence-transformers)

The modern default for document clustering in ML. Encode each article as a dense vector using a pre-trained language model, then cluster those vectors with HDBSCAN (a density-based algorithm that doesn't require specifying the number of clusters).

**Advantages:** Handles paraphrase and synonyms naturally. Works even on short texts. HDBSCAN is good at finding clusters of varying density and rejecting noise points.

**Disadvantages:** Requires running a large ML model on every article. The resulting clusters are a black box — you can't easily explain why two articles were grouped. Model quality depends heavily on the training data; models trained on general text may not understand OSINT-specific entity relationships. Vectors drift as the model is updated, potentially invalidating old groupings.

For a project where interpretability and debuggability matter more than recall of subtle semantic similarity, entity-based clustering is the stronger choice.

### Topic modeling (LDA, BERTopic)

Topic models learn a set of latent "topics" from a corpus, where each topic is a probability distribution over words. An article is represented as a mixture of topics. Articles with similar topic mixtures are clustered together.

**LDA** (Latent Dirichlet Allocation) is the classical approach. **BERTopic** is a modern variant that combines sentence embeddings with topic modeling for more coherent topics.

**Disadvantages for event detection:** Topic models group by theme, not by event. "Military conflict in the Middle East" is a topic. It might include articles about completely separate conflicts in different countries, different years, different contexts. Events are much more specific than topics.

Topic models also require training on your full corpus, which means they need periodic retraining as the document collection grows, and the topics themselves can shift in meaning over time.

### Temporal event detection

Some approaches treat event detection as a time series problem. You look for spikes in coverage of specific entities or topics over time. A sudden surge in articles mentioning a particular location or person signals a new event.

This is a useful supplementary signal but not a complete solution. It handles the detection of novelty well (a spike is easy to find) but struggles with ongoing events that maintain steady coverage without spikes, and with slow-developing stories.

It also doesn't produce article clusters — it tells you "something happened involving this entity," but not which articles belong to that event.

### Why entity-based was chosen

Entity-based clustering fits Alexandria's constraints well: it is fast (no model inference), interpretable (clusters have a named set of entities that explain them), language-neutral (QIDs are universal), and amenable to deterministic testing (you can construct exact test cases with known entity sets and verify the expected clusters). For an OSINT system where an analyst needs to understand and trust the groupings, those properties matter more than marginal improvements in recall from ML-based approaches.

The entity resolver still involves ML (named entity recognition), but it runs once per article and its output is stored. The clustering step itself is pure logic.
