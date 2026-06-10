#!/usr/bin/env python3
"""Part 1 — Data Management.

Initializes the SQLite database with the normalized schema and loads every row
from ``cell-count.csv`` into it.

Run directly, with no arguments:

    python load_data.py

This creates ``cell_counts.db`` in the repository root (overwriting any existing
copy so the load is fully reproducible).
"""

from __future__ import annotations

import os
import sys

import pandas as pd

from src.db import DB_PATH, POPULATIONS, ROOT_DIR, get_connection, init_schema

CSV_PATH = os.path.join(ROOT_DIR, "cell-count.csv")


def load() -> None:
    if not os.path.exists(CSV_PATH):
        sys.exit(f"ERROR: input file not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    # --- Reshape into the four normalized relations -------------------------
    # Subject-level attributes (constant per subject in the source data).
    projects = df[["project"]].drop_duplicates()
    projects.columns = ["project_id"]

    subjects = (
        df[["subject", "project", "condition", "age", "sex", "treatment", "response"]]
        .drop_duplicates(subset="subject")
        .rename(columns={"subject": "subject_id", "project": "project_id"})
    )

    samples = (
        df[["sample", "subject", "sample_type", "time_from_treatment_start"]]
        .drop_duplicates(subset="sample")
        .rename(columns={"sample": "sample_id", "subject": "subject_id"})
    )

    # Wide -> long: one row per (sample, population).
    cell_counts = df.melt(
        id_vars=["sample"],
        value_vars=POPULATIONS,
        var_name="population",
        value_name="count",
    ).rename(columns={"sample": "sample_id"})

    # --- Write to SQLite inside a single transaction ------------------------
    conn = get_connection()
    try:
        init_schema(conn)
        projects.to_sql("projects", conn, if_exists="append", index=False)
        subjects.to_sql("subjects", conn, if_exists="append", index=False)
        samples.to_sql("samples", conn, if_exists="append", index=False)
        cell_counts.to_sql("cell_counts", conn, if_exists="append", index=False)
        conn.commit()

        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("projects", "subjects", "samples", "cell_counts")
        }
    finally:
        conn.close()

    print(f"Loaded {CSV_PATH} -> {DB_PATH}")
    for table, n in counts.items():
        print(f"  {table:12s}: {n:>6,} rows")


if __name__ == "__main__":
    load()
