# 🌳 Skill Tree

A graph-based task manager and priority engine built with [Dash](https://dash.plotly.com/) and [Cytoscape.js](https://js.cytoscape.org/). Model your goals, skills, habits, and resources as an interactive node graph — then let the priority algorithm tell you what to work on next.

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## ✨ Features

### Interactive Graph Canvas
- **Visual node graph** — drag, zoom, and click nodes rendered with a force-directed (COSE) layout.
- **Color-coded statuses** — nodes are colored by status: 🔵 Open, 🟡 In Progress, 🔴 Blocked, 🟢 Done.
- **Shape-coded types** — each node type has a distinct shape (⭐ Goal, ◯ Topic, △ Skill, ◇ Habit, ⬠ Resource).
- **Hover tooltips** — floating tooltips display node details on mouseover.

### Node Editor Sidebar
- Create, edit, and delete nodes with a full attribute form.
- Set **Value**, **Interest**, **Time**, and **Effort** to feed the priority algorithm.
- Assign a **Context** (Mind, Body, Social, Action) for filtering.

### Relationship System
| Relation   | Meaning                                                  | Edge Style     |
|------------|----------------------------------------------------------|----------------|
| **Needs**  | Prerequisite — target is blocked until source is Done    | Solid arrow    |
| **Supports** | Reverse of Needs — marks this node as a dependency of another | Solid arrow |
| **Helps**  | Bidirectional synergy — boosts priority of connected nodes | Blue solid    |
| **Resource** | Associated resource node                               | Dotted arrow   |

### Automatic State Management
- Adding a **Needs** edge automatically marks the dependent node as **Blocked** if the prerequisite isn't Done.
- Completing a prerequisite cascades state updates to all downstream dependents.
- Cycle detection prevents circular dependencies in the Needs DAG.

### Priority Scoring Algorithm
Ranks open/in-progress nodes by the formula:

```
Priority = (Value × Interest) / (Time × Effort) + Wn·N + Wh·H
```

| Variable | Meaning |
|----------|---------|
| **N** | Count of Blocked nodes this task directly unlocks |
| **H** | Count of active synergistic (Helps) connections |
| **Wn** | Unlock weight (default 3.0) |
| **Wh** | Synergy weight (default 1.0) |

The **Suggestions** panel shows the top 5 highest-priority tasks with their scores and what they unlock.

### Community Detection
- **Islands** — finds fully disconnected components (Connected Components).
- **Clusters** — finds loosely connected sub-clusters using the Louvain modularity algorithm.
- Filter the canvas to focus on a single community.

### Filtering & Search
- Filter by **Context** and toggle **Hide Done** nodes.
- **Search** bar finds and selects nodes by name.
- **Dependency chains** panel shows prerequisite paths for a selected node.
- **Synergies** panel lists all Helps connections for a selected node.

---

## 🏗️ Project Structure

```
Skill Tree/
├── app.py              # Entry point — initializes and runs the Dash server
├── layout.py           # UI component definitions and Cytoscape stylesheet
├── callbacks.py        # All Dash callbacks and helper functions
├── graph_manager.py    # Core graph logic: CRUD, edges, scoring, communities
├── models.py           # Node dataclass with validation
├── database.py         # SQLite initialization and connection management
├── constants.py        # Enumerations, color/shape maps, algorithm defaults
├── assets/
│   └── tooltip.js      # Client-side JS for hover tooltip positioning
├── test_backend.py     # Pytest suite for GraphManager, Node model, DB
├── test_dash.py        # Basic Dash callback smoke test
├── environment.yml     # Conda environment specification
└── skilltree.db        # SQLite database (git-ignored, auto-created)
```

---

## 🚀 Getting Started

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

### Running Tests

```bash
pytest test_backend.py -v
```

Tests use a temporary database so your production data is never touched.

---

## 📦 Dependencies

| Package                    | Purpose                                  |
|----------------------------|------------------------------------------|
| `dash`                     | Web application framework                |
| `dash-cytoscape`           | Interactive graph visualization          |
| `dash-bootstrap-components`| Bootstrap-styled UI components           |
| `networkx`                 | Graph algorithms (community detection)   |
| `pandas`                   | Data manipulation                        |
| `sqlite3` (stdlib)         | Lightweight persistent storage           |
| `pytest`                   | Test framework                           |
| `ruamel.yaml`              | YAML processing                          |

---

## 🎯 Usage Guide

1. **Create a node** — click "New Node", fill in the attributes, and hit "Save".
2. **Connect nodes** — select a node, then use the Needs/Supports/Helps/Resources dropdowns to define relationships.
3. **Check priorities** — the Suggestions table automatically ranks your open tasks.
4. **Explore dependencies** — click any node to see its prerequisite chains and synergies.
5. **Find communities** — use the Community Method dropdown to detect clusters, then filter to a specific community.

---

## 📝 License

This project is for personal use.
