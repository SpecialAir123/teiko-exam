#!/usr/bin/env python3
"""Parts 2-4 — analysis pipeline.

Reads the database produced by ``load_data.py`` and writes every required output
table and plot into ``outputs/``. Run after the loader:

    python load_data.py && python run_pipeline.py

(or simply ``make pipeline``).
"""

from __future__ import annotations

import os
import sys

from src import analysis
from src.db import DB_PATH, ROOT_DIR, get_connection
from src.plots import responder_boxplot

OUTPUT_DIR = os.path.join(ROOT_DIR, "outputs")


def _section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    if not os.path.exists(DB_PATH):
        sys.exit("ERROR: database not found. Run `python load_data.py` first.")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = get_connection()

    # --- Part 2: relative frequency summary --------------------------------
    _section("Part 2 — relative frequency of each cell population per sample")
    freq = analysis.frequency_table(conn)
    freq_path = os.path.join(OUTPUT_DIR, "cell_frequencies.csv")
    freq.to_csv(freq_path, index=False)
    print(freq.head(10).to_string(index=False))
    print(f"... {len(freq):,} rows written to {freq_path}")

    # --- Part 3: responders vs non-responders ------------------------------
    _section("Part 3 — responders vs non-responders (melanoma / miraclib / PBMC)")
    stats = analysis.responder_stats(conn)
    stats_path = os.path.join(OUTPUT_DIR, "responder_stats.csv")
    stats.to_csv(stats_path, index=False)
    print(stats.to_string(index=False))
    print(f"\nStatistics written to {stats_path}")

    sig = stats.loc[stats["significant"], "population"].tolist()
    if sig:
        print(
            "\nSignificant differences (Mann-Whitney U, BH-adjusted p < 0.05): "
            + ", ".join(sig)
        )
    else:
        print("\nNo populations reached significance at adjusted p < 0.05.")

    cmp_data = analysis.responder_comparison_data(conn)
    fig = responder_boxplot(cmp_data, stats)
    plot_path = os.path.join(OUTPUT_DIR, "responder_boxplot.png")
    fig.savefig(plot_path, dpi=150)
    print(f"Boxplot written to {plot_path}")

    # --- Part 4: baseline subset -------------------------------------------
    _section("Part 4 — melanoma PBMC baseline (t=0) samples on miraclib")
    base = analysis.baseline_samples(conn)
    base_path = os.path.join(OUTPUT_DIR, "baseline_samples.csv")
    base.to_csv(base_path, index=False)
    breakdowns = analysis.baseline_breakdowns(conn)

    lines = [f"Baseline samples (melanoma, miraclib, PBMC, t=0): {len(base)}", ""]
    lines.append("Samples per project:")
    lines += [
        f"  {r.project}: {r.n_samples}"
        for r in breakdowns["samples_per_project"].itertuples()
    ]
    lines.append("\nSubjects by response:")
    lines += [
        f"  {r.response}: {r.n_subjects}"
        for r in breakdowns["subjects_by_response"].itertuples()
    ]
    lines.append("\nSubjects by sex:")
    lines += [
        f"  {r.sex}: {r.n_subjects}"
        for r in breakdowns["subjects_by_sex"].itertuples()
    ]
    report = "\n".join(lines)
    print(report)
    breakdown_path = os.path.join(OUTPUT_DIR, "baseline_breakdowns.txt")
    with open(breakdown_path, "w") as fh:
        fh.write(report + "\n")
    print(f"\nBaseline samples written to {base_path}")
    print(f"Baseline breakdowns written to {breakdown_path}")

    # --- Assignment PDF page-4 form question -------------------------------
    _section("Assignment form question (PDF p.4)")
    avg_b = analysis.melanoma_male_responder_baseline_bcell_mean(conn)
    print(
        "Melanoma males, average B-cell count for responders at time=0: "
        f"{avg_b:.2f}"
    )

    conn.close()
    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
