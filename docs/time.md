# Time

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

---

This document explains how Skill Tree turns the user's time estimate into a single number, $t(n)$. The user can give one, two, or three numbers. That estimate feeds node priority scoring, Goal ranking, and the project-duration simulation. It also drives every "expected time" the app shows.

# What is Special About Skill Tree's Time Estimation?

Most project-management tools estimate task duration with a plain arithmetic average. Skill Tree uses logarithmic and geometric methods instead. The choice rests on two foundations: cognitive psychology and probability theory.

## 1. Cognitive Scaling: The Weber-Fechner Law
Human perception of physical and abstract scales is fundamentally logarithmic, not linear. Under the **Weber-Fechner Law** of psychophysics, the perceived change in a stimulus is proportional to its *relative* change, not its *absolute* change.

In estimation terms, the cognitive leap from a **1-hour** task to a **2-hour** task feels identical to the leap from a **10-hour** task to a **20-hour** task, as both represent a doubling ($2\times$) of effort. However, a standard linear model treats the absolute difference of 10 hours in the second case as ten times more important than the 1-hour difference in the first. In reality, our mental planning brain operates on relative ratios rather than absolute sums. 

Because human uncertainty is naturally multiplicative, the arithmetic midpoint is a poor representation of our actual expectation.

## 2. Order-of-Magnitude Midpoints
The human brain is naturally better at estimating quantities across multiple orders of magnitude than it is at pinning down values within a single order of magnitude. For instance, it is far easier to state with 95% confidence that a task will take "no less than 10 hours and no more than 100 hours" than it is to confidently restrict that task to "between 30 and 60 hours." Because order-of-magnitude endpoints represent extreme limits, they activate our intuitive gut-check more reliably.

You might think that widening the endpoints so dramatically would lead to poor expected time estimates, and you would be right—but only if you use a standard arithmetic mean to derive the midpoint. Under traditional linear calculation, the arithmetic midpoint of a $10$-to-$100$ hour range is $(10 + 100) / 2 = 55$ hours. While $55$ splits the linear distance, it is conceptually warped: it is $5.5\times$ larger than the lower bound, yet only $1.8\times$ smaller than the upper bound, heavily skewing the estimate toward the worst-case scenario. In contrast, the **geometric midpoint** ($\sqrt{10 \cdot 100} \approx 31.6$ hours) splits the difference perfectly in ratio space, sitting exactly $3.16\times$ away from both endpoints.

As Sanjoy Mahajan argues in *The Art of Insight in Science and Engineering*, for the order-of-magnitude bracketing that humans naturally do, the geometric mean is the only mathematically consistent summary statistic.

## 3. The Log-Normal Reality of Tasks
In real-world project tracking, task durations are strictly bounded by zero on the left, but have an infinitely long tail on the right. Standard estimation models assume that project errors are **additive** (e.g., "each minor bug adds exactly 1 hour"), which would lead to a symmetric Normal distribution of task durations. In reality, project delays are **multiplicative** and compound exponentially (e.g., "waiting for key feedback multiplies the remaining task duration by $2\times$"). When independent factors multiply rather than add, the Central Limit Theorem dictates that the resulting durations follow a **Log-Normal distribution**.

Because task durations are log-normally distributed, their linear arithmetic means are highly volatile, easily dragged upward by rare, extreme worst-case scenarios. If used directly for scoring, these inflated averages would penalize risky but valuable tasks, delaying them indefinitely. In contrast, the geometric mean corresponds to the **median** of a log-normal distribution—the exact 50% probability threshold of completing the task. By using geometric and logarithmic methods, Skill Tree base-estimates tasks around this realistic median rather than letting a single tail-end outlier corrupt the entire priority ranking.

# Three Levels of Precision

The app accepts one, two, or three numbers from the user and produces a sensible $t(n)$ in each case. Each step up adds helpful information. 

| Input | Method | $t(n)$ |
|---|---|---|
| Only $m$ | Used directly | $t = m$ |
| $l$ and $u$ | Geometric mean | $t = \sqrt{l \cdot u}$ |
| All three | Blended PERT | A novel algorithm, discussed below |

If only $m$ is supplied, the app uses that point estimate without modification. The other two cases are discussed in detail below.

## Two Numbers

When the user supplies only two numbers $(l, u)$ representing their lower and upper bounds, the app uses the geometric mean:

$$ t(n) = \sqrt{l \cdot u} $$

