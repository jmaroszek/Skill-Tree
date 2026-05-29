# Skill Tree — Codex context

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
- **`Helps`** (Synergy) — *mutual multiplicative reinforcement*, not a lesser Soft. Doing both is significantly more valuable than the sum of doing each alone (e.g., concepts that blend unusually well). Bidirectional, non-transitive (no chains). Synergy contributes via two paths: a small **pair bonus** `d_Syn_pair * tv(partner)` pre-completion, and a **multiplicative kick on intrinsic value** `iv * (1 + d_Syn_mul * sqrt(count_done_partners))` once partners are Done. The sqrt is a diminishing-returns cap so a hub of N synergy partners gives ~`sqrt(N)`× the boost, not N× — keeps "more partners = more boost" without unbounded inflation. Multiplier applies to intrinsic only — not to the cascade or the pair bonus. See [`scoring.py`](scoring.py)'s `total_value` for the implementation.

## Where to look

Don't duplicate these in this file — they're the source of truth for their respective topics:

- [`docs/app_architecture.md`](docs/app_architecture.md) — module responsibilities, tab-callback pattern, Cytoscape pipeline, JS-Dash bridge, persistence and caching.
- [`docs/scoring.md`](docs/scoring.md) — full math for scoring, profiles, goal ranking, explainability, status cascade.
- [`docs/time.md`](docs/time.md) — the PERT blend that produces `t(n)` and the Monte Carlo simulator behind the Time Simulation panel.
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
