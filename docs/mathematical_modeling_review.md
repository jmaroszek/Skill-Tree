# Mathematical modeling review and proposed fixes

Reviewed on **2026-10-13**, against commit **`a8acfcc`** (`Refine relationship lists and time estimate editing`). This report records the findings and suggestions from the mathematical review. This review describes the implementation at that commit. **Update, 2026-10-14:** the unified synergy proposal has been accepted for implementation. The project/step architecture is deferred: the user primarily models strategic projects and accepts decomposition sensitivity to preserve simplicity. Other proposals remain deferred. Numerical examples use synthetic graphs and shipped profile defaults; they are not measurements of the user's production graph.

The main concern is that graph representation can influence priority independently of the work or benefit represented. Synergy adds a second source of distortion by repeatedly crediting shared downstream benefits and switching between incompatible unfinished and completed formulas. These deserve attention before recalibrating duration uncertainty.

The user's confirmed decision is to **keep Goal ranking as the average quality of the remaining work**. The project/step design below remains a deferred proposal. The replacement synergy function has subsequently been approved, including its tradeoffs.

| Issue | Priority | Recommended direction |
|---|---|---|
| 1. Decomposition and redundant-edge sensitivity | Highest | Establish stable units of scored work; normalize redundant Hard routes without changing dependencies |
| 3. Synergy inflation and completion discontinuity | Highest | Replace copied partner cascades with bounded reinforcement of the candidate's value |
| 2. Entered versus simulated duration percentiles | Next | Clarify input modes and expose fitted percentiles while retaining the estimator |
| 4. Uncalibrated shared duration uncertainty | Deferred | Retain the current correlation setting until suitable outcome evidence exists |
| 5. Editable forecasts undermine accuracy history | Minor | Use a behavioral rule, or lock forecast estimates while a node is Done |

**The existing model has useful foundations to preserve.** Intrinsic value is a preference transform, `IV(n) = w_v * V(n)^gamma + w_i * I(n)^gamma`. Perceived cost is `C(n) = 1 + w_e * difficulty(n) + w_t * (t(n) / 40)^beta`. The resulting ratio is a prioritization score in preference units, not a calibrated measure of objective utility or literal financial ROI. The fixed 40-hour reference prevents changes elsewhere in the graph from silently rescaling every time cost. See [scoring.py](../scoring.py) and [profile defaults in config.py](../config.py).

Ordinary Hard/Soft value flow uses the strongest route to each beneficiary. Future benefits are discounted by unique unfinished required work, using `q(R) = 1 / (1 + (R / H)^delta)` when `H > 0`; `H = 0` disables that discount. Milestones carry no own work or value and act as free intermediate hops. These are coherent design choices. Hard eligibility, Goal status exceptions, and the distinction between Hard, Soft, and Helps must survive any scoring change.

The Goal ranker sums the worth of unfinished own-work tasks in a unique Hard subtree and divides by their summed perceived costs. This is a **cost-weighted average of task quality**. Blocked required work belongs in that average. Adding work with the same value-to-cost ratio should leave the average unchanged. Goal priority, context weight, and Goal density are subsequent adjustments. See [goal_ranking.py](../goal_ranking.py) and [the scoring guide](scoring.md).

**1. Splitting work can improve its rank without improving the underlying opportunity.** Flattening Goal credit across a Hard subtree already makes a chain and a fan of the same tasks comparable. It does not make one task equivalent to several newly created tasks representing the same work.

Each unfinished task receives credit for the Goals it supports, while each task also gets its own nonlinear cost calculation. Splitting a task repeats Goal credit and changes the denominator. Copying intrinsic ratings onto the parts can amplify the effect further.

For a Sage Goal with Value 10 and Interest 10, intrinsic value is 200 and each task receives 120 of Goal credit. Give the work inherited ratings, no intrinsic value, and 80 total hours. The current inherited-rating rule also sets its difficulty cost to zero. With all Goal-level multipliers held at one:

| Representation of the same 80 hours | Total credited value | Total perceived cost | Raw Goal score |
|---|---:|---:|---:|
| One 80-hour task | 120 | 10.0943 | 11.8879 |
| Two 40-hour tasks | 240 | 14.0000 | 17.1429 |
| Eight 10-hour tasks | 960 | 28.8932 | 33.2258 |

The score rises about 44% with two pieces and 180% with eight. There is no additional benefit in this example. The issue is reproduced through `_goal_work`, rather than inferred solely from the formulas.

