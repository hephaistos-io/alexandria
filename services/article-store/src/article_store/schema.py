"""PostgreSQL schema for articles, classification_labels, entity_role_types, and conflict_events tables."""

import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id              SERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    origin          TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    content         TEXT NOT NULL,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL,
    scraped_at      TIMESTAMPTZ NOT NULL,
    manual_labels       TEXT[],
    manual_labelled_at  TIMESTAMPTZ,
    automatic_labels    TEXT[],
    classified_at       TIMESTAMPTZ,
    entities            JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);
"""

# Table for user-managed classification label definitions.
# ON CONFLICT DO NOTHING in the seed query means re-running this is safe.
SCHEMA_CLASSIFICATION_LABELS = """
CREATE TABLE IF NOT EXISTS classification_labels (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#76A9FA',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""

# Seed the 6 default topic labels.
# ON CONFLICT (name) DO NOTHING ensures we never overwrite user edits on restart.
SEED_CLASSIFICATION_LABELS = """
INSERT INTO classification_labels (name, description, color) VALUES
    ('CONFLICT',    'Armed conflicts, wars, military operations, and defense-related events',                                    '#ffb4ab'),
    ('POLITICS',    'Government actions, elections, diplomacy, policy changes, and political movements',                         '#a9c7ff'),
    ('FINANCIAL',   'Economic events, market movements, trade, sanctions, and financial regulations',                            '#bac8dc'),
    ('TECHNOLOGY',  'Technology developments, cybersecurity, AI, digital infrastructure, and innovation',                       '#5adace'),
    ('HEALTH',      'Public health crises, medical breakthroughs, disease outbreaks, and healthcare policy',                    '#fbbf24'),
    ('ENVIRONMENT', 'Climate change, natural disasters, environmental policy, and ecological events',                           '#a3e635')
ON CONFLICT (name) DO NOTHING;
"""

# Migrates the old single-value TEXT column to a TEXT[] array.
# Safe to run repeatedly — the IF EXISTS / IF NOT EXISTS guards make it a no-op
# once the migration is done.
MIGRATE_TOPIC_LABEL_TO_ARRAY = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'topic_label'
          AND data_type = 'text'
    ) THEN
        ALTER TABLE articles ADD COLUMN topic_labels TEXT[];
        UPDATE articles SET topic_labels = ARRAY[topic_label]
            WHERE topic_label IS NOT NULL;
        ALTER TABLE articles DROP COLUMN topic_label;
    END IF;
END $$;
"""

# Renames topic_labels → manual_labels and labelled_at → manual_labelled_at.
# These are the "human annotator" columns — renaming makes room for the new
# automatic_labels column produced by the topic-tagger service.
MIGRATE_RENAME_TO_MANUAL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'topic_labels'
    ) THEN
        ALTER TABLE articles RENAME COLUMN topic_labels TO manual_labels;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'labelled_at'
    ) THEN
        ALTER TABLE articles RENAME COLUMN labelled_at TO manual_labelled_at;
    END IF;
END $$;
"""

# Adds the two columns written by the automatic topic-tagger pipeline.
# IF NOT EXISTS means this is safe to run on every startup.
MIGRATE_ADD_AUTOMATIC_COLUMNS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'automatic_labels'
    ) THEN
        ALTER TABLE articles ADD COLUMN automatic_labels TEXT[];
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'classified_at'
    ) THEN
        ALTER TABLE articles ADD COLUMN classified_at TIMESTAMPTZ;
    END IF;
END $$;
"""


# Adds the entities JSONB column written by the entity-resolver pipeline.
# IF NOT EXISTS makes this a no-op on databases that already have the column.
MIGRATE_ADD_ENTITIES_COLUMN = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'entities'
    ) THEN
        ALTER TABLE articles ADD COLUMN entities JSONB;
    END IF;
END $$;
"""


# Table for user-managed entity role type definitions.
# Mirrors classification_labels but for geographic entity roles (SOURCE, AFFECTED, etc.).
SCHEMA_ENTITY_ROLE_TYPES = """
CREATE TABLE IF NOT EXISTS entity_role_types (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#76A9FA',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""

SEED_ENTITY_ROLE_TYPES = """
INSERT INTO entity_role_types (name, description, color) VALUES
    ('SOURCE',   'the entity that initiated, caused, or is responsible for the action described', '#a9c7ff'),
    ('AFFECTED', 'the entity that is impacted, targeted, or affected by the action described',    '#ffb4ab')
