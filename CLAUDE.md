# Skill Tree Project Guidelines

## Overview

A task-prioritization app that models tasks/goals as a directed graph. Users create nodes (tasks) with PERT time estimates, assign dependencies (edges), and the app ranks what to work on next using an ROI-based scoring algorithm. Built with Dash (Python) + Cytoscape.js for interactive graph visualization.

## Tech Stack

- **Backend:** Python 3.10, Dash, Dash Bootstrap Components (DARKLY theme), Dash Cytoscape, NetworkX, SQLite
- **Frontend:** Vanilla JS in `assets/` (no bundler), Cytoscape.js for the graph canvas
- **Database:** SQLite — production at `data/skilltree.db`, sandbox at `data/sandbox_skilltree.db`
- **Environment:** Conda (`environment.yml`), venv at `.venv/`
- **Tests:** pytest — run with `pytest` from project root

## App Launching

**Always launch the app in sandbox mode** to protect personal data:

```bash
python app.py -sandbox
```

Do NOT run `python app.py` or `python app.py -production` unless explicitly requested by the user. The app runs on port 8050.

## Architecture

| Layer | Key Files | Purpose |
|-------|-----------|---------|
| Entry point | `app.py` | Initializes Dash, registers callbacks, opens browser |
| Layout | `layout.py`, `goals_layout.py`, `events_layout.py`, `settings_layout.py`, `simulate_layout.py` | UI construction (tabs: Nodes, Goals, Events, Settings, Simulate) |
| Callbacks | `callbacks.py`, `goal_callbacks.py`, `event_callbacks.py`, `simulate_callbacks.py` | All Dash interactivity; each file has a `register_*_callbacks(app)` function |
| Helpers | `callback_helpers.py` | Stateless utilities for CRUD, filtering, serialization |
| Graph logic | `graph_manager.py` | Node/edge CRUD, cycle detection, filtering, cascade operations |
| Scoring | `scoring.py` | ROI-based priority ranking algorithm |
| Models | `models.py` | `Node` and `Event` dataclasses with PERT estimation |
| Config | `config.py` | `ConfigManager` class — persistent settings in SQLite Settings table |
| Events | `event_manager.py` | Dormant node activation via manual/date/node triggers |
| Simulation | `simulation.py` | Monte Carlo critical-path analysis |
| Database | `database.py` | Schema init, connection pooling |
| Styles | `styles.py` | Cytoscape stylesheet definitions |
| JS | `assets/context_menu.js`, `tooltip.js`, `fullscreen.js`, `resize_handle.js` | Context menus, tooltips, canvas interactions |

## Key Patterns

- **Callback pattern:** Almost all callbacks regenerate the full element list via `generate_elements()` after mutations. Use Dash `ALL` pattern matching for dynamic component IDs.
- **Node status:** Open / Blocked / Done. Nodes auto-block when any hard prerequisite is incomplete. Status updates cascade recursively.
- **Edge types:** `Needs_Hard`, `Needs_Soft`, `Helps`, `Resource`
- **PERT estimates:** Three-point (optimistic/most_likely/pessimistic) with blended arithmetic + logarithmic means.
- **Database:** Node `name` is the primary key. Edges use composite PK `(source, target, type)`.
- **JS ↔ Dash:** JS files use native HTML input value setters to bridge into Dash's reactive system.

## Styling

All UI styling conventions are documented in **[STYLE_GUIDE.md](STYLE_GUIDE.md)**. Always consult this file when adding or modifying UI elements. Update it when new patterns are established.

## Testing

Tests use a `temp_database` fixture that creates a temporary SQLite DB per test — never touches production data. Test files mirror the module structure: `test_backend.py`, `test_callbacks.py`, `test_events.py`, `test_helpers.py`, `test_simulation.py`.
