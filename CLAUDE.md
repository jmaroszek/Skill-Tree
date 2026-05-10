# Skill Tree — Claude context

Task-prioritization app. A directed graph of nodes (tasks/goals) and typed edges (prerequisites / synergies) is ranked by an ROI-based scoring algorithm to tell the user what to work on next. Dash + Cytoscape.js frontend, Python backend, SQLite storage.

## Must-know rules

- **Always launch the app in sandbox mode**: `python app.py --sandbox`. Never run `python app.py` (production) unless the user explicitly asks.
- **Production DB (`data/skilltree.db`)** — reads and writes are allowed when the user is asking for graph review or programmatic node/edge changes against their real data. Do **not** use it as a scratchpad: no exploratory writes, no test fixtures, no app launches against it. When in doubt about whether a write is "graph editing the user asked for" vs "experimentation", confirm first.
- **Sandbox DB (`data/sandbox_skilltree.db`)** is the target for any app-launch testing or experimentation.
- **Port is 8050.**

## Node-type semantics

Five types — each answers a different question. Picking the right one matters; misclassification muddies the rankings.

- **Goal** — a *domain, area, or capacity* the user is developing. "What am I trying to achieve here." Container-flavored, almost never atomic. "Done" = all Hard children Done (cascade). Examples: Sleep, Strength, Stoicism, Character.
- **Learn** — a *topic or body of knowledge* the user wants to integrate. Can be atomic (Sleep Pressure, Stretching) or a container with sub-Learns (Sleep Theory, Biology of Stress). "Done" = "I understand this enough to apply or explain it."
- **Action** — a *discrete practice or experiment* with a definite end. The user runs them as 6-week PIMLI cycles. "Done" = the cycle is complete. Time-on-task is the actual doing.
- **Resource** — *external material* (book, course, notes). "Done" = absorbed.
- **Milestone** — a *measurable, verifiable single-event achievement* (weight target, time, count). **Excluded from scoring** — the work happens upstream in capacity Goals; the Milestone is the checkpoint, not the practice. Use minimal time estimates (1/1/1) since the field doesn't apply.

**Decision tree (first yes wins):**
1. External material to consume? → Resource
2. Discrete practice/experiment with definite end? → Action
3. Measurable single-event achievement? → Milestone
4. Decomposes into things I'd track separately? → Goal
5. Otherwise (atomic body of knowledge) → Learn

**Goal vs Learn — the hard call:** both can have children. Distinguish by *scope*: Goal = "an area / capacity" (Sleep, Strength), Learn = "a topic / body of knowledge" (Sleep Pressure, Sleep Theory). Heuristic: "an area of my life" → Goal; "a thing I want to understand" → Learn.

**Common misclassifications to flag during reviews:**
- Goal-flavored Learn (thin decomposition, all-atom children) → demote to Learn (inherited mode if it acts as a header)
- Goal-flavored Milestone (measurable target treated as Goal) → convert to Milestone
- Goal-flavored Action (fixed-period practice treated as Goal) → convert to Action

User-facing version of this lives in the README's "Choosing the right node type" section — keep both in sync if the framework evolves.

## Edge-type semantics

The three real edge types are *not* a single "strength" gradient — `Helps` is on a different axis from `Needs_Hard`/`Needs_Soft`. Treat them as:

- **`Needs_Hard`** — must-do prerequisite. Blocks eligibility (a node with an incomplete hard prereq is automatically Blocked). Strongest transitive value flow (`d_H` per hop).
- **`Needs_Soft`** — helpful but not blocking. Weaker transitive value flow (`d_S` per hop).

**Direction convention (read this carefully — it is the most error-prone semantic in the codebase):** `A --[Needs_Hard|Needs_Soft]--> B` means **A unlocks B**: A is the prerequisite, B is the dependent. B is blocked until A is Done. Read the arrow as "leads to" / "comes before" / "unlocks." Worked example: `Statistics → Regression Hard` means complete Statistics first; Regression unblocks once Statistics is Done. The visual arrowhead in the Cytoscape graph points from prereq to dependent — visually identical to the data direction.

**Scoring cascade direction (do not get this wrong — it has caused repeated bugs):** the scoring module walks **forward along arrows**. `total_value(n)` sums what `n` *unlocks* via `H_out[n]` / `S_out[n]`, discounted per hop. Concrete consequences:

- A node mid-chain (incoming prereqs AND outgoing dependents, e.g. `ML Fundamentals`) has high TV because the downstream cascade adds up. This is the "intrinsic" use case for TV — what does completing this unlock?
- A Goal that is a **sink** (only incoming edges, e.g. `Satisfaction`: 23 in, 0 out) has TV ≈ its own IV. There are no descendants to cascade. Most user-level Goals fall in this bucket.
- A leaf prereq deep in a chain accumulates the discounted value of every node downstream that depends on it. This is why the Next-tab ranker, which uses forward TV, surfaces leaf actions and not Goals.

