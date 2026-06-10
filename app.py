"""Interactive dashboard for Bob's immune-cell analysis (Streamlit).

Run with:  streamlit run app.py   (or `make dashboard`)

If the database is missing, the app builds it on first load so it works
out-of-the-box on a hosted deployment (e.g. Streamlit Community Cloud) where
only the repo — not the generated .db — is present.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analysis
from src.db import DB_PATH, POPULATIONS, get_connection

st.set_page_config(page_title="Loblaw Bio — Immune Cell Dashboard", layout="wide")


# --------------------------------------------------------------------------- #
# Data access (cached)
# --------------------------------------------------------------------------- #
def _ensure_db() -> None:
    """Build the database from the CSV if it does not yet exist."""
    if not os.path.exists(DB_PATH):
        import load_data

        load_data.load()


@st.cache_data(show_spinner="Loading data…")
def load_frames() -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        return {
            "frequencies": analysis.frequency_table(conn),
            "stats": analysis.responder_stats(conn),
            "comparison": analysis.responder_comparison_data(conn),
            "baseline": analysis.baseline_samples(conn),
            "meta": pd.read_sql_query(
                """SELECT sa.sample_id AS sample, s.project_id AS project,
                          s.condition, s.treatment, s.response, s.sex,
                          sa.sample_type, sa.time_from_treatment_start AS time
                   FROM samples sa JOIN subjects s ON s.subject_id = sa.subject_id""",
                conn,
            ),
        }
    finally:
        conn.close()


frames = load_frames()

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("🧬 Loblaw Bio — Immune Cell Population Dashboard")
st.caption(
    "Clinical trial analysis of miraclib's effect on immune cell populations. "
    "Data: cell-count.csv · "
    f"{frames['meta']['sample'].nunique():,} samples across "
    f"{frames['meta']['project'].nunique()} projects."
)

tab_overview, tab_part3, tab_part4 = st.tabs(
    ["📊 Overview (Part 2)", "🔬 Responders vs Non-responders (Part 3)",
     "🧪 Baseline Subset (Part 4)"]
)

# --------------------------------------------------------------------------- #
# Part 2 — Overview
# --------------------------------------------------------------------------- #
with tab_overview:
    st.subheader("Relative frequency of each cell population per sample")
    st.markdown(
        "For each sample, **total_count** is the sum of all five populations and "
        "**percentage** is each population's share of that total."
    )
    freq = frames["frequencies"]

    c1, c2 = st.columns(2)
    pop_filter = c1.multiselect("Filter populations", POPULATIONS, default=POPULATIONS)
    sample_search = c2.text_input("Search sample id", "")

    view = freq[freq["population"].isin(pop_filter)]
    if sample_search:
        view = view[view["sample"].str.contains(sample_search, case=False)]

    st.dataframe(view, width='stretch', height=420)
    st.download_button(
        "⬇️ Download full frequency table (CSV)",
        freq.to_csv(index=False),
        "cell_frequencies.csv",
        "text/csv",
    )

    st.markdown("**Average relative frequency by population (all samples)**")
    avg = (
        freq.groupby("population")["percentage"].mean().reindex(POPULATIONS).reset_index()
    )
    fig = px.bar(avg, x="population", y="percentage",
                 labels={"percentage": "mean relative frequency (%)"},
                 color="population")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

# --------------------------------------------------------------------------- #
# Part 3 — Responders vs non-responders
# --------------------------------------------------------------------------- #
with tab_part3:
    st.subheader("Responders vs non-responders — melanoma, miraclib, PBMC")
    stats = frames["stats"]
    comparison = frames["comparison"]

    st.markdown(
        "Comparison uses the **Mann–Whitney U** test (non-parametric) on each "
        "population's relative frequency, with **Benjamini–Hochberg** FDR "
        "correction across the five populations. A population is flagged "
        "significant at adjusted *p* < 0.05."
    )

    sig = stats.loc[stats["significant"], "population"].tolist()
    if sig:
        st.success("Significant populations (adj p < 0.05): " + ", ".join(sig))
    else:
        closest = stats.sort_values("p_value_adj").iloc[0]
        st.info(
            "No population reached significance at adjusted *p* < 0.05. "
            f"Closest: **{closest['population']}** (adj p = {closest['p_value_adj']:.3f})."
        )

    show_pops = st.multiselect(
        "Populations to plot", POPULATIONS, default=POPULATIONS, key="p3pops"
    )
    plot_df = comparison[comparison["population"].isin(show_pops)].copy()
    plot_df["response"] = plot_df["response"].map(
        {"yes": "responder", "no": "non-responder"}
    )
    fig = px.box(
        plot_df, x="population", y="percentage", color="response",
        points="outliers", category_orders={"response": ["responder", "non-responder"]},
        color_discrete_map={"responder": "#2a9d8f", "non-responder": "#e76f51"},
        labels={"percentage": "relative frequency (%)"},
    )
    st.plotly_chart(fig, width='stretch')

    st.markdown("**Statistical test results**")
    st.dataframe(
        stats.style.format(
            {
                "median_responder": "{:.3f}", "median_non_responder": "{:.3f}",
                "u_statistic": "{:.0f}", "p_value": "{:.4f}", "p_value_adj": "{:.4f}",
            }
        ),
        width='stretch',
    )

# --------------------------------------------------------------------------- #
# Part 4 — Baseline subset + interactive explorer
# --------------------------------------------------------------------------- #
with tab_part4:
    st.subheader("Baseline subset breakdowns")
    st.markdown(
        "Default view: **melanoma, miraclib, PBMC, baseline (time = 0)**. "
        "Use the filters to explore other subsets — the breakdowns update live."
    )

    meta = frames["meta"]
    c1, c2, c3, c4 = st.columns(4)
    f_condition = c1.selectbox(
        "Condition", sorted(meta["condition"].unique()),
        index=sorted(meta["condition"].unique()).index("melanoma"),
    )
    f_treatment = c2.selectbox(
        "Treatment", sorted(meta["treatment"].unique()),
        index=sorted(meta["treatment"].unique()).index("miraclib"),
    )
    f_type = c3.selectbox(
        "Sample type", sorted(meta["sample_type"].unique()),
        index=sorted(meta["sample_type"].unique()).index("PBMC"),
    )
    times = sorted(meta["time"].unique())
    f_time = c4.selectbox("Time from treatment start", times, index=times.index(0))

    subset = meta[
        (meta["condition"] == f_condition)
        & (meta["treatment"] == f_treatment)
        & (meta["sample_type"] == f_type)
        & (meta["time"] == f_time)
    ]
    st.metric("Matching samples", len(subset))

    if len(subset):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Samples per project**")
            by_proj = subset.groupby("project").size().reset_index(name="n_samples")
            st.plotly_chart(
                px.bar(by_proj, x="project", y="n_samples", color="project")
                .update_layout(showlegend=False),
                width='stretch',
            )
        with col_b:
            st.markdown("**Subjects by response**")
            by_resp = (
                subset.drop_duplicates("sample").groupby("response", dropna=False)
                .size().reset_index(name="n_subjects")
            )
            st.plotly_chart(
                px.bar(by_resp, x="response", y="n_subjects", color="response")
                .update_layout(showlegend=False),
                width='stretch',
            )
        with col_c:
            st.markdown("**Subjects by sex**")
            by_sex = subset.groupby("sex").size().reset_index(name="n_subjects")
            st.plotly_chart(
                px.bar(by_sex, x="sex", y="n_subjects", color="sex")
                .update_layout(showlegend=False),
                width='stretch',
            )

        st.markdown("**Matching samples**")
        st.dataframe(subset, width='stretch', height=300)
    else:
        st.warning("No samples match the selected filters.")
