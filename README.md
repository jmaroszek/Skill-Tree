# Skill Tree

A graph-based task manager and priority engine that tells you what to work on next.

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## What It Does

Skill Tree replaces traditional to-do lists with a **bidirectional dependency graph**. Instead of staring at a flat list wondering what to tackle first, you map out tasks, goals, and their relationships — then let the priority algorithm calculate the **Return on Investment (ROI)** of every possible action, naturally bubbling up high-value prerequisite tasks to the top.

---

## The Priority Algorithm

The heart of Skill Tree is an ROI-based scoring engine that ranks every eligible task:

**Score = Eligibility x (Total Value / Perceived Cost)**

- **Eligibility Filter:** A node scores -1 if any Hard Prerequisite is incomplete. Soft Prerequisites never block — they just add value.
- **Intrinsic Value:** Derived from your user-assigned **Value** (1-10) and **Interest** (1-10) ratings.
- **Network Value:** The algorithm looks continuously downstream. A node inherits discounted value from everything it **Hard Unlocks**, **Soft Unlocks**, and provides **Synergy** to. Foundational bottleneck tasks naturally rise to the top because the entire graph rests on them.
- **Perceived Cost:** A sub-linear penalty based on **Difficulty** and the Monte Carlo **Time Estimate**. Long tasks are penalized, but not linearly — a 100-hour task isn't treated as 100x worse than a 1-hour task.


|Rating|Value|Interest|Effort|
|---|---|---|---|
|1|No Value: Purely cosmetic; zero skill crossover or utility.|Aversion: You feel active resistance or dread when starting.|Reflexive: Requires no active thought; muscle memory only.|
|2|Negligible: A "one-off" fix with no long-term reuse.|Boring: Monotonous; requires external stimulation to finish.|Linear: A single-step task with a known, clear outcome.|
|3|Minor: Slightly optimizes a minor, infrequent workflow.|Indifferent: No strong feelings; purely transactional.|Routine: Requires basic focus; utilizes existing skills only.|
|4|Helpful: Adds a niche tool or specific knowledge point.|Mild: Curious about the result, but not the process.|Instructive: Requires looking up documentation or syntax.|
|5|Solid: Fills a defined gap in your current skill set.|Curious: The process itself is mildly mentally rewarding.|Integrated: Requires connecting 2–3 familiar concepts.|
|6|Marketable: Demonstrates a competency relevant to your field.|Engaged: You look forward to the "problem-solving" aspect.|Technical: Involves a new domain or unfamiliar library/logic.|
|7|Strategic: Unlocks the ability to start 2+ advanced projects.|Excited: You brainstorm ideas for it during "off" hours.|Abstract: Requires architectural planning and logic design.|
|8|High Impact: A major upgrade to your primary capabilities.|Deep Flow: You consistently lose track of your surroundings.|Complex: High "mental RAM" usage; many moving variables.|
|9|Foundational: A keystone skill for your long-term identity.|Obsessed: You find it difficult to stop once you start.|Multidisciplinary: Requires synthesizing disparate systems.|
|10|Critical: The "North Star"; essential for your top-tier goals.|Pure Passion: Total immersion; the activity is its own reward.|Experimental: Solving an unsolved or highly unique problem.|


---

## Interactive Graph Canvas

- **Visual Node Graph:** Drag, zoom, and pan across a force-directed (COSE) layout. Right-click to pan the canvas, left-click to interact with nodes.
- **Color-Coded Status:** Nodes are colored by status — blue for Open, red for Blocked, green for Done, yellow for Goals.
- **Distinct Node Shapes:** Each node type gets its own shape — stars for Goals, triangles for Actions, pentagons for Resources, ellipses for Learn, and more.
- **Right-Click Context Menus:** Toggle completion, delete nodes, open linked Obsidian notes, launch a simulation, or jump to a node's full dependency chain — all from a right-click.
- **Hover Tooltips:** Instantly see a node's time estimate, Monte Carlo standard deviation, and key stats without clicking.
- **Multi-Select:** Ctrl+Click to select multiple nodes at once.

---

## Edge Types & Relationships

Skill Tree supports four distinct relationship types between nodes:

- **Hard Prerequisites** (solid arrows): Must be completed before the dependent node becomes eligible. These gate the priority algorithm.
- **Soft Prerequisites** (dashed arrows): Helpful but not blocking. They contribute value without preventing progress.
- **Synergies** (blue bidirectional arrows): Mutually beneficial relationships where working on one node boosts the value of another.
- **Resource Dependencies** (dotted arrows): Links to materials, tools, or references needed for a task.
- **Cycle Detection:** The graph prevents you from creating circular dependencies, keeping your task structure clean and solvable.

