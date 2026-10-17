"""Generate the time.md visualizations, styled to match the app's DARKLY theme.

Mirrors tools/scoring_viz.py (same palette, helpers, sizing). Outputs four
PNGs into docs/images/:
  time-lognormal-tail.png      — additive (Normal) vs multiplicative (Log-normal)
  time-quantile-reading.png    — one bracket read as hard bounds vs as percentiles
  time-estimator-accuracy.png  — error recovering the true mean: PERT vs Swanson
  time-chain-correlation.png   — chain spread vs chain length, independent vs shared

Run from the repository root: `python tools/time_viz.py`. It needs matplotlib,
which the app does not install.
"""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --- DARKLY palette (from STYLE_GUIDE.md), identical to scoring_viz.py ---
BG = "#1a1d21"        # canvas
PANEL = "#212529"     # axes face
TEXT = "#dee2e6"
MUTED = "#6c757d"
GRID = "#343a40"
BORDER = "#495057"

GOLD = "#cdbe23"      # Goal/Sage — the hero / blended estimate
BLUE = "#3e8bd6"      # brightened Learn blue
TEAL = "#2f909d"      # Milestone teal — geometric / log side
ORANGE = "#cf7b33"    # brightened Action orange
RED = "#c94c4c"       # danger — the naive / runaway curve
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


def _beta_pdf(z, a, b):
    """Beta(a, b) density on [0, 1]; vectorised. Both shapes > 1 here, so the
    endpoints are well behaved and no singularities arise."""
    norm = math.gamma(a) * math.gamma(b) / math.gamma(a + b)
    z = np.asarray(z, dtype=float)
    out = np.zeros_like(z)
    inside = (z > 0) & (z < 1)
    out[inside] = z[inside] ** (a - 1) * (1 - z[inside]) ** (b - 1) / norm
    return out


def _pert_shapes(lo, mode, hi, lam=4.0):
    span = hi - lo
    return 1 + lam * (mode - lo) / span, 1 + lam * (hi - mode) / span


# ---------------------------------------------------------------------------
# A. Additive (Normal) vs multiplicative (Log-normal) — the long right tail
# ---------------------------------------------------------------------------
def plot_lognormal_tail():
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    x = np.linspace(-80, 500, 900)

    # Both curves share the same mean (140 h): the additive and multiplicative
    # views agree on the average but disagree completely on the shape of risk.
    mean = 140.0

    # Normal: the additive assumption — symmetric, and leaks below zero.
    n_sd = 64.0
    normal = np.exp(-((x - mean) ** 2) / (2 * n_sd ** 2)) / (n_sd * math.sqrt(2 * math.pi))

    # Log-normal: real compounding delays — bounded at 0, long right tail.
    # mu chosen so E[T] = mean, i.e. mu = ln(mean) - sigma^2 / 2.
    sigma = 0.75
    mu = math.log(mean) - sigma ** 2 / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        xp = np.where(x > 0, x, 1.0)
        lognorm = np.where(
            x > 0,
            np.exp(-((np.log(xp) - mu) ** 2) / (2 * sigma ** 2))
            / (xp * sigma * math.sqrt(2 * math.pi)),
            0.0,
        )

    ax.plot(x, normal, color=RED, lw=2.0, ls=(0, (4, 3)), label="Normal (additive assumption)")
    ax.plot(x, lognorm, color=BLUE, lw=2.6, label="Log-normal (real delays)")

    # Shade the impossible negative-duration mass the Normal assigns.
    neg = x < 0
    ax.fill_between(x[neg], normal[neg], color=RED, alpha=0.30)
    ax.axvline(0, color=MUTED, lw=1.0, ls=":")
    ax.annotate("negative durations\n(impossible)", xy=(-10, 0.0007), xytext=(-78, 0.0040),
                color=MUTED, fontsize=9, va="center",
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))

    # Shade the right tail past where the Normal has effectively died — the
    # overrun the additive view rules out but the multiplicative one keeps.
    tail = x >= 300
    ax.fill_between(x[tail], lognorm[tail], color=BLUE, alpha=0.28)
    ax.annotate("the Normal rules this\nout; real projects\nstill land here",
                xy=(360, lognorm[np.argmin(np.abs(x - 360))]), xytext=(330, 0.0042),
                color=BLUE, fontsize=9, ha="left",
                arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0))

    ax.set_xlabel("Task Duration (Hours)")
    ax.set_ylabel("Probability Density")
    ax.set_title("Additive vs Multiplicative Error")
    ax.set_xlim(-80, 500)
    ax.set_ylim(0, None)
    ax.legend(loc="upper right")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/time-lognormal-tail.png", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# B. One bracket, two readings: hard bounds vs the 10th/50th/90th percentiles
