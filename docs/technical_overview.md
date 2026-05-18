# Technical Overview

*A developer's map of the Skill Tree codebase.*

This document is intended for anyone who wants to understand how the app actually works under the hood, beyond what individual file names and docstrings can tell you. It complements [`README.md`](../README.md) (feature tour) and [`STYLE_GUIDE.md`](../STYLE_GUIDE.md) (UI conventions).

---

## Getting started

### First-time setup

```bash
# Install dependencies (Python 3.10)
conda env create -f environment.yml
conda activate skill-tree
```

### Launching

```bash
# Sandbox mode — uses the example dataset (data/sandbox_skilltree.db).
# Safe to experiment with: edits don't touch the production graph.
python app.py --sandbox

# Production mode — uses data/skilltree.db.
python app.py
```

The app starts a local web server and auto-opens your browser at `http://127.0.0.1:8050`. The window title displays **"Skill Tree (Sandbox)"** in sandbox mode and **"Skill Tree"** in production, so you always know which database is live.

### Where the data lives

| File | Role |
|---|---|
| `data/skilltree.db` | Production database. Your real graph. |
| `data/sandbox_skilltree.db` | Sandbox database — a worked example dataset (currently ~750 nodes across eight life-area contexts). |
| `data/sandbox_skilltree.db` and `data/skilltree.db` schema | Identical — managed by `database.py`'s migrations. |

Both databases live under `data/` and are SQLite files. Everything — nodes, edges, events, settings, hyperparameters — is in one DB; no cache layer, no separate config file.

### Running tests

```bash
pytest
```

Tests use a `temp_database` fixture that monkeypatches `database.get_db_path()` to a per-test `tmp_path`. No test touches the sandbox or production DBs. Coverage spans 600+ tests across scoring math, graph mutations, event lifecycle, and UI helpers.

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

