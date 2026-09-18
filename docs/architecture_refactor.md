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

## Stage 5

`graph_state.revisions` owns process-wide graph/scoring revisions, publishing them
through the existing deduplicated commit callbacks. Each manager owns one
`GraphCaches` object. Query/scoring code uses these named caches; former private
attributes remain inspection aliases. Scoring and normalization keys now include
database identity, matching the existing read-cache isolation.

Synchronization, bounded cache sizes, cosmetic-edit reuse, rollback behavior, and
the single-database-per-process runtime remain unchanged. No lock narrowing was
attempted without a measured need. Validation: 128 focused tests passed.

## Stage 6

`assets/00_browser_bridge.js` owns native input dispatch, Cytoscape instance access,
and per-instance layout-hook composition. Feature assets use this boundary while
retaining their existing timing, registration order, and interaction policies.
The adapter preserves repeated input events, nested hook order, duplicate-hook
protection, and isolation when a canvas instance is replaced.

Validation: 72 focused browser contracts passed. Final regression run: 1,469 passed,
two optional real-database copy tests deselected. The old scoring-cache source-text
assertion now tests actual score refresh after changing the value exponent.
Sandbox browser checks covered Next, the Nodes canvas, context-menu editing and
an unchanged save, Details graph/subtasks/time simulation, and Events and Analyze.
No browser errors were reported during those checks. These are smoke checks, not
an exhaustive manual interaction audit. Production data was not used for testing.

The updated `app_architecture.md` describes the resulting ownership boundaries.
Scoring math, schema, callback wiring, transaction/cascade ordering, and locking
policy remain unchanged.

## Post-review cleanup

Review of the finished branch found the extraction sound — `GraphManager`'s public
surface, transaction decorators, `CoreResponse`'s field order and the browser
bridge's hook composition all match the pre-refactor behavior — with the remaining
work being compatibility scaffolding that no longer had callers. That scaffolding
is now gone:

- `generate_elements` takes the graph/event managers it renders with, and
  `register_callbacks` binds the `AppServices` instances to it. The canvas no
  longer renders through module globals while the callbacks mutate injected
  managers. Module-level managers remain as defaults for standalone callers.
- The re-export shims are removed. `callback_helpers` no longer re-exports
  `node_commands` and `context_rules`; `analyze_callbacks` no longer re-exports
  `goal_ranking`. Callers and tests import from the owning module.
- `layout.py`'s lazy `_TEMPLATE_BUILDERS` shim is deleted. Nothing referenced any
  of its twenty names, and it also turned former singletons into per-access
  rebuilds. This removes the `layout.next_view` / `next_view.py` name collision.
- `register_callbacks` and `register_sidebars_callbacks` got their docstrings
  back; the injected assignments had been placed above them, demoting each to a
  dead string expression.
- Unused imports left behind by the module split are removed, as is a dead
  `get_all_nodes()` call in `canvas_view.py` that predated the refactor and cost a
  full node read on every canvas render.
- `tests/test_architecture_boundaries.py` now enforces a layer rather than a
  naming convention: core logic modules may not import `callback_helpers`, which
  pulls in dash, dbc and plotly. View-preparation modules still may.
