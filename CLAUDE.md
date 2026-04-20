# Skill Tree — Claude context

Task-prioritization app. A directed graph of nodes (tasks/goals) and typed edges (prerequisites / synergies) is ranked by an ROI-based scoring algorithm to tell the user what to work on next. Dash + Cytoscape.js frontend, Python backend, SQLite storage.

## Must-know rules

- **Always launch the app in sandbox mode**: `python app.py -sandbox`. Never run `python app.py` (production) unless the user explicitly asks.
- **Production DB (`data/skilltree.db`) is off-limits** for any writes or experimentation. Sandbox DB (`data/sandbox_skilltree.db`) is the only safe target.
- **Do not visually test the app.** The user handles all manual / browser QA themselves. Only run `pytest` for verification.
- **Port is 8050.**

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
