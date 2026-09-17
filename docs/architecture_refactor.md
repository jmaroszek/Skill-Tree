# Architecture refactor checkpoints

Branch: `codex/architecture-refactor`.

The goal is clearer ownership with unchanged scoring, persisted data, callback
payloads, and interaction behavior. Database schema fixes are separate work.

1. Extract shared business logic and view preparation from callback modules.
2. Make application construction and startup explicit.
3. Extract core callback responsibilities while preserving its Dash wiring.
4. Separate graph persistence, rules, and query responsibilities behind the existing gateway.
5. Make revision and cache ownership explicit; retain synchronization unless measurements justify a change.
6. Consolidate browser integration behind shared adapters.

## Stage 1

- `goal_ranking.py`: ranking, normalization, and explanations shared by Analyze,
  Details, and the Goals sidebar.
- `graph_analytics.py`: analytics data preparation, separate from Dash/Plotly rendering.
- `node_commands.py`: existing editor save/delete/status operations with unchanged
  transaction boundaries.
- `context_rules.py`: pure context migration rules, usable by the state gateway.
- `editor_values.py`: shared editor and calibration values without callback imports.
- `next_view.py`: Next queries and initial view hydration, usable by layout and callbacks.

Former locations re-export extracted functions to preserve existing Python callers.
Boundary tests prevent shared modules from depending on callback registration again.

Validation: 1,451 regression tests passed (the two optional real-database copy
tests were excluded); eight dependency-boundary checks passed.

## Stage 2

`create_app(AppSettings(...))` now selects the environment, initializes the schema,
seeds required configuration, repairs status drift, constructs the layout, and
registers callbacks. `main()` retains browser/Electron launch behavior. Importing
application modules no longer initializes SQLite or installs logging handlers.

`AppServices` owns the graph/event managers captured by registered callbacks.
Standalone helper APIs retain inert default managers for compatibility; the process
still owns one database, as before. Layout component factories replace templates
that previously queried settings at import time. Former template names remain
available to Python callers through lazy construction.

Validation: 1,460 tests passed, excluding the two optional real-database copy tests.

## Stage 3

The core callback retains its existing Inputs, Outputs, trigger gates, mutation
order, and modal flow. `canvas_view.py` owns visual preparation, `sidebar_state.py`
owns sidebar/draft decisions, and `CoreResponse` names the 28 output fields. Partial
responses and the final response use named fields; compatibility indices are derived
from that contract instead of being independently maintained magic numbers.

Validation: 150 focused callback, editor, calibration, atomic-save, and Next tests passed.

## Stage 4

`GraphManager` remains the public gateway and transaction owner. It delegates row
reads and node insert/update/rename persistence to `GraphRepository`, traversal and
view queries to `graph_queries.py`, scoring orchestration to `graph_scoring.py`, and
pure endpoint/prerequisite rules to `graph_rules.py`. Mutations, status cascades,
completion notifications, and transaction decorators remain together in the gateway.
Repository writes join the same connection lease, including lifecycle-history writes.

Validation: 541 backend, transaction, consistency, snapshot, scoring, Details graph,
and habit tests passed.
