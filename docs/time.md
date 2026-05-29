# Time

This document explains how Skill Tree turns the user's time estimate into a single number, $t(n)$. The user can give one, two, or three numbers. That estimate feeds node priority scoring, Goal ranking, and the project-duration simulation. It also drives every "expected time" the app shows.

# Why Time Estimates Live in Ratio Space

Most project-management tools collapse a time estimate into a plain arithmetic average. Skill Tree takes a different path. It works with durations in ratio space, using geometric and logarithmic methods rather than ordinary averages. The choice is not cosmetic. It changes which tasks rise to the top of the ranking, so it is worth explaining before the mechanics.

## Task Durations Are Multiplicative, Not Additive

Standard estimation imagines that errors add up. Each surprise tacks on a fixed amount: one more bug, one more hour. If that were true, task durations would cluster symmetrically around their expected value in a Normal Distribution.

Real delays do not add, they multiply. Waiting on feedback doesn't cost a flat hour; it stretches whatever work remains. A wrong assumption doesn't add a step; it doubles the remaining effort. Pile up enough of these independent multipliers and the durations spread into a **log-normal** shape: bounded by zero on the left, with a long tail running out to the right. The exact distribution is not the point. The asymmetry is. A task can run many times over, but it can never take less than no time at all.

This shape is why estimation should happen in ratio space. The brain already works there. It is far easier to say with confidence that a task will take "no less than 10 hours and no more than 100" than to pin it to "between 30 and 60." The wide, order-of-magnitude bracket activates a reliable gut-check. The narrow one demands a precision we don't have.

## The Typical Task Takes the Median Time

Widening the bracket so dramatically seems like it should ruin the estimate. It only does if you take the arithmetic mean.

The arithmetic midpoint of a 10-to-100 hour range is $(10 + 100) / 2 = 55$ hours. That number splits the linear distance, but it is warped in ratio terms. It sits $5.5\times$ above the lower bound and only $1.8\times$ below the upper one. It leans hard toward the worst case.

The geometric mean, $\sqrt{10 \cdot 100} \approx 31.6$ hours, splits the range evenly in ratio space. It is $3.16\times$ from each endpoint, favoring neither bound. On the log-normal shape those bounds imply, that same value is the **median**: the point with an even chance of being beaten. So it is both the neutral center of the bracket and the honest answer to "how long will this usually take." That is the number the app estimates around.

## Why the Median Matters for a Ranking Tool

Skill Tree ranks tasks. It does not schedule them. That changes which number is the right one to compute.

The arithmetic mean is hostage to that long right tail. A single rare worst case drags it upward, far past anything the task will usually cost. In a scheduler padding for safety, that caution has its place. In a ranking tool, it is a distortion. An inflated estimate buries a valuable task beneath cheaper ones and delays it indefinitely.

It also punishes honesty. A user who reports a fat but truthful worst case should not watch their task sink in priority for the admission. Computing around the median keeps the ranking incentive-compatible: the realistic cost drives the score, and an honest tail does not tank it. The median is also the more actionable planning number, the duration to expect rather than to fear.

## The Median Is Recovered, Not Estimated

There is a fair objection lurking here. You cannot estimate a median directly. Nobody can. A reader who has followed this far might ask how the app expects a number no one knows how to name.

It doesn't. What a person can do is bracket a task: a plausible low, a plausible high, and maybe a most-likely value between them. Skill Tree asks only for those. The median is never supplied by the user. It is recovered by the math. For the log-normal distribution a low and high imply, the geometric mean $\sqrt{l \cdot u}$ lands on the median, so the typical-case duration falls out of the only numbers the user ever had to give.

This is also why the app elicits in ratio space. The same instinct that makes an order-of-magnitude bracket easy to state is the one the math relies on. The user thinks in ratios, the computation works in ratios, and the two stay coherent. Nobody is asked for a number their intuition cannot produce.

## When Uncertainty Is Low, Linear Is Fine

None of this means the arithmetic mean is wrong. It means it breaks down as uncertainty grows.

