# App Architecture

This document covers how the app is organized — modules, the tab-callback pattern, the Cytoscape rendering pipeline, the JS–Dash bridge, and how persistence and caching are coordinated. For the math that drives recommendations, see [algorithms.md](algorithms.md). For the user-facing tour, see [README.md](../README.md).

## Module Map

| Module | Role |
|---|---|
| [app.py](../app.py) | Entry point. Sets `config.ENVIRONMENT`, configures logging, runs startup migrations and the `recompute_all_statuses` safety net, registers each tab's callbacks. |
| [models.py](../models.py) | `Node` and `Event` dataclasses, the `blend_time_estimate` PERT blend, edge / status constants. |
| [database.py](../database.py) | Thin sqlite3 wrapper. Resolves the active DB path from `config.ENVIRONMENT` and runs `init_db` on first connection. |
| [config.py](../config.py) | Module-level defaults and `ConfigManager`, a classmethod-only facade over the `Settings` key/value table. |
| [graph_manager.py](../graph_manager.py) | Single gateway for graph state. Node/edge CRUD, cycle detection, status cascade, scoring memo, version counters. |
| [event_manager.py](../event_manager.py) | Same pattern as GraphManager, for the `Events` table and dormant-node activation. |
| [scoring.py](../scoring.py) | Pure functions. Build adjacency from edges, walk it, return ranked nodes. No DB access. |
| [simulation.py](../simulation.py) | Monte Carlo time simulation. Pure NumPy. |
| [callbacks.py](../callbacks.py) | Registers the `core_engine` callback that owns the Cytoscape canvas. `generate_elements(...)` lives here. |
| [callback_helpers.py](../callback_helpers.py) | Stateless helpers extracted from the larger `*_callbacks.py` files (link parsing, filters, form-state diffs). |
| [layout.py](../layout.py) + `*_layout.py` | Dash layout factories. No callbacks. |
| [styles.py](../styles.py) | Dash component style dicts. |
| [assets/](../assets) | Served raw. Cytoscape extension hooks, sidebar JS, the JS-Dash value-setter bridge (below). |
| Tab modules | [next_callbacks.py](../next_callbacks.py), [details_callbacks.py](../details_callbacks.py), [analyze_callbacks.py](../analyze_callbacks.py), [event_callbacks.py](../event_callbacks.py), [settings_callbacks.py](../settings_callbacks.py), [sidebars_callbacks.py](../sidebars_callbacks.py). Each exposes one `register_*_callbacks(app)`. |

## Tab Callbacks

Each tab module exposes one entry point: `register_*_callbacks(app)`. The function attaches every Dash callback the tab needs in a single bottom-up pass and returns nothing. [`app.py`](../app.py) imports each module and calls each `register_*` exactly once. Adding a tab is one new module plus one new `register_*` line.

The pattern decouples the tabs from each other — a tab module only sees the `app` instance and the three shared persistence layers (`GraphManager`, `EventManager`, `ConfigManager`), never another tab's internals. Cross-tab coordination happens through the persistence layer (DB writes flip version counters; other tabs see the change on their next callback).

## Cytoscape Pipeline

Cytoscape is the canvas that renders the graph on the Nodes, Details, and Events tabs. Every callback that mutates graph state ends by returning a fresh `generate_elements(...)` result. That function is the single source of truth for what Cytoscape sees: it reads filtered nodes from `GraphManager`, applies depth and neighbor-link controls, and assembles the Cytoscape element list (nodes + edges with their visual properties).

## JS-Dash bridge

Some interactions require Python to push a value into a React-controlled `<input>` (e.g., populating the editor from a right-click). React only re-renders when its internal value descriptor sees a `set` call — plain `el.value = "x"` is silently ignored. The bridge in [`assets/`](../assets) uses:

```js
Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
el.dispatchEvent(new Event("input", { bubbles: true }));
```

This is the only way to programmatically poke a controlled input and have React notice.

## Persistence Layers and Caching

`ConfigManager` is classmethod-only. Every `get_*` round-trips through the `Settings` SQLite table; there is no in-process cache. This is why the per-tab `GraphManager` instances (each tab module constructs its own) stay coherent — a value the Settings tab writes is immediately visible to the next read from any other tab.

`GraphManager` carries two class-level version counters:

- `_graph_version` — bumps on any node or edge mutation. Used by UI-level caches.
- `_scoring_version` — bumps only when a *scoring-relevant* field changes (`type`, `value`, `interest`, `difficulty`, `time_o/m/p`, `time_mode`, `value_mode`, `status`, `dormant`). Cosmetic edits (description, paths, context, aliases) bump `_graph_version` only.

A per-instance scoring memo persists `total_value` results across `score_nodes` calls; it is keyed by `_scoring_version` and dropped when that counter advances. Filter toggles, priority-goal changes, and cosmetic edits all leave it intact, so the next scoring run is near-free.

Because the counters are class attributes, every `GraphManager` instance in the process sees the same version. A mutation in any callback module is visible to every other module's cache on the next access.
