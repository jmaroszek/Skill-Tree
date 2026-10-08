# Skill Tree — agent context

Shared by every coding agent: Codex reads this file directly, and `CLAUDE.md` imports it.

Task-prioritization app. A directed graph of nodes (tasks/goals) and typed edges (prerequisites / synergies) is ranked by an ROI-based scoring algorithm to tell the user what to work on next. Dash + Cytoscape.js frontend, Python backend, SQLite storage.

## Must-know rules

- **Always launch the app in sandbox mode**: `python app.py --sandbox --port 8051` (add `--dev` for hot reload). Never run `python app.py` (production) unless the user explicitly asks.
- **Production DB (`%LOCALAPPDATA%\Skill Tree\Data\skilltree.db`)** — reads and writes are allowed when the user is asking for graph review or programmatic node/edge changes against their real data. Do **not** use it as a scratchpad: no exploratory writes, no test fixtures, no app launches against it. When in doubt about whether a write is "graph editing the user asked for" vs "experimentation", confirm first.
- **Sandbox DB (`%LOCALAPPDATA%\Skill Tree\Data\sandbox_skilltree.db`)** is the target for any app-launch testing or experimentation.
- **Ports:** sandbox on 8051, production on 8050 — kept distinct so the sandbox can run alongside the user's production instance.
- **Access token:** the server answers only requests carrying its per-launch token. Use the tab it opens, or run with `--no-browser` and use the link it prints (also in `<Data>/sandbox_skilltree.instance.json`). For throwaway data, set `SKILLTREE_HOME` to an absolute folder.
- **Showing the sandbox to the user:** don't hand them the `?token=` link, and don't let the server open a browser tab. A browser launched from the agent's terminal hangs the user's Chrome on that link and it never finishes loading. Start the server yourself with `python app.py --sandbox --port 8051 --dev --no-browser` (from a worktree if you're in one), then tell them to run `C:\Users\jonah\Documents\Code\Terminal\Batch\skill_tree_sandbox.bat`. That opens the Electron window, which attaches to the sandbox server already running, so they see your worktree's code. A server restart issues a new token: if the window says "This link is out of date", they close it and rerun the `.bat`. To look at it yourself, use the in-app browser pane.

## Domain model

The conceptual guide (how to build a good graph) is [`docs/modeling.md`](docs/modeling.md); the scoring math is [`docs/scoring.md`](docs/scoring.md). Read those before editing node/edge/scoring machinery or doing a hands-on graph review. The node type changes scoring behavior, so it isn't just a label.

## Node-type semantics

Five types — each answers a different question. Picking the right one matters; misclassification muddies the rankings.

- **Goal** — a *domain, area, or capacity* the user is developing. "What am I trying to achieve here." Container-flavored, almost never atomic. "Done" = the user judges it met. When its last Hard child is marked Done, the app suggests marking the Goal Done too (the auto-Done modal), but never does it on its own. The status cascade never changes a Goal's status. Examples: Sleep, Strength, Stoicism, Character.
- **Learn** — a *topic or body of knowledge* the user wants to integrate. Can be atomic (Sleep Pressure, Stretching) or a container with sub-Learns (Sleep Theory, Biology of Stress). "Done" = "I understand this enough to apply or explain it."
- **Action** — a *discrete practice or experiment* with a definite end. The user runs them as 6-week PIMLI cycles. "Done" = the cycle is complete. Time-on-task is the actual doing.
- **Resource** — *external material* (book, course, notes). "Done" = absorbed.
- **Milestone** — a *measurable, verifiable single-event achievement* (weight target, time, count). **Excluded from scoring** — the work happens upstream in capacity Goals; the Milestone is the checkpoint, not the practice. `Node` forces its time and value to inherited, so it has no estimate to set. Value passes through a Milestone as a free hop: A→M→B scores like A→B.

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

The user-facing version of this is Node Types in [`docs/modeling.md`](docs/modeling.md). Keep both in sync if the framework evolves.

## Edge-type semantics

The three real edge types are *not* a single "strength" gradient — `Helps` is on a different axis from `Needs_Hard`/`Needs_Soft`. Treat them as:

- **`Needs_Hard`** — must-do prerequisite. Blocks eligibility (a node with an incomplete hard prereq is automatically Blocked). Strongest transitive value flow (`d_H` per hop).
- **`Needs_Soft`** — helpful but not blocking. Weaker transitive value flow (`d_S` per hop).
- **`Helps`** (Synergy) — *mutual multiplicative reinforcement*, not a lesser Soft. Doing both is significantly more valuable than the sum of doing each alone (e.g., concepts that blend unusually well). Bidirectional, non-transitive (no chains). Synergy contributes via two paths: a small **pair bonus** pre-completion (`d_Syn_pair` of each unfinished partner's total value, times `m_cross` when the partner is in another context), and a **multiplicative kick on intrinsic value** `iv * (1 + d_Syn_mul * sqrt(count_done_partners))` once partners are Done. The sqrt is a diminishing-returns cap so a hub of N synergy partners gives ~`sqrt(N)`× the boost, not N× — keeps "more partners = more boost" without unbounded inflation. Multiplier applies to intrinsic only — not to the cascade or the pair bonus. See [`scoring.py`](scoring.py)'s `total_value` for the implementation.

**Edge direction — easy to get backwards.** `A --Needs_Hard/Soft--> B` means **A unlocks B**: A is the prerequisite, B is the dependent, and B stays Blocked until A is Done. Read the arrow as "leads to / unlocks," *not* "depends on." Value cascades **forward** along arrows (completing A flows discounted value to everything it unlocks); **eligibility runs backward** (a node is Blocked by its *incoming* hard prereqs). Mixing up these two directions has caused repeated bugs. [`docs/scoring.md`](docs/scoring.md) has the forward cascade (The DAG Cascade) and how a Goal is ranked by the hard subtree that leads into it (Goal Scoring).

## Where to look

Don't duplicate these in this file — they're the source of truth for their respective topics:

- [`docs/app_architecture.md`](docs/app_architecture.md) — module responsibilities, tab-callback pattern, Cytoscape pipeline, JS-Dash bridge, persistence and caching.
- [`docs/modeling.md`](docs/modeling.md) — how to build a good graph: node types, relationships, contexts. Read it before a hands-on graph review.
- [`docs/scoring.md`](docs/scoring.md) — full math for scoring, profiles, goal ranking, explainability, status cascade.
- [`docs/time.md`](docs/time.md) — what the lower/expected/upper bracket means, the weighting rule that produces `t(n)`, and the Monte Carlo simulator behind the Time Simulation panel.
- [`README.md`](README.md) — why the app exists, and the map to the five user documents.
- [`docs/features.md`](docs/features.md) — full feature tour written for non-technical readers, grounded in the sandbox dataset.
- [`STYLE_GUIDE.md`](STYLE_GUIDE.md) — UI conventions (colors, typography, spacing, component styles). Consult before touching any UI; update it when you establish new patterns.
- [`docs/user/`](docs/user/) — install, privacy and troubleshooting, for people using the app. Keep them true when the behavior they describe changes.
- `docs/production_readiness_plan.md` is the **private, gitignored** checklist for making the app downloadable by others (packaging, data safety, hardening). If it is in your checkout, read it before production-readiness work and check off items as you finish them. If it is missing (cloud container, worktree), ask the user for the latest copy. Never commit it.

## Tech stack (one-liner)

Python 3.13, Dash + Dash Bootstrap Components (DARKLY theme), Dash Cytoscape, NetworkX, NumPy, Plotly, SQLite via stdlib `sqlite3`. No bundler — JS in `assets/` is served raw.

## Non-obvious conventions

- Every tab module exposes exactly one public function: `register_*_callbacks(app)`. `app.py` imports and calls each. New tab = one more `register_*` call.
- Node `name` is the primary key; edges have composite PK `(source, target, type)` so the same pair can carry both a prerequisite and a synergy.
- Almost all callbacks that mutate state end by returning a fresh `generate_elements(...)` element list from [`callbacks.py`](callbacks.py). That function is the single source of truth for what the Nodes canvas shows.
- Status is cascading: a node auto-Blocks when any hard prerequisite is incomplete; `_update_dependent_nodes_state` walks the downstream chain on every Done-flip. Goals are exempt: they keep whatever status the user set.
- The JS-Dash bridge uses native HTML `value` setters (via `Object.getOwnPropertyDescriptor`) to get React to notice programmatic input changes — plain `el.value = ...` is silently ignored.
- `ConfigManager` is classmethod-only and round-trips everything through the `Settings` SQLite table. There is no persistent settings cache. Read operations may share a `database.read_snapshot()`; it expires at the end of the operation and is invalidated by local writes, so subsequent operations see fresh state across tab modules.

## Testing

Run the tests for what you changed while you work, and the whole suite once before you commit:

```bash
pytest tests/test_simulation.py tests/test_simulation_service.py   # while working: the tests for what you changed
python -m ruff check .                                              # before committing: a lint error fails CI
pytest -n auto                                                      # before committing: the whole suite, on every core
```

- To find the tests for a file, search `tests/` for its name: a module's, or a JS or CSS asset's. Shared code (`models`, `database`, `graph_manager`, `config`, `scoring`, `callback_helpers`) is tested all over the suite: after changing it, run all of it.
- `pytest --lf` reruns only what failed last time. `-n auto` needs pytest-xdist, which `requirements-dev.txt` and `environment.yml` install.
- Don't wait on CI after pushing: it runs everything, on four platforms, on every push. Look at the last run before you push again (`gh run list --limit 3`); when it's red, fixing it comes first.

Tests use a `temp_database` fixture that gives each test its own copy of a new database in `tmp_path` and monkeypatches `database.get_db_path` to it. Nothing writes to the sandbox or production DBs. Two scoring tests in `test_scoring_differential.py` read each one when it exists: they take a read-only snapshot into `tmp_path` and score the copy. They skip when the file is missing.

`pytest` leaves out the browser journeys in `tests/e2e`: a real server, driven in Chromium, through what a new user does in their first hour. They check what ends up in the database, not layout, focus order or timing; keep any new one that way. Run them for a change to a workflow they cover: `pytest tests/e2e`. CI runs them on Linux only. They need Playwright; see [`docs/setup.md`](docs/setup.md) section 4. Each starts its own server against a throwaway `SKILLTREE_HOME`.

## Key patterns to follow when editing

- Use Dash `ALL` pattern-matching (`Input({'type': 'x', 'index': ALL}, ...)`) for any dynamically-generated component list.
- Prefer extracting pure logic to [`callback_helpers.py`](callback_helpers.py) (stateless) or [`graph_manager.py`](graph_manager.py) (DB-backed) rather than growing the already-large `*_callbacks.py` files further.
- The node editor's fields are declared once, as `EDITOR_FORM` in [`callback_helpers.py`](callback_helpers.py). A callback that reads the form takes that dict as one State and receives a dict of values. A new editor field goes there, not into each callback's State list.
- Build canvas elements with `build_node_element` / `build_edge_element` in [`callback_helpers.py`](callback_helpers.py). A canvas chooses which nodes it shows; it doesn't decide how a node looks or which data fields it carries.
- Behavior that belongs on every canvas loops over `CANVASES` in [`canvases.py`](canvases.py), or `window.SkillTree.canvases` in `assets/`. Don't list canvas IDs by hand.
- Cycle detection is already handled in `graph_manager.add_edge` — don't reimplement.
- For anything time/duration-related, let the `Node.time` property weight the bracket; don't compute a single "time" from `time_o/m/p` yourself.
- When you add a scoring-relevant field to `Node`, also add it to `graph_manager._SCORING_RELEVANT_FIELDS`, or the scoring cache won't invalidate and rankings silently go stale. See [`docs/app_architecture.md`](docs/app_architecture.md).
