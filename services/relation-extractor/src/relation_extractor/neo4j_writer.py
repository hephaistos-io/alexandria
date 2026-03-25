"""Write extracted relations to Neo4j as a temporal knowledge graph.

Nodes represent entities (identified by Wikidata QID).
Edges represent typed relations with temporal metadata:
  - base_strength: highest NLI confidence ever seen for this edge
  - first_seen / last_seen: temporal bounds
  - article_count: how many articles evidenced this relation
  - last_article_url: the most recent article

Upsert pattern: MERGE on (source_qid, target_qid, relation_type).
On create: set initial values. On match: update strength, timestamp, count.
"""

import logging

import neo4j

logger = logging.getLogger(__name__)

# MERGE on both entity nodes first, then on the typed relation between them.
# ON CREATE / ON MATCH let us handle both insert and update in one round-trip.
#
# Why we store relation_type as a property rather than as a label:
# Neo4j relationship types are schema-level constants — you can't create a
# relationship with a dynamic type using MERGE. Storing it as a property
# on a generic RELATION edge is the standard workaround for dynamic type sets.
UPSERT_QUERY = """
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
"""

# Uniqueness constraint on Entity.qid ensures MERGE is efficient (index lookup
# rather than full scan) and prevents duplicate entity nodes.
CONSTRAINT_QUERY = (
    "CREATE CONSTRAINT entity_qid IF NOT EXISTS"
    " FOR (e:Entity) REQUIRE e.qid IS UNIQUE"
)


class Neo4jWriter:
    """Upserts entity-relation-entity triples into Neo4j.

    Opens one driver at construction and holds it open for the lifetime of
    the service — Neo4j drivers manage a connection pool internally, so
    creating a new driver per article would be wasteful.
    """

    def __init__(self, uri: str, auth: tuple[str, str]) -> None:
        self._driver = neo4j.GraphDatabase.driver(uri, auth=auth)
        # Ensure the uniqueness constraint exists before we start writing.
        # This is idempotent (IF NOT EXISTS) so it's safe to run every startup.
        with self._driver.session() as session:
            session.run(CONSTRAINT_QUERY)
        logger.info("Neo4j writer ready (uri=%s)", uri)

    def upsert_relations(self, relations: list[dict], article_url: str) -> None:
        """Upsert a batch of relations into Neo4j.

        Each relation is written in its own transaction. Neo4j doesn't support
        MERGE in a single batched statement the way SQL does UPSERT, so individual
        transactions per relation is the standard pattern. The driver's connection
        pool keeps this efficient.
        """
        with self._driver.session() as session:
            for rel in relations:
                session.execute_write(self._upsert_one, rel, article_url)

    @staticmethod
    def _upsert_one(tx: neo4j.ManagedTransaction, rel: dict, article_url: str) -> None:
        """Execute the upsert for a single relation within a managed transaction."""
        tx.run(
            UPSERT_QUERY,
            source_qid=rel["source_qid"],
            source_name=rel["source_name"],
            source_type=rel["source_type"],
            target_qid=rel["target_qid"],
            target_name=rel["target_name"],
            target_type=rel["target_type"],
            relation_type=rel["relation_type"],
            confidence=rel["confidence"],
            article_url=article_url,
        )

    def close(self) -> None:
        """Close the Neo4j driver and release connection pool resources."""
        self._driver.close()
        logger.info("Neo4j driver closed")
