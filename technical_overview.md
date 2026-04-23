# Technical Overview

*A developer's map of the Skill Tree codebase.*

This document is intended for anyone who wants to understand how the app actually works under the hood, beyond what individual file names and docstrings can tell you. It complements [`README.md`](README.md) (feature tour) and [`STYLE_GUIDE.md`](STYLE_GUIDE.md) (UI conventions).

---

## 1. The big picture

Skill Tree is a **single-page web app** built on Plotly's **Dash** framework, with an interactive graph rendered by **Cytoscape.js**, persistence through **SQLite**, and priority math that leans on **NetworkX**, **NumPy**, and **Plotly**.

The stack:

| Layer | Library | Role |
|---|---|---|
| Web framework | Dash + Flask | Routes, callbacks, layout-as-Python-objects |
| UI kit | Dash Bootstrap Components (DARKLY theme) | Buttons, modals, nav tabs, cards |
| Graph canvas | Dash Cytoscape (wraps Cytoscape.js) | The interactive node-link diagram |
| Graph algorithms | NetworkX | Cycle detection, subtree BFS, community detection |
| Numerics | NumPy, scipy-free PERT-Beta sampling | Monte Carlo duration simulation |
| Charts | Plotly | Histograms and heatmaps in the Details/Analyze tabs |
| Storage | SQLite (stdlib `sqlite3`) | Everything: nodes, edges, events, settings |
| Client-side JS | Plain vanilla JS in `assets/` (no bundler) | Context menus, tooltips, resize handles, drag ordering |

There is intentionally **no build step** on the front end. The JS in `assets/` is served statically by Dash, and everything stateful flows through Dash callbacks or `dcc.Store` components that JS can poke at directly.

---

## 2. Architecture at a glance

```
┌────────────────────────────────┐
│              app.py            │  entry point
└────────────────────────────────┘
              │
              ├── build_app_layout() ─► layout.py (+ details_layout.py,
              │                          events_layout.py, settings_layout.py,
              │                          analyze_layout.py)
              │
              ├── register_callbacks()       ─► callbacks.py       ┐
              ├── register_next_callbacks()  ─► next_callbacks.py  │
              ├── register_details_...       ─► details_callbacks  │ Dash wiring
              ├── register_event_...         ─► event_callbacks    │
              ├── register_settings_...      ─► settings_callbacks │
              └── register_analyze_...       ─► analyze_callbacks  ┘
                       │
                       │ call into
                       ▼
              ┌──────────────────┐
              │  callback_helpers │  stateless helpers shared by all tabs
              └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  graph_manager   │  SQLite CRUD + cascade logic + caches
              │  event_manager   │  Event/dormant-node lifecycle
              │  config          │  ConfigManager (Settings table facade)
              └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │    database.py   │  schema, migrations, connection factory
              │    scoring.py    │  pure scoring algorithm (no DB)
              │    simulation.py │  pure Monte Carlo (no DB)
              │    models.py     │  Node + Event dataclasses
              │    styles.py     │  Cytoscape stylesheet definitions
              └──────────────────┘
```

### Module-by-module responsibilities

#### Entry point

- [`app.py`](app.py) — Reads the `-sandbox` CLI flag into `config.ENVIRONMENT` **before** anything else imports `database` (the DB path depends on it). Initializes Dash with the DARKLY Bootstrap theme, builds the layout, and wires every tab's callbacks by calling its `register_*_callbacks(app)` function. Also defines a single Flask route, `/open-obsidian`, which resolves a relative vault path and launches the Obsidian URL scheme via `subprocess.Popen`.

#### Layout

- [`layout.py`](layout.py) — Top-level window: the tab bar, the main canvas, global `dcc.Store` components that every tab reads/writes, modals, and the editor sidebar. Delegates per-tab content to the smaller `*_layout.py` modules.
- [`details_layout.py`](details_layout.py), [`events_layout.py`](events_layout.py), [`settings_layout.py`](settings_layout.py), [`analyze_layout.py`](analyze_layout.py) — One file per tab, exposing a `build_*_tab_content()` that returns the Dash element tree.

