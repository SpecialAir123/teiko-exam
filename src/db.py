"""Database layer: schema definition and connection helper.

The schema is normalized into four tables that mirror the real-world entities in
the trial data:

    projects (1) ──< (N) subjects (1) ──< (N) samples (1) ──< (N) cell_counts

``cell_counts`` is stored in *long* format (one row per sample x population)
rather than five wide columns. This is the key design choice: adding a new
immune population is a data change, not a schema change, and per-population
aggregation (the heart of every analysis here) becomes a simple GROUP BY.

A single view, ``sample_frequencies``, encodes the Part 2 relative-frequency
calculation once so that the pipeline and the dashboard share identical logic.
"""

from __future__ import annotations

import os
import sqlite3

# Absolute path to the repository root (parent of this src/ directory) so the
# DB always lands in the root regardless of the caller's working directory.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "cell_counts.db")

# The five immune cell populations measured for every sample.
POPULATIONS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS sample_frequencies;
DROP TABLE IF EXISTS cell_counts;
DROP TABLE IF EXISTS samples;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS projects;

-- A clinical project / study.
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY
);

-- A patient. All of condition/age/sex/treatment/response are constant per
-- subject in the source data, so they live here rather than on each sample.
CREATE TABLE subjects (
    subject_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    condition  TEXT,            -- indication, e.g. melanoma / carcinoma / healthy
    age        INTEGER,
    sex        TEXT,            -- M / F
    treatment  TEXT,            -- miraclib / phauximab / none
    response   TEXT             -- yes / no  (NULL for untreated subjects)
);

-- A biological sample drawn from a subject at a given timepoint.
CREATE TABLE samples (
    sample_id                 TEXT PRIMARY KEY,
    subject_id                TEXT NOT NULL REFERENCES subjects(subject_id),
    sample_type               TEXT,        -- PBMC / WB
    time_from_treatment_start INTEGER      -- days; 0 = baseline
);

-- Long-format cell counts: one row per (sample, population).
CREATE TABLE cell_counts (
    sample_id  TEXT NOT NULL REFERENCES samples(sample_id),
    population TEXT NOT NULL,
    count      INTEGER NOT NULL,
    PRIMARY KEY (sample_id, population)
);

-- Indexes supporting the common filter / group-by access patterns.
CREATE INDEX idx_subjects_filters ON subjects(condition, treatment, response);
CREATE INDEX idx_samples_filters  ON samples(sample_type, time_from_treatment_start);
CREATE INDEX idx_samples_subject  ON samples(subject_id);
CREATE INDEX idx_cell_counts_pop  ON cell_counts(population);

-- Part 2 relative-frequency calculation, defined once and reused everywhere.
-- For each sample: total = sum across the five populations; percentage = the
-- population's share of that total.
CREATE VIEW sample_frequencies AS
    SELECT
        cc.sample_id                                  AS sample,
        tot.total_count                               AS total_count,
        cc.population                                 AS population,
        cc.count                                      AS count,
        ROUND(100.0 * cc.count / tot.total_count, 4)  AS percentage
    FROM cell_counts cc
    JOIN (
        SELECT sample_id, SUM(count) AS total_count
        FROM cell_counts
        GROUP BY sample_id
    ) tot ON tot.sample_id = cc.sample_id;
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection with foreign-key enforcement enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """(Re)create all tables, indexes and views. Idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
