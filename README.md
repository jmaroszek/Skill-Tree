# Skill Tree

A graph-based task manager and priority engine that tells you what to work on next.

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## What It Does

Skill Tree replaces traditional to-do lists with a **bidirectional dependency graph**. Instead of staring at a flat list wondering what to tackle first, you map out tasks, goals, and their relationships — then let the priority algorithm figure out the **Return on Investment (ROI)** of every possible action, naturally bubbling up high-value prerequisite tasks to the top.

Think of it as a to-do list that actually understands *why* things matter and *what order* to do them in.

---

## The Priority Algorithm

The heart of the app is an ROI-based scoring engine that ranks every eligible task:

**Score = Eligibility x (Total Value / Perceived Cost)**

- **Eligibility:** A node scores -1 if any Hard Prerequisite is incomplete. Soft Prerequisites never block — they just add value.
- **Intrinsic Value:** Derived from your **Value** (1-10) and **Interest** (1-10) ratings.
- **Network Value:** The algorithm looks continuously downstream. A node inherits discounted value from everything it unlocks and synergizes with. Foundational bottleneck tasks naturally rise to the top because the whole graph rests on them.
- **Perceived Cost:** A sub-linear penalty based on **Difficulty** and the **Time Estimate**. Long tasks are penalized, but not linearly — a 100-hour task isn't treated as 100x worse than a 1-hour task.

---

## Tabs

### Next

Your at-a-glance priority dashboard. Shows your **top-N eligible nodes** ranked by ROI score (normalized to 0-100). Updates live as your graph changes.

Filter by context, subcontext, value/interest thresholds, max time/difficulty, node type, or a specific goal's subtasks.

### Nodes

The interactive graph canvas where you build and explore your task network.

- **Visual Graph:** Drag, zoom, and pan a force-directed (COSE) layout. Right-click to pan, left-click to interact.
- **Color-Coded Status:** Blue for Open, red for Blocked, green for Done, yellow for Goals.
- **Distinct Shapes:** Each node type gets its own shape — stars for Goals, triangles for Actions, pentagons for Resources, and more.
- **Right-Click Context Menus:** Toggle completion, delete nodes, open linked Obsidian notes, run a simulation, or jump to a node's dependency chain.
- **Hover Tooltips:** See time estimates, standard deviation, and key stats without clicking.
- **Multi-Select:** Ctrl+Click to grab multiple nodes at once.

### Details

A deep-dive view for any node. Select a node and get:

- **Dependency Graph:** An isolated sub-graph showing only the nodes in that task's dependency chain, with interactive navigation.
- **Subtask Table:** All prerequisites laid out with status, time estimates, and clickable links for quick traversal.
- **Monte Carlo Simulation:** Run a stochastic simulation across the full dependency chain (10,000 samples). View a histogram of estimated completion times with expected duration, standard deviation, and confidence intervals.
- **Goal Sidebar:** Toggle a panel listing your ranked goals with completion stats and drag-to-reorder priority.

### Events

Plan work that shouldn't clutter your graph until the time is right.

- **Named Events:** Group future work under events like "Conference Q4" or "Project Launch."
- **Dormant Nodes:** Attach hidden nodes that stay invisible until their event fires.
- **Three Trigger Modes:** Manual (click a button), date-based (fires on a schedule), or node-based (fires when a specific node is marked Done).
- **Activation Delays:** Stagger dormant nodes with time offsets from the trigger.

### Settings

- **Algorithm Profiles:** Default (balanced), Curious (emphasizes interest), Industrious (emphasizes value), or Custom (full control over every hyperparameter).
- **Custom Node Types:** Add/remove/reorder types with custom shapes and colors.
- **Visual Customization:** Configure status colors, edge type colors, and reset to defaults.
- **Time Units:** Set hours-per-week and hours-per-month conversions.

---

## Edge Types

- **Hard Prerequisites** (solid arrows): Must be completed before the dependent node becomes eligible. These gate the priority algorithm.
- **Soft Prerequisites** (dashed arrows): Helpful but not blocking. They contribute value without preventing progress.
- **Synergies** (blue bidirectional arrows): Mutually beneficial relationships where working on one boosts the value of another.
- **Cycle Detection:** The graph prevents circular dependencies, keeping your task structure solvable.

---

## Contexts & Community Detection

- **Hierarchical Contexts:** Organize nodes into Contexts and Subcontexts. Subcontexts cascade — selecting a parent automatically includes its children.
- **Connected Components:** Identify disconnected "island" projects.
- **Louvain Clustering:** Discover tightly-knit clusters of related tasks.
- **Orphan Detection:** When restructuring contexts or types, the app identifies affected nodes and guides you through migration.

---

## External Integrations

- **Obsidian:** Link vault notes to nodes and open them from the right-click menu.
- **Google Drive:** Attach Drive links and open from context menu.
- **Website URLs:** Store and access any external URL per node.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| **Double-click node** | Open node editor |
| **Right-click node** | Context menu |
| **Right-click + drag** | Pan canvas |
| **Scroll** | Zoom in/out |
| **Ctrl + Click** | Multi-select nodes |
| **Delete / Backspace** | Delete selected nodes (with confirmation) |
| **Ctrl + S** | Save node editor |
| **Left-click background** | Deselect all nodes |

---

## Getting Started

```bash
# Install dependencies
conda env create -f environment.yml
conda activate skilltree

# Launch (sandbox mode — safe for experimentation)
python app.py -sandbox

# Launch (production — uses your real data)
python app.py
```

The app opens automatically at `http://127.0.0.1:8050`.
