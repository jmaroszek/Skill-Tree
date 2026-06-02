# Skill Tree — Claude context

Task-prioritization app. A directed graph of nodes (tasks/goals) and typed edges (prerequisites / synergies) is ranked by an ROI-based scoring algorithm to tell the user what to work on next. Dash + Cytoscape.js frontend, Python backend, SQLite storage.

## Must-know rules

- **Always launch the app in sandbox mode**: `python app.py --sandbox --port 8051`. Never run `python app.py` (production) unless the user explicitly asks.
- **Production DB (`data/skilltree.db`)** — reads and writes are allowed when the user is asking for graph review or programmatic node/edge changes against their real data. Do **not** use it as a scratchpad: no exploratory writes, no test fixtures, no app launches against it. When in doubt about whether a write is "graph editing the user asked for" vs "experimentation", confirm first.
- **Sandbox DB (`data/sandbox_skilltree.db`)** is the target for any app-launch testing or experimentation.
- **Ports:** sandbox on 8051, production on 8050 — kept distinct so the sandbox can run alongside your production instance.

## Domain model

Just enough to keep the right mental model — *not* a modeling manual. The conceptual guide (how to build a good graph) is [`docs/modeling.md`](docs/modeling.md); the scoring math is [`docs/scoring.md`](docs/scoring.md). Read those before editing node/edge/scoring machinery or doing a hands-on graph review.

**Node types** — **Goal** (a domain/capacity; a container and a scoring *sink*), **Learn** (a topic/body of knowledge), **Action** (a bounded practice/experiment), **Resource** (external material), **Milestone** (a measurable single-event checkpoint, **excluded from scoring**). The type changes scoring behavior, so it isn't just a label.

**Edge types** — **`Needs_Hard`** (blocking prerequisite), **`Needs_Soft`** (non-blocking but helpful prep), **`Helps`** (bidirectional synergy — *not* a weaker Soft; it reinforces rather than sequences, and does not cascade).

**Edge direction — the one thing I tend to get backwards.** `A --Needs_Hard/Soft--> B` means **A unlocks B**: A is the prerequisite, B is the dependent, and B stays Blocked until A is Done. Read the arrow as "leads to / unlocks," *not* "depends on." Value cascades **forward** along arrows (completing A flows discounted value to everything it unlocks); **eligibility runs backward** (a node is Blocked by its *incoming* hard prereqs). Mixing up these two directions has caused repeated bugs — [`docs/scoring.md`](docs/scoring.md) has the cascade math, the sink/leaf consequences, and the inverted-graph trick for ranking Goals by their prerequisite subtree.

## Where to look

Don't duplicate these in this file — they're the source of truth for their respective topics:

- [`docs/app_architecture.md`](docs/app_architecture.md) — the layering, module map, `dcc.Store` wiring, and the cross-file flows (mutation→render, right-click→editor, status cascade, scoring) plus versioning/caching.
- [`docs/scoring.md`](docs/scoring.md) — full math for scoring, profiles, goal ranking, explainability, status cascade.
- [`docs/time.md`](docs/time.md) — the PERT blend that produces `t(n)` and the Monte Carlo simulator behind the Time Simulation panel.
- [`README.md`](README.md) — full feature tour written for non-technical readers, grounded in the sandbox dataset.
- [`STYLE_GUIDE.md`](STYLE_GUIDE.md) — UI conventions (colors, typography, spacing, component styles). Consult before touching any UI; update it when you establish new patterns.

## Tech stack (one-liner)

Python 3.10, Dash + Dash Bootstrap Components (DARKLY theme), Dash Cytoscape, NetworkX, NumPy, SciPy, Plotly, SQLite via stdlib `sqlite3`. No bundler — JS in `assets/` is served raw.

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
- When you add a scoring-relevant field to `Node`, also add it to `graph_manager._SCORING_RELEVANT_FIELDS`, or the scoring cache won't invalidate and rankings silently go stale. See [`docs/app_architecture.md`](docs/app_architecture.md).
