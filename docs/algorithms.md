# Algorithms

This document describes the math that powers the app's intelligent recommendations. 


 
For how the code is organized, see [app_architecture.md](app_architecture.md). For the user-facing tour, see [README.md](../README.md).


# Notation
All sections below share the notation introduced next.

## Edges

Edges are typed. Each one carries a label that tells the algorithm what kind of relationship it encodes, and a direction (or lack thereof) that determines how the algorithm traverses it.

| Symbol | Description | Directed |
|---|---|---|
| $E_H$ | Hard prerequisites — the source must be Done before the target can be worked on | Yes |
| $E_S$ | Soft prerequisites — the source is helpful but not strictly required for the target | Yes |
| $E_Y$ | Helps relationships — mutual synergy between two nodes | No |

The full edge set is $E = E_H \cup E_S \cup E_Y$.

A → B means A is a prerequisite for B. The scoring cascade walks forward (along arrows), and eligibility walks backward (against arrows).

## Node Attributes

| Symbol | Range | Meaning |
|---|---|---|
| $V(n)$ | $\{1, \ldots, 10\}$ | Value rating |
| $I(n)$ | $\{1, \ldots, 10\}$ | Interest rating |
| $D(n)$ | $\{1, \ldots, 10\}$ | Difficulty rating |
| $t(n)$ | $\ge 0$ | Point estimate for time, in hours |
| $\text{status}(n)$ | $\{\text{Open}, \text{Blocked}, \text{Done}\}$ | Lifecycle state |
| $\text{ctx}(n)$ | string or null | Context |

## Adjacency Maps

| Symbol | Definition | Meaning |
|---|---|---|
| $H_{\text{out}}(n)$ | $\{m : (n, m) \in E_H\}$ | Nodes $n$ unlocks via Hard |
| $S_{\text{out}}(n)$ | $\{m : (n, m) \in E_S\}$ | Nodes $n$ unlocks via Soft |
| $H_{\text{in}}(n)$ | $\{m : (m, n) \in E_H\}$ | Hard prereqs of $n$ |
| $Y(n)$ | $\{m : \{n, m\} \in E_Y\}$ | Synergy partners (symmetric) |

