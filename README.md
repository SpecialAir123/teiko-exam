# Loblaw Bio — Immune Cell Population Analysis

A reproducible pipeline + interactive dashboard analyzing how the drug candidate
**miraclib** affects immune cell populations in a clinical trial.

Input: `cell-count.csv` — counts of five immune populations (`b_cell`,
`cd8_t_cell`, `cd4_t_cell`, `nk_cell`, `monocyte`) for **10,500 samples** from
**3,500 subjects** across **3 projects**, plus sample metadata.

---

## Running the code (GitHub Codespaces or local)

```bash
make setup       # install dependencies (requirements.txt)
make pipeline    # Part 1 (build + load DB) then Parts 2-4 (tables + plots)
make dashboard   # launch the interactive Streamlit dashboard
```

- `make pipeline` creates `cell_counts.db` in the repo root and writes all
  result tables/plots to `outputs/`.
- `make dashboard` starts Streamlit locally (default <http://localhost:8501>).
  In Codespaces, open the forwarded port when prompted.

Requires Python 3.10+. The scripts also run standalone, with no arguments:

```bash
python load_data.py      # Part 1: initialize schema + load CSV -> cell_counts.db
python run_pipeline.py    # Parts 2-4: write tables/plots to outputs/
```

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

A view, `sample_frequencies`, encodes the per-sample relative-frequency
calculation once (total per sample + each population's percentage) so the
pipeline and dashboard share identical logic.

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

**Scaling to hundreds of projects / thousands of samples / many analytics.** The
model already scales: `cell_counts` grows as `samples × populations`, indexed on
its primary key and on `population`, and the subject/sample filter columns are
indexed, so cohort queries stay index-driven. To go further:

- Migrate the same schema to **Postgres** (the SQL is standard) for concurrent
  writes, partitioning, and richer types. `cell_counts` is the obvious candidate
  for **partitioning by project** (or time) plus a per-population covering index.
- The relative-frequency view can become a **materialized view** refreshed on
  load, so dashboards read pre-aggregated rows instead of recomputing.
- For many "types of analytics," keep `cell_counts` as the central **fact table**
  and add **dimension tables** (e.g. assay, batch, timepoint) — a clean star
  schema that BI tools and ad-hoc SQL both handle well.

---

## Code structure

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

**Why this structure.** The analytics live in `src/analysis.py` as small, pure
functions that take a SQLite connection and return DataFrames. Both the batch
pipeline (`run_pipeline.py`) and the dashboard (`app.py`) import the *same*
functions, so there is a single source of truth for every calculation — the
dashboard can never drift from the graded outputs. `load_data.py` and the
analysis are decoupled through the database: the loader's only job is to produce
a clean normalized DB, and everything downstream reads from it.

---

## Dashboard

**Live dashboard:** <https://teiko-exam-tom5ubedw5uk77w5y3zefa.streamlit.app/>

Three tabs: **Overview** (per-sample frequency table + summary chart),
**Responders vs Non-responders** (interactive boxplots + statistical test table),
and **Baseline Subset** (breakdown charts with live filters for
condition / treatment / sample type / timepoint).