#### Callbacks

Each tab's Dash reactivity lives in its own `*_callbacks.py`. They all follow the same shape: a single top-level `register_*_callbacks(app)` function that attaches decorated `@app.callback` closures. This keeps `app.py` agnostic about the internals and makes it easy to tree-shake callbacks in tests.

- [`callbacks.py`](callbacks.py) (~2k LOC) — The busiest one. Contains `generate_elements()` (the single source of truth for what Cytoscape sees), the node editor CRUD flow, the Nodes-tab right-click/double-click handlers, link management (Obsidian/Drive/Website), and the manual-override machinery.
- [`next_callbacks.py`](next_callbacks.py) — Small. Ranked list on the Next tab.
- [`details_callbacks.py`](details_callbacks.py) — Everything about the Details tab: sub-graph rendering, Monte Carlo, goal sidebar, navigation history, suggestions.
- [`event_callbacks.py`](event_callbacks.py) — Events tab CRUD, dormant-node editing, trigger handling.
- [`settings_callbacks.py`](settings_callbacks.py) — All settings forms and the migration flow for renamed contexts/types.
- [`analyze_callbacks.py`](analyze_callbacks.py) — Pure read-only computes (`_compute_*`) and their Plotly chart formatters (`_render_*`).

#### Stateless utilities