## Hyperparameters
All knobs are profile-tuned; defaults and per-profile values are in the [Scoring Profiles](#scoring-profiles) section.

| Symbol | Role |
|---|---|
| $w_V, w_I$ | Weights on Value and Interest in intrinsic value |
| $w_e, w_t$ | Weights on Difficulty and time in perceived cost |
| $\beta$ | Sub-linear exponent on time in perceived cost |
| $d_H, d_S$ | Per-hop discount factors for Hard and Soft cascade |
| $d_{\text{Syn,pair}}$ | Pair-bonus weight for each synergy partner |
| $d_{\text{Syn,mul}}$ | Completion-multiplier weight on intrinsic value |
| $m_{\text{cross}}$ | Cross-context synergy bonus multiplier |
| $b$ | Priority-goal boost (rank-1 multiplier) |
| $\alpha$ | Density-normalization exponent (scored nodes) |
| $\alpha_g$ | Density-normalization exponent (Goals) |



# Priority Scoring Algorithm
## Overview

This is the most important algorithm in the whole app, as it tells the user what to work on next. Each node is a project, and a project's base priority score is the ratio of its value to cost. This base is adjusted by various multipliers including the goal-priority boost, context weight, and density normalization. To be a ranked, a node must be eligible, and not be a container. This implies that open Learn, Resource, and Action nodes, with neither its rating or time attributes set to `inherited` are ranked, while Goals and Milestones are not. Goals are ranked through a similar, but different scoring algorithm discussed later.

Only eligible nodes are ranked — defined formally in [Eligibility, Status, and the Cascade](#eligibility-status-and-the-cascade) at the end of this document, together with the status-cascade machinery that maintains it.

## Intrinsic Value

The intrinsic value of a node is how appealing it is. Mathematically, $V(n)$ and $I(n)$ are the user's ratings. $w_V$ and $w_I$ are the weights applied by the scoring profile.

$$ \text{IV}(n) = w_V \cdot V(n) + w_I \cdot I(n) $$

Nodes with an inherited value mode have $\text{IV}(n) = 0$, regardless of what is in the database. The node is a pure structural conduit — the cascade still flows through it, but it contributes no ratings of its own.

## Perceived Cost

The perceived cost of a node is how "expensive" it is to complete, in terms of time and energy. The user supplies the difficulty rating ($D(n)$) directly. $t(n)$ may also be supplied directly, as a point estimate, but it is more common that the user will provide either two estimates, a lower and upper bound, or three, which adds an expected time estimate too. How the final $t(n)$ is estimated is discussed in [time.md](time.md).

$$ \text{Cost}(n) = 1 + w_e \cdot D(n) + w_t \cdot t(n)^\beta $$

Three parameters control the scaling of the user supplied difficulty estimate, and the app's derived time estimate. $w_e$ and $w_t$ are straightforward linear scalars, once again set by the scoring profiles. The exponent ($\beta \in (0, 1]$)  is a "sublinear damper." This makes long projects feel proportionally less expensive than their raw time estimate would suggest, which tracks human psychology. For example, at the Sage default $\beta = 0.85$, a 100-hour project's time penalty is $\approx 50\times$ that of a 1-hour project, not $100\times$ worse, as it would be if $\beta =1$. Finally, the constant $1$ keeps the denominator positive even when both $D$ and $t$ are zero, as it is if the node is a container (both value and time modes are inherited).

## Total Value

### The DAG Cascade for Hard and Soft Edges

A project isn't only worth its own ratings. If completing it unlocks a chain of other valuable projects, that downstream value should flow back and lift its priority. The DAG cascade is how the algorithm formalizes this. Walking forward along Hard and Soft edges from $n$, every descendant contributes a discounted portion of its intrinsic value back to $n$'s total.

$$ \text{TV}_{\text{dag}}(n) = \text{IV}(n) + d_H \!\!\!\sum_{m \in H_{\text{out}}(n)}\!\!\! \text{TV}_{\text{dag}}(m) + d_S \!\!\!\sum_{m \in S_{\text{out}}(n)}\!\!\! \text{TV}_{\text{dag}}(m) $$

A node's total cascade value is its own intrinsic value, plus the sum over its Hard children (each discounted by $d_H$, and recursively containing its own cascade), plus the analogous sum over its Soft children. The recursion unwinds into a discounted sum over the whole reachable subtree.

The discount factors satisfy $0 < d_S < d_H < 1$ by convention. Hard edges carry a stronger per-step signal because a hard prerequisite is *essential* to its dependent (Calculus genuinely cannot be done without Algebra), while a soft prerequisite is merely *helpful* (a UX course improves a personal-website project but isn't required). Both factors are less than 1, so contributions decay geometrically with depth. The further away a descendant sits, the less of its value reaches $n$ — which tracks the user's actual confidence, since ratings on distant downstream projects are more likely to drift before the user ever gets there.

Why Hard and Soft only, and not Helps? Two reasons, one is for correctness and one is for performance. First, Hard and Soft edges are directed and acyclic (DAG) — cycle detection in `GraphManager.add_edge` enforces this on every insert — so the recursion above always terminates. Second, the DAG property means each node's $\text{TV}_{\text{dag}}$ can be memoized: computed once and reused for every ancestor that asks. Helps edges, by contrast, are bidirectional and can form cycles, so they get a separate, depth-limited treatment in the next section. Amortized total work for the cascade is $O(N + |E_H| + |E_S|)$.

The performance impact of this split is hard to overstate. Without memoization, the recursion has to re-walk each descendant once per ancestor that reaches it, and the path count explodes exponentially in graphs with even modest diamond structure. An earlier version of the algorithm that lumped all edge types together — and therefore couldn't memoize, because the Helps cycles would have produced incorrect cached values — took several minutes per scoring pass on a graph the size of the typical user's -- slow enough that the Next tab was effectively unusable. But now, with memoization unlocked by the DAG split (every node's $\text{TV}_{\text{dag}}$ computed exactly once and reused), the same pass now finishes in a handful of milliseconds — roughly **ten thousand times faster.** A small structural decision — handling synergies outside of the cascade — is where that enormous performance improvement comes from.

### Example
A descendant $k$ hops away contributes its intrinsic value scaled by the product of edge discounts along the path. For a single chain of all-Hard or all-Soft edges, that's $d_H^k$ or $d_S^k$. The following table uses the Sage's (default) scoring profile ($d_H = 0.6$, $d_S = 0.4$) and a downstream node with $\text{IV} = 100$:

| Depth $k$ | Hard weight $d_H^k$ | Hard contribution | Soft weight $d_S^k$ | Soft contribution |
|---|---|---|---|---|
| 0 (self) | 1.000 | 100.00 | 1.000 | 100.00 |
| 1 | 0.600 | 60.00 | 0.400 | 40.00 |
| 2 | 0.360 | 36.00 | 0.160 | 16.00 |
| 3 | 0.216 | 21.60 | 0.064 | 6.40 |
| 4 | 0.130 | 12.96 | 0.026 | 2.56 |
| 5 | 0.078 | 7.78 | 0.010 | 1.02 |

Notice that the hard chain stays relevant 4-5 hops our (the descendant at depth 4 still contributes ~13% of its raw intrinsic value, and ~8% at at depth 5). Soft chains, in contrast, are effectively null past depth 3.

### Synergistic Contributions to Total Value

Synergy edges work differently from prerequisites. They don't say "this unlocks that," they say "doing both is worth more than doing either alone." 

One example is learning a Foreign Language and Travel. Time abroad helps solidify vocabulary in a way no classroom drill can match, while even modest fluency opens up locations that monolingual tourists would have a hard time navigating. Each genuinely amplifies the other, so the algorithm should reward that pairing in its scoring. 


Synergies influence total value in two stages: one mechanism, the pair bonus, is in play before either partner is done, and the second mechanism, the completion multiplier, comes online only after one task has been completed.

#### Pair Bonus 
A small bonus that applies before either partner has been started. Each synergy partner $z$ contributes a fraction $d_{\text{Syn,pair}}$ of its own cascade-derived total value back to $n$:

$$ \text{Syn}_+(n) = d_{\text{Syn,pair}} \!\!\!\sum_{z \in Y(n)}\!\!\! c(n, z) \cdot \text{TV}_{\text{dag}}(z) $$

Effectively, the pair bonus increases the liklihood that synergistic projects surface together, even before either is started. 

##### Cross-Context Coefficient
The cross-context coefficient $c(n, z)$ amplifies the pair bonus of synergies that span different domains. 

$$ c(n, z) = \begin{cases} m_{\text{cross}} & \text{if } \text{ctx}(z) \ne \text{ctx}(n)\\ 1 & \text{otherwise} \end{cases} $$

This parameter is used to encourage exploration in the explore vs. exploit tradeoff. Two profiles that have a high completion multiplier are the Creator and Explorer. The Creator profile sets $m_{\text{cross}} = 2.0$ to reward cross-domain connections that can serve as creative inspiration. The Explorer profile sets $m_{\text{cross}} = 1.5$ to reward curiosity and reinforce concepts in different domains, hypothetically leading to better generalization. Other profiles leave $m_{\text{cross}}$ at $1.0$, so within-context synergies count the same as cross-context ones.

#### Completion Multiplier
The completion multiplier gives a synergistic partner a large boost after the other one is done. Notice that this relationship is *multiplicative,* which scales priority more aggressively than the *additive* pair bonus described previously. 


Let $k(n) = |\{z \in Y(n) \, \vert \, \text{status}(z) = \text{Done}\}|$ be the count of finished partners. Then:

$$ \mu_Y(n) = 1 + d_{\text{Syn,mul}} \cdot \sqrt{k(n)} $$

The square root is a diminishing-returns guard. Without it, a node with 10 Done synergy partners would inflate by 10-20x under typical values for $d_{\text{Syn,mul}}$, which is empirically way too much. With it, 10 Done partners give roughly 3× the kick of 1, and the curve flattens further from there. The intuition: the first Done synergy partner provides most of the realized "doing both" payoff -- each additional one helps less.

#### Synergies are Depth-1 Relationships
Synergies do not chain (or cascade) like hard and soft edges do. They are treated as depth-1 relationships, meaning only the immediate synergy partners of $n$ contribute to its score (not the partners of those partners). 

There are good conceputual and algorithmic reasons to enforce this relationship. First, not all relationships described by $A \leftrightarrow B \leftrightarrow C$ are meaningful. For example, Cooking $\leftrightarrow$ Chemistry $\leftrightarrow$ Pharmacology. Understanding Chemistry sharpens your intuition for cooking because you understanding why acids, heat, and time matter. Chemistry will also improve your understanding of Pharmacology, since drug mechanisms are fundamentally chemical. But it doesn't follow that Cooking helps with Pharmacology, or Pharmacology helps with Cooking. The synergistic relationships are real, but the relationships are not transitive, because the endpoints don't actually inform each other. 

It's second reason is for algorithmic performance. Helps edges are bidirectional and can form cycles, so a cascade along them would either fail to terminate, or fall back on path-enumerating logic that defeats memoization — the problem flagged earlier in the [DAG Cascade Section](#the-dag-cascade-for-hard-and-soft-edges). This is a nice additional benefit that naturally follows the strong conceptual argument.

## Total Value

Total value is derived from three pieces.

$$ \text{TV}(n) = \underbrace{\mu_Y(n) \cdot \text{IV}(n)}_{\text{boosted intrinsic}} + \underbrace{\big(\text{TV}_{\text{dag}}(n) - \text{IV}(n)\big)}_{\text{cascade from descendants}} + \underbrace{\text{Syn}_+(n)}_{\text{synergy pair bonus}} $$

Read this as three additive terms: $n$'s own intrinsic value scaled by the synergy multiplier, plus the pure cascade portion (the recursive $\text{TV}_{\text{dag}}$ with $\text{IV}(n)$ subtracted out so it isn't double-counted), plus the synergy pair bonus.

Notice that the multiplier $\mu_Y$ applies *only* to intrinsic value, not to the cascade or the pair bonus. This is intentional. Completing a synergy partner makes the surviving node more valuable on its own merits — the "doing both" payoff has been realized — but it doesn't retroactively change what the node inherits from its descendants or from its other synergy partners.

## Base Score

$$ P_{\text{base}}(n) = \frac{\text{TV}(n)}{\text{Cost}(n)} $$

The base score is return on investment in the literal sense: value per unit of cost. High value over low cost rises to the top. The rest of the algorithm adjusts this base ratio.

## Goal Priority Boost

The user may mark up to three Goals as priorities — their #1, #2, and #3 most important objectives. Marking a Goal as a priority boosts the priority score of every Hard prerequisite in that Goal's subtree, nudging the algorithm to recommend work that drives toward what the user has explicitly said matters most.

Let $\Pi = (g_1, g_2, g_3)$ be the priority goals in rank order. From a single profile knob $b$ (the `goal_boost`), three rank multipliers are derived:

$$ \rho_1 = b, \quad \rho_2 = 1 + 0.66 (b - 1), \quad \rho_3 = 1 + 0.33 (b - 1) $$

Ranks 2 and 3 sit at two-thirds and one-third of the rank-1 premium, so they always stay proportionally between $1$ and $b$. For Sage's default $b = 1.50$, this gives $\rho_1 = 1.50$, $\rho_2 \approx 1.33$, $\rho_3 \approx 1.17$. For the goal-driven Pragmatist's aggressive $b = 2.00$, the rank-1 prereqs are doubled, resulting in a higher secondary and tertiary goal boosts too. 

When a node sits in multiple priority subtrees, **the highest applicable rank wins.** Mathematically, now, let $A_H(g_r)$ be the set of nodes that feed into $g_r$ via Hard edges. A node's boost is then 

$$ \rho(n) = \max\big(\{1\} \cup \{\rho_r : n \in A_H(g_r)\}\big) $$


## Context Multipliers
Two final modulations, applied multiplicatively after the goal boost. Both reflect context-level concerns rather than per-node properties.

### Context Weight
Context weight is a user-configurable scalar defaulting to 1. This lets the user manually emphasize or de-emphasize whole life areas — for example, doubling the weight on Money during a tight quarter, or halving the weight on Humanities during a STEM-focused stretch. 

### Density Normalization
This is a counterweight to context size. Without it, a heavily decomposed context (say, 60 nodes) would crowd out a sparser one (say, 5 nodes) just by sheer headcount, even if the sparse context has higher per-node value. Density normalization corrects for this. Let $B(n) = (\text{ctx}(n), \text{subctx}(n))$ be the (context, subcontext) bucket, and let $|B|$ be the count of [eligible](#eligibility) nodes in that bucket. Then 

$$ \delta(n) = \frac{1}{\max(1,\, |B(n)|)^\alpha} $$

The exponent $\alpha \in [0, 1]$ controls how aggressively dense buckets get damped. At $\alpha = 0$ the term vanishes (no normalization). At $\alpha = 1$, each bucket's combined weight is exactly its single-node weight — perfect flattening, so the dense context never wins by attrition. The Sage default $\alpha = 0.30$ damps heavily decomposed contexts without erasing their advantage. The intent is to keep the user well-rounded: even if STEM contains the user's biggest projects, density normalization gives smaller contexts a fair chance to surface their best candidates.

A note on buckets: `(context, None)`, or nodes with no specific subcontext, are treated as one bucket within the context. These nodes represent a broadly applicable set of projects within a major life area, such as relationships, science, or entertainment.

## Final Score

Putting it all together:

$$ P(n) = P_{\text{base}}(n) \cdot \rho(n) \cdot w_c(\text{ctx}(n)) \cdot \delta(n) $$

A node's final priority is its ROI ratio, scaled by the goal-priority boost, the user's context weighting, and the density correction. The multipliers compose multiplicatively, so a node in a small, weighted-up, priority-goal subtree can stack all three to surface aggressively; a node in a large, weighted-down, non-priority context can be pushed deeper into the list.

For display on the Next tab, scores are linearly rescaled against the top eligible node.

$$ P_{\text{display}}(n) = 100 \cdot \frac{P(n)}{\max_{m \in \text{eligible}} P(m)} $$

This results in the top ranked node having a priority of 100, with every other project being expressed as a proportion of that project's priority. 

(The Explain feature reports both the raw and normalized score.)


## Complexity

The whole pipeline is engineered to stay fast even on large graphs. End-to-end, the whole pipeline has a time complexity of $O(N + E + N \log N)$, which is impressive, to say the least.

Stage by stage:

| Stage | Cost | Note |
|---|---|---|
| Adjacency build | $O(N + E)$ | One pass over nodes and edges |
| Memoized $\text{TV}_{\text{dag}}$ over all nodes | $O(N + \lvert E_H\rvert + \lvert E_S\rvert)$ amortized | DAG property means each node is computed once, no matter how many ancestors reach it |
| Synergy contribution | $O(\lvert Y(n)\rvert)$ per node, $O(\lvert E_Y\rvert)$ total | Depth-1 only, so each Helps edge is touched twice across the graph |
| Ranking sort | $O(N \log N)$ | Standard comparison sort on the final priority scores |

On my graph (~750 nodes, ~1000 edges), the full pipeline runs in 5-8 ms. In practice, you can build an arbitrarily large graph -- much larger than this -- and the scoring math will keep up. 

## Scoring Profiles

The six built-in profiles are essentially hyperparameter bundles. First, the full numerical table showing the hyperparameters, and then, a description of how each is used to fullfill the perspective.

### Profile Hyperparameters
| Parameter | Symbol | Sage | Explorer | Compounder | Pragmatist | Creator | Glider |
|---|---|---|---|---|---|---|---|
| Value weight | $w_V$ | 1.00 | 1.00 | 1.00 | 1.50 | 1.00 | 1.00 |
| Interest weight | $w_I$ | 1.00 | 1.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| Hard discount | $d_H$ | 0.60 | 0.60 | 0.80 | 0.65 | 0.60 | 0.45 |
| Soft discount | $d_S$ | 0.40 | 0.40 | 0.50 | 0.20 | 0.40 | 0.30 |
| Synergy pair bonus | $d_{\text{Syn,pair}}$ | 0.10 | 0.15 | 0.10 | 0.05 | 0.25 | 0.05 |
| Synergy completion mult | $d_{\text{Syn,mul}}$ | 0.40 | 0.60 | 0.40 | 0.25 | 0.80 | 0.20 |
| Cross-context synergy mult | $m_{\text{cross}}$ | 1.00 | 1.50 | 1.00 | 1.00 | 2.00 | 1.00 |
| Difficulty weight | $w_e$ | 2.50 | 2.50 | 1.50 | 2.50 | 2.50 | 3.50 |
| Time weight | $w_t$ | 1.00 | 1.00 | 0.85 | 1.50 | 1.00 | 4.00 |
| Time exponent | $\beta$ | 0.85 | 0.85 | 0.70 | 0.85 | 0.85 | 0.95 |
| Priority goal boost | $b$ | 1.50 | 1.50 | 1.50 | 2.00 | 1.50 | 1.00 |
| Density exponent (scored) | $\alpha$ | 0.30 | 0.40 | 0.20 | 0.20 | 0.30 | 0.40 |
| Density exponent (Goals) | $\alpha_g$ | 0.20 | 0.30 | 0.15 | 0.15 | 0.20 | 0.30 |

> [!Note] Customization
> A Custom profile is also available, exposing every parameter for fine tuning.

### The Perspective of Each Profile
| Profile | Perspective | Parameter Tweaks |
|---|---|---|
| **Sage** | The reference baseline — balanced ROI ranking with no strong lean in any direction. | All other profiles are expressed as deltas off these defaults. |
| **Explorer** | Curiosity-driven. Favors what you find interesting, rewards cross-domain links, and gives sparse contexts a fair shot. | $w_I > w_V$ flips the intrinsic value ranking toward interest. Synergy parameters elevated and $m_{\text{cross}} = 1.5$ rewards cross-domain pairs. Higher $\alpha$ damps dense contexts harder so abscure work surfaces. |
| **Compounder** | Long-payoff foundational work. Distant downstream value matters; heavy investments shouldn't feel scary. | Cascade discounts $d_H, d_S$ raised so value carries further down the chain. Cost knobs $w_e, w_t, \beta$ all lowered so big projects have a smaller cost penalty. |
| **Pragmatist** | Goal-driven execution. What you said matters most should dominate; ignore distractions. | $w_V$ favored over $w_I$. Synergy parameters minimized; $d_S$ slashed so soft-helpful work doesn't bubble up. $b = 2.0$ doubles the rank-1 priority-goal boost. |
| **Creator** | Synthesis and cross-disciplinary work. Rewards pairings that blend across domains. | Synergy parameters 2-3× their Sage values; $m_{\text{cross}} = 2.0$ doubles cross-domain pair bonuses, the highest of any profile. |
| **Glider** | Light, varied, low-friction work. For seasons when you need to coast. | Every cost knob raised ($w_e \uparrow$, $w_t \times 4$, $\beta \to 0.95$) so heavy work is penalized hard. Cascade and synergy contributions damped. $b = 1.0$ disables the priority-goal boost so non-priority work competes fairly. |

# Goal Scoring

The algorithm discussed previously is wrong for Goals, because **goals are sinks.** That is, they have many incoming edges, but few out-going edges. If the previous algorithm were used to rank goals, the forward cascade would collapse to $\text{TV}_{\text{dag}}(g) = \text{IV}(g)$, which means every Goal would rank identically by its own value and interest sliders — ignoring every node feeding into it. The meaningful question for a Goal is the inverse: how much prereq work is subsumed, and what's that worth per unit of time?

## The Edge Inversion Trick

Define the inverted graph $G' = (N, E_H', E_S', E_Y)$ where

$$ E_H' = \{(t, s) : (s, t) \in E_H\}, \quad E_S' = \{(t, s) : (s, t) \in E_S\} $$

and $E_Y$ is unchanged (synergies are already symmetric). In $G'$, the prereqs of a node in $G$ become its forward dependents. Run the standard `total_value` on $G'$ and the forward cascade walks the prereq subtree:

$$ \text{TV}'(g) = \text{IV}(g) + d_H \!\!\!\sum_{m \in H_{\text{in}}(g)}\!\!\! \text{TV}_{\text{dag}}'(m) + d_S \!\!\!\sum_{m \in S_{\text{in}}(g)}\!\!\! \text{TV}_{\text{dag}}'(m) + \text{Syn}_+'(g) $$

The recursive $\text{TV}_{\text{dag}}'$ inside continues along $E_H'$ and $E_S'$, so the discounted sum runs over the whole transitive prereq subtree. The synergy bonus is computed the same way as in the forward direction. This reuses all the existing scoring machinery. How about that? 

## Cost For Goals

Raw $\text{TV}'(g)$ is extensive — it grows with subtree size — so unmodified it would rank Goals by how big they are. The cost denominator turns it into a priority signal. Let $A_H(g)$ be the Hard-only prereq closure and define

$$ R(g) = \{n \in A_H(g) : \text{status}(n) \ne \text{Done}\} $$

as the **remaining** hard subtree (work still owed before the Goal is Done). The cost is the beta-compressed sum of remaining time:

$$ \text{Cost}'(g) = 1 + w_t \cdot \left(\sum_{n \in R(g)} t(n)\right)^\beta $$

You may have noticed that effort is included in the primary scoring algorithm, but it is dropped from the Goal scoring algorithm. Here is my reasoning: it is better to assess the difficulty of a goal through the difficulty of its subtasks, rather than estimate it directly. Thus, the time remanining signal, after compression, is a better measure of how costly a goal is. 

## Goal Score

Like the traditional ranking, a Goal's priority is composed of a base score adjusted by the same family of multipliers: rank, context weight, and a density correction. The density correction uses a separate exponent — and a Goal-only bucket count — to fit the smaller populations involved.

$$ P_g(g) = \underbrace{\frac{\text{TV}'(g)}{\text{Cost}'(g)}}_{\text{Base Score}} \cdot \underbrace{\rho(g)}_{\text{Goal Priority}} \cdot \underbrace{w_c(\text{ctx}(g))}_{\text{Context Weight}} \cdot \underbrace{\delta_g(g)}_{\text{Goal Density}} $$

The Goal density correction is defined analogously to the leaf-node $\delta$, but bucketed by Goal headcount alone. Let $B_g(g) = (\text{ctx}(g), \text{subctx}(g))$ be the Goal's bucket and $|B_g(g)|$ the count of **open** Goals sharing that bucket (Done Goals are excluded — they aren't competing for sidebar attention). Then:

$$ \delta_g(g) = \frac{1}{\max(1,\, |B_g(g)|)^{\alpha_g}} $$

The exponent $\alpha_g$ is smaller than the leaf-node $\alpha$ because Goal populations are about an order of magnitude smaller — a heavily decomposed scored-node bucket sits around 20-40, while a heavily decomposed Goal bucket maxes out around 4-5. The Sage default of $\alpha_g = 0.20$ damps a 5-Goal bucket by about 28%, which is in the same correctional ballpark as the leaf-level $\delta$ at its typical bucket sizes. Profiles that already lean explore-y ($\alpha = 0.40$ for Explorer and Glider) bump $\alpha_g$ to $0.30$, and goal-driven profiles (Pragmatist, Compounder) drop it to $0.15$ to let already-priority subtrees dominate. Setting $\alpha_g = 0$ disables the correction entirely.

Why a Goal-only bucket count, rather than the full scored-node count from the leaf-level $\delta$? A heavily decomposed area produces both more leaves *and* more Goals. If Goals shared the leaf bucket count, a Goal in that area would be penalized twice — once for its own subtree size (already inflating $\text{Cost}'(g)$) and again for the leaves it happens to sit next to. Counting only Goals isolates the relevant question: "how crowded is the sidebar within this corner of the graph?"

> [!NOTE] Utility
> The Goals sidebar and the Analyze tab's Completion chart both rank Goals by the priority ranking explained here

## Milestone Transparency
Milestones are checkpoints, not work. A Milestone like "10 strict pull-ups" sits in the middle of a Goal's prereq tree but doesn't itself represent practice. — the practice happens in capacity Goals upstream of it. When ranking Goals, the app replaces every Milestone with a pass-through that has an intrinsic value of 0, and inherits its descendants' time.Value cascades through the Milestone unchanged; the Milestone's own  ratings don't dilute the signal.

# Eligibility, Status, and the Cascade

Eligibility decides which nodes the scoring algorithm will consider in the first place. It depends on each node's `status`, which is itself the cached output of a function over the graph and the user's Done-flips — maintained by an incremental cascade that fires whenever a status changes. This section covers the gate (eligibility), the function it consults (status), and the machinery that keeps that function honest (the cascade).

## Eligibility

Only nodes that you can work on are scored. Eligibility filters out nodes whose Hard prerequisites aren't all Done. Formally:

$$ \text{eligible}(n) = \begin{cases} 1 & \text{if } \forall\, m \in H_{\text{in}}(n),\ \text{status}(m) = \text{Done} \\ 0 & \text{otherwise} \end{cases} $$

This is the only place where the algorithm walks Hard prereq edges *against* their arrow direction. The cascade walks forward (from $n$ to its dependents); eligibility walks backward (from $n$ to its prereqs). Non-eligible nodes are assigned $P = -1$ and dropped before the ranking sort. The same exclusion applies to Goals, Milestones, and Containers, as well as Done or Blocked nodes.

## The status function

A node's `status` is the cached output of a function of the graph and the user's Done-flips, not a free parameter. The function:

$$ \text{status}(n) = \begin{cases} \text{Done} & \text{user marked Done and prereqs are still satisfied} \\ \text{Blocked} & \exists\, m \in H_{\text{in}}(n),\ \text{status}(m) \ne \text{Done} \\ \text{Open} & \text{otherwise} \end{cases} $$

Goals are exempt — their status is user-controlled and never recomputed. They are tracking nodes, not work nodes; the user decides when one is "achieved."

Notice that the Blocked clause is exactly the negation of the eligibility predicate above. A node with `status = Blocked` is precisely a non-eligible node (excepting the type/container exclusions, which eligibility adds on top). The two definitions are the same condition viewed from opposite ends: status assigns the label, eligibility reads it.

## Incremental cascade

When any node's status changes via `GraphManager.update_node`, `_update_dependent_nodes_state(node_name)` runs. It collects the direct Hard dependents ($H_{\text{out}}(n)$) and runs an iterative BFS through `_cascade_update_states`:

```
queue = direct Hard dependents of changed_node
while queue:
    u = queue.pop()
    if u seen: continue
    if u.type == 'Goal': continue
    is_blocked = any(prereq.status != Done for prereq in H_in(u))
    new_status = Blocked if is_blocked else Open
    if u.status == Done and not is_blocked: continue  # Done is monotonic
    if u.status == new_status: continue                # no change
    write u.status = new_status
    enqueue every node in H_out(u)
```

A status change only propagates further when it actually flips a downstream node — short-circuiting on no-change keeps the cascade bounded by the genuinely affected frontier, not the full Hard-downstream closure. Cycles are impossible because Hard edges are a DAG (enforced at write time).

## Done is monotonic

A Done node only re-derives to Blocked if a prereq becomes un-Done. It never silently flips back to Open — that would risk un-marking work the user said they finished. The cascade respects this by short-circuiting on Done nodes that still satisfy their prereqs.

The payoff for eligibility: an eligible node stays eligible until the user actively un-Dones one of its prereqs. There's no hidden path by which the gate quietly closes on the user's selected work.

## Cycle prevention on edge inserts

`GraphManager._will_create_cycle(source, target)` runs before every Hard or Soft edge insert. It does a forward BFS from `target` along Hard + Soft out-edges; if the walk ever reaches `source`, the new edge would close a cycle and the insert is rejected. Helps edges skip this check (they're bidirectional and can form arbitrary undirected cycles without breaking anything).

This is the invariant that lets `total_value` memoize safely — the Hard + Soft subgraph is enforced to be a DAG at write time, not assumed at read time. The `computing` set inside `_tv_dag` is a belt-and-braces guard against the unreachable case where a cycle slips through anyway (corrupted DB, restored backup with mismatched constraints).

## Startup safety net

`recompute_all_statuses()` runs on app launch from [`app.py`](../app.py). It walks every non-Goal node, re-derives status from the current Hard prereqs, and writes back any drift. Drifted node counts are logged so silent bypass paths (direct SQL, restored backups, bugs in cascade-skipping code paths) surface in `data/app.log` rather than being papered over.

This is the only place that touches `status` without going through the incremental cascade. Every other write path either calls `update_node` (which fires the cascade) or `add_edge` / `remove_edge` for Hard edges (which call `_update_node_state` on the affected target).

# Explain Feature

`explain_score` decomposes a node's TV into per-ancestor contributors so the Explain modal can show "who contributed what." The challenge: with diamond paths (multiple routes from $n$ to a descendant $D$), the contribution of $D$ is the sum over all paths. A naive recursion would re-traverse each subtree per ancestor.

The trick exploits the linearity of the additive portion of TV. For any descendant $D$, its contribution to $n$'s TV equals a single scalar weight $W(D)$ times $\text{IV}(D)$:

$$ \text{contribution}(D) = W(D) \cdot \text{IV}(D) $$

where $W(D)$ is the sum over all $n$-rooted paths to $D$ of the product of edge discounts along that path. The synergy completion multiplier is *not* linear in IV — it's a node-level scalar — so it's handled separately.

## Computing $W$ by forward propagation

Build $W$ in a single topological pass over the reachable Hard + Soft subgraph rooted at $n$, with a depth-1 Synergy seed.

```
W[n] = 1
for z in Y(n) \ {n}:
    W[z] += c(n, z) * d_Syn_pair        # depth-1 synergy seed

for u in topological order over reachable nodes:
    if W[u] == 0: continue
    for v in H_out(u): W[v] += d_H * W[u]
    for v in S_out(u): W[v] += d_S * W[u]
```

Reachability is computed by a stack walk from $n$ plus its synergy seeds; topological order falls out of a Kahn-style in-degree decrement over the reachable subset.

Because Hard + Soft is a DAG, the topological order is well-defined and each node $u$ is processed exactly once after all its predecessors have committed their contributions to $W[u]$. Diamonds collapse naturally — both paths to $D$ add to the same $W[D]$ on their respective passes.

## Identity

The forward propagation produces weights satisfying

$$ \sum_D W(D) \cdot \text{IV}(D) = \text{IV}(n) + \big(\text{TV}_{\text{dag}}(n) - \text{IV}(n)\big) + \text{Syn}_+(n) $$

— exactly the additive portion of $\text{TV}(n)$. The synergy multiplier $\mu_Y(n)$ contributes the remaining $\text{IV}(n) \cdot (\mu_Y(n) - 1)$ as a node-level scalar applied outside this sum. So:

$$ \text{TV}(n) = \text{IV}(n) \cdot (\mu_Y(n) - 1) + \sum_D W(D) \cdot \text{IV}(D) $$

This identity is what makes contributor percentages add up sensibly in the Explain modal.

## First-hop categorization

Each descendant is tagged with the type of the *first* edge taken from $n$ on the shortest path to it: `Hard`, `Soft`, or `Synergy` (or `Self` for $n$ itself). This is what populates the breakdown rows in the modal — hard_cascade, soft_cascade, synergy contributions. Ties at equal depth break Hard > Soft > Synergy by convention so the more "structural" category wins display ownership.

## Next

- [`scoring.py`](../scoring.py) is the canonical reference for everything in the scoring, goal scoring, and explainability sections. Every formula above maps to identifiable lines in that module.
- [`graph_manager.py`](../graph_manager.py) (specifically `_cascade_update_states`, `_will_create_cycle`, and `recompute_all_statuses`) is the canonical reference for the status cascade.
- [time.md](time.md) covers the PERT blend and Monte Carlo simulation that produce the $t(n)$ used in the Perceived Cost formula above.
- [README.md](../README.md) is the user-facing tour and the source of truth for product semantics — what each feature does and why it exists.
- [CLAUDE.md](../CLAUDE.md) captures repo conventions, edge-direction gotchas, and the must-know rules for editing the codebase.