A separate representation effect appears in ordinary prerequisite routes. Suppose `A -> B -> C` are Hard edges under Sage. The route from A to C has weight `0.6^2 = 0.36`. Adding the transitively redundant Hard edge `A -> C` raises that weight to `0.6`, even though the required order is already expressed. In a probe with 40 hours per node, A rated 5/5 with Difficulty 5, B using inherited ratings, and C rated 10/10, A's base score rose from **7.6290 to 10.4162**. C's remaining-work discount did not change. See `_strongest_routes` and `_credited_routes` in [scoring.py](../scoring.py).

The recommended decomposition fix is an **explicit distinction between a scored project and its bookkeeping steps**. A project remains an existing Learn, Action, or Resource; this does not require a sixth node type or repurposing Goal. It carries one set of benefit ratings, one difficulty estimate, one cost calculation, and its external relationships. Its steps divide that same work without creating additional benefit or additional independent recommendations. A step that has a useful outcome of its own can instead be promoted to an independent scored project.

The Goal calculation would remain `sum(project worth) / sum(project perceived cost)`, with each project counted once in a Goal's Hard closure. An 80-hour project represented by one, two, or eight bookkeeping steps would therefore retain the 11.8879 score in the example above. Adding another independent project of the same quality would also preserve the average. This retains the chosen meaning of Goal ranking and the existing cost curve.

This is a meaningful feature and data-model change. The graph does not currently contain enough information to infer which nodes are independent benefits and which are bookkeeping fragments. Existing nodes should remain separate scored projects by default; consolidation should be explicit. Until that distinction exists, the practical mitigation is to keep nodes at a consistent project scale and use checklists for small steps, as [the modeling guide](modeling.md) already recommends.

The project/step design needs the following integration rules:

- Home should present a startable step associated with its project's merit. Several available steps must not occupy several recommendation slots or incur several variety penalties for one project. Context and Goal boosts apply once at the project level.
- Step completion and blocking remain meaningful. A project with no startable step cannot become actionable merely because its score is high. Project completion must have an explicit rule; the existing user-controlled completion of Goals remains intact.
- Pure bookkeeping steps must not acquire independent external value or dependency relationships. Such a relationship needs an explicit project-level interpretation or promotion of the step to an independent project. Grouping must preserve prerequisite order and avoid cycles in the projected graph.
- Remaining hours, Goal averages, and future-work discounts must use the same project membership and count each piece of work once. Completing work can legitimately change a score; simply changing its representation should not.
- Explain and Focus must show how the recommended step relates to the scored project and the real prerequisite paths. New membership, status, and estimate changes must invalidate every affected score and simulation cache.
- Splitting a project must preserve its forecast distribution. For a pure partition, allocate a single project-duration draw among steps with shares summing to one. Sampling newly created steps separately would change uncertainty despite unchanged work. In a two-way split of a typical 20/40/80 bracket at correlation 0.4, ordinary separate sampling reduces the total standard deviation to about **82.6%** of the original. Partitioning the same draw preserves it exactly. Conditioning on actual progress is a separate forecasting decision.

For redundant Hard edges, the proposed scoring view should use a canonical effective ordering while preserving the user's stored graph and its status rules. A transitive reduction is a candidate for ordinary Hard DAGs. It must not indiscriminately remove Goal membership links, treat Soft links as redundant Hard links, or traverse Goal status exceptions as if Goals were ordinary enforced prerequisites. Done-node barriers and Milestone transparency also need explicit treatment. The ordinary-DAG prototype passed; these application-specific cases are unresolved integration work.

Merely dividing Goal credit by the number of children would change the average-quality contract, and it would not remove nonlinear cost effects. Applying the cost curve to all hours under a Goal would introduce a new preference for Goal size. Neither is a complete repair under the chosen semantics.

One adjacent coupling should remain visible during this work: **an own-work node with inherited ratings currently loses its difficulty cost too**. In a 40-hour Sage probe, Difficulty 1 and Difficulty 10 both produced cost 7 when ratings were inherited. A possible later cleanup would tie effort exemption to having no own work, but that would change existing rankings and should be evaluated separately. The decomposition example above deliberately retains the current rule.

**3. Synergy can repeatedly credit the same benefit, and finishing a partner can reduce the boost.** The current unfinished-partner bonus starts a separate value channel at each direct Helps partner. Each channel deduplicates its own DAG paths, but contributions to the same beneficiary are then added across channels. Helps does not chain through another Helps edge, yet a hub can still import the same downstream benefit through many partners. See `_value_contributions` in [scoring.py](../scoring.py).

