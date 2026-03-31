# Skill Tree

A graph-based task manager and priority engine built with [Dash](https://dash.plotly.com/) and [Cytoscape.js](https://js.cytoscape.org/). Model your goals, skills, habits, and resources as an interactive node graph — then let the priority algorithm tell you what to work on next.

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## What It Does

Skill Tree breaks away from traditional list-based task managers. By mapping out tasks into a bidirectional dependency graph, the app calculates the **Return on Investment (ROI)** for every possible thing you could do, naturally bubbling up high-value prerequisite tasks to the top. 

Here are the core components that make the engine tick:

### Interactive Graph Canvas
- **Visual Node Graph:** Drag, zoom, and explore nodes rendered with a force-directed (COSE) layout. Primary interaction is mapped intuitively (Right-click to pan canvas, Left-click to interact).
- **Visual Language:** Nodes are color-coded by status (Open is blue, Blocked is red, Done is green) and styled by type (Goals are natively rendered as yellow stars, Topics, Skills, etc. have distinct custom shapes). 
- **Right-Click Context Menus:** Quickly toggle completion, delete nodes, open associated Obsidian vault files, or jump straight to a node's full dependency / synergy chains. 
- **Hover Tooltips:** Get immediate summaries including time estimates and Monte Carlo standard deviations without clicking.

### Goals & Subtasks System
- **Goals Tab:** A dedicated workspace for overarching objectives. Goals are prioritized with explicit ranks (#1, #2, #3, ...) which act as powerful multiplier bonuses in the scoring algorithm.
- **Mini Dependency Graphs:** Inside the Goals Tab, focus on an isolated sub-graph containing only the subtasks strictly necessary to achieve that specific goal.
- **Progress Tracking:** Goals automatically track the percentage completion of their underlying subtasks, converting to "Done" seamlessly when prerequisites are cleared.

### Events & Dormant Nodes
- **Trigger-Based Workflows:** Want to plan tasks that shouldn't clutter your graph until the time is right? Tie them to Events.
- **Automated Triggers:** Events can be triggered manually, scheduled to open on a specific **Date**, or set to automatically fire when a specific **Node completes**.
- **Activation Delays:** Nodes tied to events can be staggered (e.g., spawn Task B exactly 2 weeks after the triggering event fires). 

### Monte Carlo Simulation Engine
- Beyond elementary time estimates, Skill Tree employs a built-in Monte Carlo simulation engine.
- By providing Optimistic, Most Likely, and Pessimistic time bounds, the engine runs critical-path analysis across your entire dependency chain thousands of times, surfacing highly accurate Expected Times and Standard Deviations directly in your suggestions.

### Dynamic Settings & Contexts
- **Highly Configurable:** The Settings modal lets you tune all algorithm hyperparameters without touching code, switch between ideological profiles (e.g. "Curious" vs "Industrious"), and enforce logic rules (like standard 1:4 ratios for weeks-to-months conversions).
- **Custom Node Types:** Manage custom shapes and colors for brand new node types dynamically.
- **Hierarchical drill-down:** Formally map Subcontexts to Parent Contexts to keep massive graphs perfectly filtered. 
- **Community Detection:** Built-in modularity algorithms let you isolate tightly-knit clusters of tasks or identify completely disconnected "island" projects.

---

## The Priority Scoring Algorithm

The core capability of the app is the algorithm determining priority scores:

**Score = Eligibility × (Recursive Total Value / Perceived Cost)**

1. **Eligibility Filter:** A node is ineligible (score = -1) if any of its **Hard Prerequisites** are incomplete. Soft Prerequisites do not block nodes.
2. **Intrinsic Value:** Based on user-assigned 'Value' and 'Interest'.
3. **Network Value:** The algorithm recursively looks continuously downstream. A node inherits discounted value from what it **Hard Unlocks**, what it **Soft Unlocks**, and nodes it provides **Synergy** to. Completing a foundational bottleneck task will artificially inflate its score because of everything resting on top of it.
4. **Perceived Cost:** A penalty sub-linearly scaled by the task's **Difficulty** and the Monte Carlo **Time Estimate**. Long, agonizing tasks are penalized, but not purely linearly (a 100-hour task isn't 100x worse than a 1-hour task).

---

## Project Architecture

Skill Tree runs locally as a Dash web application backed by SQLite. The codebase is heavily modularized with thorough Pytest coverage:

- **`models.py`:** Core dataclasses for Nodes and Events.
- **`graph_manager.py` / `event_manager.py`:** Separation of concerns handling CRUD operations, database queries, and complex graph state cascades.
- **`simulation.py`:** The topological BFS sorting and Monte Carlo sample generation engine.
- **`scoring.py`:** The recursive network-value priority scoring algorithm.
- **`app.py`, `callbacks.py` & layout modules:** The presentation layer dynamically updating cytoscape trees, context menus, and toolbars based on UI interactions.

---

*(Note: Features and behavior tailored for subjective continuous usage)*
