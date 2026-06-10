"""Static plotting helpers (used by the pipeline to write PNGs)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend for CI / Codespaces
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src.db import POPULATIONS


def responder_boxplot(
    data: pd.DataFrame, stats: pd.DataFrame, title: str | None = None
) -> plt.Figure:
    """Boxplot of relative frequency by response, one panel per population.

    ``data``  : output of analysis.responder_comparison_data
    ``stats`` : output of analysis.responder_stats (for significance markers)
    """
    sns.set_theme(style="whitegrid")
    sig = dict(zip(stats["population"], stats["significant"]))
    padj = dict(zip(stats["population"], stats["p_value_adj"]))

    fig, axes = plt.subplots(1, len(POPULATIONS), figsize=(4 * len(POPULATIONS), 5), sharey=False)
    for ax, population in zip(axes, POPULATIONS):
        sub = data[data["population"] == population]
        sns.boxplot(
            data=sub, x="response", y="percentage", hue="response",
            order=["yes", "no"], palette={"yes": "#2a9d8f", "no": "#e76f51"},
            legend=False, ax=ax,
        )
        sns.stripplot(
            data=sub, x="response", y="percentage", order=["yes", "no"],
            color="0.3", size=2, alpha=0.25, ax=ax,
        )
        marker = "  *significant*" if sig.get(population) else ""
        ax.set_title(f"{population}\n(adj p = {padj.get(population):.2e}){marker}")
        ax.set_xlabel("response")
        ax.set_ylabel("relative frequency (%)")
        ax.set_xticklabels(["responder", "non-responder"])

    fig.suptitle(
        title or "Cell population relative frequency: responders vs non-responders\n"
        "(melanoma, miraclib, PBMC)",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig
