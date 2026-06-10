"""Parts 2-4 — analytics.

Every function takes a SQLite connection and returns a pandas DataFrame (or a
small dict of DataFrames). Keeping these as pure query/compute functions lets
both the pipeline (``run_pipeline.py``) and the dashboard (``app.py``) reuse the
exact same logic.
"""

from __future__ import annotations

import sqlite3
from typing import Dict

import pandas as pd
from scipy.stats import mannwhitneyu
from statsmodels.stats.multitest import multipletests

from src.db import POPULATIONS

# Cohort used throughout Parts 3 & 4.
MIRACLIB_MELANOMA_PBMC = (
    "condition = 'melanoma' AND treatment = 'miraclib' AND sample_type = 'PBMC'"
)


# --------------------------------------------------------------------------- #
# Part 2 — per-sample relative frequencies
# --------------------------------------------------------------------------- #
def frequency_table(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return the Part 2 summary table.

    Columns: sample, total_count, population, count, percentage.
    One row per (sample, population). Logic lives in the SQL view so it is
    defined exactly once (see src/db.py).
    """
    return pd.read_sql_query(
        "SELECT sample, total_count, population, count, percentage "
        "FROM sample_frequencies ORDER BY sample, population",
        conn,
    )


# --------------------------------------------------------------------------- #
# Part 3 — responders vs non-responders (melanoma / miraclib / PBMC)
# --------------------------------------------------------------------------- #
def responder_comparison_data(conn: sqlite3.Connection) -> pd.DataFrame:
    """Tidy frame of population frequencies for the Part 3 cohort.

    Columns: sample, population, percentage, response ('yes'/'no').
    """
    query = f"""
        SELECT f.sample, f.population, f.percentage, s.response
        FROM sample_frequencies f
        JOIN samples  sa ON sa.sample_id  = f.sample
        JOIN subjects s  ON s.subject_id  = sa.subject_id
        WHERE {MIRACLIB_MELANOMA_PBMC}
          AND s.response IN ('yes', 'no')
    """
    return pd.read_sql_query(query, conn)


def responder_stats(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-population comparison of responders vs non-responders.

    Uses the Mann-Whitney U test (non-parametric: cell-frequency distributions
    are not guaranteed normal and the test is robust to that). Raw p-values are
    corrected for testing five populations with the Benjamini-Hochberg FDR
    procedure. A population is flagged ``significant`` when its adjusted
    p-value < 0.05.

    Columns: population, n_responder, n_non_responder, median_responder,
    median_non_responder, u_statistic, p_value, p_value_adj, significant.
    """
    data = responder_comparison_data(conn)
    rows = []
    for population in POPULATIONS:
        sub = data[data["population"] == population]
        resp = sub.loc[sub["response"] == "yes", "percentage"]
        nonr = sub.loc[sub["response"] == "no", "percentage"]
        u_stat, p_val = mannwhitneyu(resp, nonr, alternative="two-sided")
        rows.append(
            {
                "population": population,
                "n_responder": int(resp.size),
                "n_non_responder": int(nonr.size),
                "median_responder": round(float(resp.median()), 4),
                "median_non_responder": round(float(nonr.median()), 4),
                "u_statistic": float(u_stat),
                "p_value": float(p_val),
            }
        )

    result = pd.DataFrame(rows)
    result["p_value_adj"] = multipletests(result["p_value"], method="fdr_bh")[1]
    result["significant"] = result["p_value_adj"] < 0.05
    return result


# --------------------------------------------------------------------------- #
# Part 4 — baseline subset (time_from_treatment_start == 0)
# --------------------------------------------------------------------------- #
def baseline_samples(conn: sqlite3.Connection) -> pd.DataFrame:
    """Melanoma PBMC baseline samples from miraclib-treated patients.

    Columns: sample, subject, project, response, sex, time_from_treatment_start.
    """
    query = f"""
        SELECT sa.sample_id AS sample,
               s.subject_id AS subject,
               s.project_id AS project,
               s.response,
               s.sex,
               sa.time_from_treatment_start
        FROM samples sa
        JOIN subjects s ON s.subject_id = sa.subject_id
        WHERE {MIRACLIB_MELANOMA_PBMC}
          AND sa.time_from_treatment_start = 0
        ORDER BY sa.sample_id
    """
    return pd.read_sql_query(query, conn)


def baseline_breakdowns(conn: sqlite3.Connection) -> Dict[str, pd.DataFrame]:
    """Three breakdowns of the baseline subset.

    - samples_per_project : sample count per project
    - subjects_by_response: distinct-subject count by response (yes/no)
    - subjects_by_sex     : distinct-subject count by sex (M/F)
    """
    df = baseline_samples(conn)
    subjects = df.drop_duplicates(subset="subject")

    samples_per_project = (
        df.groupby("project").size().reset_index(name="n_samples")
    )
    subjects_by_response = (
        subjects.groupby("response").size().reset_index(name="n_subjects")
    )
    subjects_by_sex = (
        subjects.groupby("sex").size().reset_index(name="n_subjects")
    )
    return {
        "samples_per_project": samples_per_project,
        "subjects_by_response": subjects_by_response,
        "subjects_by_sex": subjects_by_sex,
    }


# --------------------------------------------------------------------------- #
# PDF page-4 form question
# --------------------------------------------------------------------------- #
def melanoma_male_responder_baseline_bcell_mean(conn: sqlite3.Connection) -> float:
    """Average raw B-cell count for melanoma male responders at baseline (t=0).

    Answers the standalone form question on page 4 of the assignment PDF.
    """
    query = """
        SELECT AVG(cc.count) AS avg_b_cell
        FROM cell_counts cc
        JOIN samples  sa ON sa.sample_id  = cc.sample_id
        JOIN subjects s  ON s.subject_id  = sa.subject_id
        WHERE cc.population = 'b_cell'
          AND s.condition  = 'melanoma'
          AND s.sex        = 'M'
          AND s.response   = 'yes'
          AND sa.time_from_treatment_start = 0
    """
    value = conn.execute(query).fetchone()[0]
    return round(float(value), 2)