**To rank by "value of the prerequisite subtree" (everything that flows INTO a node), invert the Hard/Soft edges before calling `total_value`** — see [`analyze_callbacks._rank_goals`](analyze_callbacks.py) for the worked pattern. Don't try to invent a new traversal; just flip source ↔ target on Hard/Soft, keep Helps symmetric, rebuild adjacency, and the existing scoring machinery does the right thing against the flipped graph.

**Eligibility is the OPPOSITE direction:** a node is Blocked until every name in `Hard_in[node]` (incoming hard edges) has status Done. So eligibility walks against arrows; TV walks along them.

**Vocabulary trap:** when a Goal sits visually "at the top" of a tree, the things "below it" are *prereqs flowing in* — which in graph-theory terms are the Goal's **ancestors** (they precede it in topological order), NOT its descendants. The Goal is the descendant of its prereqs. To avoid confusion, prefer "prereqs" / "dependents" over "ancestors" / "descendants" in code, comments, and conversation.

**Hard edges encode two distinct things, both valid:** (a) genuine logical prerequisites ("you need linear algebra before deep learning"), and (b) the user's personal sequencing preference for what to study first ("I want to do supervised learning before deep learning, even though deep learning is technically a kind of supervised learning"). When auditing, **don't "correct" edges that look weird from a pure-taxonomy standpoint** — they may be deliberate sequencing preference. When the direction looks surprising, ask before flipping.

- **`Helps`** (Synergy) — *mutual multiplicative reinforcement*, not a lesser Soft. Doing both is significantly more valuable than the sum of doing each alone (e.g., concepts that blend unusually well). Bidirectional, non-transitive (no chains). Synergy contributes via two paths: a small **pair bonus** `d_Syn_pair * tv(partner)` pre-completion, and a **multiplicative kick on intrinsic value** `iv * (1 + d_Syn_mul * sqrt(count_done_partners))` once partners are Done. The sqrt is a diminishing-returns cap so a hub of N synergy partners gives ~`sqrt(N)`× the boost, not N× — keeps "more partners = more boost" without unbounded inflation. Multiplier applies to intrinsic only — not to the cascade or the pair bonus. See [`scoring.py`](scoring.py)'s `total_value` for the implementation.

## Where to look

Don't duplicate these in this file — they're the source of truth for their respective topics:

- [`technical_overview.md`](technical_overview.md) — architecture, module responsibilities, data lifecycle, algorithms, data structures, JS-Dash bridge.
- [`README.md`](README.md) — full feature tour written for non-technical readers, grounded in the sandbox dataset.
- [`STYLE_GUIDE.md`](STYLE_GUIDE.md) — UI conventions (colors, typography, spacing, component styles). Consult before touching any UI; update it when you establish new patterns.

## Tech stack (one-liner)

Python 3.10, Dash + Dash Bootstrap Components (DARKLY theme), Dash Cytoscape, NetworkX, NumPy, Plotly, SQLite via stdlib `sqlite3`. No bundler — JS in `assets/` is served raw.

## Non-obvious conventions

- Every tab module exposes exactly one public function: `register_*_callbacks(app)`. `app.py` imports and calls each. New tab = one more `register_*` call.
- Node `name` is the primary key; edges have composite PK `(source, target, type)` so the same pair can carry both a prerequisite and a synergy.
- Almost all callbacks that mutate state end by returning a fresh `generate_elements(...)` element list from [`callbacks.py`](callbacks.py). That function is the single source of truth for what Cytoscape sees.
- Status is cascading: a node auto-Blocks when any hard prerequisite is incomplete; `_update_dependent_nodes_state` walks the downstream chain on every Done-flip.
- The JS-Dash bridge uses native HTML `value` setters (via `Object.getOwnPropertyDescriptor`) to get React to notice programmatic input changes — plain `el.value = ...` is silently ignored.
- `ConfigManager` is classmethod-only and round-trips everything through the `Settings` SQLite table. There's no in-process cache, which is why multiple `GraphManager` / `EventManager` instances stay consistent across tab modules.

## Testing

```bash
pytest
```

Tests use a `temp_database` fixture that monkeypatches `database.get_db_path` to a per-test `tmp_path`. Nothing touches sandbox or production DBs.

## Key patterns to follow when editing

- Use Dash `ALL` pattern-matching (`Input({'type': 'x', 'index': ALL}, ...)`) for any dynamically-generated component list.
- Prefer extracting pure logic to [`callback_helpers.py`](callback_helpers.py) (stateless) or [`graph_manager.py`](graph_manager.py) (DB-backed) rather than growing the already-large `*_callbacks.py` files further.
- Cycle detection is already handled in `graph_manager.add_edge` — don't reimplement.
- For anything time/duration-related, let the `Node.time` property do the PERT blend; don't compute a single "time" from `time_o/m/p` yourself.
