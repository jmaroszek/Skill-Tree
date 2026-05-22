# Time

This document covers how the app turns the user's time estimates into the numbers that feed scoring, simulation, and calibration. For how those numbers plug into the priority algorithm, see [algorithms.md](algorithms.md). For the user-facing tour, see [README.md](../README.md).

Two algorithms operate on the same three-point estimate $(o, m, p)$:

- **The blended PERT estimate** collapses the three numbers into a single $t(n)$ that scoring uses everywhere. Deterministic, fast, called on every node read.
- **The Monte Carlo simulation** keeps the distribution intact and draws thousands of samples to project total time over a prerequisite chain. Driven by the Time Simulation panel on the Details tab.

Both share the same input schema, the same degenerate-input fallbacks, and the same PERT weighting philosophy, but they answer different questions: "what single number should rank this node?" vs. "how long until this whole subtree is done?"

---

# Notation

| Symbol | Meaning |
|---|---|
| $o, m, p$ | Optimistic, most-likely, and pessimistic time estimates (hours), supplied per node |
| $t(n)$ | Blended point estimate used by scoring |
| $\bar{t}_{\text{arith}}$ | Arithmetic PERT mean |
| $\bar{t}_{\text{log}}$ | Logarithmic (geometric-style) PERT mean |
| $r$ | Uncertainty ratio $p/o$ |
| $w(r)$ | Blend weight in $[0, 1]$, tilting between arithmetic and logarithmic means |
| $\lambda$ | PERT shape parameter, fixed at $4$ |
| $\alpha, \beta$ | Beta-distribution shape parameters derived from $(o, m, p)$ |
| $T$ | A single sampled duration |
| $N$ | Number of Monte Carlo trials (default 10,000) |

---

# Why Three Numbers Instead of One

A single point estimate hides everything interesting about a task. "This will take 40 hours" reads as confident, but it doesn't say whether you mean 35-45 (tight) or 10-200 (a guess and a prayer). Two tasks with identical $m = 40$ but wildly different uncertainty should not score the same, and a planner that only sees the midpoint cannot tell them apart.

The three-point estimate $(o, m, p)$ — optimistic, most-likely, pessimistic — is the smallest input that captures both *expectation* and *uncertainty*. PERT's original use case was construction scheduling, where the same insight applies: most tasks have a typical duration plus a long tail of things that can go wrong. By forcing the user to think about all three numbers, the app collects enough signal to compute a meaningful point estimate *and* to sample a realistic distribution when the user asks for one.

The user is encouraged (but not required) to supply all three. Short-circuits handle every partial case, so even one number is enough to keep the algorithm running.

---

# Blended PERT Estimate

The function [`models.blend_time_estimate`](../models.py) takes $(o, m, p)$ and returns a single number for $t(n)$. This is the value scoring sees in the Cost formula and what every UI surface displays as "expected hours."

## Short-circuits

Before the blend runs, three degenerate cases are handled directly:

| Input | Output | Rationale |
|---|---|---|
| Only $m$ supplied | $t = m$ | No uncertainty information; trust the point estimate as-is |
| Only $o$ and $p$ supplied | $t = \sqrt{o \cdot p}$ | Geometric mean — symmetric in multiplicative uncertainty, the right center when $m$ is unknown |
| All three missing | $t = 1.0$ | Fallback so the Cost denominator never divides by something undefined |