---

## Goals & Subtasks

- **Dedicated Goals Tab:** A focused workspace for your overarching objectives, separate from the main graph.
- **Priority Ranking:** Rank goals as #1, #2, #3, etc. Each rank acts as a powerful **score multiplier** in the algorithm, ensuring subtasks of your top goals rise to the surface.
- **Mini Dependency Graphs:** Each goal displays an isolated sub-graph containing only the nodes strictly necessary to achieve it. Edit and toggle completion right from the goal view.
- **Auto-Progress Tracking:** Goals automatically compute completion percentage from their subtasks and transition to "Done" when all prerequisites are cleared.
- **Blocked Detection:** Goals automatically show as blocked when all remaining subtasks are themselves blocked.

---

## Events & Dormant Nodes

Plan work that shouldn't clutter your graph until the time is right.

- **Named Events:** Create events like "Conference Q4" or "Project Launch" to group future work.
- **Dormant Nodes:** Attach hidden nodes to events. They stay invisible on the canvas until their event triggers, keeping your graph clean.
- **Three Trigger Modes:**
  - **Manual:** Click a button to fire the event when you're ready.
  - **Date-Based:** Schedule the event to trigger on a specific date.
  - **Node-Based:** Automatically trigger when a specific node is marked Done.
- **Activation Delays:** Stagger dormant nodes — e.g., "Promote webinar" activates 2 weeks after "Webinar Published" is completed.
- **Cascading Triggers:** Completing a node can trigger linked events, which awaken their dormant nodes in one smooth cascade.

---

## Monte Carlo Simulation Engine

Go beyond simple time estimates with stochastic simulation.

- **PERT Estimates:** Provide Optimistic, Most Likely, and Pessimistic time bounds for any node. The engine uses proper beta distributions — not simple averages.
- **Critical Path Analysis:** Select any node and run a Monte Carlo simulation across its entire dependency chain (10,000 samples by default).
- **Rich Results:** View a histogram of estimated completion times plus key statistics — expected duration, standard deviation, and 5th/95th percentile bounds.
- **Chain Summary:** See every node in the critical path, with clickable links to navigate the main canvas.
- **Flexible Inclusion:** Optionally include soft dependencies and synergies in the simulation for a fuller picture.

---

## Smart Suggestions

The Suggestions panel shows your **top-N eligible nodes** ranked by ROI score, normalized to a 0-100 scale. Suggestions update live as your graph changes.

Filter suggestions by:
- Context and Subcontext
- Minimum Value or Interest threshold
- Maximum Time or Difficulty
- Node Type
- Specific Goal (show only that goal's subtasks)

Adjust the number of suggestions shown with increase/decrease buttons.

---

## Contexts & Community Detection

### Hierarchical Contexts
- Organize nodes into **Contexts** and **Subcontexts** for clean filtering across large graphs.
- Subcontexts cascade — selecting a parent context automatically includes its children.
- Dropdowns update dynamically as you add or rename contexts.

### Community Detection
- **Connected Components:** Identify completely disconnected "island" projects with no ties to the main graph.
- **Louvain Clustering:** Run modularity algorithms to discover tightly-knit clusters of related tasks.
- **Orphan Detection:** When restructuring contexts or node types, the app identifies affected nodes and guides you through a migration workflow to prevent data loss.

---

## Settings & Customization

### Algorithm Profiles
Tune how the priority algorithm weighs competing factors:
- **Default:** Balanced weights across value, interest, and cost.
- **Curious:** Emphasizes interest — great for exploratory, learning-driven phases.
- **Industrious:** Emphasizes value and penalizes difficulty more — ideal for shipping mode.
- **Custom:** Set every hyperparameter yourself — value/interest weights, edge discount factors, effort/time cost weights, sub-linearity exponent, and goal boost multiplier.

### Custom Node Types
- Add, remove, and reorder node types beyond the defaults.
- Assign custom shapes (rectangle, circle, triangle, pentagon, star, and more) and colors per type.

### Visual Customization
- Configure node colors per status (Open, Blocked, Done, Goal).
- Reset to defaults at any time.

### Time Units
- Configure hours-per-week and hours-per-month conversion ratios.
- Time estimates auto-format to the most readable unit (e.g., "2w" instead of "80h").

---

## External Integrations

- **Obsidian:** Link one or more Obsidian vault notes to any node. Open them directly from the right-click context menu.
- **Google Drive:** Attach Google Drive links to nodes and open them from the context menu.
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
