# Skill Tree

A graph-based task manager and priority engine built with [Dash](https://dash.plotly.com/) and [Cytoscape.js](https://js.cytoscape.org/). Model your goals, skills, habits, and resources as an interactive node graph — then let the priority algorithm tell you what to work on next.

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## Features

### Interactive Graph Canvas
- **Visual node graph** — drag, zoom, and click nodes rendered with a force-directed (COSE) layout.
- **Color-coded statuses** — nodes are colored by status: Open (blue), Blocked (red), Done (green).
- **Shape-coded types** — each node type has a distinct shape (Goal, Topic, Skill, Habit, Resource).
- **Hover tooltips** — floating tooltips display node details on mouseover.
- **Right-click context menu** — toggle Done, open in Obsidian, or delete nodes via context menu.
- **Resizable sidebar** — drag the edge of the sidebar to adjust the canvas/sidebar split.

### Node Editor Sidebar
- Create, edit, and delete nodes with a full attribute form.
- Set **Value**, **Interest**, **Difficulty**, and **Time** (Optimistic, Most Likely, Pessimistic) to feed the priority algorithm.
- Assign a **Context** (e.g., Mind, Body, Social, Action) and optional **Subcontext** for hierarchical filtering.
- Link nodes to **Obsidian** vault files and **Google Drive** documents with one-click open buttons.

### Relationship System
| Relation           | Meaning                                                              | Edge Style   | Algorithm Role                                      |
|--------------------|----------------------------------------------------------------------|--------------|-----------------------------------------------------|
| **Needs (Hard)**   | Hard prerequisite — target is **Blocked** until source is Done       | Solid arrow  | Eligibility gate; value propagates at decay `d_H`   |
| **Needs (Soft)**   | Soft prerequisite — recommended before starting, but not blocking    | Dashed arrow | Value propagates at decay `d_S`; does **not** block |
| **Supports (Hard)**| Reverse of Needs Hard — marks this node as a hard dependency of another | Solid arrow | Same as Needs Hard, from the other perspective      |
| **Supports (Soft)**| Reverse of Needs Soft — marks this node as a soft dependency of another | Dashed arrow| Same as Needs Soft, from the other perspective      |
| **Helps**          | Bidirectional synergy — boosts priority of connected nodes           | Blue solid   | Value propagates bidirectionally at decay `d_Syn`   |
| **Resource**       | Associated resource node                                             | Dotted arrow | Not used in scoring                                 |

### Automatic State Management
- Adding a **Needs (Hard)** edge automatically marks the dependent node as **Blocked** if the prerequisite isn't Done. Soft prerequisites do **not** block.
- Completing a prerequisite cascades state updates to all downstream dependents.
- Cycle detection prevents circular dependencies in the Needs DAG.

### Global Settings Modal
- Configure **node types**, **contexts**, and **subcontexts** without touching code.
- Tune all scoring **hyperparameters** individually, or switch between preset scoring profiles.
- Set the **Obsidian vault root path** for file browsing integration.

### Sandbox Mode
- Run the app with `--sandbox` to get a separate, isolated database for experimentation without affecting your production data.

### Priority Scoring Algorithm

The algorithm calculates a dynamic priority score for each node as **Return on Investment**: the ratio of recursive total value to perceived cost, gated by an eligibility filter. It rewards nodes that unlock high-value downstream work and penalizes high-effort or high-time tasks using sub-linear scaling. Bidirectional synergies and soft prerequisites also contribute value, but only hard prerequisites block a node from being scored.

The **Suggestions** panel shows the top highest-priority tasks with their scores and what they unlock.

#### Time Estimation (T_n)

The system accepts three hour-based estimates — **Optimistic (O)**, **Most Likely (M)**, and **Pessimistic (P)** — and blends arithmetic and logarithmic PERT formulas based on the uncertainty ratio `P/O`.

**Base PERT equations:**

```
E_arith = (O + 4M + P) / 6
E_log   = exp( (ln(O) + 4·ln(M) + ln(P)) / 6 )
```

**Blending weight (w)** based on the uncertainty ratio `r = P / O`:

```
w = 0                                    if r <= 2
w = (ln(r) - ln(2)) / (ln(10) - ln(2))  if 2 < r < 10
w = 1                                    if r >= 10
```

**Final time estimate:**

```
T_n = (1 - w) · E_arith + w · E_log
```

When uncertainty is low (`r <= 2`), the arithmetic mean dominates. As uncertainty grows, the formula smoothly shifts toward the logarithmic (geometric) mean, which is more conservative for skewed estimates.

**Fallbacks:** If only M is provided, `T_n = M`. If only O and P are provided, `T_n = sqrt(O · P)` (geometric mean). If all three are missing, `T_n = 1.0`.

#### Intrinsic Value (IV_n)

Each node's intrinsic value is a weighted sum of its user-assigned **Value** (V, 1-10) and **Interest** (I, 1-10):

```
IV_n = w_v · V_n + w_i · I_n
```

#### Recursive Total Value (TV_n)

Value cascades through the graph from downstream nodes. The total value of a node is its intrinsic value plus the discounted total value of all nodes it connects to:

```
TV_n(visited) = IV_n + NV_n(visited ∪ {n})
```

where the **Network Value (NV_n)** sums over three types of connections:

```
NV_n(visited) = d_H  · Σ TV_x(visited)   for x in H_out \ visited
              + d_S  · Σ TV_y(visited)   for y in S_out \ visited
              + d_Syn · Σ TV_z(visited)   for z in Syn \ visited
```

| Set       | Description                                |
|-----------|--------------------------------------------|
| `H_out`   | Nodes where n is a **hard** prerequisite   |
| `S_out`   | Nodes where n is a **soft** prerequisite   |
| `Syn`     | Nodes that **synergize** (Helps) with n    |

The recursion passes a **visited set** to prevent infinite loops caused by bidirectional synergy edges. Each node's priority calculation starts with an **empty** visited set — TV values are never globally memoized or cached across nodes, since the output depends on the visited state.

**Base case:** If a node has no unvisited downstream connections, `NV_n = 0` and `TV_n = IV_n`.

#### Perceived Cost (C_n)

A sub-linear penalty on time avoids heavily punishing long-term tasks:

```
C_n = 1 + w_e · E_n + w_t · (T_n)^β
```

where `E_n` is the node's **Difficulty** (1-10), `T_n` is the blended PERT time, and `β < 1` compresses the time contribution (e.g., a 100-hour task is not 100x more costly than a 1-hour task). The `+1` constant ensures a minimum cost floor.

#### Eligibility Filter (δ_n)

Only nodes whose hard prerequisites are **all** complete are eligible for scoring:

```
δ_n = 1   if all hard prerequisites for node n are Done
δ_n = 0   if ≥ 1 hard prerequisites are incomplete
```

Soft prerequisites and synergies do **not** affect eligibility. Nodes with `δ_n = 0`, as well as Done and Blocked nodes, receive a score of `-1` (ineligible).

#### Final Priority Score (P_n)

```
P_n = δ_n · ( TV_n(∅) / C_n )
```

#### Hyperparameters

| Parameter | Symbol | Default | Description |
|-----------|--------|---------|-------------|
| Value weight | `w_v` | 1.00 | Multiplier for base Value in intrinsic value |
| Interest weight | `w_i` | 1.00 | Multiplier for base Interest in intrinsic value |
| Hard prereq decay | `d_H` | 0.60 | Decay factor for hard prerequisite value propagation |
| Soft prereq decay | `d_S` | 0.25 | Decay factor for soft prerequisite value propagation |
| Synergy decay | `d_Syn` | 0.35 | Decay factor for bidirectional Helps value propagation |
| Difficulty weight | `w_e` | 2.50 | Multiplier for the 1-10 difficulty score in cost |
| Time weight | `w_t` | 1.00 | Multiplier for the time estimate in cost |
| Time dampener | `β` | 0.85 | Power-law exponent for sub-linear time scaling |

#### Scoring Profiles

Three pre-configured profiles tune the hyperparameters for different prioritization philosophies:

| Parameter | Default | Curious | Industrious |
|-----------|---------|---------|-------------|
| `w_v`    | 1.00 | 1.00 | 1.50 |
| `w_i`    | 1.00 | 1.50 | 1.00 |
| `d_H`    | 0.60 | 0.75 | 0.50 |
| `d_S`    | 0.25 | 0.35 | 0.15 |
| `d_Syn`  | 0.35 | 0.50 | 0.25 |
| `w_e`    | 2.50 | 1.00 | 4.00 |
| `w_t`    | 1.00 | 2.50 | 3.00 |
| `β`      | 0.85 | 0.50 | 0.70 |

- **Default** — Balanced baseline.
- **Curious** — Favors interest (`w_i=1.5`) and network exploration (higher `d_H`, `d_Syn`). Lower difficulty penalty makes hard tasks less daunting.
- **Industrious** — Favors raw value (`w_v=1.5`) and heavily penalizes effort (`w_e=4.0`) and time (`w_t=3.0`). Lower network decay focuses on immediate returns.

### Community Detection
- **Islands** — finds fully disconnected components (Connected Components).
- **Clusters** — finds loosely connected sub-clusters using the Louvain modularity algorithm.
- Filter the canvas to focus on a single community.

### Filtering & Search
- Filter by **Context**, **Subcontext**, and toggle **Hide Done** nodes.
- Filter by minimum **Value**, minimum **Interest**, maximum **Time**, and maximum **Difficulty**.
- **Search** bar finds and selects nodes by name.
- **Dependency chains** panel shows prerequisite paths for a selected node.
- **Synergies** panel lists all Helps connections for a selected node.

---

## Project Structure

```
Skill Tree/
├── app.py              # Entry point — initializes and runs the Dash server
├── layout.py           # UI component definitions and Cytoscape stylesheet
├── callbacks.py        # All Dash callbacks and helper functions
├── graph_manager.py    # Core graph logic: CRUD, edges, state management, communities
├── scoring.py          # Priority scoring algorithm (ROI-based with network value)
├── models.py           # Node dataclass with validation and edge type constants
├── database.py         # SQLite initialization, migrations, and connection management
├── config.py           # Configuration manager, hyperparameters, profiles, UI defaults
├── assets/
│   ├── custom.css      # Main application styles
│   ├── theme.css       # Color theme and fullscreen overrides
│   ├── tooltip.js      # Client-side JS for hover tooltip positioning
│   ├── context_menu.js # Right-click context menu behavior
│   ├── fullscreen.js   # Fullscreen toggle functionality
│   └── resize_handle.js # Draggable sidebar resize handle
├── tests/
│   ├── test_backend.py  # Pytest suite: models, PERT, CRUD, edges, state, scoring, config
│   └── test_callbacks.py # Pytest suite: callback helpers (filters, save, delete, toggle)
├── environment.yml     # Conda environment specification
└── skilltree.db        # SQLite database (git-ignored, auto-created)
```

---

## Getting Started

### Prerequisites
- [Conda](https://docs.conda.io/en/latest/) (Miniconda or Anaconda)

### Installation

```bash
# Clone the repository
git clone https://github.com/jmaroszek/Skill-Tree.git
cd Skill-Tree

# Create and activate the conda environment
conda env create -f environment.yml
conda activate skill-tree
```

### Running the App

```bash
python app.py
```

Open your browser to **http://127.0.0.1:8050** — the database is auto-created on first run.

To launch in sandbox mode (isolated database for experimentation):

```bash
python app.py --sandbox
```

### Running Tests

```bash
pytest tests/ -v
```

Tests use a temporary database so your production data is never touched.

---

## Dependencies

| Package                    | Purpose                                  |
|----------------------------|------------------------------------------|
| `dash`                     | Web application framework                |
| `dash-cytoscape`           | Interactive graph visualization          |
| `dash-bootstrap-components`| Bootstrap-styled UI components           |
| `networkx`                 | Graph algorithms (community detection)   |
| `sqlite3` (stdlib)         | Lightweight persistent storage           |
| `pytest`                   | Test framework                           |

---

## Usage Guide

1. **Create a node** — click "New Node", fill in the attributes, and hit "Save".
2. **Connect nodes** — select a node, then use the Needs/Supports/Helps/Resources dropdowns to define relationships.
3. **Check priorities** — the Suggestions table automatically ranks your open tasks.
4. **Explore dependencies** — click any node to see its prerequisite chains and synergies.
5. **Find communities** — use the Community Method dropdown to detect clusters, then filter to a specific community.
6. **Tune scoring** — open the Settings modal to adjust hyperparameters or switch scoring profiles.

---