The geometric-mean short-circuit deserves a note. The arithmetic average $(o + p) / 2$ is the intuitive choice, but it sits closer to $p$ than feels right when $p \gg o$ (a range of 1-100 averages to 50.5, which doesn't reflect "I think it'll be around 10"). The geometric mean — $\sqrt{1 \cdot 100} = 10$ — pulls toward the multiplicative midpoint, which tracks human intuition about uncertainty far better.

## The blend

When all three estimates are supplied, the blend combines two PERT-style means, each weighting the most-likely value four times more heavily than the endpoints.

The **arithmetic PERT mean** is the classical formula:

$$ \bar{t}_{\text{arith}} = \frac{o + 4m + p}{6} $$

The **logarithmic PERT mean** uses the same $1{:}4{:}1$ weighting on the logs:

$$ \bar{t}_{\text{log}} = \exp\!\left(\frac{\log o + 4 \log m + \log p}{6}\right) $$

This is the geometric counterpart — symmetric in multiplicative space, so a project estimated at $(1, 4, 16)$ centers naturally without the long $p$ tail dominating.

The blend tilts between the two as a function of the uncertainty ratio $r = p/o$. A small $r$ means tight estimates; a large $r$ means deep uncertainty:

$$ w(r) = \begin{cases} 0 & \text{if } r \le 2 \\[4pt] \dfrac{\log r - \log 2}{\log 10 - \log 2} & \text{if } 2 < r < 10 \\[8pt] 1 & \text{if } r \ge 10 \end{cases} $$

The final estimate is the weighted average:

$$ t(n) = (1 - w(r)) \cdot \bar{t}_{\text{arith}} + w(r) \cdot \bar{t}_{\text{log}} $$

The rationale is psychological. A tight range ($r \le 2$) signals the user is confident, so the symmetric arithmetic mean — which doesn't underweight $m$ — is the right answer. A wide range ($r \ge 10$) signals deep uncertainty, where the long pessimistic tail can drown an overconfident $m$ under the arithmetic mean; the log mean pulls back toward the geometric center, which is more robust. Between those bounds the blend interpolates logarithmically in $r$, so successive *doublings* of uncertainty get equal weight — moving from $r = 2$ to $r = 4$ matters as much as moving from $r = 5$ to $r = 10$.

## Example

The following table shows the blend in action with $m = 40$ held constant, sweeping $o$ and $p$ to vary the uncertainty ratio:

| $o$ | $m$ | $p$ | $r = p/o$ | $\bar{t}_{\text{arith}}$ | $\bar{t}_{\text{log}}$ | $w(r)$ | $t(n)$ |
|---|---|---|---|---|---|---|---|
| 30 | 40 | 50 | 1.67 | 40.00 | 39.69 | 0.00 | 40.00 |
| 20 | 40 | 80 | 4.00 | 43.33 | 40.00 | 0.43 | 41.90 |
| 10 | 40 | 120 | 12.00 | 48.33 | 36.84 | 1.00 | 36.84 |
| 5  | 40 | 200 | 40.00 | 67.50 | 33.79 | 1.00 | 33.79 |

Notice how the tight estimate (top row) returns essentially $\bar{t}_{\text{arith}}$ unchanged. As uncertainty widens, the arithmetic mean climbs aggressively — the $p = 200$ row arithmetic-averages to 67.5 even though $m$ is still 40 — while the log mean stays anchored near $m$. The blend favors the arithmetic mean when the user seems confident and the log mean when they don't, which keeps the headline number from being yanked around by a single overcautious pessimistic guess.

## Calibration

The same blend runs on the user's *actual* recorded time. When a node is marked Done, the user can record what it really took as either a single number or a three-point range (`actual_time_lower`, `actual_time_point`, `actual_time_upper`). [`blend_time_estimate`](../models.py) is applied identically, so forecast and actual are computed by the same formula and remain directly comparable. This is what makes the calibration loop work: the "I thought this would take 40 hours but it actually took 90" feedback is measured against the same blend the algorithm used in the first place.

# Monte Carlo Simulation

The blended estimate gives one number per node. That's enough for ranking, but not for answering questions like "if I commit to this Goal today, how long until I finish?" The Monte Carlo simulator in [`simulation.py`](../simulation.py) keeps the underlying PERT distribution intact, draws thousands of samples across the full prerequisite chain, and returns an empirical distribution over total time.

## PERT-Beta sampling

The blended estimate uses moments of the PERT family. The simulator samples directly from it. Given $(o, m, p)$ with $o < m < p$, draw $X \sim \text{Beta}(\alpha, \beta)$ on $[0, 1]$ with shape parameters

$$ \alpha = 1 + \lambda \cdot \frac{m - o}{p - o}, \qquad \beta = 1 + \lambda \cdot \frac{p - m}{p - o} $$

using $\lambda = 4$, then rescale to the user's actual range:

$$ T = o + (p - o) \cdot X $$

The result is a unimodal distribution on $[o, p]$ peaked near $m$, with mean closely tracking $\bar{t}_{\text{arith}}$ and standard deviation $\approx (p - o) / 6$. The choice $\lambda = 4$ is the conventional PERT weighting — it makes the mode equal exactly $m$ when $m$ is the midpoint of $[o, p]$, and keeps $\alpha, \beta \ge 1$ everywhere so the density stays unimodal and bounded strictly inside $[o, p]$. Other $\lambda$ values are mathematically valid but break one of those guarantees.

Degenerate inputs are caught the same way as in the deterministic blend:

| Input | Treatment |
|---|---|
| All three missing | Constant 1 hour per trial |
| Only $m$ | Sample from $(0.5m,\, m,\, 2m)$ — an approximated spread that preserves $m$ as the mode |
| Only $o, p$ | Set $m = \sqrt{o \cdot p}$ and sample normally |
| $p \le o$ | Degenerate range — return constant $\max(m, 0.1)$ |

## Chain collection

Before any sampling happens, the simulator BFS-walks backward from the target node along Hard edges, collecting every prerequisite. At the *root* node only (not deeper in the chain), Soft and Helps edges may also be followed, depending on the user's "include soft / include helps" toggles in the Time Simulation panel. This asymmetry is deliberate: the user's question is "how long until I finish *this* node, including its broader context," not "how long until I finish this node plus the soft prereqs of every node in its subtree" — which would explode the chain.

A few exclusions follow naturally:

- **Done nodes are dropped.** Their time is already paid; including them would inflate the estimate by work the user has already finished.
- **Containers contribute zero time.** A node with `time_mode='inherited'` (or a Goal with no time estimate set) is a structural conduit — its children are already in the chain and sample independently, so adding the container's own time would double-count. The code uses an explicit `is_container` check that handles both the explicit inherited mode and the legacy "Goal with all-zero time fields" heuristic.

## Serial summation

For $N = 10{,}000$ trials, draw one duration sample per remaining node and sum across the chain:

$$ T_{\text{total}}^{(i)} = \sum_{n \in R} T_n^{(i)}, \qquad i = 1, \ldots, N $$

where $R$ is the set of incomplete nodes collected above. The model assumes one person working one task at a time, so durations add sequentially regardless of dependency structure. The simulator does not attempt to model parallel work — a graph-coloring schedule would be wrong for the typical user and substantially more complex to compute.

The output is the empirical distribution of $T_{\text{total}}$. The Time Simulation panel summarizes it with the $P_{10}, P_{25}, P_{50}, P_{75}, P_{90}$ percentiles and renders it as a histogram with the three headline percentiles overlaid. The user can then say things like "I'm 90% confident this will take less than 200 hours" rather than offering a single fragile point estimate.

## Performance

Each trial is a single vectorized NumPy operation — `np.random.beta` over the entire trial-count vector at once, then a per-node array sum. There is no Python loop over trials. The full 10,000-trial simulation finishes in a few milliseconds on a typical graph, comfortably fast enough to re-run on every toggle change.

Trial count is configurable in the Settings tab (Time section). The default of 10,000 is large enough to stabilize the headline percentiles to within a fraction of a percent — bumping it higher buys negligible accuracy and costs proportionally more time.

## Where to go from here

- [`models.blend_time_estimate`](../models.py) is the canonical reference for the deterministic blend — every formula in the first half of this document maps to identifiable lines there.
- [`simulation.py`](../simulation.py) is the canonical reference for the Monte Carlo sampler, including the chain-collection BFS and the container exclusion logic.
- [`algorithms.md`](algorithms.md) — the Perceived Cost section explains where $t(n)$ plugs into the priority scoring formula.
- [`README.md`](../README.md) — the time-estimate guidance written for non-technical readers, including when to use one number vs. two vs. three.