When the bracket is narrow, multiplicative and additive views nearly agree, and the arithmetic mean is a perfectly good summary. The geometric machinery only earns its keep when the spread is wide and the tail starts to matter. This is the tension the app resolves by *blending* the two: it leans linear when uncertainty is low and shifts toward geometric as it rises. Blended PERT, described below, is how that shift is made.

# Three Levels of Precision

The app accepts one, two, or three numbers from the user and produces a sensible $t(n)$ from each. Every number you add sharpens the estimate.

| Input | Method | $t(n)$ |
|---|---|---|
| Only $m$ | Used directly | $t = m$ |
| $l$ and $u$ | Geometric mean | $t = \sqrt{l \cdot u}$ |
| All three | Blended PERT | A principled blend, discussed below |

With a single number, the app takes it at face value: $t = m$. The two- and three-number cases each deserve a closer look.

## Two Numbers

When the user supplies a low and a high, $(l, u)$, the app takes their geometric mean:

$$ t(n) = \sqrt{l \cdot u} $$

This is the logarithmic midpoint from [The Typical Task Takes the Median Time](#the-typical-task-takes-the-median-time). It sits the same ratio away from each bound rather than the same distance, splitting the bracket where the typical case actually falls.

## Three Numbers

The three-point estimate $(l, m, u)$ — low, expected, and high — is the smallest input that captures both expectation and uncertainty. Supplying all three is optional but encouraged. It unlocks the app's most capable estimator, Blended PERT.

# PERT

PERT stands for Program Evaluation and Review Technique. The US Navy developed it in the late 1950s to manage massive defense programs. Exact durations were impossible to pin down, but any single task could be bracketed by a best, typical, and worst case. From those three numbers, classic PERT produces one estimate:

$$ t_e = \frac{l + 4m + u}{6} $$

This is a weighted arithmetic average. The expected value $m$ counts four times as much as either endpoint. The classic technique models the task's duration as a **Beta distribution** on the interval $[l, u]$.

In Skill Tree, this formula is only the baseline. Human time-estimation is non-linear and dogged by multiplicative uncertainty. To counter that bias, Skill Tree recomputes the same PERT weighting in log space.

## Geometric PERT

The logarithmic version keeps the same $1{:}4{:}1$ weighting. The difference is that it is symmetric in multiplicative space. It carries the same advantage over arithmetic PERT that the geometric mean carries over the arithmetic mean.

$$ \bar{t}_{\text{log}} = \exp\!\left(\frac{\log l + 4 \log m + \log u}{6}\right) $$

## Blended PERT

Blended PERT is a weighted average of the two: the arithmetic PERT mean and its logarithmic counterpart. The blend tilts between them according to the **uncertainty ratio** $r = u/l$. This ratio is a compact measure of how unsure the user is. A small $r$ means tight, confident estimates. A large $r$ means deep uncertainty.

$$ w(r) = \begin{cases} 0 & \text{if } r \le 2 \\[4pt] \dfrac{\log r - \log 2}{\log 10 - \log 2} & \text{if } 2 < r < 10 \\[8pt] 1 & \text{if } r \ge 10 \end{cases} $$

The final estimate is the weighted average:

$$ t(n) = (1 - w(r)) \cdot \bar{t}_{\text{arith}} + w(r) \cdot \bar{t}_{\text{log}} $$

## The Statistical Bridge: Beta and Log-Normal

Project-management statistics offers two natural models for a task's duration, and they pull in opposite directions.

The classical PERT baseline uses a **Beta distribution** on the bounded interval $[l, u]$. It is convenient to work with, and it enforces a hard constraint: the task cannot take less than $l$ or more than $u$.

The real-world view is the **log-normal distribution** on $[0, \infty)$. Delays compound multiplicatively, which skews durations to the right and leaves an open-ended tail.

Blended PERT bridges the two. Computing $\bar{t}_{\text{log}}$ applies the $1{:}4{:}1$ weighting in log space, which is the same as assuming the *logarithm* of the duration follows a Beta distribution. Exponentiating that gives a **Log-Beta distribution**: bounded like the Beta, right-skewed like the log-normal. The weight $w(r)$ chooses between the regimes, holding to the plain Beta model when uncertainty is low and sliding toward Log-Beta as it grows.

## Why the Weight Shifts With Uncertainty

The transition between the arithmetic and logarithmic means tracks a real shift in how uncertainty behaves as the bracket widens.

When estimates are tight — say 10 to 20 hours, or 40 to 60 — the uncertainty is roughly additive and symmetric. The scope is clear, and the variation is minor, linear noise. Here the arithmetic mean is the right tool. It suits symmetric, near-normal spreads, and switching to the logarithmic mean would only drag $t(n)$ below the most likely value $m$ for no reason. So the app trusts the bounds and uses $\bar{t}_{\text{arith}}$ directly ($w = 0$).

When estimates span an order of magnitude — say 5 to 100 hours — the uncertainty turns multiplicative. The large upper bound is speculative: blockers, unknowns, the occasional disaster. Now the arithmetic mean breaks down, because a single big $u$ dominates it. Estimate $(5, 20, 200)$ and the arithmetic mean climbs to 47.5 hours, more than double the most likely 20. That inflated number would sink the task's priority and delay it indefinitely, purely as punishment for naming a cautious worst case. The logarithmic mean compresses that tail. For the same $(5, 20, 200)$ it returns about 22.9 hours: anchored near $m$, nudged up slightly for the uncertainty, but not hijacked by it. Shifting fully to $\bar{t}_{\text{log}}$ ($w = 1$) rewards an honest upper bound instead of penalizing it.

Between these regimes, $w(r)$ slides smoothly from one to the other as confidence degrades. The interpolation runs in log space because $r$ is itself multiplicative. Each doubling of the ratio — $r = 2$ to $4$, then $4$ to $8$ — is an equal step in lost confidence, so each should move the weight equally.

## Example - Comparing PERTs

The table below holds the most likely estimate fixed at $m = 480$ hours, roughly three months of full-time work. It sweeps the uncertainty ratio $r$ through successive doublings: $2, 4, 8, 16$.

| $l$ | $m$ | $u$ | $r = u/l$ | $\bar{t}_{\text{arith}}$ | $\bar{t}_{\text{log}}$ | $w(r)$ | $t(n)$ |
|---|---|---|---|---|---|---|---|
| 360 | 480 | 720 | 2.00 | 500.00 | 489.52 | 0.00 | 500.00 |
| 240 | 480 | 960 | 4.00 | 520.00 | 480.00 | 0.43 | 502.77 |
| 180 | 480 | 1440 | 8.00 | 590.00 | 489.52 | 0.86 | 503.45 |
| 150 | 480 | 2400 | 16.00 | 745.00 | 517.07 | 1.00 | 517.07 |

The first row is the confident estimate. Its ratio is $r \le 2$, so the blend returns $\bar{t}_{\text{arith}}$ unchanged. As the bracket widens, the arithmetic mean climbs fast — too fast. By the last row, an upper bound of 2400 hours pushes the arithmetic average to 745 hours, even though the best guess is still 480. The logarithmic mean holds the tail in check, settling at a stable 517 hours instead. That is the blend working as intended: it lifts the estimate above $m$ to acknowledge the uncertainty, without letting one speculative worst case send it skyward.

## The Reflection Feature

After you finish a project, the reflection feature lets you record how long it actually took. A meticulous time tracker will have the exact number. If you don't, you can record the actual time the same way you estimated it, with a low, expected, and high bound. Real durations are usually less uncertain than forecasts, so the blend matters less here. Still, the actual time runs through the same algorithm, so the before-and-after numbers stay directly comparable.

# Monte Carlo Simulation

The blended estimate gives one number per node. That is enough to rank tasks, but not enough to answer a question like "if I commit to this Goal today, how long until I finish?" The Monte Carlo simulator in [`simulation.py`](../simulation.py) answers it. It keeps the underlying PERT distribution intact and draws thousands of samples across the full prerequisite chain. The result is an empirical distribution for the whole project, shown on the Details Tab. The panel plots it as a histogram marked with the $P_{10}, P_{50}, P_{90}$ percentiles. Now the user can say "I'm 90% confident this will take less than 200 hours," instead of trusting a single fragile point estimate.

## PERT-Beta Sampling

Each node's duration is sampled from a PERT-Beta distribution. Draw $X \sim \text{Beta}(\alpha, \beta)$ on $[0, 1]$ with shape parameters

$$ \alpha = 1 + \lambda \cdot \frac{m - l}{u - l}, \qquad \beta = 1 + \lambda \cdot \frac{u - m}{u - l} $$

using $\lambda = 4$, then rescale to the user's actual range:

$$ T = l + (u - l) \cdot X $$

The result is a unimodal distribution on $[l, u]$. Its mode sits exactly at $m$, its mean closely tracks $\bar{t}_{\text{arith}}$, and its standard deviation is $\approx (u - l) / 6$. The choice $\lambda = 4$ is the conventional PERT weighting. It keeps $\alpha, \beta \ge 1$ everywhere, so the density stays unimodal and strictly inside $[l, u]$, and it reproduces the classical $(l + 4m + u)/6$ as the mean. Other values of $\lambda$ are valid but break one of those guarantees.

If the user does not supply all three time estimates, the simulation falls back to one of two methods:

| Input | Treatment |
|---|---|
| Only $m$ | Sample from $(0.5m,\, m,\, 2m)$ — an approximated spread that preserves $m$ as the mode |
| Only $l, u$ | Set $m = \sqrt{l \cdot u}$ and sample normally |


## Chain Collection

Before sampling begins, the simulator BFS-walks backward from the target node along Hard edges, collecting every prerequisite. At the *root* node only (not deeper in the chain), Soft and Helps edges may also be followed, depending on the user's "include soft / include helps" toggles on the Details Tab. This asymmetry is deliberate: the user's question is "how long until I finish *this* node, including its broader context," not "how long until I finish this node plus the soft prereqs of every node in its subtree" — which would explode the chain.

Two exclusions follow naturally to prevent inflating the simulation results. First, completed tasks are dropped because their time has already been paid; including done nodes would distort the remaining time estimate. Second, container nodes contribute zero duration. Because these containers act as structural conduits, their child tasks are already added to the chain and sampled independently.

## Serial Summation

For $N = 10{,}000$ trials, draw one duration sample per remaining node and sum across the chain:

$$ T_{\text{total}}^{(i)} = \sum_{n \in R} T_n^{(i)}, \qquad i = 1, \ldots, N $$

where $R$ is the set of incomplete, non-container nodes collected above. The model assumes one person working one task at a time, so durations add sequentially regardless of dependency structure. The simulator does not attempt to model parallel work — a graph-coloring schedule would be wrong for the typical user and substantially more complex to compute.

## What's Not Modeled

A few omissions are worth flagging, since they bound how the simulator's output should be read:

- **Parallel work.** As above, durations sum serially. A user who actually runs two independent subtrees in parallel will finish faster than the simulator predicts.
- **Correlation between tasks.** Each node samples independently. In reality, a user who's underestimating one task is often underestimating its neighbors too — independent sampling smooths over that correlation, so the headline percentiles end up slightly tighter than perfectly-correlated worst cases would imply.
- **Calendar time.** The simulator outputs total *work* hours. Translating that into "weeks until done" depends on how many hours per week the user actually puts in, which is a separate Settings field used elsewhere but not applied here.

Each of these would be tractable to add, but each would require more input from the user without dramatically changing the answer for the typical use case.

# Navigation
## Tutorial
Each cell is clickable.
```mermaid
flowchart LR
    R(["README"]) --> F(["Features"]) --> S(["Scoring"]) --> T(["Time"]) --> M(["Modeling"])
    classDef current fill:#ffd966,stroke:#b58900,stroke-width:2px,color:#000;
    classDef other fill:#2b2b2b,stroke:#555,color:#bbb;
    class T current
    class R,F,S,M other
    click R "../README.md"
    click F "features.md"
    click S "scoring.md"
    click M "modeling.md"
```

## Other Resources

| Resource | What's there |
|---|---|
| [models.py](../models.py) | The module that implements `blend_time_estimate` — every formula in the first half of this document maps to identifiable lines there |
| [simulation.py](../simulation.py) | The module that implements the Monte Carlo sampler, including the chain-collection BFS and the container exclusion logic |
