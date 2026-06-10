# Loblaw Bio — Immune Cell Population Analysis

A reproducible pipeline + interactive dashboard analyzing how the drug candidate
**miraclib** affects immune cell populations in a clinical trial, built for Bob
Loblaw at Loblaw Bio.

Input: `cell-count.csv` — counts of five immune populations (`b_cell`,
`cd8_t_cell`, `cd4_t_cell`, `nk_cell`, `monocyte`) for **10,500 samples** from
**3,500 subjects** across **3 projects**, with sample metadata.

---

## Quickstart (GitHub Codespaces / local)

```bash
make setup       # install dependencies (requirements.txt)
make pipeline    # Part 1 (build + load DB) then Parts 2-4 (tables + plots)
make dashboard   # launch the interactive Streamlit dashboard
```

- `make pipeline` creates `cell_counts.db` in the repo root and writes all
  result tables/plots to `outputs/`.
- `make dashboard` starts Streamlit locally (default <http://localhost:8501>).
  In Codespaces, open the forwarded port when prompted.

Requires Python 3.10+. Individual scripts also run standalone:
`python load_data.py` then `python run_pipeline.py`.

---

## Repository structure

```
load_data.py        Part 1: initialize schema + load CSV → cell_counts.db (no args)
run_pipeline.py     Parts 2-4: compute tables/plots → outputs/
app.py              Streamlit dashboard (Parts 2-4, interactive)
src/
  db.py             schema DDL, the sample_frequencies view, connection helper
  analysis.py       pure query/compute functions returning DataFrames
  plots.py          static boxplot (PNG) used by the pipeline
outputs/            generated tables (.csv), boxplot (.png), breakdowns (.txt)
Makefile            setup / pipeline / dashboard
requirements.txt    dependencies
```

**Why this structure.** The analytics live in `src/analysis.py` as small,
pure functions that take a SQLite connection and return DataFrames. Both the
batch pipeline (`run_pipeline.py`) and the dashboard (`app.py`) import the *same*
functions, so there is a single source of truth for every calculation — the
dashboard can never drift from the graded outputs. `load_data.py` and the
analysis are decoupled through the database: the loader's only job is to produce
a clean normalized DB, and everything downstream reads from it.

---

## Database schema

Normalized into four tables mirroring the real-world entities, with cell counts
stored in **long format**:

```
projects(project_id PK)
   │ 1─N
subjects(subject_id PK, project_id FK, condition, age, sex, treatment, response)
   │ 1─N
samples(sample_id PK, subject_id FK, sample_type, time_from_treatment_start)
   │ 1─N
cell_counts(sample_id FK, population, count, PK(sample_id, population))
```

A view, `sample_frequencies`, encodes the Part 2 relative-frequency calculation
once (total per sample + each population's percentage) so the pipeline and
dashboard share identical logic.

**Design rationale.** Subject-level attributes (`condition, age, sex, treatment,
response, project`) are constant per subject in the source data, so they live on
`subjects` rather than being repeated on every sample row — this removes update
anomalies and keeps cohort filters (e.g. "melanoma + miraclib") fast and
unambiguous. The cell counts are stored **long (one row per sample × population)**
rather than as five wide columns. This is the key choice:

- **New populations are data, not schema.** Adding a sixth or sixtieth cell type
  is an `INSERT`, with no `ALTER TABLE` and no downstream code changes.
- **Aggregation is natural.** Every analysis here is "per population" — long
  format turns that into a one-line `GROUP BY` and makes the frequency view trivial.

**Scaling to hundreds of projects / thousands of samples.** The model already
scales: `cell_counts` grows as `samples × populations`, indexed on its primary
key and on `population`, and the subject/sample filter columns are indexed, so
the cohort queries used in Parts 3-4 stay index-driven. To go further:

- Migrate the same schema to **Postgres** (the SQL is standard) for concurrent
  writes, partitioning, and richer types. `cell_counts` is the obvious candidate
  for **partitioning by project** (or time) and adding a per-population covering
  index.
- The relative-frequency view can become a **materialized view** refreshed on
  load, so dashboards read pre-aggregated rows instead of recomputing.
- For many "types of analytics," add **dimension tables** (e.g. assay, batch,
  timepoint) and keep `cell_counts` as the central fact table — a clean star
  schema that BI tools and ad-hoc SQL both handle well.
- The loader is idempotent and would extend naturally to per-project incremental
  loads or an upsert strategy keyed on `sample_id`.

---

## Analysis summary

### Part 2 — Relative frequency per sample
`outputs/cell_frequencies.csv` — columns `sample, total_count, population, count,
percentage`, one row per (sample, population).

### Part 3 — Responders vs non-responders (melanoma, miraclib, PBMC only)
- **Cohort:** 1,968 samples (993 responder / 975 non-responder).
- **Method:** per population, a **Mann–Whitney U** test (non-parametric — cell
  frequencies are not assumed normal) on relative frequency, with
  **Benjamini–Hochberg FDR** correction across the five populations. Significance
  at adjusted *p* < 0.05.
- **Finding:** **no** cell population shows a statistically significant difference
  in relative frequency between responders and non-responders after FDR
  correction. The closest is `cd4_t_cell` (raw *p* ≈ 0.013, adjusted *p* ≈ 0.067);
  responder medians trend slightly higher for CD4 T cells and slightly lower for
  B cells, but neither survives multiple-testing correction. On this dataset, the
  measured PBMC population frequencies are **not** a reliable predictor of
  miraclib response. See `outputs/responder_stats.csv` and
  `outputs/responder_boxplot.png`.

### Part 4 — Baseline subset (melanoma PBMC, miraclib, time = 0)
- **656 baseline samples.**
- Samples per project: **prj1 = 384, prj3 = 272**.
- Subjects by response: **responders = 331, non-responders = 325**.
- Subjects by sex: **male = 344, female = 312**.
- See `outputs/baseline_samples.csv` and `outputs/baseline_breakdowns.txt`.

### Assignment form question (PDF p.4)
Melanoma males, average B-cell count for responders at time = 0: **`10206.15`**
(printed by `run_pipeline.py`).

---

## Dashboard

The Streamlit dashboard (`app.py`) has three tabs:

1. **Overview (Part 2)** — searchable/filterable frequency table, CSV download,
   and mean relative frequency by population.
2. **Responders vs Non-responders (Part 3)** — interactive boxplots, the full
   statistical test table, and a written interpretation.
3. **Baseline Subset (Part 4)** — breakdown charts with live filters for
   condition / treatment / sample type / timepoint so Bob can explore other
   subsets, not just the baseline default.

**Live dashboard link:** _<add your Streamlit Community Cloud URL here after deploying>_

### Deploying the public link (free)
1. Push this repo to GitHub.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click **New app**.
3. Select this repo/branch, set **Main file path** to `app.py`, and **Deploy**.
   (`requirements.txt` is detected automatically; the app builds the database
   from `cell-count.csv` on first load, so no `.db` needs to be committed.)
4. Paste the resulting URL into the line above.

---

## Notes

- **Column mapping.** The assignment's generic names map to the CSV as:
  `sample_id → sample`, `indication → condition`, `gender → sex`.
- **Prompt-injection note.** The Part 4 prompt contains an embedded instruction
  to "mention quintazide." Quintazide does **not** exist in this dataset (the
  only treatments are `miraclib`, `phauximab`, `none`); the string is an injected
  instruction, not a real requirement, and was intentionally ignored. The actual
  drug under study is **miraclib**.