In a Creator probe, A and ten potential partners each had 40 hours and ratings 5/5. The partners were in another context, and each was a Hard prerequisite of the same 40-hour, 10/10 beneficiary D. Keeping all those Hard dependencies fixed, varying only how many partners had a Helps edge to A produced:

| Helps partners connected to A | Combined route weight for D | D's contribution to A |
|---|---:|---:|
| 1 | 0.99 | 130.09 |
| 3 | 2.97 | 390.27 |
| 10 | 9.90 | 1,300.88 |

D has intrinsic value 200. Its repeated contribution is the mechanism of inflation; the large number is not ten independent outcomes. The remaining-work discount was held constant across these cases.

Completion uses a different formula: `IV(A) * d_Syn_mul * sqrt(done partner count)`. This has diminishing marginal growth, but **no finite upper bound**. It also applies only to A's intrinsic value, whereas the unfinished bonus imports partner DAG value and applies a cross-context multiplier.

For two otherwise isolated 40-hour nodes, each rated 5/5 with Difficulty 5 and connected across contexts, Creator gives the candidate total value **130.0824 before its partner is Done and 115.0000 afterward**. With cost unchanged, its base score falls from 8.9712 to 7.9310. Sage gives 54.4490 then 70.0000 in the same setup, so the failure depends on the profile and graph. The isolated Creator example separates this discontinuity from legitimate loss of already-realized downstream value.

The proposed replacement is **bounded reinforcement of the candidate's own synergy-free value**, without copying partner DAGs. A concrete candidate tested during the review is:

```text
B = candidate's DAG value without any Helps contribution
M = (w_v + w_i) * 10^gamma
A = min(max(B, 0), M)

s = completed-partner strength, s >= 0
eta = unfinished-partner anticipation fraction, 0 <= eta <= 1
c_j = cross-context coefficient for partner j, otherwise 1

a_j = 1                                      if partner j is Done
      (1 - (1 - eta)^c_j) * q(R_j)            otherwise

x_j = a_j / (2 - a_j)
X = sum(x_j over distinct direct partners)
synergy_bonus = s * A * 2X / (1 + X)
total_value = B + synergy_bonus
```

Here `R_j` is the partner's unique unfinished Hard workload excluding the candidate's own work, using the same completion-work convention as the DAG calculation. Cross-context coefficients must be valid and nonnegative; an implementation should handle a zero coefficient explicitly. `B` is measured before cost, Goal boosts, context weights, and recommendation variety. The value cap `M` is the profile's maximum intrinsic value, so scaling both value weights scales the cap and bonus consistently.

This construction provides specific properties:

- With one Done partner, the bonus is `s * A`; with two it is `4s * A / 3`. Even arbitrarily many partners cannot push it above `2s * A`.
- Adding a partner cannot reduce the bonus when the candidate base and other inputs are held fixed.
- An unfinished partner has exposure at most one. Marking that partner Done cannot reduce its exposure. A cross-context coefficient above one raises anticipation toward the completed level without exceeding it.
- A shared downstream beneficiary is not copied once per partner. The calculation is nonrecursive and uses direct Helps relationships only.
- A candidate with inherited ratings can still receive reinforcement when its ordinary DAG value is positive. A candidate with zero base value receives none.

For the shipped profiles, an initial mapping is `s = d_Syn_mul` and `eta = d_Syn_pair / d_Syn_mul`. All six shipped profiles have a valid ratio. This reproduces the Sage isolated-pair example. Under Creator, the candidate's proposed total becomes **98.8076 before completion and 115.0000 afterward**, removing the isolated completion drop by reducing excessive anticipation.

These parameters need versioned meanings and explicit handling of custom settings. A custom configuration with a zero completed strength and a positive pair strength cannot be faithfully mapped by that ratio. Silently clamping arbitrary existing settings would conceal a model change.

There are intentional tradeoffs. Dense hubs receive less credit. Partner-specific intrinsic value no longer directly determines the candidate's bonus. Completed reinforcement uses the candidate's capped DAG value, which changes the current intrinsic-only rule. The cap and saturation shape are defensible preference choices, not empirically fitted constants. Profile behavior, especially Creator and Explorer, must be reviewed after the change.