ON CONFLICT (name) DO NOTHING;
"""

# Adds columns for manual entity role annotations.
# manual_entity_roles stores human-corrected roles as JSONB keyed by entity identifier.
# entity_roles_labelled_at records when the annotation was made.
# Table for user-managed relation type definitions used by the relation-extractor.
# The description field is the NLI hypothesis fragment: "In this context, {A} {description} {B}".
# The directed flag controls whether A→B and B→A are distinct (true) or equivalent (false).
SCHEMA_RELATION_TYPES = """
CREATE TABLE IF NOT EXISTS relation_types (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#76A9FA',
    directed    BOOLEAN NOT NULL DEFAULT true,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""

SEED_RELATION_TYPES = """
INSERT INTO relation_types (name, description, directed, color) VALUES
    ('SANCTIONS',                   'imposes sanctions against',                             true,  '#ffb4ab'),
    ('ALLIED_WITH',                 'has a formal military or political alliance with',      false, '#a9c7ff'),
    ('TRADES_WITH',                 'conducts trade with',                                   false, '#bac8dc'),
    ('PROVIDES_MILITARY_AID_TO',    'provides military aid or weapons to',                   true,  '#5adace'),
    ('PROVIDES_HUMANITARIAN_AID_TO','provides humanitarian aid or disaster relief to',       true,  '#34d399'),
    ('AT_WAR_WITH',                 'is at war or in armed conflict with',                   false, '#ff6b6b'),
    ('NEGOTIATES_WITH',             'is in peace or ceasefire negotiations with',            false, '#fbbf24'),
    ('HOSTS',                       'hosts a military base or permanent presence of',        true,  '#a3e635'),
    ('FUNDS',                       'provides financial funding to',                         true,  '#c084fc'),
    ('ACCUSES',                     'accuses or blames',                                     true,  '#f97316'),
    ('CONDEMNS',                    'publicly condemns the actions of',                      true,  '#ef4444'),
    ('DEPLOYS_FORCES_TO',           'deploys military forces to',                            true,  '#6366f1'),
    ('SUPPORTS',                    'publicly expresses political support for',              true,  '#8b5cf6')
ON CONFLICT (name) DO NOTHING;
"""


MIGRATE_ADD_ENTITY_ROLE_COLUMNS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'manual_entity_roles'
    ) THEN
        ALTER TABLE articles ADD COLUMN manual_entity_roles JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'articles'
          AND column_name = 'entity_roles_labelled_at'
    ) THEN
        ALTER TABLE articles ADD COLUMN entity_roles_labelled_at TIMESTAMPTZ;
    END IF;
END $$;
"""


# Stores structured conflict events produced by data-ingestion services
# (e.g. ACLED, UCDP, GDELT). source + source_id together form the natural key
# — the UNIQUE constraint plus ON CONFLICT DO NOTHING in the consumer means
# re-ingesting the same event from the same source is a safe no-op.
SCHEMA_CONFLICT_EVENTS = """
CREATE TABLE IF NOT EXISTS conflict_events (
    id              SERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    event_date      TIMESTAMPTZ,
    place_desc      TEXT,
    links           TEXT[],
    fetched_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (source, source_id)
);
"""


# Detected events — clusters of articles and conflict events that share
# entities, geography, and timeframe.  The event-detector service writes
# these; the monitoring-api reads them for the frontend map.
SCHEMA_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    slug         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'emerging'
                 CHECK (status IN ('emerging', 'active', 'cooling', 'historical')),
    heat         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    entity_qids  TEXT[] NOT NULL,
    centroid_lat DOUBLE PRECISION,
    centroid_lng DOUBLE PRECISION,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ DEFAULT now()
);
"""

SCHEMA_EVENT_ARTICLES = """
CREATE TABLE IF NOT EXISTS event_articles (
    event_id   INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    article_id INT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, article_id)
);
"""

SCHEMA_EVENT_CONFLICTS = """
CREATE TABLE IF NOT EXISTS event_conflicts (
    event_id          INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    conflict_event_id INT NOT NULL REFERENCES conflict_events(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, conflict_event_id)
);
"""


def apply_schema(conn: psycopg.Connection) -> None:
    """Create tables and run all pending migrations.

    Idempotent — safe to call on every startup. Migrations run in order:
    1. Create articles table (IF NOT EXISTS — no-op if already present)
    2. Migrate old single-value topic_label TEXT → topic_labels TEXT[]
    3. Rename topic_labels → manual_labels, labelled_at → manual_labelled_at
    4. Add automatic_labels TEXT[] and classified_at TIMESTAMPTZ columns
    5. Add entities JSONB column
    6. Create classification_labels table (IF NOT EXISTS)
    7. Seed default classification labels (ON CONFLICT DO NOTHING)
    8. Create entity_role_types table (IF NOT EXISTS)
    9. Seed default entity role types (ON CONFLICT DO NOTHING)
    10. Add manual_entity_roles JSONB and entity_roles_labelled_at columns
    11. Create relation_types table (IF NOT EXISTS)
    12. Seed default relation types (ON CONFLICT DO NOTHING)
    13. Create conflict_events table (IF NOT EXISTS)
    14. Create events table (IF NOT EXISTS)
    15. Create event_articles junction table (IF NOT EXISTS)
    16. Create event_conflicts junction table (IF NOT EXISTS)
    """
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        cur.execute(MIGRATE_TOPIC_LABEL_TO_ARRAY)
        cur.execute(MIGRATE_RENAME_TO_MANUAL)
        cur.execute(MIGRATE_ADD_AUTOMATIC_COLUMNS)
        cur.execute(MIGRATE_ADD_ENTITIES_COLUMN)
        cur.execute(SCHEMA_CLASSIFICATION_LABELS)
        cur.execute(SEED_CLASSIFICATION_LABELS)
        cur.execute(SCHEMA_ENTITY_ROLE_TYPES)
        cur.execute(SEED_ENTITY_ROLE_TYPES)
        cur.execute(MIGRATE_ADD_ENTITY_ROLE_COLUMNS)
        cur.execute(SCHEMA_RELATION_TYPES)
        cur.execute(SEED_RELATION_TYPES)
        cur.execute(SCHEMA_CONFLICT_EVENTS)
        cur.execute(SCHEMA_EVENTS)
        cur.execute(SCHEMA_EVENT_ARTICLES)
        cur.execute(SCHEMA_EVENT_CONFLICTS)
    conn.commit()