- [`callback_helpers.py`](callback_helpers.py) — The "not a callback but shared by callbacks" drawer: link row serialization, filter builders, `handle_save` / `handle_delete` / `handle_toggle_done` / `handle_group_delete` (extracted so they're directly testable without a Dash context), and suggestions-table formatters.

#### Domain layer

- [`graph_manager.py`](graph_manager.py) — The single gateway between callbacks and SQLite for node/edge data. Handles cascade status updates (a node auto-Blocks when any hard prerequisite isn't Done), cycle detection, filtered queries, subtree BFS, and the two internal cache invalidation counters (`_graph_version`, `_scoring_version`) that let higher-level caches skip work.
- [`event_manager.py`](event_manager.py) — Same shape as `GraphManager`, scoped to Events and EventNodes. Owns `check_pending_events()`, which is called on each relevant page load and after node completions to flip triggered events and their dormant nodes.
- [`config.py`](config.py) — `ConfigManager` is a classmethod-only facade over the `Settings` key/value table, with typed getters/setters for every stored preference. Also holds the `DEFAULT_*` constants used as first-run defaults and the global `ENVIRONMENT` flag that flips the DB path.

#### Pure modules (no DB, no Dash)

- [`scoring.py`](scoring.py) — The priority algorithm. Pure functions, fully testable without any state. See §4 for the algorithm's detail.
- [`simulation.py`](simulation.py) — Monte Carlo duration math. Pure NumPy.
- [`models.py`](models.py) — `Node` and `Event` dataclasses, edge-type constants, and the blended-PERT `time` property.

#### Infrastructure

- [`database.py`](database.py) — Schema DDL, idempotent `init_db()` (guarded by a module-level `_initialized` flag so it's safe to call from many places), and `ALTER TABLE` migrations for columns added over time.
- [`styles.py`](styles.py) — Cytoscape stylesheet (the JSON-ish dicts that tell Cytoscape how each node type and edge type should look).

#### Client-side

Vanilla JS files in `assets/` are auto-loaded by Dash. Each one attaches listeners to specific DOM elements and communicates with Python by writing to hidden `dcc.Store` inputs (using native HTML setters — see [§6](#6-the-js-dash-bridge)).

| File | Role |
|---|---|
| `context_menu.js` | Right-click menus on nodes (Edit / Details / Obsidian / Drive / Toggle Done / Delete) |
| `tooltip.js` | Hover tooltips with time/stats; show/hide delays, reposition to stay on-screen |
| `competence_popup.js` | The seven-level competence popup in the editor |
| `ratings_popup.js` | Value/Interest/Effort descriptions popup |
| `fullscreen.js` | Fullscreen toggle for any Cytoscape container |
| `resize_handle.js` | Drag-to-resize handles (horizontal and vertical) |
| `details_resize.js` | Multi-way resize coordinator for the Details tab |
| `details_goal_sortable.js`, `event_sortable.js` | Drag-to-reorder the goal / event lists |
| `drag_coordinator.js` | Single source of truth for "who is currently dragging" to stop two drag gestures from fighting |
| `cyto_lifecycle.js` | Rebinds Cytoscape listeners when Dash re-renders the canvas |
| `editor_sidebar.js`, `events_sidebar.js`, `filters_sidebar.js`, `goals_sidebar.js` | Sidebar open/close with CSS transitions |
| `link_open_visibility.js` | Disables the Open buttons on link rows when the URL/path field is empty |
| `locate_node.js` | Pan/zoom the graph to center a named node |

---

## 3. The data lifecycle: boot to first render

Tracing what happens from `python app.py -sandbox` to the moment you can click a node:

1. **CLI parsing.** `app.py` inspects `sys.argv` for `-sandbox`. If present, it mutates `config.ENVIRONMENT = "sandbox"` **before** anything else imports `database`. This ordering matters: `database.get_db_path()` reads `ENVIRONMENT` at call time to decide between `data/skilltree.db` and `data/sandbox_skilltree.db`.
2. **Schema init.** Every `GraphManager` / `EventManager` constructor (or direct call) invokes `database.init_db()`. That function is guarded by a module-level `_initialized` flag — it runs once per process, creates all five tables (`Nodes`, `Edges`, `Events`, `EventNodes`, `Aliases`, `Settings`) with `CREATE TABLE IF NOT EXISTS`, and attempts the additive migrations (`ALTER TABLE ... ADD COLUMN`) inside `try/except` so they're no-ops on an up-to-date DB.
3. **Default seeding.** `ConfigManager.ensure_action_type()` and `ensure_goal_type()` make sure the built-in node types exist in Settings. Any missing `Settings` key falls back to a `DEFAULT_*` constant from `config.py`.
4. **Layout construction.** `build_app_layout(initial_elements=generate_elements(), env=ENVIRONMENT)` runs. `generate_elements()` is the **single source of truth** for the Nodes-tab graph: it reads all nodes + edges from SQLite, applies any filters, and returns a flat list of Cytoscape element dicts. The layout tree includes this initial snapshot so the first paint has data.
5. **Callback wiring.** Six `register_*_callbacks(app)` calls attach every Dash callback. Each registration is independent — no callback function is shared across modules.
6. **HTTP server.** `app.run(debug=True, dev_tools_ui=False)` starts Flask on port 8050. `app.py` spawns a 0.5-second-delayed `webbrowser.open` so the tab pops up automatically.
7. **First HTTP request.** Dash serves the initial HTML + the bundled `assets/*.js`. The client-side JS modules attach their listeners. Cytoscape reads the seeded elements and renders the graph. The Next tab is the default active tab (tab order: Next → Nodes → Details → Events → Analyze → Settings).
8. **Interactive loop.** After first render, every user action triggers one or more `@app.callback`s. Most mutations end with a call to `generate_elements()` again, which Dash diffs into the Cytoscape component. The JS files keep running quietly, reacting to events the Python side doesn't know about (right-click menus, hover tooltips, drag gestures).

---

## 4. Core algorithms in plain English

### Priority scoring (`scoring.py`)

Every eligible active node is scored by:

```
score = eligibility * (total_value / perceived_cost)
```

- **Eligibility** is 1 if every hard prerequisite is Done, else 0. A zero-eligibility node is pushed to the bottom of the list.
- **Intrinsic value** of a node is `w_v * value + w_i * interest`, with `w_v` and `w_i` configurable hyperparameters.
- **Total value** is intrinsic value *plus* a recursive discounted sum over everything this node unlocks or synergizes with. A node that sits upstream of ten valuable tasks inherits some of their value, which is why foundational bottleneck tasks rise to the top naturally. The recursion has the discount factors `d_H` (hard edges out), `d_S` (soft edges out), and `d_Syn` (synergies).
- **Perceived cost** is `1 + w_e * difficulty + w_t * (time ** beta)`, where `beta < 1` makes the time penalty sub-linear (a 100-hour task is expensive but not 100× worse than a 1-hour task).
- **Goal boost.** The top three Priority Goals each multiply the scores of everything in their hard-prerequisite subtree — the #1 goal at full strength, #2 at ~66%, #3 at ~33%. Highest-rank boost wins if a node belongs to multiple priority subtrees.

`score_nodes()` composes the above, returning the active-nodes list sorted descending on `priority_score`.

#### A short history of `total_value()`

The Total Value recursion has gone through three stages as the graph grew. Each iteration fixed a performance wall the previous one eventually hit. Let `N` = nodes, `E_D` = Hard + Soft edges (which form a DAG — `graph_manager.add_edge` enforces this), `E_S` = Helps edges (which may form cycles, since Helps is bidirectional), `b` = average DAG branching factor, `d` = max DAG depth.

**Stage 1 — no memoization.** Pure recursive DFS with a per-call `visited` set as the only safeguard against cycles.

- Per outer call (scoring one node): **O(P(n))**, where `P(n)` is the number of distinct directed walks that respect the simple-path constraint imposed by `visited`. In a DAG with uniform branching, `P(n) ≤ b^d` — exponential in depth.
- `score_nodes` batch of N active nodes: **O(N · b^d)**.
- Why it was fine for a while: at ~300 nodes with shallow hierarchies and few cross-context edges, the subgraph reachable from any node was small. `b^d` stayed under ~100 and scoring ran in milliseconds.

**Stage 2 — outer-call memoization.** Same recursion, with one addition: the TOP-level call for each node is cached in an `external_memo` dict, keyed by name and invalidated via `_scoring_version` when the graph mutates. Inner recursive calls cannot safely read/write this memo because they're path-dependent (the `visited` set prunes differently depending on where the traversal started).

- First call in a batch: **O(N · b^d)** — no faster than Stage 1, because inside a single `score_nodes` batch each node is an outer call exactly once, so the memo never hits on inner recursion.
- Re-scoring the same graph (no mutation): **O(N)** lookups — every outer call is a cache hit.
- Amortized over K re-scorings: **O(N · b^d + K · N)**. Great for "sort the list again" interactions, useless for the batch itself.
- Why it eventually failed: the production DB grew past ~500 nodes with heavy cross-context edges. Hub nodes like `Science`, `Math`, and `Health` began pulling value-cascades from dozens of sources. A single foundational Learn's outer call recursed through thousands of simple paths, because each "visited-prunes-differently" branch forked independently at every diamond. The scoring callback is synchronous, so the UI froze.

**Stage 3 — DAG memoization + shallow Syn bonus.** Split the recursion by edge type:

1. `_tv_dag(n)`: recurses only over Hard + Soft out-edges. Because Hard+Soft is a DAG, the `visited` set never prunes differently across paths — so results are path-independent and safe to cache **globally**. Memoized across inner and outer calls. Each node is computed exactly once per batch.
2. `total_value(n)` adds a **depth-1 Syn bonus**: `d_Syn × _tv_dag(z)` for every immediate Helps neighbor `z` of `n`. No recursion through Syn edges — this is the tradeoff that avoids cycle complications without needing `visited` bookkeeping.

- `_tv_dag` amortized across the entire batch: **O(N + E_D)** (each node's computation visits its out-edges once).
- Syn bonus per outer call: **O(δ_Syn)** where δ_Syn is the node's Helps out-degree. Total: **O(N · δ_Syn̄) = O(E_S)**.
- `score_nodes` batch: **O(N + E_D + E_S) = O(N + E)**. Linear in graph size.
- Re-scoring unchanged graph: **O(N)** (memo hits throughout).

**Semantic change in Stage 3.** Stage 1 and 2 computed a deep mixed-edge walk where a synergy neighbor's DAG children's synergy neighbors' DAG children (and so on) all contributed to the score. Stage 3 keeps the DAG-cascade identical but truncates Syn at depth 1. Test suite confirms exact equivalence for pure-DAG graphs. For graphs with Helps edges, scores differ slightly in absolute value but rank ordering is preserved — and the user's stated intent for Helps ("synergistic sibling") maps more cleanly to depth-1 anyway.

**Scaling back of the envelope**, for a graph with properties like the production DB (1.7 edges/node, branching ≈ 2, depth ≈ 8):

| N | Stage 1 / 2 (first-batch) ops | Stage 3 ops | Expected speedup |
|---|---|---|---|
| 300 | ~10⁴ | ~10³ | ~10× |
| 500 | ~10⁵ – 10⁶ (empirically hangs UI) | ~10³ | ~100–1000× |
| 1000 | ~10⁶ – 10⁷ | ~3·10³ | ~300–3000× |

Stage 3's cost grows linearly, Stage 1/2's grows worse than linearly and is dominated by a constant-factor `b^d` term that inflates as the graph gets more connected. At 487 nodes / 832 edges the actual observed speedup was ~4000× (30 s → 7 ms).

### Cascade status (`graph_manager._update_node_state`)

A node's status is Open, Blocked, or Done. Done is set manually. Blocked is derived: any node with at least one incomplete hard prerequisite is Blocked. When a node flips to Done (or is added, deleted, or has edges changed), `_update_dependent_nodes_state` walks its hard-downstream dependents and recomputes their status recursively. Each mutation bumps `_graph_version` (for UI invalidation) and, if the change touched a scoring-relevant field, `_scoring_version` (for the priority memo).

### Helps-edge semantics in `get_goal_subtree`

`get_goal_subtree` walks a goal's prerequisite tree over a caller-supplied set of edge types. For the directed types (`Needs_Hard`, `Needs_Soft`) it recurses in the usual way. For `Helps`, traversal is **seed-only**: direct synergy partners of the goal are added (bidirectionally, 1 step), but BFS from those partners only follows directed types. Helps does not chain.

The reason: an earlier version walked `Helps` transitively AND cascaded Hard/Soft from every Helps-reached node. Because `Helps` is bidirectional and the graph is densely synergy-linked, the Details tab's Synergies toggle would pull in most of the graph for well-connected goals (measured: 3 direct partners → 305 nodes for `Problem Solving`). Seed-only keeps Synergies-on focused on "direct partners + what you'd need to unlock them."

The Details tab's relationship column uses set arithmetic to label Synergy nodes: `overall_subtree − hard_soft_subtree`, so a partner's Hard prereq is correctly tagged "Synergy" rather than "Soft" (see [`details_layout.build_details_subtasks_table`](details_layout.py)).

### PERT time (`models.Node.time`)

The `time` property on a Node blends three estimates (optimistic, most likely, pessimistic) into one number. Low-uncertainty estimates (pessimistic/optimistic ratio ≤ 2) use the classic arithmetic PERT mean `(o + 4m + p) / 6`. High-uncertainty estimates (ratio ≥ 10) use the geometric/log mean. Between those bounds, it smoothly interpolates. There are also fallbacks for when only partial estimates are provided. The result is what shows up everywhere in the UI as "Time."

### Event activation (`event_manager.check_pending_events`)

An Event has one of three trigger types:

- **Manual** — the user clicks a button.
- **Date** — the event has a `trigger_date` and today's date is ≥ that value.
- **Node** — the event has a `trigger_node` and that node's status is Done.

When an event triggers, `check_pending_events` iterates its attached `EventNodes` rows. Each has a `delay_days` offset — the wake-up date becomes `event_date + delay_days`. If that date has arrived (or the delay is zero), the dormant node flips to active (`dormant = 0`). Any `override_on_trigger` flag gets applied at the same time.

### Monte Carlo simulation (`simulation.simulate_task_chain`)

For a target node, BFS walks backward through the dependency graph (hard by default; soft/synergies optional at the target level), collecting every incomplete prerequisite. Each one is sampled 10,000 times from a PERT-Beta distribution whose `alpha` and `beta` parameters come from the three-point estimate (`lambda=4` weighting). The per-simulation total is the **serial sum** of all sampled durations — the assumption is one person working on one task at a time. `_compute_stats` reduces the 10,000 samples into mean, std, percentiles (p10/p25/p50/p75/p90), min, max.

---

## 5. Data structures in memory

### `Node` (dataclass, `models.py`)

| Field | Type | Notes |
|---|---|---|
| `name` | str | Primary key. Renaming cascades through edges, events, aliases, and overrides. |
| `type` | str | One of `Learn`, `Action`, `Goal`, `Resource` (user-extensible in Settings). |
| `description` | str | Free-text user notes. |
| `value` | int 1-10 | User rating — how important is this? |
| `interest` | int 1-10 | User rating — how fun/engaging? |
| `difficulty` | int 1-10 | User rating — how hard? (Stored as "difficulty"; labeled "Effort" in the UI.) |
| `time_o` | float | Optimistic estimate, in hours. |
| `time_m` | float | Most-likely estimate, in hours. |
| `time_p` | float | Pessimistic estimate, in hours. |
| `time_mode` | str | `'manual'` (use the three-point fields) or `'inherited'` (pull from hard prereqs). |
| `status` | str | `Open`, `Blocked`, or `Done`. `Blocked` is derived from prereq state. |
| `competence` | Optional[str] | Seven-level skill tier (`Outsider` → `Innovator`). |
| `context` / `subcontext` | Optional[str] | Life area and sub-area (Health → Exercise, etc.). |
| `obsidian_path` / `google_drive_path` / `website` | Optional[str] | Legacy single-link fields. Multi-link data now lives in Dash stores. |
| `dormant` | int | `1` while attached to a pending event; `0` once active. |
| `priority_score` | Optional[float] | Populated by `scoring.score_nodes()`; not persisted. |
| `time` | float (`@property`) | Computed blended PERT estimate. Not a stored field. |

### Edges

Stored as plain `dict` rows `{'source': str, 'target': str, 'type': str}` with composite primary key `(source, target, type)`. Three real edge types plus a deprecated one:

| Type | Meaning |
|---|---|
| `Needs_Hard` | Target is Blocked until source is Done. Gates eligibility in scoring. |
| `Needs_Soft` | Source helps but doesn't block. Contributes discounted value. |
| `Helps` | Mutually boosts both endpoints. Symmetric — one row expresses the whole relationship. |
| `Resource` | **Deprecated.** Migrated to `Needs_Soft` at startup; constant kept only for legacy rows. |

### `Event` (dataclass) + `EventNodes` table

Events are simple:

| Field | Type | Notes |
|---|---|---|
| `name` | str | Primary key. |
| `description` | str | Free-text. |
| `status` | str | `Pending` or `Triggered`. |
| `trigger_date` | Optional[str] | ISO date (`YYYY-MM-DD`) for date-based triggers. |
| `trigger_node` | Optional[str] | Node name for node-completion triggers. |

Manual, date, and node triggers are distinguished by which of `trigger_date` / `trigger_node` is populated (both null → manual).

`EventNodes` is the attachment table — one row per (event, dormant node) pair:

| Field | Type | Notes |
|---|---|---|
| `event_name` | str | FK to `Events.name`. Part of composite PK. |
| `node_name` | str | FK to `Nodes.name`. Part of composite PK. |
| `delay_days` | int | Offset from the trigger date before this node wakes up. |
| `activation_date` | Optional[str] | Computed at trigger time: `trigger_date + delay_days`. |
| `activated` | int | `0` = still dormant, `1` = woken up and the node's `dormant` flag flipped. |
| `override_on_trigger` | int | If `1`, apply a priority override when the node activates. |
| `override_mode` | Optional[str] | Which override mode to apply (see manual override docs in scoring). |

### The graph at runtime

**During a request**, the shape of the graph is held two ways:

- **As Dash/Cytoscape elements** — a flat Python list of element dicts (`{'data': {...}, 'classes': '...'}`), what `generate_elements()` returns and what the browser actually sees.
- **As NetworkX `DiGraph`** — built on-demand inside `GraphManager` methods that need graph algorithms (cycle check, subtree BFS, Louvain community detection). These graphs are cheap to build because the node/edge count is small.

**Settings** are stored in a tiny `Settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)` table, where `value` is JSON. `ConfigManager.get_*` parses on read, `set_*` serializes on write — no in-process cache, which is what keeps multi-instance consistency painless.

---

## 6. The JS–Dash bridge

Dash's normal flow is: user interacts with a Dash component → callback runs on the server → server sends new props → component re-renders. That's great for buttons and dropdowns, but awful for the fine-grained interactivity the Nodes tab needs (right-click menus, hover tooltips, drag gestures).

The pattern used throughout `assets/*.js`:

1. JS listens for a DOM event (right-click, hover, drag, etc.).
2. JS writes the event payload into a hidden `<input>` element — **using the native value setter** (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, JSON.stringify(payload))`).
3. JS dispatches an `input` event so React (which Dash uses internally) notices the mutation.
4. A Dash callback keyed on that input fires and does the Python-side work.

Skipping the native setter and just assigning `el.value = ...` doesn't work — React tracks the previous value on the element and ignores the change. The verbose prototype-descriptor pattern is the canonical workaround.

When you see a hidden `<input id="edit-trigger-input">` or `<input id="delete-trigger-input">` in the layout, that's what's going on — a JS-to-Python mailbox.

---

## 7. Testing

- Tests live in `tests/` and use a `temp_database` fixture (`monkeypatch` points `database.get_db_path` at a per-test `tmp_path`). Production and sandbox DB files are never touched.
- Suites are organized by module: `test_backend.py` (Node/Graph/scoring), `test_callbacks.py` (handler shims), `test_events.py`, `test_helpers.py`, `test_simulation.py`, `test_analyze.py`, plus regression tests like `test_generate_elements_regression.py` and `test_populate_editor_arity.py`.
- Run with `pytest` from the repo root. The suite currently has 600+ tests and runs in ~20 seconds.

---

## 8. Conventions worth knowing

- **Element regeneration after mutations.** Most callbacks that change the graph end by returning a fresh `generate_elements(...)` result. Partial updates aren't the style — the source of truth is SQLite, so re-deriving the element list is simple and avoids divergence.
- **Pattern-matching callback IDs.** Dynamically-generated components (link rows, context menu items, filter chips) use Dash's `ALL` and `{'type': 'x', 'index': n}` dict IDs so a single callback can handle a variable number of inputs.
- **The `register_*_callbacks(app)` signature.** Every tab module exposes exactly one public function with that name. `app.py` doesn't need to know anything else. New tab? Add one more `register_*` call in `app.py`.
- **Cache invalidation counters.** `GraphManager._graph_version` bumps on every write; `_scoring_version` only bumps on scoring-relevant writes. Higher-level caches (like the scoring memo and the goal-subtree cache) check these counters to decide whether to reuse results.
- **Flask side-route.** The one-off `/open-obsidian` route in `app.py` exists because Obsidian's URL scheme only works reliably when invoked from a real shell, and the only way to escape Chrome's click-handler sandbox is a server-side shell-out.
- **Edge PK is composite.** `(source, target, type)` — the *same* two nodes can have both a Hard Prerequisite and a Synergy between them, because they're different rows.
- **Node rename is intentionally atomic.** `GraphManager.rename_node` temporarily disables foreign keys, updates the `Nodes` row, then updates every table that references the old name (`Edges`, `Events`, `EventNodes`, `Aliases`), then re-enables FKs. This avoids the cascade-delete you'd otherwise trigger by changing a primary key.
