"""Generate the scoring.md visualizations, styled to match the app's DARKLY theme.

Outputs three PNGs into docs/images/:
  scoring-cost-beta.png       — sublinear time damper (t/t_ref)^beta
  scoring-cascade-decay.png   — geometric decay of Hard/Soft discounts
  scoring-density.png         — density normalization 1/|B|^alpha

Run from the repository root: `python tools/scoring_viz.py`. It needs matplotlib,
which the app does not install.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Import app modules (scoring.TIME_REF_HOURS) when run as tools/scoring_viz.py,
# where sys.path[0] is tools/ rather than the repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- DARKLY palette (from STYLE_GUIDE.md) ---
BG = "#1a1d21"        # canvas
PANEL = "#212529"     # axes face
TEXT = "#dee2e6"
MUTED = "#6c757d"
GRID = "#343a40"
BORDER = "#495057"

GOLD = "#cdbe23"      # Goal/Sage — the reference baseline
BLUE = "#3e8bd6"      # brightened Learn blue, Hard
TEAL = "#2f909d"      # Milestone teal, Soft / low end
ORANGE = "#cf7b33"    # brightened Action orange, high end
RED = "#c94c4c"       # danger — the rejected/naive curve
VIOLET = "#9b6fc4"    # brightened Resource

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": PANEL,
    "axes.edgecolor": BORDER,
    "axes.labelcolor": TEXT,
    "axes.titlecolor": TEXT,
    "text.color": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "grid.color": GRID,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "legend.frameon": False,
    "figure.dpi": 150,
})


def finish(ax):
    ax.grid(True, alpha=0.5, linewidth=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


# ---------------------------------------------------------------------------
# 1. Perceived cost — the beta time damper
# ---------------------------------------------------------------------------
def plot_cost_beta():
    """The time penalty w_t * (t / t_ref)**beta, normalized at the reference.

    Every curve passes through (t_ref, w_t) by construction, which is the whole
    point of dividing by t_ref: beta bends the curve without moving its height.
    Curves are drawn at a shared w_t so the shapes are directly comparable.
    """
    from skilltree.domain.scoring import TIME_REF_HOURS

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    t = np.linspace(0.01, 500, 800)
    w_t = 6.0
    betas = [(0.95, ORANGE, "Glider"), (0.70, GOLD, "Pragmatist"),
             (0.60, TEAL, "Sage / most"), (0.50, MUTED, "Compounder")]
    for b, c, label in betas:
        ax.plot(t, w_t * (t / TIME_REF_HOURS) ** b, color=c, lw=2.4,
                label=fr"$\beta = {b}$  ({label})")
    ax.plot(t, w_t * (t / TIME_REF_HOURS), color=MUTED, lw=1.3, ls=(0, (4, 3)),
            label=r"linear ($\beta = 1$)")

    # Mark the reference: all curves meet here, at exactly w_t.
    ax.axvline(TIME_REF_HOURS, color=MUTED, lw=0.9, ls=(0, (2, 4)), alpha=0.7)
    ax.plot([TIME_REF_HOURS], [w_t], marker="o", ms=5, color=MUTED, zorder=5)
    ax.annotate(
        fr"all curves meet at $t_{{\mathrm{{ref}}}} = {TIME_REF_HOURS:.0f}$h,"
        "\n"
        r"where the penalty is exactly $w_t$",
        xy=(TIME_REF_HOURS, w_t), xytext=(238, 2.5),
        color=TEXT, fontsize=9,
        arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1,
                        shrinkA=0, shrinkB=4),
    )

    ax.set_xlabel("Time (Hours)")
    ax.set_ylabel("Time Penalty")
    ax.set_title("Perceived Cost — the time term")
    ax.set_xlim(0, 500)
    ax.set_ylim(0, 60)
    ax.legend(loc="upper left")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/scoring-cost-beta.png", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2. DAG cascade — geometric decay of edge discounts
# ---------------------------------------------------------------------------
def plot_cascade_decay():
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    k = np.arange(0, 7)
    ax.plot(k, 0.6 ** k * 100, color=BLUE, lw=2.4, marker="o", ms=6,
            label=r"Hard  $d_H = 0.6$")
    ax.plot(k, 0.4 ** k * 100, color=TEAL, lw=2.4, marker="s", ms=6,
            label=r"Soft  $d_S = 0.4$")

    ax.axhline(10, color=MUTED, lw=0.9, ls=":")
    ax.text(6, 11.5, "≈10% relevance floor", color=MUTED, fontsize=9, ha="right")

    ax.set_xlabel("Depth (Hops Downstream)")
    ax.set_ylabel("% of Descendant Value")
    ax.set_title("DAG Cascade")
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 100)
    ax.set_xticks(k)
    ax.legend(loc="upper right")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/scoring-cascade-decay.png", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3. Density normalization — 1/|B|^alpha
# ---------------------------------------------------------------------------
def plot_density():
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    n = np.linspace(1, 60, 500)
    alphas = [(0.10, TEAL, "α = 0.10  (Pragmatist)"),
              (0.30, GOLD, "α = 0.30  (Sage, Creator)"),
              (0.45, ORANGE, "α = 0.45  (Glider)"),
              (0.65, RED, "α = 0.65  (Explorer)")]
    for a, c, label in alphas:
        ax.plot(n, 1 / n ** a, color=c, lw=2.4, label=label)
    ax.plot(n, 1 / n, color=MUTED, lw=1.5, ls=(0, (4, 3)), label="α = 1.0  (full flattening)")
    ax.axhline(1.0, color=MUTED, lw=0.9, ls=(0, (2, 4)), alpha=0.6)

    ax.set_xlabel("Eligible Nodes in Bucket")
    ax.set_ylabel("Density Weight")
    ax.set_title("Density Normalization")
    ax.set_xlim(1, 60)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper right")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/scoring-density.png", facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    plot_cost_beta()
    plot_cascade_decay()
    plot_density()
    print("wrote 3 figures to docs/images/")