- [`app.py`](app.py) — Reads the `--sandbox` CLI flag into `config.ENVIRONMENT` **before** anything else imports `database` (the DB path depends on it). Initializes Dash with the DARKLY Bootstrap theme, builds the layout, and wires every tab's callbacks by calling its `register_*_callbacks(app)` function. Also defines a single Flask route, `/open-obsidian`, which resolves a relative vault path and launches the Obsidian URL scheme via `subprocess.Popen`.

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
- [`event_manager.py`](event_manager.py) — Same shape as `GraphManager`, scoped to Events and EventNodes. Owns `check_pending_activations()` (delayed dormant nodes whose date has arrived) and `check_scheduled_triggers()` (date-based events that are now due) — called on each relevant page load. Node-completion events flow through `auto_trigger_by_node_completion()`, fired automatically inside `GraphManager.update_node` whenever a node transitions to Done.
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
| `goal_context_menu.js` | Right-click menu specifically for Goal nodes in the Goals sidebar (set/clear Priority Goal slot, etc.) |
| `tooltip.js` | Hover tooltips with time/stats; show/hide delays, reposition to stay on-screen |
| `ratings_popup.js` | Value/Interest/Effort descriptions popup |
| `fullscreen.js` | Fullscreen toggle for any Cytoscape container |
| `resize_handle.js` | Drag-to-resize handles (horizontal and vertical) |
| `details_resize.js` | Multi-way resize coordinator for the Details tab |
| `details_goal_sortable.js`, `event_sortable.js` | Drag-to-reorder the goal / event lists |
| `freeze_positions.js` | Persists per-canvas drag positions so the physics engine doesn't reshuffle hand-arranged corners on relayout |
| `drag_coordinator.js` | Single source of truth for "who is currently dragging" to stop two drag gestures from fighting |
| `cyto_lifecycle.js` | Rebinds Cytoscape listeners when Dash re-renders the canvas |
| `editor_sidebar.js`, `events_sidebar.js`, `filters_sidebar.js`, `goals_sidebar.js` | Sidebar open/close with CSS transitions |
| `link_open_visibility.js` | Disables the Open buttons on link rows when the URL/path field is empty |
| `locate_node.js` | Pan/zoom the graph to center a named node |
| `graph_settings_dismiss.js` | Click-outside-to-close behavior for the per-canvas layout-settings popovers |
| `disable_number_wheel.js` | Stops scroll-wheel from inadvertently incrementing numeric inputs in the editor |
| `hard_reload_on_restart.js` | Forces a full page reload when the dev server restarts (catches edits to non-Dash assets that wouldn't otherwise hot-reload) |
| `custom.css`, `theme.css` | Global styling; see [`STYLE_GUIDE.md`](../STYLE_GUIDE.md) for the conventions they enforce |
| `trigger_badge.svg` | Static asset — badge shown on event tiles. |

---

## 3. The data lifecycle: boot to first render

Tracing what happens from `python app.py --sandbox` to the moment you can click a node:

1. **CLI parsing.** `app.py` inspects `sys.argv` for `--sandbox`. If present, it mutates `config.ENVIRONMENT = "sandbox"` **before** anything else imports `database`. This ordering matters: `database.get_db_path()` reads `ENVIRONMENT` at call time to decide between `data/skilltree.db` and `data/sandbox_skilltree.db`.
2. **Schema init.** Every `GraphManager` / `EventManager` constructor (or direct call) invokes `database.init_db()`. That function is guarded by a module-level `_initialized` flag — it runs once per process, creates all six tables (`Nodes`, `Edges`, `Events`, `EventNodes`, `Aliases`, `Settings`) with `CREATE TABLE IF NOT EXISTS`, and attempts the additive migrations (`ALTER TABLE ... ADD COLUMN`) inside `try/except` so they're no-ops on an up-to-date DB.
3. **Default seeding.** `ConfigManager.ensure_action_type()`, `ensure_goal_type()`, and `ensure_milestone_type()` make sure the four built-in node types beyond Resource (`Learn` is in `DEFAULT_NODE_TYPES`; `Action`, `Goal`, `Milestone` are seeded into the Settings table at startup if missing) exist. Any missing `Settings` key falls back to a `DEFAULT_*` constant from `config.py`.
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
score = eligibility
        * (total_value / perceived_cost)
        * goal_boost_if_applicable
        * context_weight(n.context)
        * (1 / n_active[(n.context, n.subcontext)] ** alpha)
```

- **Eligibility** is 1 if every hard prerequisite is Done, else 0. A zero-eligibility node is pushed to the bottom of the list.
- **Intrinsic value** of a node is `w_v * value + w_i * interest`, with `w_v` and `w_i` configurable hyperparameters. Short-circuits to `0` when `value_mode='inherited'` (see Container modes below).
- **Total value** is intrinsic value *plus* a recursive discounted sum over Hard/Soft prereqs (the DAG cascade), plus an M3 hybrid synergy contribution. The synergy contribution has two parts: a small **additive pair bonus** `d_Syn_pair × tv(partner)` summed over immediate synergy neighbors regardless of their state, and a **multiplicative kick on intrinsic value** that fires when a synergy partner is Done — `intrinsic × (1 + d_Syn_mul × sqrt(count_done_partners))`. The sqrt is a diminishing-returns cap: 1 partner gives the full d_Syn_mul kick, 4 partners give 2×, 16 give 4× — preserving "more partners = more boost" while keeping dense synergy hubs from running away. The multiplier applies to *intrinsic only*, not to the cascade. Two hyperparameters (`d_Syn_pair` ≈ 0.10, `d_Syn_mul` ≈ 0.40 in the Sage profile) replace the single old `d_Syn`. The asymmetry encodes the semantic distinction: synergy is a *categorically different* relationship from Hard/Soft (mutual reinforcement, not directional dependency), so it doesn't sit on the same "necessity" axis. The pair-bonus term can be further scaled by `cross_context_mult` when the synergy partner sits in a different context from the node being scored — this is the Creator profile's lever for rewarding lateral cross-domain links over within-domain synergies. Defaults to 1.0 (off) for every other profile.
- **Perceived cost** is `1 + w_e * difficulty + w_t * (time ** beta)`, where `beta < 1` makes the time penalty sub-linear (a 100-hour task is expensive but not 100× worse than a 1-hour task). The difficulty term short-circuits to `0` when `value_mode='inherited'`; the time term short-circuits to `0` when `time_mode='inherited'` (see Container modes below).
- **Goal boost.** The top three Priority Goals each multiply the scores of everything in their hard-prerequisite subtree — the #1 goal at full strength, #2 at ~66%, #3 at ~33%. Highest-rank boost wins if a node belongs to multiple priority subtrees.
- **Context weight.** User-assigned per parent context; defaults to 1.0. Subcontexts inherit their parent's weight. Lets the user state cross-context importance explicitly ("Health > abstract math") even before decomposing those areas. Persisted under the `CONTEXT_WEIGHTS` Settings key.
- **Density normalization.** `1 / n_active[(context, subcontext)] ** alpha`, where `n_active` counts active (not Done, not Blocked, not type=Goal) nodes in the target's `(context, subcontext)` bucket. The `alpha` hyperparameter tunes strength: 0 disables, 0.5 compensates moderately, 1.0 fully cancels size bias. Motivation: without this, a heavily decomposed context crowds top-N recommendations regardless of its cross-context importance, because the cascade sums contributions without normalizing for granularity. Per-profile defaults are conservative (0.20–0.30) — the user feels the effect but can dial up/down via Custom.

Both context weight and density multipliers apply **after** TV/cost — the cascade itself and its memoization are untouched.

`score_nodes()` composes the above, returning the active-nodes list sorted descending on `priority_score`.

#### Container modes (`time_mode` / `value_mode`)

Two orthogonal flags let a node opt out of contributing its own ratings to scoring, leaving it as a structural conduit whose score depends entirely on what cascades up from descendants. Both default to `'manual'`; either or both can be set to `'inherited'` per node.

- **`time_mode='inherited'`** zeros the time term in `perceived_cost`. The `Node.time` property short-circuits to `0`, and `_compute_priority_score` passes `time_override=0.0`. Use when a node has no marginal time of its own — its work is just completing its hard children. Common case: a Goal node whose total effort is the sum of its sub-Learns.
- **`value_mode='inherited'`** zeros the **intrinsic-value AND difficulty** terms together. `intrinsic_value()` short-circuits to `0`, and `_compute_priority_score` passes `effort_override=0.0` to `perceived_cost`. The node still passes cascade upward to its parents — only its own ratings drop out. Use for *pure container* nodes that exist purely to group children (the canonical "header" Learn whose value IS its descendants).

The four combinations are all valid and mean different things:

| `time_mode` | `value_mode` | Meaning | Example |
|---|---|---|---|
| `manual` | `manual` | **Atomic node.** Has its own time, ratings, and cost. Standard case for Learns, Resources, and most Actions. | A book with concrete reading time and a value/interest rating |
| `inherited` | `manual` | **Time-aggregating Learn.** Has its own intrinsic value (the domain matters in itself) but its time rolls up from children. | A `Mastery` Learn header with rated importance, holding three book Resources |
| `manual` | `inherited` | **Rare.** Effort + value zeroed but time stays manual. Mostly arises mid-edit while toggling. Not a typical persistent state. | — |
| `inherited` | `inherited` | **Pure container.** No own time, no own value, no own effort — the node is purely structural. Score = cascade / (1 + 0 + 0) = cascade. | A `Transcendentalism` Learn that exists only to group `Walden` and `Emerson Essays` under American Philosophy |

Settings are persisted as text columns on the `Nodes` table (added via auto-migration in `database.init_db`). Toggles in the editor sidebar live next to the Override switch (`value_mode`) and inside the Time Estimates section (`time_mode`); the Add-Node modal mirrors both.

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
2. `total_value(n)` adds a **depth-1 Syn pair bonus**: `d_Syn_pair × _tv_dag(z)` for every immediate Helps neighbor `z` of `n`, plus a **completion multiplier on intrinsic value** of the form `iv × (1 + d_Syn_mul × sqrt(done_partner_count))`. No recursion through Syn edges — depth-1 only, so no cycle bookkeeping needed.

- `_tv_dag` amortized across the entire batch: **O(N + E_D)** (each node's computation visits its out-edges once).
- Syn loop per outer call: **O(δ_Syn)** where δ_Syn is the node's Helps out-degree. Each iteration accumulates the pair bonus and tests the partner's status for the multiplier. Total: **O(N · δ_Syn̄) = O(E_S)**.
- `score_nodes` batch: **O(N + E_D + E_S) = O(N + E)**. Linear in graph size.
- Re-scoring unchanged graph: **O(N)** (memo hits throughout).

**Semantic change in Stage 3.** Stages 1 and 2 computed a deep mixed-edge walk where a synergy neighbor's DAG children's synergy neighbors' DAG children (and so on) all contributed to the score. Stage 3 keeps the DAG cascade identical but truncates Syn at depth 1, capturing the user's "synergy = lateral mutual reinforcement, not transitive prereq" intent more cleanly anyway.

**Stage 3.1 — M3 hybrid synergy.** Replaced the single additive `d_Syn × _tv_dag(z)` term with a two-part scheme: a small partner-state-blind pair bonus (`d_Syn_pair × _tv_dag(z)`) plus a multiplicative kick on intrinsic value when partners are Done (`iv × (1 + d_Syn_mul × sqrt(count_done_partners))`). The pair bonus encodes "the user marked these two as related, so co-promote them"; the multiplier encodes "doing both is more than the sum of doing each alone" — kicks in only after at least one partner is Done. The sqrt is a diminishing-returns cap added in the correctness-hardening pass: a single Done partner gives the full d_Syn_mul kick (sqrt(1)=1), but a hub of 16 partners only gives 4× that — preventing dense synergy networks from inflating any single node's score unboundedly. Multiplier applies to intrinsic only, not to the cascade or the pair bonus, so completing a synergy partner doesn't artificially amplify upstream Hard prereqs. Test suite covers: partner Open ⇒ multiplier dormant; partner Done ⇒ multiplier active; multiple Done partners accumulate sub-linearly via sqrt; pure-DAG nodes are unaffected by synergy params.

**Scaling back of the envelope**, for a graph with properties like the production DB (1.7 edges/node, branching ≈ 2, depth ≈ 8):

| N | Stage 1 / 2 (first-batch) ops | Stage 3 ops | Expected speedup |
|---|---|---|---|
| 300 | ~10⁴ | ~10³ | ~10× |
| 500 | ~10⁵ – 10⁶ (empirically hangs UI) | ~10³ | ~100–1000× |
| 1000 | ~10⁶ – 10⁷ | ~3·10³ | ~300–3000× |

Stage 3's cost grows linearly, Stage 1/2's grows worse than linearly and is dominated by a constant-factor `b^d` term that inflates as the graph gets more connected. At 487 nodes / 832 edges the actual observed speedup was ~4000× (30 s → 7 ms).

**Memo invalidation is narrow.** `GraphManager.calculate_priority_scores` caches the per-node TV memo across calls and invalidates it only when (a) the graph mutates (`_scoring_version` bumps) or (b) a *TV-affecting* hyperparameter changes. The cache key set (`TV_AFFECTING_KEYS` in `graph_manager.py`) is `('w_v', 'w_i', 'd_H', 'd_S', 'd_Syn_pair', 'd_Syn_mul', 'cross_context_mult')` — exactly the parameters that feed into `total_value`. Everything else (`w_e, w_t, beta, goal_boost, alpha, context_weights`) is either a cost term or a post-score multiplier, so changing any of them re-ranks cheaply without re-walking the cascade. This is what lets the user tune density normalization or adjust context weights in the Settings tab without paying the first-batch cost.

### Scoring profiles (`config.PROFILES`)

Hyperparameters are bundled into six named profiles defined in [`config.py`](config.py). Each profile is a dict from knob name to value; switching the active profile is a one-key write to the `HP_PROFILE` Settings row, plus a write to `HYPERPARAMS` storing the resolved knob values (so user-customized overrides persist even after a profile switch). The active hyperparams flow into `scoring.score_nodes` via the `hyperparams` argument that `GraphManager.calculate_priority_scores` assembles per call.

| Profile | Lean | What changes vs. Sage |
|---|---|---|
| `Sage` | Balanced baseline | — |
| `Explorer` | Interest over Value | `w_i = 1.5`, synergy params up (`d_Syn_pair = 0.15`, `d_Syn_mul = 0.60`), `cross_context_mult = 1.5`, `alpha = 0.40` (heavier density haircut lets sparse subcontexts surface) |
| `Compounder` | Deep cascade, light cost | `d_H = 0.80`, `d_S = 0.50`, `w_e = 1.5`, `w_t = 0.85`, `beta = 0.70`, `alpha = 0.20` |
| `Pragmatist` | Value + Goal-boost | `w_v = 1.5`, `d_S = 0.20`, synergy params halved, `w_t = 1.5`, `goal_boost = 2.0`, `alpha = 0.20` |
| `Creator` | Cross-context synergy | `d_Syn_pair = 0.25`, `d_Syn_mul = 0.80`, `cross_context_mult = 2.0` |
| `Glider` | Time-penalty maximalist | `w_e = 3.5`, `w_t = 4.0`, `beta = 0.95`, cascade dampened (`d_H = 0.45`, `d_S = 0.30`), synergies minimal, `goal_boost = 1.0` (priority-subtree boost off), `alpha = 0.40` |

User-facing prose on when to use each lives in [`README.md`](../README.md#scoring-profiles-the-knobs-by-profile); this doc treats the profiles as code-level constants. Adding a new profile is: add a key to `PROFILES`, add a label to the dropdown in `settings_layout.py`, and write a regression test that locks the new defaults in `test_scoring_differential.py`.

### `explain_score` — per-node breakdown for the UI popup

[`scoring.explain_score(node_name, all_nodes, edges, hyperparams, priority_goals)`](scoring.py) returns a dict that decomposes a single node's priority score into its constituent parts: intrinsic value (with the synergy completion multiplier broken out), perceived cost (with override flags for inherited modes), the breakdown of total value by cascade path (`hard_cascade` / `soft_cascade` / `synergy`), the goal-boost record if applicable, the per-context adjustment (weight × density multiplier), and a sorted list of every descendant whose IV propagates into this node — with `depth`, first-hop `via` (`Self`/`Hard`/`Soft`/`Synergy`), per-contributor weight, and percentage-of-TV.

The forward propagation of weights from a starting node is done by `_contribution_weights`, which walks the DAG in topological order and accumulates `W(name) = sum over paths of product of edge discounts`. By linearity, `contribution(D) = W(D) × IV(D)` and the contributions sum to `intrinsic + cascade + syn_additive` exactly — which is how the popup's breakdown table can sum to the displayed TV without drifting from `score_nodes`. The synergy completion multiplier is a node-level scalar applied separately and reported in its own row.

The popup also surfaces an **eligible / block_reason** field: ineligible nodes (Done, Blocked, Goal, Milestone, container, missing prereqs) still get a full breakdown so users can see *why* a node is currently parked at score `-1.0`.

### Shortest-path focus (`shortest_paths_focus_data`)

For the Details tab's "show me how this node reaches my top recommendations" feature: given a source and a ranked list of `(rank, target_name)` tuples, this returns the BFS shortest paths from source to each target (Hard + Soft + a depth-1 Helps seed), plus per-node and per-edge `min_rank` annotations so the Cytoscape stylesheet can color shared segments by the most-valuable path that uses them. Shares the same edge set as `explain_score`'s contribution graph; the Helps seed matches the single-hop pair-bonus rule.

### Cascade status (`graph_manager._update_node_state`)

A node's status is Open, Blocked, or Done. Done is set manually. Blocked is derived: any node with at least one incomplete hard prerequisite is Blocked. When a node flips to Done (or is added, deleted, or has edges changed), `_update_dependent_nodes_state` walks its hard-downstream dependents and recomputes their status recursively. Each mutation bumps `_graph_version` (for UI invalidation) and, if the change touched a scoring-relevant field, `_scoring_version` (for the priority memo).

### Helps-edge semantics in `get_goal_subtree`

`get_goal_subtree` walks a goal's prerequisite tree over a caller-supplied set of edge types. For the directed types (`Needs_Hard`, `Needs_Soft`) it recurses in the usual way. For `Helps`, traversal is **seed-only**: direct synergy partners of the goal are added (bidirectionally, 1 step), but BFS from those partners only follows directed types. Helps does not chain.

The reason: an earlier version walked `Helps` transitively AND cascaded Hard/Soft from every Helps-reached node. Because `Helps` is bidirectional and the graph is densely synergy-linked, the Details tab's Synergies toggle would pull in most of the graph for well-connected goals (measured: 3 direct partners → 305 nodes for `Problem Solving`). Seed-only keeps Synergies-on focused on "direct partners + what you'd need to unlock them."

The Details tab's relationship column uses set arithmetic to label Synergy nodes: `overall_subtree − hard_soft_subtree`, so a partner's Hard prereq is correctly tagged "Synergy" rather than "Soft" (see [`details_layout.build_details_subtasks_table`](details_layout.py)).

### PERT time (`models.Node.time`)

The `time` property on a Node blends three estimates (optimistic, most likely, pessimistic) into one number. Low-uncertainty estimates (pessimistic/optimistic ratio ≤ 2) use the classic arithmetic PERT mean `(o + 4m + p) / 6`. High-uncertainty estimates (ratio ≥ 10) use the geometric/log mean. Between those bounds, it smoothly interpolates. There are also fallbacks for when only partial estimates are provided. The result is what shows up everywhere in the UI as "Time."

The property short-circuits to `0` when `time_mode='inherited'` so the cost denominator of an inherited-time container is `1 + 0 + 0 = 1` (its priority falls out of the cascade entirely). It also short-circuits to `0` when the three-point fields are all zero (a defensive guard against stored-but-empty rows).

### Habit mode (`callback_helpers.habit_to_hours`)

When `time_mode='habit'`, the canonical `time_o/m/p` hours stored on the node are derived from `habit_duration × habit_intensity_{o,m,p}`, expressed via the unit fields. The conversion lives in `callback_helpers.habit_to_hours` and runs whenever the user edits a habit-mode node:

- **Duration unit** → days. `'days'` = 1, `'weeks'` = 7, `'months'` = 30, `'years'` = 365.
- **Intensity unit** → hours/day. `'min_per_day'` = intensity/60, `'hr_per_day'` = intensity, `'min_per_week'` = intensity/(60×7), `'hr_per_week'` = intensity/7.
- **Total hours** = `duration_days × intensity_hours_per_day`.

So `4 weeks × 15 min/day` ≈ `28 × 0.25 = 7 hours` for the expected leg. The three intensity values produce three hours values (`time_o`, `time_m`, `time_p`), which then flow through the standard PERT blend like any manual estimate. From scoring's perspective Habit mode is invisible: by the time `score_nodes` runs, the hours are already canonical fields.

Why the indirection? "10 minutes a day for 8 weeks" is a more honest UI for recurring practice than "9 hours total," and the structure is preserved across mode toggles (`models.Node` keeps the habit fields populated even when `time_mode='manual'`, so a user who toggles can restore their input). The intensity-unit set covers the four natural cadence patterns (minutes/hours × per-day/per-week) — daily quick practices, daily deeper sessions, weekly time-blocks, etc.

### Time-unit conversion (`config.ConfigManager.get_time_multiplier`)

The editor's time-input control lets the user enter values in **hours**, **weeks**, **months**, or **years**. `get_time_multiplier(unit)` resolves each into a multiplier-to-hours using two persisted settings (`hours_per_week`, `hours_per_month` from the `TIME_SETTINGS` Settings row, with defaults of 40 and 160 respectively) plus a derived hours-per-year:

```
hours_per_year = HOURS_PER_YEAR_MULT × hours_per_month   # HOURS_PER_YEAR_MULT = 13
```

The `13` constant encodes "one year is 13 nominal months of productivity" — that's ≈ 52 weeks after vacation/overhead adjustment. Hours-per-year is **not** stored as its own Settings row; it derives at read time so changing `hours_per_month` flows through to year-denominated displays consistently. The same multiplier set drives the friendly time-unit display in the Next tab, tooltip strings, and Analyze chart x-axes (`ConfigManager.format_time_friendly` picks the largest unit whose value reads as a tidy number — hours → weeks → months → years).

### Event activation (`event_manager.check_pending_activations` + `check_scheduled_triggers`)

An Event has one of three trigger types:

- **Manual** — the user clicks a button.
- **Date** — the event has a `trigger_date` and today's date is ≥ that value.
- **Node** — the event has a `trigger_node` and that node's status is Done.

When an event triggers, `trigger_event` iterates its attached `EventNodes` rows. Each has a `delay_days` offset — the wake-up date becomes `event_date + delay_days`. If that date has arrived (or the delay is zero), the dormant node flips to active (`dormant = 0`). `check_pending_activations` is the polling sweep that fires the delayed activations on subsequent page loads. Any `override_on_trigger` flag gets applied at the same time.

### Monte Carlo simulation (`simulation.simulate_task_chain`)

For a target node, BFS walks backward through the dependency graph (hard by default; soft/synergies optional at the target level), collecting every incomplete prerequisite. Each one is sampled 10,000 times from a PERT-Beta distribution whose `alpha` and `beta` parameters come from the three-point estimate (`lambda=4` weighting). The per-simulation total is the **serial sum** of all sampled durations — the assumption is one person working on one task at a time. `_compute_stats` reduces the 10,000 samples into mean, std, percentiles (p10/p25/p50/p75/p90), min, max.

---

## 5. Data structures in memory

### `Node` (dataclass, `models.py`)

| Field | Type | Notes |
|---|---|---|
| `name` | str | Primary key. Renaming cascades through edges, events, aliases, and overrides via `GraphManager.rename_node`. |
| `type` | str | One of `Learn`, `Action`, `Goal`, `Resource`, `Milestone` (user-extensible in Settings — additional types get their own color/shape in the Node Types manager). |
| `description` | str | Free-text user notes. |
| `value` | int 1-10 | User rating — how important is this? |
| `interest` | int 1-10 | User rating — how fun/engaging? |
| `difficulty` | int 1-10 | User rating — how hard? (Stored as "difficulty"; labeled "Effort" in the UI.) |
| `time_o` | float | Optimistic estimate, in hours. |
| `time_m` | float | Most-likely estimate, in hours. |
| `time_p` | float | Pessimistic estimate, in hours. |
| `time_mode` | str | `'manual'` (use the three-point fields), `'inherited'` (zero own time in cost; aggregate from hard children), or `'habit'` (compute hours from duration × intensity — see *Habit mode* below). Drives `Node.time` short-circuiting. |
| `value_mode` | str | `'manual'` (use own ratings) or `'inherited'` (zero own intrinsic value and effort in scoring; rely entirely on cascade from descendants). Independent of `time_mode`. See *Container modes*. |
| `habit_duration` | float | Habit mode: how long the habit runs. Unit in `habit_duration_unit`. Inert when `time_mode != 'habit'` but preserved across mode toggles so re-enabling Habit restores the user's last input. |
| `habit_duration_unit` | str | One of `'days'`, `'weeks'`, `'months'`, `'years'`. |
| `habit_intensity_o` / `_m` / `_p` | float | Habit mode: three-point estimate of intensity (e.g. minutes/day) used to derive `time_o`/`time_m`/`time_p` in hours. Same three-point shape as manual mode, expressed at the habit level. |
| `habit_intensity_unit` | str | One of `'min_per_day'`, `'hr_per_day'`, `'min_per_week'`, `'hr_per_week'`. Combined with `habit_duration_unit` to yield hours. |
| `status` | str | `Open`, `Blocked`, or `Done`. `Blocked` is derived from prereq state by `_update_node_state`. |
| `context` / `subcontext` | Optional[str] | Life area and sub-area (Health → Exercise, etc.). `(context, None)` is a meaningful bucket meaning "broad area, not a specific subarea." `context = None` is uncategorized (rejected at add-time by current builds, but legacy rows may exist). |
| `obsidian_path` / `google_drive_path` / `website` | Optional[str] | Legacy single-link fields. Multi-link data now lives in Dash stores. |
| `dormant` | int | `1` while attached to a pending event; `0` once active. |
| `priority_score` | Optional[float] | Populated by `scoring.score_nodes()`; not persisted. |
| `total_value` | Optional[float] | Populated by `scoring.score_nodes()`; not persisted. |
| `time` | float (`@property`) | Computed blended PERT estimate. Not a stored field. Short-circuits to `0` when `time_mode='inherited'`. |
| `is_container` | bool (`@property`) | True when **both** `time_mode='inherited'` and `value_mode='inherited'` — the node is a pure structural conduit and is excluded from Next-tab ranking. |

### Edges

Stored as plain `dict` rows `{'source': str, 'target': str, 'type': str}` with composite primary key `(source, target, type)`. Three real edge types plus a deprecated one:

| Type | Meaning |
|---|---|
| `Needs_Hard` | **Must-do prerequisite.** Target is Blocked until source is Done; gates eligibility in scoring. Strongest, transitive value flow (`d_H` per hop). Use when the knowledge from A is required for B, or when the order is genuinely forced. |
| `Needs_Soft` | **Helpful but not required.** Source provides discounted value to target without blocking it. Weaker, transitive value flow (`d_S` per hop). Use when A would meaningfully improve B but B is doable without it. |
| `Helps` (Synergy) | **Lateral mutual reinforcement.** Symmetric — one row expresses the whole relationship. Non-transitive (no chains). Two distinct scoring effects: a small **pair bonus** `d_Syn_pair × tv(partner)` co-promotes synergy partners pre-completion, and a **completion multiplier** `(1 + d_Syn_mul × √done_partners)` scales intrinsic value once partners are Done. The sqrt is a diminishing-returns cap. Use when two nodes have a genuine multiplicative effect on each other (e.g., concepts that blend unusually well, where doing both is meaningfully more than the sum of doing each alone). |
| `Resource` | **Deprecated.** Migrated to `Needs_Soft` at startup; constant kept only for legacy rows. |

### `Aliases` table

Each node can carry zero or more alternate names. The table is a simple `(alias TEXT, node_name TEXT)` mapping with `alias` as the primary key (every alias resolves to exactly one node, but a node can have many aliases). Aliases are used by:

- **Search** — the editor's search box and the Nodes-tab locate-bar match against aliases as well as canonical names.
- **Auto-complete and dropdowns** — pickers that resolve a typed string to a node consult aliases.
- **Rename hardening** — `GraphManager.rename_node` does NOT touch aliases (renaming the node leaves its aliases pointing to the new canonical name, since the FK is enforced via the atomic rename pattern).

Aliases are managed in the node editor's collapsible "Aliases" panel under the Name field. There's no UI to list all aliases globally; the table is queried via `GraphManager.get_aliases(node_name)`.

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

#### Settings keys you'll encounter

| Key | Stored value | What it controls |
|---|---|---|
| `HP_PROFILE` | str (e.g. `"Sage"`, `"Explorer"`) | Active scoring profile. Picked from `config.PROFILES`. |
| `HYPERPARAMS` | dict of knob → number | Resolved scoring hyperparameters. Overlays the profile defaults so per-knob customizations persist. |
| `CONTEXT_WEIGHTS` | dict[context → float] | Per-context multipliers applied after raw score. Default 1.0 for any context not listed. |
| `CONTEXTS` | list[str] | Ordered list of contexts. Edited via Settings → Contexts. Renames flow through the migration modal. |
| `SUBCONTEXTS` | dict[context → list[str]] | Per-context subcontext lists. |
| `CONTEXT_SORT_MODE` / `SUBCONTEXT_SORT_MODE` | str | Display sort for dropdowns: `'definition'` / `'alphabetical'` / `'length'`. |
| `NODE_TYPES` | list[str] | Active node types. `Learn` is in `DEFAULT_NODE_TYPES`; `Action`/`Goal`/`Milestone` are seeded by `ensure_*_type()` at startup. |
| `NODE_COLORS` / `NODE_SHAPES` | dict[type → str] | Per-type style. |
| `PRIORITY_GOALS` | list[str] (up to 3) | Ranked Priority Goals — drives the `goal_boost` cascade. |
| `GOAL_ORDER` | list[str] | Full Goal display order in the Details → Goals sidebar (drag-to-reorder writes here). |
| `OVERRIDE` | dict | Manual override metadata for the Next tab's MANUAL OVERRIDE block. |
| `TIME_SETTINGS` | dict (`hours_per_week`, `hours_per_month`) | The two persisted time-conversion ratios. Hours-per-year derives from `hours_per_month × 13`. |
| `TIME_ESTIMATE_DEFAULTS` | dict | Prefill values for new-node time-estimate fields plus the default time mode (`'manual'` / `'inherited'` / `'habit'`). |
| `GRAPH_LAYOUT_DEFAULTS`, `DETAILS_GRAPH_LAYOUT_DEFAULTS`, `EVENTS_GRAPH_LAYOUT_DEFAULTS` | dict | Per-canvas physics tuning (edge length, gravity, repulsion). |
| `FILTERS` / `REMEMBER_FILTERS` | dict / bool | Last-applied filter set on the Next tab and whether to restore it on reload. |
| `ANALYZE_LIMITS` | dict | Per-section row limits for the Analyze tab charts. |
| `TITLECASE_LINTER` | dict (`enabled`, `exclusions`) | Optional title-case validator for new node names. |
| `OBSIDIAN_VAULT`, `GDRIVE_ROOT_PATH` | str | Root paths for resolving relative Obsidian/Drive links. |
| `SHOW_SCORING_PERF` | bool | Whether to display the scoring-perf timings strip at the bottom of the Next tab. |

Every key has a getter/setter pair on `ConfigManager` (see [`config.py`](config.py)). New keys: add a `DEFAULT_*` constant and matching `get_*`/`set_*` methods; the table auto-stores on first write.

### Community detection (`graph_manager.detect_communities`)

The Analyze tab and the Filters panel consume clustering results from `GraphManager.detect_communities(method=...)`:

- `method="components"` — connected components of the underlying undirected projection. Use for "Islands."
- `method="louvain"` — Louvain community detection via `networkx.algorithms.community.louvain_communities(subgraph, seed=42)`. The fixed seed makes results stable across reloads of the same graph.
- **Orphans** are computed separately by walking nodes with degree 0 in the same projection.

Results are memoized at `_community_cache`, keyed by `(method, sorted_allowed_names, _graph_version)`, so re-querying communities during a session of pure scoring tweaks is free (only graph mutations invalidate). Community names are auto-derived by `name_community` — it picks the most common shared context/subcontext among the cluster's members, or falls back to a top-keyword heuristic over the cluster's node names.

### Migration helper (renamed contexts and types)

When a user renames a context, subcontext, or node type that has active nodes attached, `settings_callbacks` opens a **migration modal**: each affected node gets dropdowns to pick its new context/subcontext (or type). The flow runs `_apply_per_node_migrations` over the user's selections, which calls `GraphManager.apply_node_migration(node_name, field, new_value)` per row. A sentinel value lets the user explicitly mark a node as needing a different category than the bulk default. `_migrate_context_weights` (`settings_callbacks.py`) handles the related question "should the old context's `CONTEXT_WEIGHTS` entry follow the rename or be dropped?" by inspecting how the user mapped nodes. The whole batch is committed atomically; canceling the modal touches nothing.

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
- Run with `pytest` from the repo root. The suite has 600+ tests and runs in ~20 seconds.

### Suite layout

| File | Coverage |
|---|---|
| `test_backend.py` | Core: Node, GraphManager, ConfigManager, edge mutations, cascade status, rename atomicity. The biggest single file. |
| `test_callbacks.py` | Stateless callback handlers (`handle_save`, `handle_delete`, `handle_toggle_done`, `handle_group_delete`) extracted from the Dash-context shims. |
| `test_helpers.py` | `callback_helpers` utilities: link row serialization, filter builders, habit→hours conversion, formatters. |
| `test_simulation.py` | Monte Carlo: PERT-Beta sampling shape, percentile calculations, serial-sum semantics, edge cases (no estimates, single-node chains). |
| `test_analyze.py` | Pure `_compute_*` functions powering the Analyze charts: time sinks, bottlenecks, goal-risk, context coverage. |
| `test_events.py`, `test_events_improvements.py` | Event lifecycle: manual/date/node triggers, dormant-node activation, delay handling, scheduled-trigger sweeps. |
| `test_override.py` | Manual override modes and the four override-scope choices (node only, +hard, +soft, +all). |
| `test_habit.py` | Habit-mode conversion (`habit_to_hours`) and round-tripping `time_mode='habit'` through CRUD. |
| `test_details_graph.py` | Details-tab subgraph derivation (`get_goal_subtree` with various edge-type sets), depth-limiting, neighbor-links toggle. |
| `test_container_suggestions.py` | "Suggested next" container-style nodes on the Next tab. |
| `test_scoring_explanation.py` | `explain_score`: composition adds up, contributor ordering, ineligibility paths. |
| `test_scoring_context_adjustment.py` | Context weight × density normalization math; bucket counting; `(context, None)` semantics. |
| `test_scoring_cross_context.py` | `cross_context_mult` flow through both `total_value` and `explain_score`. |
| `test_scoring_differential.py` | Correctness guard: memoized `score_nodes` must produce byte-equal outputs to an inline unmemoized baseline across randomized graphs, pathological shapes (self-loops, cycles, bidirectional pairs), and real sandbox/production DBs under multiple hyperparameter profiles. The harness threads the active profile (including `cross_context_mult`) into the baseline scorer so the comparison is apples-to-apples. |
| `test_scoring_memo_and_community_cache.py` | Memo invalidation (`TV_AFFECTING_KEYS`) and `_community_cache` reuse semantics. |
| `test_scoring_perf.py` | Linear-in-graph-size scaling smoke checks. |
| `test_edges_indexes.py` | SQLite index coverage on the Edges table. |
| `test_layout_smoke.py`, `test_app_smoke.py` | Layout builds without errors at boot; smoke tests for the full app. |
| `test_tab_toggle.py`, `test_state_drift_cleanup.py` | Tab-switch state continuity; cleanup invariants. |
| `test_core_engine_tab_gate.py` | "Don't compute analyze charts if the user hasn't opened the tab" laziness. |
| `test_generate_elements_regression.py` | Locks `generate_elements()` output shape against the legacy formatter. |
| `test_populate_editor_arity.py` | Ensures the node-editor populate callback's signature matches its registered Inputs. |

---

## 8. Conventions worth knowing

- **Element regeneration after mutations.** Most callbacks that change the graph end by returning a fresh `generate_elements(...)` result. Partial updates aren't the style — the source of truth is SQLite, so re-deriving the element list is simple and avoids divergence.
- **Pattern-matching callback IDs.** Dynamically-generated components (link rows, context menu items, filter chips) use Dash's `ALL` and `{'type': 'x', 'index': n}` dict IDs so a single callback can handle a variable number of inputs.
- **The `register_*_callbacks(app)` signature.** Every tab module exposes exactly one public function with that name. `app.py` doesn't need to know anything else. New tab? Add one more `register_*` call in `app.py`.
- **Cache invalidation counters.** `GraphManager._graph_version` bumps on every write; `_scoring_version` only bumps on scoring-relevant writes. Higher-level caches (like the scoring memo and the goal-subtree cache) check these counters to decide whether to reuse results.
- **Flask side-route.** The one-off `/open-obsidian` route in `app.py` exists because Obsidian's URL scheme only works reliably when invoked from a real shell, and the only way to escape Chrome's click-handler sandbox is a server-side shell-out.
- **Edge PK is composite.** `(source, target, type)` — the *same* two nodes can have both a Hard Prerequisite and a Synergy between them, because they're different rows.
- **Node rename is intentionally atomic.** `GraphManager.rename_node` temporarily disables foreign keys, updates the `Nodes` row, then updates every table that references the old name (`Edges`, `Events`, `EventNodes`, `Aliases`), then re-enables FKs. This avoids the cascade-delete you'd otherwise trigger by changing a primary key.