Rather than linearly splitting the difference, this directly implements the logarithmic midpoint discussed in [The Case for Multiplicative Uncertainty](#the-case-for-multiplicative-uncertainty-why-geometric-means).

## Three Numbers

The three-point estimate $(l, m, u)$ — lower, expected, and upper — is the smallest input that captures both **expectation** and **uncertainty**. The user is encouraged (but not required) to supply all three, as it enables the most powerful time estimation method in the app. 

## PERT 

PERT, which stands for Program Evaluation and Review Technique, was developed by the US Navy in the late 1950s to manage massive defense programs where the exact durations of large projects were difficult to pin down, but any individual task could be reasonably bracketed by a best, typical, and worst case estimate. The classic PERT formulation produces a single estimate from these three values using the following formula: 

$$ t_e = \frac{l + 4m + u}{6} $$

Notice that this is a weighted arithmetic average where the expected value counts 4x as much as the endpoints. Under this assumption, project duration follows a **Beta Distribution**. 

**Picture of Beta Distribution w/ comments**

In Skill Tree, this classic formulation serves as the baseline, but because human time-estimation is inherently non-linear and suffers from multiplicative uncertainty, my transforms the traditional PERT formula into log space to counter act the innate biases in the human brain for estimating project durations.

## Geometric PERT

The logarithmic version uses the same $1{:}4{:}1$ weighting, but crucially, it is symmetric in multiplicative space, offering the same advantages that the geometric mean has over the arithmetic mean. 

$$ \bar{t}_{\text{log}} = \exp\!\left(\frac{\log l + 4 \log m + \log u}{6}\right) $$


## Blended PERT
Blended PERT is a weighted average of the original arithmetic mean and a new, logarithmically transformed version. The blend tilts between the arithmetic and logarithmic versions as a function of the **uncertainty ratio:** $r = u/l$. This simple ratio concisely represents the user's uncertainty about how long a project will take. A small $r$ means confident, tight estimates, and a large $r$ means deep uncertainty.

$$ w(r) = \begin{cases} 0 & \text{if } r \le 2 \\[4pt] \dfrac{\log r - \log 2}{\log 10 - \log 2} & \text{if } 2 < r < 10 \\[8pt] 1 & \text{if } r \ge 10 \end{cases} $$

The final estimate is the weighted average:

$$ t(n) = (1 - w(r)) \cdot \bar{t}_{\text{arith}} + w(r) \cdot \bar{t}_{\text{log}} $$

### The Statistical Bridge: Bounded Beta vs. Unbounded Log-Normal

A common dilemma in project management statistics is the choice of probability distribution:
1. **The Classical PERT Baseline (Beta)**: Traditionally, individual tasks are modeled using a **Beta distribution** mapped to the bounded interval $[l, u]$. This is computationally convenient and enforces hard physical constraints (a task cannot take less than $l$ hours or more than $u$ hours).
2. **The Real-World Delay Phenomenon (Log-Normal)**: Historically, compounding project delays are **multiplicative** (errors multiply rather than add), which naturally produces a right-skewed **Log-Normal distribution** on $[0, \infty)$. 

Skill Tree's Blended PERT elegantly reconciles these two models. By applying the $1:4:1$ PERT weighting in log-space to compute $\bar{t}_{\text{log}}$, the algorithm implicitly assumes that the *logarithm* of the task duration follows a Beta distribution. The resulting exponentiated variable follows a **Log-Beta distribution**. 

The Log-Beta distribution combines the mathematical strengths of both worlds: it enforces hard, realistic task boundaries $[l, u]$ while exhibiting the robust, multiplicative properties of a Log-Normal distribution. The confidence dial $w(r)$ acts as a regime selector, using the standard Beta model when uncertainty is low ($r \le 2$) and seamlessly shifting to the Log-Beta model when uncertainty compounds ($r \ge 10$).

### Motivation for the Blended Weighting

The choice to dynamically transition between the arithmetic and logarithmic PERT means based on $r$ is driven by a fundamental shift in how uncertainty behaves at different scales:

#### 1. Low Uncertainty ($r \le 2$): The Additive Regime
When your estimates are tight (e.g., $10$ to $20$ hours, or $40$ to $60$ hours), the uncertainty is **additive** and symmetric. You have a clear understanding of the scope, and the small variation is driven by minor, linear fluctuations. 
* **Why Arithmetic PERT?** The standard arithmetic PERT mean ($\bar{t}_{\text{arith}}$) is mathematically optimized for symmetric, near-normal distributions. If you are highly confident, using the logarithmic mean would unnecessarily drag the expected time $t(n)$ below your most likely estimate $m$. We trust the linear bounds and use $\bar{t}_{\text{arith}}$ directly ($w = 0$).

#### 2. High Uncertainty ($r \ge 10$): The Multiplicative Regime
When your estimates span an order of magnitude or more (e.g., $5$ to $100$ hours), the uncertainty becomes **multiplicative**. The massive upper bound $u$ represents a speculative "worst-case scenario" (black swans, unknown unknowns, or major blockers).
* **The Arithmetic Failure**: Under arithmetic PERT, a huge upper bound completely dominates the calculation. For example, if you estimate $(5, 20, 200)$, the arithmetic mean climbs to $47.5$ hours—more than double your most likely estimate of $20$. This heavily penalizes the task's priority score, delaying it indefinitely just because you added a cautious worst-case safety buffer.
* **Why Logarithmic PERT?** In log-space, the multiplicative tail is compressed. The logarithmic mean for $(5, 20, 200)$ is $\approx 22.9$ hours. It keeps the expected duration anchored near $m$ while still reflecting a slight upward pull from the uncertainty. This prevents a single overcautious, speculative "worst-case" guess from yanking the priority score of a task.
* **The Safety Net**: By shifting completely to $\bar{t}_{\text{log}}$ ($w = 1$), the algorithm rewards you for supplying a realistic upper bound, ensuring you aren't penalized for honesty about worst-case scenarios.

#### 3. The Transition ($2 < r < 10$): The Confidence Dial
The blend weight $w(r)$ acts as a "non-linearity dial" that smoothly shifts the model from an additive assumption (arithmetic) to a multiplicative assumption (logarithmic) as confidence degrades. 
* We interpolate **logarithmatically** because the uncertainty ratio $r$ itself is multiplicative. Successive *doublings* of uncertainty (e.g., moving from $r=2$ to $r=4$, and $r=5$ to $r=10$) represent equal steps in the degradation of confidence, and thus should receive equal shifts in the blending weight.

## Example - Comparing PERTs

The following table shows the blend in action with $m = 480$ hours (representing roughly three months of full-time work) held constant, sweeping the uncertainty ratio $r$ through doubling intervals $2, 4, 8, \text{and } 16$:

| $l$ | $m$ | $u$ | $r = u/l$ | $\bar{t}_{\text{arith}}$ | $\bar{t}_{\text{log}}$ | $w(r)$ | $t(n)$ |
|---|---|---|---|---|---|---|---|
| 360 | 480 | 720 | 2.00 | 500.00 | 489.52 | 0.00 | 500.00 |
| 240 | 480 | 960 | 4.00 | 520.00 | 480.00 | 0.43 | 502.77 |
| 180 | 480 | 1440 | 8.00 | 590.00 | 489.52 | 0.86 | 503.45 |
| 150 | 480 | 2400 | 16.00 | 745.00 | 517.07 | 1.00 | 517.07 |

Notice how the confident estimate in the first row returns $\bar{t}_{\text{arith}}$ unchanged, since $r \le 2$. But as uncertainty widens, the arithmetic mean climbs aggressively -- *too aggressively.* The last row's upper bound of $2400$ results in an arithmetic average of $745.00$ hours, even though your best guess is still $480$ hours. Conversely, the geometric mean compresses this tail, keeping the estimate anchored at a stable and sensible $517.07$ hours. This shows the power of the blending strategy: it correctly pulls the estimate above $m$ to account for uncertainty, but prevents it from skyrocketing due to a speculative worst-case scenario.

## The Reflection Feature

The app has a reflection feature that allows you to record how long a project actually took after you complete it. If you are a meticulous time tracker, you may have the definitive number, but if you aren't, you can use the same lower, expected, and upper bound strategy to record actual time. The uncertainty on these estimates tends to be lower, so blending isn't as necessary, but it is important to run these numbers through the same algorithm so the pre and post-project numbers are directly comparable. 

# Monte Carlo Simulation

The blended estimate gives one number per node. That's enough for ranking, but not for answering questions like "if I commit to this Goal today, how long until I finish?" The Monte Carlo simulator in [`simulation.py`](../simulation.py) keeps the underlying PERT distribution intact, drawing thousands of samples across the full prerequisite chain, and returns an empircal distribution for the project on the Details Tab. The panel presents the distribution as a histogram with the $P_{10}, P_{50}, P_{90}$ percentiles. This allows the user to say say "I'm 90% confident this will take less than 200 hours," rather than offering a single fragile point estimate.

## PERT-Beta Sampling

$X \sim \text{Beta}(\alpha, \beta)$ on $[0, 1]$ with shape parameters

$$ \alpha = 1 + \lambda \cdot \frac{m - l}{u - l}, \qquad \beta = 1 + \lambda \cdot \frac{u - m}{u - l} $$

using $\lambda = 4$, then rescale to the user's actual range:

$$ T = l + (u - l) \cdot X $$

The result is a unimodal distribution on $[l, u]$ with mode at exactly $m$, mean closely tracking $\bar{t}_{\text{arith}}$, and standard deviation $\approx (u - l) / 6$. The choice $\lambda = 4$ is the conventional PERT weighting — it keeps $\alpha, \beta \ge 1$ everywhere so the density stays unimodal and bounded strictly inside $[l, u]$, and it produces the classical $(l + 4m + u)/6$ as the mean. Other $\lambda$ values are mathematically valid but break one of those guarantees.

If the user does not supply all three time estimates, the simulation falls back to one of these two methods

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


# Other Resources

| Resource | What's there |
|---|---|
| [models.py](../models.py) | The module that implements `blend_time_estimate` — every formula in the first half of this document maps to identifiable lines there |
| [simulation.py](../simulation.py) | The module that implements the Monte Carlo sampler, including the chain-collection BFS and the container exclusion logic |

---

<table width="100%"><tr>
<td align="left"><a href="scoring.md">← Previous: Scoring</a></td>
<td align="right"><a href="modeling.md">Next: Modeling →</a></td>
</tr></table>
