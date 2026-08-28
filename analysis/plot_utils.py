# Rashed-Step 14.A-08-28-2026-start
"""
Shared plotting helper for every figure-generation script in analysis/.
Every figure goes through save_line_figure() so all of the paper's
figures share one consistent, publication-quality look: gridded,
bordered (visible spines on all four sides), a fixed per-series
color/marker/linestyle registry (so a given technology - or a given
technology's model-vs-simulated pair - is drawn identically across every
figure this module produces), a legend, and high-resolution PDF+JPG
output into analysis/generated/.
"""
import os
from typing import Dict, Sequence

import matplotlib
matplotlib.use("Agg")  # headless - this module never opens an interactive window
import matplotlib.pyplot as plt

GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# One style per series LABEL, reused across every figure this module
# generates - keeps a technology visually identical (same color + marker)
# whether it's plotted alone, against its analytical model, or against
# the other technology, so a reader flipping between the paper's figures
# doesn't have to re-learn the legend each time. Model-vs-simulated pairs
# share a color and differ by linestyle (dashed=model, solid=simulated)
# and marker, per the "different marker for each technology" request.
SERIES_STYLE: Dict[str, dict] = {
    "Wi-Fi (Model)":     dict(color="#1f77b4", marker="o", linestyle="--"),
    "Wi-Fi (Simulated)": dict(color="#1f77b4", marker="s", linestyle="-"),
    "NR-U (Model)":      dict(color="#d62728", marker="^", linestyle="--"),
    "NR-U (Simulated)":  dict(color="#d62728", marker="D", linestyle="-"),
    "Wi-Fi":             dict(color="#1f77b4", marker="s", linestyle="-"),
    "NR-U":              dict(color="#d62728", marker="D", linestyle="-"),
    "Fairness Index":    dict(color="#2ca02c", marker="^", linestyle="-"),
}

LINEWIDTH = 2.2
MARKERSIZE = 8
MARKEREDGEWIDTH = 1.3
FONTSIZE_LABEL = 13
FONTSIZE_TITLE = 14
FONTSIZE_TICK = 11
FONTSIZE_LEGEND = 11
DPI = 300  # high resolution - safe for both print and screen viewing


def save_line_figure(
    x: Sequence[float],
    series: Dict[str, Sequence[float]],
    xlabel: str,
    ylabel: str,
    title: str,
    output_stem: str,
    x_ticks_as_int: bool = True,
    figsize=(7.5, 5.5),
) -> Dict[str, str]:
    """
    Draws one gridded, bordered line plot - one line per (label, y-values)
    pair in `series`, styled per SERIES_STYLE (falls back to matplotlib's
    default color/marker cycle for any label not in the registry, so this
    still works for one-off series names) - and saves it as both a vector
    PDF and a high-resolution (300 DPI) JPG under analysis/generated/.

    output_stem: filename WITHOUT extension or directory, e.g.
      "occupancy_model_vs_simulation" ->
        analysis/generated/occupancy_model_vs_simulation.pdf
        analysis/generated/occupancy_model_vs_simulation.jpg

    Returns {"pdf": <path>, "jpg": <path>}.
    """
    fig, ax = plt.subplots(figsize=figsize)

    for label, y in series.items():
        style = SERIES_STYLE.get(label, {})
        ax.plot(
            x, y,
            label=label,
            linewidth=LINEWIDTH,
            markersize=MARKERSIZE,
            markeredgewidth=MARKEREDGEWIDTH,
            markerfacecolor="white",
            **style,
        )

    ax.set_xlabel(xlabel, fontsize=FONTSIZE_LABEL)
    ax.set_ylabel(ylabel, fontsize=FONTSIZE_LABEL)
    ax.set_title(title, fontsize=FONTSIZE_TITLE)
    ax.tick_params(axis="both", labelsize=FONTSIZE_TICK)

    if x_ticks_as_int:
        ax.set_xticks(list(x))

    # Gridded.
    ax.grid(True, which="major", linestyle=":", linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)  # grid behind the data lines, not on top of them

    # Bordered - visible, print-legible spines on all four sides.
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(1.2)
        spine.set_color("black")

    ax.legend(fontsize=FONTSIZE_LEGEND, framealpha=0.9, edgecolor="black")

    fig.tight_layout()

    pdf_path = os.path.join(GENERATED_DIR, f"{output_stem}.pdf")
    jpg_path = os.path.join(GENERATED_DIR, f"{output_stem}.jpg")
    fig.savefig(pdf_path, dpi=DPI, bbox_inches="tight")
    fig.savefig(jpg_path, dpi=DPI, bbox_inches="tight", format="jpg")
    plt.close(fig)

    return {"pdf": pdf_path, "jpg": jpg_path}
# Rashed-Step 14.A-08-28-2026-end