The monotonicity claim has a precise limit: it holds with the candidate's base `B` fixed. If a partner is also a Hard/Soft beneficiary, completing it can legitimately remove unearned DAG value from `B`. Total priority need not rise in that case. Explain should separate this loss of future benefit from the change in synergy. Goal averages should continue to exclude ordinary downstream cascades and Helps unless a separate change to their meaning is agreed.

**2. The duration model does not generally reproduce the percentiles requested by the editor.** The bracket tooltips present Lower, Expected, and Upper as P10, P50, and P90. The sampler preserves `Node.time` as its theoretical mean and the upper-to-lower ratio as its lognormal spread. It cannot generally honor all the entered quantile locations at the same time. See [models.py](../models.py), [simulation.py](../simulation.py), and [duration_ui.py](../duration_ui.py).

For a nondegenerate three-point bracket:

```text
t = 0.3 * lower + 0.4 * middle + 0.3 * upper
sigma = log(upper / lower) / (2 * 1.2815515655446004)
mu = log(t) - sigma^2 / 2
fitted quantile at probability p = exp(mu + sigma * Phi_inverse(p))
```

Analytic fitted values, without Monte Carlo sampling error:

| Entered Lower / Expected / Upper, hours | Mean used | Fitted P10 / P50 / P90, hours | Model chance of exceeding entered Upper |
|---|---:|---|---:|
| 20 / 40 / 80 | 46 | 19.87 / 39.74 / 79.48 | 9.79% |
| 10 / 90 / 100 | 69 | 14.57 / 46.09 / 145.75 | 19.43% |

The second bracket is valid under current editor ordering rules, but its modeled median is about half the entered middle. Even a geometrically symmetric bracket can shift slightly because the weighted mean is an approximation. With only Expected entered, the app instead treats that value as the mean and imputes a spread; the same 50/50 tooltip is therefore misleading for that input mode.

The recommended near-term repair is transparency while preserving one consistent mean throughout the system:

- Distinguish a single mean estimate from a percentile bracket in labels and guidance. Explain that the two-bound mode supplies a geometric middle before calculating the mean.
- Calculate fitted quantiles analytically from the same parameters used by the sampler. Keep ordinary cases quiet; expose entered versus fitted values when the deviation is material. A 10% relative-deviation threshold is a candidate presentation rule, not a statistical confidence test.
- Label chart probabilities as outputs of the fitted model. Explain the imputed spread for a mean-only estimate and the fact that Upper is not a hard maximum.
- Preserve stored estimates and `Node.time`; use the shared estimator in ranking, totals, simulation, and actual-time summaries. Avoid a UI repair that silently changes scores.

This repairs the misleading interpretation; it does **not** make arbitrary three-point brackets fit exactly. An exact-fit model would need more flexible distribution and tail assumptions, and a decision about whether its mean replaces the existing scoring mean. That would be a separate modeling change. Fitted-quantile diagnostics and a correlation-sensitivity display were not present in the reviewed implementation.