# ---------------------------------------------------------------------------
def plot_quantile_reading():
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    lo, mid, hi = 20.0, 40.0, 80.0
    x = np.linspace(0.1, 170, 1400)

    # Reading 1 — the classic PERT premise: [lo, hi] is the whole support.
    a, b = _pert_shapes(lo, mid, hi)
    z = (x - lo) / (hi - lo)
    inside = (z > 0) & (z < 1)
    beta = np.zeros_like(x)
    beta[inside] = _beta_pdf(z[inside], a, b) / (hi - lo)

    # Reading 2 — the app's premise: lo and hi are the 10th and 90th percentiles.
    z90 = 1.2815515655446004
    sigma = math.log(hi / lo) / (2 * z90)
    mean = 0.3 * lo + 0.4 * mid + 0.3 * hi
    mu = math.log(mean) - sigma ** 2 / 2
    lognorm = np.exp(-((np.log(x) - mu) ** 2) / (2 * sigma ** 2)) / (x * sigma * math.sqrt(2 * math.pi))

    ax.plot(x, beta, color=RED, lw=2.0, ls=(0, (4, 3)),
            label="Read as hard bounds — nothing past 80 h")
    ax.plot(x, lognorm, color=GOLD, lw=2.6,
            label="Read as the 10th / 50th / 90th percentiles")

    tail = x >= hi
    ax.fill_between(x[tail], lognorm[tail], color=GOLD, alpha=0.30)
    ax.annotate("a tenth of the mass\nsits past the upper estimate",
                xy=(97, 0.0030), xytext=(101, 0.0135), color=GOLD, fontsize=9, ha="left",
                arrowprops=dict(arrowstyle="->", color=GOLD, lw=1.0))

    for value, label in ((lo, "lower\n20 h"), (mid, "expected\n40 h"), (hi, "upper\n80 h")):
        ax.axvline(value, color=MUTED, lw=1.0, ls=":")
        ax.annotate(label, (value, 0), textcoords="offset points", xytext=(0, -32),
                    ha="center", color=MUTED, fontsize=9, annotation_clip=False)

    ax.set_xlabel("Task Duration (Hours)", labelpad=26)
    ax.set_ylabel("Probability Density")
    ax.set_title("The Same Three Numbers, Two Readings")
    ax.set_xlim(0, 170)
    ax.set_ylim(0, None)
    ax.legend(loc="upper right")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/time-quantile-reading.png", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# C. Error recovering the true mean, as the underlying spread widens
# ---------------------------------------------------------------------------
def plot_estimator_accuracy():
    from scipy import stats

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    sigmas = np.linspace(0.12, 1.1, 90)

    def series(rule):
        out = []
        for s in sigmas:
            d = stats.lognorm(s, scale=100)
            l, m, u = d.ppf(0.10), d.ppf(0.50), d.ppf(0.90)
            out.append(100 * (rule(l, m, u) / d.mean() - 1))
        return np.array(out)

    ax.axhline(0, color=BORDER, lw=1.2)
    ax.plot(sigmas, series(lambda l, m, u: (l + 4 * m + u) / 6), color=VIOLET, lw=2.3,
            ls=(0, (4, 3)), label="PERT weighting, 1 : 4 : 1")
    ax.plot(sigmas, series(lambda l, m, u: 0.3 * l + 0.4 * m + 0.3 * u), color=GOLD, lw=2.8,
            label="Swanson weighting, 0.3 : 0.4 : 0.3")

    ax.axvspan(0.2, 0.5, color=TEAL, alpha=0.14)
    ax.annotate("the spread this graph\nactually carries", xy=(0.35, -14.5), ha="center",
                color=TEAL, fontsize=9)

    ax.set_xlabel("Spread of the underlying duration (log-normal sigma)")
    ax.set_ylabel("Error in the expected duration (%)")
    ax.set_title("Recovering the True Mean From Three Percentiles")
    ax.set_xlim(0.12, 1.1)
    ax.set_ylim(-27, 4)
    ax.legend(loc="lower left")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/time-estimator-accuracy.png", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------------------
# D. Chain spread against chain length, independent vs shared estimating error
# ---------------------------------------------------------------------------
def plot_chain_correlation():
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    rng = np.random.default_rng(20260911)
    counts = [1, 2, 3, 5, 8, 12, 20, 30, 50, 80, 120]
    trials = 60000
    z90 = 1.2815515655446004
    lo, mid, hi = 20.0, 40.0, 80.0
    sigma = math.log(hi / lo) / (2 * z90)
    mean = 0.3 * lo + 0.4 * mid + 0.3 * hi

    def spread(n, rho):
        shared = rng.standard_normal(trials)
        total = np.zeros(trials)
        for _ in range(n):
            own = rng.standard_normal(trials)
            z = math.sqrt(rho) * shared + math.sqrt(1 - rho) * own
            total += mean * np.exp(sigma * z - 0.5 * sigma ** 2)
        p10, p90 = np.percentile(total, [10, 90])
        return p90 / p10

    for rho, color, style, label in (
        (0.0, RED, (0, (4, 3)), "Independent tasks (rho = 0)"),
        (0.4, GOLD, "solid", "Shared estimating error (rho = 0.4)"),
    ):
        ax.plot(counts, [spread(n, rho) for n in counts], color=color, lw=2.5,
                ls=style, marker="o", ms=4, label=label)

    ax.axhline(1.0, color=BORDER, lw=1.2)
    ax.annotate("uncertainty has\nevaporated", xy=(115, 1.14), xytext=(40, 1.75),
                color=RED, fontsize=9, ha="left",
                arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))

    ax.set_xscale("log")
    ax.set_xticks(counts)
    ax.set_xticklabels([str(c) for c in counts])
    ax.set_xlabel("Tasks Remaining in the Project")
    ax.set_ylabel("Width of the 80% forecast (P90 / P10)")
    ax.set_title("Where a Project's Uncertainty Goes")
    ax.set_ylim(0.95, None)
    ax.legend(loc="upper right")
    finish(ax)
    fig.tight_layout()
    fig.savefig("docs/images/time-chain-correlation.png", facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    plot_lognormal_tail()
    plot_quantile_reading()
    plot_estimator_accuracy()
    plot_chain_correlation()
    print("wrote 4 figures to docs/images/")
