# ML Techniques in Alexandria

This document explains the machine learning concepts behind Alexandria's NLP pipeline.
It is written for someone who understands programming but is new to ML and NLP.
The goal is to teach transferable ideas — not to walk through the code line by line.

---

## Table of Contents

1. [Named Entity Recognition (NER)](#1-named-entity-recognition-ner)
2. [Zero-Shot Classification via NLI](#2-zero-shot-classification-via-nli)
3. [Entity Resolution / Entity Linking](#3-entity-resolution--entity-linking)
4. [Relation Extraction via NLI](#4-relation-extraction-via-nli)
5. [Tradeoffs and Limitations](#5-tradeoffs-and-limitations)

---

## 1. Named Entity Recognition (NER)

### What NER does

Named Entity Recognition is the task of scanning text and identifying spans that refer
to real-world things: people, places, organizations, and similar categories. The output
is a list of *mentions* — each with the text surface form, a type label, and the position
in the original string where it appeared.

For the sentence:

> "The United Nations condemned Iran's missile test on Tuesday."

A NER model produces something like:

| Text             | Label | Start | End |
|------------------|-------|-------|-----|
| United Nations   | ORG   | 4     | 18  |
| Iran             | GPE   | 29    | 33  |
| Tuesday          | DATE  | 55    | 62  |

Alexandria's `ner-tagger` service does exactly this, producing `TaggedMention` objects
with `text`, `label`, `start_char`, and `end_char`.

### Entity label taxonomy: OntoNotes

spaCy's English models are trained on a corpus called OntoNotes 5.0, which defines
18 entity categories. The most important ones for Alexandria are:

| Label     | Meaning                                                      |
|-----------|--------------------------------------------------------------|
| `PERSON`  | People, fictional or real                                    |
| `ORG`     | Companies, agencies, institutions                            |
| `GPE`     | Geopolitical entities: countries, cities, states             |
| `LOC`     | Non-GPE locations: mountains, bodies of water, regions       |
| `FAC`     | Facilities: airports, bridges, named buildings               |
| `NORP`    | Nationalities, ethnic or political groups                    |
| `EVENT`   | Named events: wars, elections, natural disasters             |
| `LAW`     | Named legal documents, treaties                              |
| `DATE`    | Absolute or relative dates ("Tuesday", "last year")          |
| `CARDINAL`| Numeric values that don't fit another category               |
| `QUANTITY`| Measurements ("4,000 km")                                    |

The entity-resolver service only attempts Wikidata lookups for types that correspond
to real-world entities (`PERSON`, `ORG`, `GPE`, etc.). It skips `CARDINAL`, `DATE`,
`QUANTITY`, and similar types — there is nothing meaningful to look up for "at least 18".

### How spaCy's transformer model works (conceptual)

`en_core_web_trf` is spaCy's transformer-based NER model. The simpler model,
`en_core_web_sm` (the one currently loaded in production), uses a convolutional
neural network, but both follow the same conceptual steps:

1. **Tokenisation.** The text is split into tokens. Transformers use a subword
   tokeniser (e.g. "unemployment" becomes "un", "employ", "ment"). This lets the
   model handle words it has never seen before by decomposing them into familiar pieces.

2. **Contextual embeddings.** Each token is converted into a vector — a list of
   numbers that encodes its meaning *in context*. Crucially, the word "Iran" gets a
   different vector when it appears as the subject of a diplomatic statement versus
   a geographic reference. This is what "transformer" models do: they look at the
   entire surrounding sentence to build context-sensitive representations.

3. **Sequence labelling.** A classification head on top of the embeddings assigns
   each token a BIO tag: `B-GPE` (beginning of a GPE span), `I-GPE` (inside a GPE
   span), or `O` (not an entity). Adjacent `B` and `I` tags are merged into spans.

4. **Output.** The spans are returned as `doc.ents`, each carrying the surface text,
   label, and character offsets.

### Character offsets and why they matter

NER output includes `start_char` and `end_char` — the byte positions of the entity
mention in the original string. These are essential because downstream services need
to locate the mention in context. The role-classifier uses them to extract the sentence
*containing* an entity. The relation-extractor uses them to determine which sentences
two entities co-occur in.

If you only had the text "Iran", you would not know which "Iran" in a 3,000-character
article this was, or what was said about it nearby. The offsets anchor the mention to
a specific location in the text, preserving context.

### When NER fails

NER is a statistical model trained on newspaper text from a specific time period. It
fails in several predictable ways:

**Ambiguity.** "Georgia" is a US state (`GPE`), a country (`GPE`), and a person's
name (`PERSON`). The model uses surrounding context to disambiguate, but it will
sometimes be wrong — and downstream services have no way to tell it made a mistake.

**Novel entities.** A newly founded organisation or a recently prominent political
figure will not appear in the training data. The model might recognise it as an entity
but assign the wrong label, or miss it entirely.

**Context dependency.** Short headlines lack the context that helps a model classify
correctly. "Attack on Bridge" gives no indication of which bridge or which kind of
attack; longer article text usually does.

**Boundary errors.** A model might tag "United" without "Nations", or tag "the White
House" when only "White House" is the entity. These boundary errors propagate to the
resolver, which then searches Wikidata for a surface form that may not match any entry.

---

## 2. Zero-Shot Classification via NLI

Zero-shot classification is the dominant ML technique in Alexandria. It appears in
three services: `topic-tagger`, `role-classifier`, and `relation-extractor`. The key
idea is that you can classify text into categories *without any labelled training
examples for those categories*. Understanding why this works requires understanding
Natural Language Inference.

### What is Natural Language Inference (NLI)?

NLI is a task where a model reads two pieces of text — a *premise* and a *hypothesis* —
and decides the relationship between them. There are three possible outputs:

- **Entailment**: the hypothesis is true given the premise.
- **Contradiction**: the hypothesis is false given the premise.
- **Neutral**: the premise neither confirms nor denies the hypothesis.

Example:

> Premise: "Soldiers clashed with protesters near the capital."
> Hypothesis: "This text is about armed conflict."
> Output: Entailment (high confidence)

> Premise: "The central bank raised interest rates by 0.5 percent."
> Hypothesis: "This text is about armed conflict."
> Output: Contradiction or Neutral (low confidence)

NLI models are trained on large datasets of premise-hypothesis pairs with
entailment/contradiction/neutral labels. This training teaches the model a general
capacity for textual reasoning — understanding what *follows from* what.

### Turning classification into NLI

The trick is to reformulate "does this text belong to category X?" as "does this text
entail the hypothesis that it is about X?".

You provide:
- The text to classify as the **premise**.
- For each candidate category, a sentence about that category as the **hypothesis**.

The model scores each hypothesis independently. The category whose hypothesis receives
the highest entailment score becomes the predicted label.

In Alexandria's topic-tagger:

```
premise:    "An airstrike killed at least 12 civilians in northern Syria on Monday."
hypotheses: ["This text is about armed conflicts, wars, and military operations.",
             "This text is about economic policy, trade, and financial markets.",
             "This text is about elections, governance, and political institutions."]
```

The model assigns high entailment to the first hypothesis and low scores to the others.

The hypothesis template in the topic-tagger is literally `"This text is about {}"`,
where `{}` is replaced with each label's description.

### Why use full descriptions instead of label names

Using just the label name as the hypothesis — `"This text is about CONFLICT"` — gives
the model very little to work with. The word "CONFLICT" is an abstraction; the model's
reasoning ability works best on natural, descriptive sentences.

Compare:
- Weak hypothesis: `"This text is about CONFLICT"`
- Strong hypothesis: `"This text is about armed conflicts, wars, and military operations"`

The second hypothesis is richer. The model knows what "armed conflicts", "wars", and
"military operations" mean from its pre-training on text, and can reason about whether
the premise is related to any of those things.

This is why labels in Alexandria are stored with both a short `name` (used for display
and storage) and a full `description` (used as the NLI hypothesis). Changing a
description is functionally equivalent to redefining what the label means — no
retraining needed.

### What is DeBERTa and why was it chosen?

The model used in all three Alexandria services is
`MoritzLaurer/deberta-v3-base-zeroshot-v2.0`. DeBERTa (Disentangled Attention with
Enhanced Mask Decoder) is a transformer architecture from Microsoft, released in 2021.
It improved on BERT and RoBERTa by using a two-stream attention mechanism that
separately encodes position and content, making it better at understanding fine-grained
linguistic relationships — exactly what NLI requires.

The specific variant used here was fine-tuned on a large NLI dataset specifically
designed for zero-shot classification tasks. It was chosen over the more commonly
cited `facebook/bart-large-mnli` for two reasons:

1. **Size.** DeBERTa-v3-base is roughly 300MB. BART-large is around 1.6GB. The
   difference matters when each service runs in its own container on a machine without
   a GPU.

2. **Accuracy.** Despite being much smaller, the MoritzLaurer DeBERTa model matches
   or outperforms BART-large-mnli on standard zero-shot benchmarks. This is because it
   was fine-tuned specifically for zero-shot classification, while BART-large-mnli is
   a general-purpose NLI model.

### multi_label=True vs multi_label=False

When calling the zero-shot pipeline from HuggingFace's `transformers` library, you
must decide whether labels are mutually exclusive.

**`multi_label=False`** (used by `role-classifier`):

The model runs a single NLI inference pass and then applies softmax across all
candidate labels. Softmax forces all scores to sum to 1 — so the labels compete.
This is appropriate when you believe an entity plays exactly one role in an article.
The role-classifier uses this mode because "source of the conflict" and "target of
the conflict" are mutually exclusive framings of a single entity's relationship to an
event.

**`multi_label=True`** (used by `topic-tagger` and `relation-extractor`):

Each hypothesis is scored independently. There is no competition between labels.
An article can score high for both CONFLICT and POLITICS, and both will be kept if
they exceed the threshold. This is appropriate when labels are not mutually exclusive.
A news article can genuinely be about both armed conflict *and* the political response
to it. Similarly, two countries can simultaneously trade with and be in military
conflict with each other.

The choice between these two modes is not a tuning parameter — it is a statement about
the nature of your label space. Ask yourself: "can two labels both be true at the same
time?" If yes, use `multi_label=True`.

### The key advantage: no training data

Traditional supervised classification requires hundreds or thousands of labelled
examples per category. To add a new topic category with a supervised approach, you
would need to:

1. Collect and annotate a new training set for that category.
2. Retrain or fine-tune the model.
3. Redeploy.

With zero-shot NLI classification, adding a new label means inserting a row into the
database with a name and a description. The next time the service's label-refresh
timer fires, the new label is picked up and immediately used for all subsequent
articles. No model retraining, no redeployment.

This flexibility comes at a cost — covered in the tradeoffs section.

---

## 3. Entity Resolution / Entity Linking

### What problem it solves

NER produces *mentions* — raw text spans from an article. The same real-world entity
can appear under many surface forms: "Iran", "the Islamic Republic", "Tehran" (used
metonymically for the government), "Iranian forces". Without resolution, these look
like four different entities to any downstream analysis.

Entity resolution (also called entity linking or named entity disambiguation) maps each
mention to a canonical identifier in a knowledge base. Alexandria uses Wikidata as that
knowledge base. After resolution, all four of the above would ideally link to Wikidata
item Q794.

### Why Wikidata

Wikidata is a structured, multilingual knowledge base with over 100 million items, each
identified by a unique QID (e.g. Q794 for Iran). It is:

- Freely accessible via a REST API.
- Multilingual, which helps when articles reference non-English place names.
- Rich in properties: coordinates (P625), instance-of (P31), country (P17), and many more.
- Maintained collaboratively, so major world events and newly prominent entities are
  added relatively quickly.

The alternative would be a private knowledge base or a static gazetteer, but those
require maintenance and quickly become stale in a news monitoring context.

### What QIDs are

A QID is Wikidata's stable, language-neutral identifier for an item. Q794 means Iran
regardless of whether you searched for "Iran", "Irán", or "Іран". Using QIDs as
canonical identifiers in Alexandria's database means:

- Two services that independently resolve "Iran" and "Islamic Republic" can produce
  the same QID, and downstream code can recognise them as the same entity.
- The relation-extractor can de-duplicate entities by QID before constructing pairs.
- The graph of entity relationships uses QIDs as node identifiers, making it stable
  across article batches.

### The escalation strategy

Resolution for each mention follows three steps:

1. **Redis cache lookup.** Before making any API call, check whether this mention +
   label combination has been seen before. Redis is an in-memory key-value store that
   responds in under a millisecond. Cache TTL is 7 days — long enough that common
   entities (major countries, well-known organisations) are almost always served from
   cache.

2. **Wikidata API search.** On a cache miss, call the Wikibase REST API search endpoint
   with the mention text. The API returns the top-matching Wikidata item by relevance.
   A filter step checks whether the result is a Wikimedia-internal item (disambiguation
   page, category page) and discards those.

3. **Property fetch.** For geographic entity types (`GPE`, `LOC`, `FAC`), make a
   second API call to fetch the P625 (coordinate location) property. Coordinates are
   essential for downstream conflict-matching, which uses geographic proximity to
   associate articles with known conflict zones.

The result is then written back to the cache, whether or not a match was found.

### The `__NONE__` sentinel pattern

When a search returns no results, there is nothing to cache — unless you handle it
explicitly. Without a sentinel, every future request for the same mention would miss
the cache and repeat the API call, wasting quota on a known failure.

Alexandria stores the string `"__NONE__"` in Redis for confirmed misses. On subsequent
cache reads, the code checks: if the cached value is the sentinel, return `None`
immediately without calling the API again. This is called *negative caching*.

The sentinel must be a value that could not possibly be confused with a real result. A
JSON-encoded Wikidata result always starts with `{`, so any non-JSON string works as a
sentinel. `"__NONE__"` was chosen because it is unambiguous and self-documenting.

### Why coordinates matter downstream

Once geographic entities have coordinates, the conflict-matching pipeline can use
spatial proximity to associate articles with known armed conflict records from UCDP
(Uppsala Conflict Data Program). A country-based match would miss sub-national
conflicts; coordinate-based matching can determine that an article mentioning a
specific city falls within the bounding area of a known conflict.

---

## 4. Relation Extraction via NLI

### The goal

After NER and resolution, Alexandria knows *which* entities appear in an article. The
relation-extractor's goal is to determine *how* those entities are connected. It
produces typed, directed or undirected edges: "Russia — [is in conflict with] — Ukraine",
"Germany — [provides aid to] — Ukraine".

These edges form a knowledge graph that accumulates across articles and can be queried
to understand patterns across events.

### Entity pair construction with context windows

Extracting a relation between two entities requires a context window — the portion of
the article that describes their relationship. You cannot feed an entire 5,000-word
article to the NLI model; it would lose focus, and inference would be slow.

The relation-extractor uses sentence-level windows:

1. Split the article into sentences.
2. Map each resolved entity to the sentence indices where it appears.
3. Only consider pairs of entities that co-occur in the same or adjacent sentences.
   Pairs further apart are unlikely to have a meaningful relational context in the
   shared text.
4. Construct a premise from the title plus the shared sentence(s).

This approach is a pragmatic approximation. Real-world relation extraction research
uses more sophisticated methods (dependency parsing, coreference resolution), but for
a background pipeline running on CPU, this simple windowing strategy captures most
useful relations.

### The hypothesis template pattern

For relation extraction, the hypothesis is constructed per entity pair, not per label:

```
"In this context, {entity_A} {relation_description} {entity_B}"
```

For the pair (Russia, Ukraine) and a relation described as "is engaged in armed
conflict with", the hypothesis becomes:

```
"In this context, Russia is engaged in armed conflict with Ukraine"
```

This is tested as an NLI hypothesis against the premise (the shared sentence context).
If the model finds the hypothesis entailed by the premise, the relation is emitted.

All relation candidates for a given pair are batched into a single pipeline call.
This is more efficient than one call per relation type, because the model only needs
to encode the premise once.

### Directed vs undirected relations

Some relations have a meaningful direction; others do not.

A *directed* relation like "provides military aid to" is asymmetric: Germany providing
aid to Ukraine is a different fact than Ukraine providing aid to Germany. For directed
relations, only the forward hypothesis `"A [description] B"` is tested. If it passes
the threshold, the edge is stored as `A → B`.

An *undirected* relation like "has a trade relationship with" is symmetric: if A trades
with B, then B trades with A. For undirected relations, both orderings are tested
(`"A [description] B"` and `"B [description] A"`), and the higher of the two scores
is used. The edge is then stored in a canonical form (the entity with the smaller QID
as source) to avoid storing the same fact twice in the database.

This directed/undirected distinction is stored as a property on the relation type
definition, not hardcoded in the extractor. Adding a new undirected relation type
requires only a database row with `directed=false`.

### Confidence thresholds

The relation-extractor uses a higher threshold (0.65) than the topic-tagger (0.30).
This reflects the different cost of false positives. Spurious topic tags are mildly
misleading. Spurious relation edges, if they accumulate, corrupt the knowledge graph
with connections that don't exist. A higher threshold trades recall (missing some
real relations) for precision (only asserting relations with strong evidence).

The right threshold is always empirical. You observe the model's outputs on real data,
look at what it gets wrong in each direction, and move the threshold until the
precision/recall balance fits your use case.

---

## 5. Tradeoffs and Limitations

### Zero-shot vs fine-tuned models

Zero-shot classification is not state of the art. A model fine-tuned on labelled
examples from your specific domain will nearly always outperform a zero-shot approach
on that domain. The tradeoff is:

| Dimension         | Zero-shot                              | Fine-tuned                            |
|-------------------|----------------------------------------|---------------------------------------|
| Training data     | None needed                            | Hundreds to thousands of examples     |
| Label flexibility | Change a DB row                        | Retrain and redeploy                  |
| Accuracy ceiling  | Moderate (~70–85% on well-defined tasks) | High (~90–97% on well-defined tasks) |
| Iteration speed   | Hours                                  | Days to weeks                         |
| Brittleness       | Depends on description quality         | Depends on dataset quality and coverage |

For Alexandria's use case — a rapidly evolving news domain where new event types and
entities emerge constantly — the zero-shot approach is the right first choice. It lets
the system work immediately and adapt to new label taxonomies without annotation
campaigns. If specific classifiers prove to be unreliable in practice, they can be
replaced with fine-tuned alternatives one at a time.

### CPU inference constraints

None of Alexandria's ML services use a GPU. All three zero-shot services run with
`device=-1`, which is the HuggingFace/PyTorch argument for CPU-only inference.

The reason is practical: GPUs are expensive to provision continuously (as opposed to
in burst training jobs), and the pipeline is designed to run as persistent background
workers processing articles as they arrive, not in batch training runs. On CPU,
DeBERTa-v3-base takes roughly 0.5–2 seconds per inference call. This is acceptable
for a background pipeline where articles are processed asynchronously via a message
queue.

The implication is that Alexandria's ML pipeline would not scale well to processing
thousands of articles per minute. For the current scope — OSINT monitoring across a
manageable set of feeds — CPU inference is sufficient. If throughput became a
bottleneck, the right solution would be to provision GPU workers for the zero-shot
services, not to replace the models.

### The accuracy ceiling of zero-shot approaches

Zero-shot models have a structural accuracy ceiling because they were not trained on
your labels. They understand language, but they do not know what *you* mean by
"BELLIGERENT" or "AFFECTED REGION" in the specific context of armed conflict analysis.

The description text partially bridges this gap. A well-written description that uses
language the model has seen in context during pre-training will score much better than
a jargon-heavy description.

Poorly written descriptions actively hurt performance. If you write:

> "The primary kinetic actor initiating force projection"

...the model will struggle, not because the concept is hard but because that phrasing
does not appear in news text. Prefer:

> "A country or group that initiated an attack or military operation"

Improving descriptions is the lowest-cost way to improve zero-shot accuracy, and it
should be tried before reaching for fine-tuning.

### When to switch to supervised learning

Zero-shot classification becomes the wrong choice when:

1. **Accuracy requirements are strict.** If the output feeds automated decision-making
   (rather than analyst review), 80% accuracy may not be good enough, and annotating
   a training set becomes justified.

2. **The label space is stable.** If the set of topics or role types has not changed
   in months and is unlikely to change, there is no flexibility cost to fine-tuning.

3. **You have annotation data.** If analysts are already reviewing and correcting model
   outputs, those corrections are labelled data. A fine-tuned model trained on that
   data will outperform the zero-shot baseline.

4. **The domain is highly specialised.** General-purpose NLI models handle everyday
   news well, but struggle with domain-specific language: military doctrine, legal
   terminology, financial instruments. Domain-specific fine-tuning recovers that gap.

The architecture of Alexandria's classifiers — a pipeline object plus a label list —
is specifically designed so that the zero-shot model can be swapped for a fine-tuned
one without changing the surrounding service code. The interface is the same; only the
model weights change.