Swanson's rule remains a reasonable provisional approximation for modest skew. The cited research studies its use for hydrocarbon reserve estimates; it does not calibrate this user's task durations. Its approximation should not be presented as a distribution-independent identity. See [Hurst, Brown, and Swanson (2000)](https://archives.datapages.com/data/bulletns/2000/12dec/1883/1883.htm) and [the app's duration guide](time.md).

**4. Shared uncertainty materially changes long-project forecasts, but there is insufficient evidence to replace the setting.** The simulator combines a common normal factor and a task-specific normal factor, with default correlation 0.4. This is correlation in log-duration, not directly correlation between duration hours. It preserves every marginal distribution and its theoretical mean. The setting is explicitly provisional in [config.py](../config.py).

A 100,000-trial probe of 30 identical 20/40/80-hour tasks produced the following serial work-hour totals. The theoretical mean is 1,380 hours for every row; small observed mean differences are sampling error.

| Log-duration correlation | Simulated P10 | Simulated P50 | Simulated P90 |
|---|---:|---:|---:|
| 0 | 1,197.6 | 1,372.3 | 1,573.2 |
| 0.4 | 825.9 | 1,300.5 | 2,039.2 |
| 1 | 594.0 | 1,195.7 | 2,384.9 |

Retain **0.4** for now, as requested. Zero would assume independent estimation errors and can make large totals implausibly precise. A replacement needs trustworthy original forecasts, actual outcomes, and enough related projects to distinguish shared error from individual variation. More simulation trials improve numerical precision; they do not establish the right correlation. These forecasts sum work hours and do not model calendar scheduling or parallel execution.

**5. Editing a completed node's estimate can rewrite apparent estimation accuracy.** `_compute_estimation_accuracy` compares captured actual time with the node's current `Node.time`. Lifecycle events record transitions and recommendation ranks, but do not freeze the forecast. An estimate of 100 hours against an actual 200 hours becomes apparently perfect if the estimate is later edited to 200. See [graph_analytics.py](../graph_analytics.py) and [the lifecycle schema in database.py](../database.py).

The immediate behavioral solution is to leave forecasts alone when completing work and enter the actual duration separately. A small product option is to make forecast fields read-only while the node is Done, retaining editable actuals and allowing deliberate forecast revision after reopening. Here, **fixing an estimate means freezing it**, not replacing it with the actual duration. Enforcement should cover write paths as well as the editor if it is intended as a data guarantee.

This does not recover an estimate revised before completion, and reopening can still change the historical baseline. That limitation is acceptable for the requested minor scope. Immutable forecast snapshots and per-cycle calibration history can wait; present-day accuracy summaries should not be treated as rigorous calibration data in the meantime.

**Implementation should proceed through explicit acceptance properties.** Implement the accepted synergy function using existing strategic project nodes as the scored units; the deferred project/step architecture is not a prerequisite. Independent projects should remain distinguishable from bookkeeping partitions in both systems. Then address the percentile presentation problem. Keep correlation calibration and comprehensive forecast history deferred.

| Area | Required acceptance property before activation |
|---|---|
| Goal meaning | Adding independent work with the same value-to-cost ratio preserves the raw average |
| Decomposition | A pure split preserves project merit, raw Goal score, total workload, and the full forecast distribution |
| Recommendation variety | Multiple steps of one project do not multiply candidate slots or variety counts |
| Dependencies | Raw Hard eligibility and user-controlled Goal status remain correct; Soft and Helps retain distinct meanings |
| Graph transformations | Redundant ordinary Hard edges and inserted Milestones do not manufacture value; Goal and Done exceptions have explicit regression cases |
| Synergy | Fixed-base bonuses are bounded, nondecreasing with added partners, and nondecreasing when a partner becomes Done |
| Overlap | Shared beneficiaries and mixed Hard/Soft/Helps pairs have no accidental duplicate credit |
| Explain and Focus | Displayed components sum to the score and identify the relationships actually credited |
| State and persistence | Edits, completion, reopening, grouping, import/export, and settings migration refresh every affected result |
| Duration | Ranking and simulation share the same theoretical mean; fit diagnostics match the actual sampler |
| Profiles and performance | All six profiles and custom settings behave intentionally; representative graphs remain responsive |

Use an isolated graph copy to compare current and proposed rankings before activation. Explain large movements in terms of the corrected mechanism, especially for inherited-rating work and dense synergy hubs. Agreement with the old ranking is not itself the success criterion, because correcting the findings intentionally changes some ranks. Preserve recoverable settings and data before any membership migration. Update [modeling.md](modeling.md), [scoring.md](scoring.md), [time.md](time.md), and the relevant [AGENTS.md](../AGENTS.md) semantics when implementation changes behavior.

**Validation so far supports the findings and selected mathematical properties, not complete integration safety.** Earlier in this review, the focused scoring, Goal ranking, simulation, calibration, suggestion, and priority-Goal tests passed: **485 passed in 14.47 seconds**. This used the `skill-tree` environment, an isolated `SKILLTREE_HOME`, temporary test databases, and excluded the two differential tests that read real sandbox/production databases. It was not the full repository suite or a browser test.

Exploratory probes also checked the proposed synergy function on **6,000 generated cases across all six profiles**, with assertions for boundedness, added-partner monotonicity, completion monotonicity at fixed base, and common value-weight scaling. Those checks passed. Ordinary Hard-DAG normalization was checked on **1,000 generated DAGs** with redundant reachability edges added; the reduced edge sets agreed. Partitioning a project-duration draw into random shares preserved totals to floating-point precision, with a largest observed error of about `2.84e-14` hours.

Those proposal probes were run in memory and are not yet committed regression tests. They do not cover the application's full state machine, migrations, real-user ranking changes, or UI behavior. The main decomposition, pair-completion, and fitted-percentile examples were rechecked against the reviewed source while writing this report. No application code, settings, or graph data was changed as part of the review or report.
