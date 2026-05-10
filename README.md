# Skill Tree

**A to-do list that understands *why* things matter.**

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

---

## What is this, really?

Most to-do lists let you pile up tasks and check them off. That's fine until the list grows past a few dozen items — then every morning becomes a "what on earth do I do first?" problem. You know some things matter more than others. You know some things have to happen before other things. You know some tasks are fun and some are slogs. A flat list doesn't capture any of that.

Skill Tree is a different kind of to-do list. You still jot down tasks, but you also draw lines between them: "I can't do *this* until I finish *that*." "These two help each other." "This little thing unlocks a bigger goal." Once the lines are in place, the app looks at the whole picture and tells you — every morning — the single most worthwhile thing to tackle next.

**[SCREENSHOT: the overall app window showing the Next tab with the ranked list, so readers can anchor on the vibe before we dig in.]**

It's called Skill Tree because the relationships between your tasks start to look like a tree of skills — the little roots at the bottom are the foundational things, the big showy fruits at the top are your goals.

---

## The tour we're about to take

This README walks through the app using a real example dataset (the **sandbox**) so you can see every feature in context. The sandbox is a made-up portrait of someone who's trying to get in shape, save money, get promoted at work, learn Spanish, and have friends over for dinner. It has 67 tasks, 80 connections between them, and 3 upcoming events. When you see phrases like *"Run First 5K"* or *"Save $10k Emergency Fund"* throughout, those are real nodes in the sandbox.

If you want to follow along, skip down to [Getting Started](#getting-started) first and launch the app in sandbox mode. Then come back here.

---

## The six tabs

Across the top of the window there are six tabs: **Next**, **Nodes**, **Details**, **Events**, **Analyze**, and **Settings**. They're each a different way of looking at the same underlying web of tasks.

**[SCREENSHOT: close-up of the top tab bar with all six tabs visible.]**

---

## Next — the "just tell me what to do" tab

This is the tab the app opens on. It's designed so that if you only ever looked at one screen, this is the one that would still be useful.

At the top you'll see three sections:

- **MANUAL OVERRIDE** — if you've told the app "I want to work on this specific thing today," it shows up here. You can right-click any node on the Nodes tab and set it as a manual override.
- **PRIORITY GOALS** — the three goals you've marked as most important, in order. In the sandbox these are *Run First 5K* (#1), *Save $10k Emergency Fund* (#2), and *Hold A 10-Minute Spanish Conversation* (#3). The #1 goal gets a bigger nudge in the rankings than #2, which gets more than #3.
- **TOP RECOMMENDATIONS** — the live ranking. Every eligible task gets a score out of 100, and the highest-scoring ones sit at the top.

**[SCREENSHOT: the Next tab with the three sections visible, showing "Download Couch-To-5K App" at the top of the recommendations with a big "100".]**

### Reading the ranked table

Each row is a task. The columns tell you everything at a glance: its name, its type (Action? Learning? Resource?), what life area it belongs to (Health, Finance, Career, etc.), its priority score, how you rated it on Value/Interest/Effort, how long it'll take, and whether it has any linked notes in Obsidian or Google Drive.

**[SCREENSHOT: close-up of a single row in the top-recommendations table, with columns labeled.]**

The checkmark/x columns (Obsidian, Drive, Override) show at a glance whether a node has an external note, a linked file, or is currently being manually overridden. Clicking the priority score opens a popup that shows exactly how the algorithm arrived at that number — including any adjustments from the two levers below.

### Shaping the ranking across contexts

Two settings in the **Settings** tab shape how contexts interact with the ranking, both applied after a task's raw score is computed:

- **Context weights** (*Settings → Contexts → Priority Weights*) let you say "Health matters more than abstract math" even before you've decomposed those areas. Each context gets a weight; 1.0 is baseline, 2.0 doubles that context's scores relative to others, 0.5 halves them.
- **Density normalization** (*Settings → Algorithms → Context Density Exponent α*) counteracts the bias where a heavily-decomposed context would otherwise crowd out a sparser one just because it has more nodes competing for top-N slots. Default α = 0.3 compensates mildly; 0 disables it, 1.0 fully cancels size bias. Each profile ships with a sensible α starting point — tune to taste. Uncategorized nodes (no context set) are exempt — they don't share a bucket and don't penalize each other.

When either lever is active, the explain-score popup surfaces an **Adjustments** section that breaks the final score down multiplier by multiplier. The math is documented in full in [`technical_overview.md`](technical_overview.md).

### Filters

On the right of the Next tab is a **Filters** panel. It can narrow the ranked list to any slice you want:

- By **context** (Health, Finance, Career, Home, Social, Learning in the sandbox)
- By **subcontext** (once a context is picked, its sub-areas appear)
- By **node type** (hide Resource nodes, for example)
- By **value / interest thresholds** (hide the 1s and 2s)
- By **maximum time or difficulty** (show me only things under 2 hours)
- By **which goal** a task belongs to (show me only *Run First 5K* subtasks)

There's a **Clear Filters** button and a counter at the top that shows how many tasks matched.

**[SCREENSHOT: the filters panel open with several filters applied, and the result count visible.]**

### The suggestion counter

Small thing but worth mentioning — above the table, the app shows "Showing top X of Y eligible." Useful when filters trim the list.

---

## Nodes — the full graph

Click **Nodes** and you're looking at your entire task network as a graph. Dots for tasks, lines between them. The physics engine auto-arranges things so related stuff clumps together.

**[SCREENSHOT: the full Nodes tab with the sandbox graph sprawling out, sidebars collapsed.]**

### The visual code

Every dot is color-coded and shaped:

- **Yellow stars** are **Goals** (the five in the sandbox: *Save $10k Emergency Fund*, *Earn Senior-Level Promotion*, *Run First 5K*, *Hold A 10-Minute Spanish Conversation*, *Host A Dinner Party For 6 Friends*).
- **Blue circles** are open **Learn** items (*Read "Born To Run"*, *Learn 500 Core Spanish Words*).
- **Orange triangles** are open **Actions** (*Track Expenses For A Month*, *Call Parents Weekly*).
- **Purple pentagons** are **Resources** — things you can repeatedly draw on (*Watch Plumbing YouTube Tutorial*).
- **Orange diamonds** (or whichever shape you've configured) are **Milestones** — measurable achievement targets that don't compete in the ranking algorithm but stay visible as motivation.
- **Red** means the task is **Blocked** — you can't start it yet because a prerequisite isn't done.
- **Green** means **Done**.

The five types each answer a different question. There's a deeper section on this — [Choosing the right node type](#choosing-the-right-node-type) — worth reading once before you build out a graph in earnest.

The lines between them have meaning too. Solid arrows are **Hard Prerequisites** — *you literally cannot do the arrow's destination until the source is Done*. Dashed arrows are **Soft Prerequisites** — helpful but not strictly required. Wavy lines are **Synergies** — two tasks that boost each other's value.

**[SCREENSHOT: a close-up of a small portion of the graph showing one of each: a yellow star (goal), a red blocked node, a green done node, and examples of the three arrow styles.]**

### Interacting with the graph

- **Drag** a node to reposition it.
- **Scroll** to zoom in and out.
- **Right-click + drag** on empty canvas to pan.
- **Left-click** empty canvas to deselect everything.
- **Ctrl+Click** multiple nodes to select a group.
- **Delete** or **Backspace** removes the selected nodes (with a confirmation pop-up — no accidents).
- **Hover** over any node and a tooltip pops up with its time estimate, the spread (how uncertain the estimate is), and its key stats.

**[SCREENSHOT: a tooltip floating next to a node, showing the hover info.]**

- **Double-click** a node to open the **Node Editor** (a full sidebar on the right).
- **Right-click** a node to get a context menu with quick actions: *Edit*, *Details*, *Toggle Done*, *Delete*, and — if the node has linked external files — *Open in Obsidian* and *Open in Google Drive*.

**[SCREENSHOT: the right-click context menu popped out from a node.]**

### The search box

Top of the Nodes tab has a **Search** field. Type any part of a name and it filters the dropdown. Click the crosshair icon next to it and the graph will pan/zoom to center that node. Handy when you have 67+ nodes and you're looking for something specific.

**[SCREENSHOT: the search box with "5K" typed into it and the dropdown filtered.]**

### The node editor — where you actually build your graph

Double-click any node (or right-click → *Edit*) and a big sidebar slides out on the right. This is where you define everything about a task.

**[SCREENSHOT: the full node editor sidebar open on *Run First 5K*, with all the sections visible.]**

Working top to bottom:

- **Name.** The primary identifier. Renaming is safe — all the arrows and events follow automatically.
- **Aliases.** Click the expand arrow next to the name field to add alternate names. Useful if you sometimes call the same task different things.
- **Type.** Goal, Learn, Action, Resource, or Milestone. (You can add your own types in Settings.) See [Choosing the right node type](#choosing-the-right-node-type) for what each one means and how to pick.
- **Context + Subcontext.** Which area of your life this belongs to. The subcontext list automatically updates when you pick a context.
- **Description.** Free-text notes about the task.
- **Competence.** Seven levels from *Outsider* all the way to *Innovator*. Click the question mark for a popup explaining each level.

**[SCREENSHOT: the Competence popup showing all seven levels with descriptions.]**

- **Ratings: Value / Interest / Effort.** Each on a 1-10 scale. Click a number to set it. Click the question mark for the rating descriptions.
- **Inherit (Ratings).** A toggle right next to Override. Treats this node as a *pure container* — its own value, interest, and effort all drop out of scoring, and the node's priority comes entirely from what cascades up from its children. Use for "header" nodes that exist purely to group other things (e.g. a `Transcendentalism` Learn that sits above `Walden` and `Emerson Essays` and has no work of its own beyond reading them).

**[SCREENSHOT: the Ratings popup showing what each number on the Value scale means.]**

- **Status.** Open, Blocked, or Done. (Blocked sets automatically if a hard prerequisite isn't done, but you can override.)
- **Time Estimates.** Three numbers — *Optimistic* (if everything goes right), *Expected* (most likely), *Pessimistic* (if it goes sideways). Pick your unit — Hours, Days, Weeks, or Months. The app blends these three numbers into a single expected duration using a method called PERT estimation. If you'd rather skip the three-number thing, choose **Inherit** and the node will pull its time from whatever feeds into it.

#### When to use which Inherit toggle

The two Inherit toggles — one next to the Ratings sliders, one inside Time Estimates — are independent. You'll often want one but not the other:

- **Inherit Time only** (most common for headers): the node has its own *importance* worth rating (e.g. a `Mastery` Learn header you genuinely care about, with v=7 / i=7), but its actual *time investment* is just the sum of reading the books underneath it. Set Inherit on Time, leave Inherit on Ratings off, and rate value/interest/effort the way you would for any focused topic.
- **Inherit Ratings only**: rare. Mostly a transient state while you're toggling things — not a typical persistent setting.
- **Both Inherit on**: pure container. The node has no work of its own at all — it exists purely as a structural grouping, and its score is exactly the rolled-up score of its children. Mark it Done when all the children are done.
- **Neither**: standard. The node has its own time, ratings, and effort. This is the default for atomic Learns, Resources, and most Actions.

Quick rule of thumb: *if you'd describe a node as "the topic itself,"* leave Inherit Ratings off; *if you'd describe it as "the thing that holds these other things,"* turn it on.
- **Progress** (for Resource nodes only) — a 0-100% slider so you can track partial completion on ongoing resources.
- **Relationships: Hard / Soft / Supports.** Dropdowns where you pick the other nodes this one depends on (Hard/Soft) or mutually boosts (Supports). This is how you grow the web.

**[SCREENSHOT: the relationships section showing several nodes linked as hard prerequisites.]**

#### What the three edge types actually mean

These three relationship types aren't just "stronger" and "weaker" versions of the same idea — they encode genuinely different kinds of connections, and the scoring algorithm treats each one differently. Worth understanding before you draw a lot of arrows.

- **Hard** — a *must-do* prerequisite. The knowledge from A is required for B, or A is just the order that makes most sense to do things in. *Example: algebra has to come before calculus; an introductory book before a reference text.* Hard edges are the only ones that gate eligibility — a node with an incomplete hard prereq is automatically Blocked. The scoring algorithm propagates value strongly through Hard edges (and transitively, so a node sitting upstream of a long Hard chain inherits real weight).
- **Soft** — *helpful, but not required*. Provides value to the dependent task; you could complete the dependent without it and probably do okay on intuition alone. *Example: learning UX design before setting up a website.* Soft edges propagate value too, but with a smaller per-hop discount than Hard. The Curious profile leans into Soft edges; Industrious leans away from them, since Industrious is built around the critical path.
- **Supports / Synergy** — *mutual multiplicative reinforcement*, not a weaker prereq. Two nodes that, done together, are significantly more valuable than the sum of their parts. *Example: Zen and Taoism — learning more about either one deepens your understanding of the other.* Synergy is bidirectional and lateral; it does *not* sit on the same "necessity" axis as Hard and Soft. The scoring algorithm reflects this with two distinct effects: a small **pair bonus** that co-promotes synergy partners into joint consideration before either is started, and a larger **completion multiplier** that boosts a node's intrinsic value once a synergy partner is Done. (More on the multiplier in Settings → Scoring.)

The visual treatment in the subtasks table mirrors this: Hard and Soft sit in the same cool-blue family with different intensities (necessity gradient), while Synergy lands in a distinct teal because it's a categorically different relationship.

- **Obsidian / Google Drive / Website.** Add rows to link external notes and files. Each row has a small browse button to pick a file and an open button to launch it.
- **Override.** A toggle that lets you manually force a priority boost on this node. Useful when the algorithm's ranking doesn't match your gut on a given day.

At the bottom: **Save**, **Save & Close**, and **×** (close without saving). If you have unsaved changes and hit close, a confirmation pops up.

**[SCREENSHOT: the unsaved-changes confirmation modal.]**

### Graph layout controls

Below the graph canvas there's a small settings panel (you can collapse it) with three sliders: **Edge Length**, **Gravity**, and **Repulsion**. These tune how the physics engine arranges nodes. There's also a **Relayout** button to reshuffle and a **Restore Defaults** button.

**[SCREENSHOT: the graph-layout sliders panel.]**

---

## Details — zoom in on one node at a time

The Nodes tab is your whole graph. The **Details** tab is a microscope on one node.

**[SCREENSHOT: the Details tab with *Run First 5K* selected — its mini dependency graph on the left, subtask table in the middle, goal sidebar on the right.]**

Pick a node from the search bar at the top (or get to this tab via right-click → *Details* on the Nodes tab). You'll see:

### The mini dependency graph

A tidy sub-graph showing only the nodes in *this one task's* dependency chain. In the sandbox, looking at *Run First 5K* reveals *Complete Week 4 Runs* as a hard prerequisite, plus helpers like *Get Annual Physical*, *Start Strength Training Program*, and *Stretch Daily*.

**[SCREENSHOT: the isolated dependency graph for *Run First 5K*.]**

Controls:

- **Max Depth slider** — how many hops deep to show (1-5 or All).
- **Animate** toggle — turn the spring physics on/off.
- **Neighbor links** toggle — show or hide non-prereq connections.

There are also two resize handles (horizontal and vertical) on the panel so you can stretch it, plus a **Fullscreen** button that expands the sub-graph to fill the whole window.

**[SCREENSHOT: the subgraph in fullscreen mode.]**

### The subtask table

Below the graph, a table of every prerequisite in the chain: status, time, and clickable links to Obsidian / Drive if set. Each row has a small trash icon to remove the link between this node and that one (it does *not* delete the node — just the edge).

**[SCREENSHOT: the subtask table with several rows, highlighting the trash-icon column.]**

### Back / Forward navigation

Because you'll often hop from node to node, the Details tab remembers where you've been — there are ← and → arrows at the top, just like a web browser.

### The Goals sidebar

Toggle open the right sidebar for a ranked list of your Goals with live completion stats (*3 of 12 subtasks done, 25%*). You can **drag to reorder** the list — the top 3 become your Priority Goals, which get the algorithm's goal-boost bonus.

**[SCREENSHOT: the Goals sidebar open with the five sandbox goals listed and the top three highlighted.]**

### Monte Carlo simulation

One of the coolest features. Click **Run Simulation** and the app will sample task durations 10,000 times across the entire dependency chain, showing you:

- A histogram of how long the whole chain might take.
- The **expected duration** (average).
- **Standard deviation** (how spread out the outcomes are).
- Confidence intervals: *50% confidence* (the median), *75%*, and *95%* — "95% of the time, this will take less than X."

**[SCREENSHOT: the simulation histogram with the percentile markers labeled.]**

This is hugely useful when a goal feels vague. You can tell your partner "running a 5K will probably take 8-14 weeks" instead of shrugging.

### Suggestions

A small panel below the graph shows quick-add suggestions — nodes that might plausibly belong in this subgraph. Click to add.

---

## Events — plan the future without cluttering today

**[SCREENSHOT: the Events tab with the Events sidebar open showing three events listed.]**

Some tasks you don't want to see yet. You know you'll need to book flights for a summer trip, but why should *Book Flights* clutter your "what do I do today" view in April?

That's what Events are for. An Event is a bundle of tasks that stay **dormant** (hidden, not scored, not shown) until the event triggers.

The sandbox has three examples:

- **Summer Vacation** (date-triggered, 2026-07-01). When July 1 rolls around, three dormant nodes wake up: *Book Flights*, *Research Destinations*, *Create Packing List*.
- **New Year Kickoff** (date-triggered, 2027-01-01). Activates *Begin Meditation Streak*, *Start Duolingo Streak*, *Start Gym Membership*.
- **Move To New Apartment** (node-triggered). Waits until the node *Sign Lease* is marked Done, then wakes up *Book Movers*, *Buy A Couch*, *Change Mailing Address*, *Set Up Utilities*.

### Three trigger types

- **Manual** — you click a button when you're ready. Good for "when I feel like it" batches.
- **Date** — fires when a specific date arrives.
- **Node** — fires when a specific task flips to Done.

### The Events sidebar

Open it from the left-side toggle. It shows every event, search-filterable, with sort modes (Manual order, A→Z, Z→A). There's a **Hide Triggered** checkbox so your old/fired events don't clutter the list, and a **New Event** button.

**[SCREENSHOT: the events sidebar with the three sandbox events listed and sort controls visible.]**

You can **drag-to-reorder** events to get your preferred manual ordering.

### The event editor

Click an event to open its editor on the right. Fields: **Name**, **Description**, **Trigger Type** (radio), **Trigger Date** (if Date), **Target Node** (if Node).

Below the editor, a **Dormant Nodes** table lists every task waiting for this event. You can add new dormant nodes here — clicking the **+** button opens a modal very similar to the regular node editor, plus an **Activation Delay** field (e.g. "wake this one up 2 weeks *after* the event fires").

**[SCREENSHOT: the add-dormant-node modal showing all the fields.]**

### Announcements

When an event triggers (either on its own or when you manually click the trigger button), an **Announcements modal** pops up confirming what just woke up. It's a gentle nudge rather than a silent change.

**[SCREENSHOT: the announcements modal after an event trigger.]**

### The events graph

Just like the Details tab, the Events tab has its own mini-graph showing the event's dormant nodes and how they relate, with the same fullscreen and graph-settings controls.

---

## Settings — make it yours

**[SCREENSHOT: the top of the Settings tab showing the Algorithm Profile dropdown.]**

### Algorithm profiles

Four presets, plus custom:

- **Default** — balanced across everything.
- **Curious** — weights Interest more heavily than Value, good when you want the algorithm to push "fun" stuff up the list.
- **Industrious** — weights Value and Effort more, for when you want to grind through the hard-but-important stuff.
- **Custom** — full manual control of every hyperparameter.

The custom inputs include:

- **Value emphasis** — how much your Value rating matters.
- **Interest emphasis** — how much your Interest rating matters.
- **Effort penalty** — how much harder tasks get deprioritized.
- **Hard prerequisite boost** — how much a node's priority inherits from things that depend on it via hard edges.
- **Soft prerequisite boost** — same but for soft edges.
- **Pending Bonus** — a small extra weight applied to synergy partners regardless of completion state. Co-promotes synergy pairs so they tend to surface together in the ranking before any work starts. Keep this small — typical values 0.05–0.15.
- **Done Multiplier** — the multiplicative kick applied to a node's intrinsic value once a synergy partner is Done. Each Done partner adds this much to the multiplier (e.g. 0.40 means one Done partner makes the node 40% more valuable; two Done partners makes it 80% more valuable). This is what captures the "doing both is more than the sum of the parts" intent.
- **Goal boost** — how much extra nudge a Priority Goal gets.
- **Time estimate weight** — how heavily the time estimate affects cost.
- **Time mode** — how the three PERT numbers blend.

Each input has a small **↺** (restore) button to go back to the default.

**[SCREENSHOT: the hyperparameter section of Settings showing several inputs.]**

### Graph layout defaults

Per-canvas layout tuning — separately for the main Nodes graph, the Details sub-graph, and the Events sub-graph. Edge length, gravity, repulsion.

### Time estimate defaults

When you create a new node, these are the values pre-filled in its PERT fields (Optimistic / Expected / Pessimistic) and unit.

### Time conversion

Set how many **hours per week** and **hours per month** you expect to work on Skill Tree tasks. This is what turns a "14 hour" estimate into "roughly 2 weeks of your real life" in tooltips.

### Node type manager

Add, delete, or reorder node types. Each type has a color (color picker) and a shape (dropdown of Cytoscape shapes — ellipse, triangle, star, pentagon, square, diamond, etc.). You can change both at any time.

**[SCREENSHOT: the Node Types manager showing the five built-in types with color swatches and shapes.]**

### Subcontexts per context

The subcontext list is editable per context. In the sandbox, **Health** has subcontexts like *Exercise* and *Preventive*; **Finance** has *Savings* and *Investing*; etc. Add or remove subcontexts here.

### Status colors

Customize the Open / Blocked / Done / Goal / Override colors directly. Restore defaults any time.

### Linter

A toggle for the optional **title-case linter** — when on, it flags node names that don't follow consistent title case, with an editable list of exclusions (small words like "a", "the", "and" that stay lowercase).

### Analyze tab options

Configure how many items each section of the Analyze tab shows.

---

## Analyze — the "zoom out" tab

The Analyze tab is the bird's-eye view of your whole portfolio. Instead of "what do I do next," it answers questions like "am I over-loaded in Health right now?" and "which goals share the most prerequisites?"

**[SCREENSHOT: the Analyze tab with multiple charts visible.]**

At the top, an **Overview** strip shows: total Goals, Active Nodes, Done, percentage Blocked, and total Remaining Time. In the sandbox: 5 Goals, 50 Active Nodes, 7 Done, 28% Blocked, 32.7 months of estimated remaining work.

Below that, sections (each configurable in Settings for how many items to show):

- **Goals** — side-by-side completion bars and a heatmap showing which goals share prerequisites.
- **Top time sinks** — nodes that'll consume the most hours.
- **Bottlenecks** — nodes that block the most downstream work.
- **Ratings breakdown** — average Value / Interest / Effort per context.
- **Goal risk** — goals whose dependency chain has the most Blocked or high-uncertainty nodes.
- **Dependency structure** — stats on the graph's connectedness, depth, and orphan nodes.
- **Context coverage** — how your estimated time is distributed across life areas.

**[SCREENSHOT: the Goals overlap heatmap with goal names on both axes.]**

Each chart is interactive — hover to see exact values, and the nodes it references are always real nodes you can jump to via the Nodes tab.

---

## The small stuff worth knowing

A grab-bag of features that don't fit cleanly into any one tab:

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **Double-click node** | Open the node editor |
| **Right-click node** | Context menu |
| **Right-click + drag** | Pan the canvas |
| **Scroll** | Zoom in/out |
| **Ctrl + Click** | Multi-select |
| **Delete / Backspace** | Delete selected (with confirmation) |
| **Ctrl + S** | Save in the node editor |
| **Left-click background** | Deselect all |

### Sidebars you can toggle

Most tabs have collapsible sidebars (filters, goals, events) that you can open or hide with a little toggle button. When a sidebar is open, the main canvas gets a drag-to-resize handle so you can balance the space however you want.

**[SCREENSHOT: mid-drag on a resize handle, showing the cursor and the subtle highlight.]**

### Fullscreen mode

Any of the graph views (main Nodes, Details sub-graph, Events sub-graph) has a Fullscreen toggle. Escape key exits.

### External link conventions

- **Obsidian** links store paths relative to your configured vault. The app opens them via the `obsidian://` URL scheme.
- **Google Drive** links can be either Drive URLs or local paths to Drive-synced files.
- **Website** links are just URLs — they open in your default browser.

### Cycle detection

The app won't let you create a circular dependency (A requires B requires C requires A). If you try, it warns you and refuses the edge.

### Migration helper

Renaming a Context or Type? The app notices which nodes are affected and opens a **migration modal** where you map old values to new, so nothing gets orphaned.

**[SCREENSHOT: the migration modal showing old values on the left and dropdowns for the new values on the right.]**

### Override conflict resolution

If you apply a priority override that would conflict with a pending event's override (or another active one), a modal asks you to pick which one wins.

### Error modal

If something goes wrong (invalid time estimate, duplicate name, etc.), a small error modal pops up with the specific message and a dismiss button. Errors never silently fail.

---

## Getting started

### First-time setup

```bash
# Install dependencies
conda env create -f environment.yml
conda activate skill-tree

# Launch in sandbox mode (uses the example dataset — safe to mess around)
python app.py --sandbox
```

The app opens automatically at `http://127.0.0.1:8050`.

### Sandbox vs. production

- **Sandbox** uses `data/sandbox_skilltree.db` — the example dataset described throughout this README.
- **Production** uses `data/skilltree.db` — your real life, once you've built it.

To launch production, drop the `--sandbox` flag:

```bash
python app.py
```

The window title changes from **"Skill Tree (Sandbox)"** to **"Skill Tree"** so you always know which dataset is live.

### Building your own graph

A sensible way to start:

1. Add a **Goal** for something you actually want (Type: Goal).
2. Break it into 2-4 big tasks that would move it forward.
3. Link each task to the goal with a **Hard Prerequisite** edge.
4. Keep going — break the big tasks into smaller ones, add some **Resources** (books, courses, tools), draw **Synergy** lines where two things genuinely boost each other.
5. Open the **Next** tab and see what the algorithm thinks you should do first.

But before you go deep, read the next section — most graph problems trace back to picking the wrong type for a node.

---

## Choosing the right node type

The five types aren't just visual labels. Each one answers a *different question* and behaves differently under the scoring algorithm. Picking the wrong type doesn't break anything, but it does muddy the rankings — a node typed as a Goal that should really be a Learn pollutes the cascade with a value rating that doesn't belong there; a Goal that should really be a Milestone competes for "next up" recommendations even though there's nothing to *do* on it directly.

Get the type right and the algorithm rewards you with rankings that match your gut.

### The five types at a glance

| Type | Core question it answers | "Done" means | Time-on-task |
|---|---|---|---|
| **Goal** | What domain, area, or capacity am I developing? | All Hard children Done (cascade) | None of its own — typically inherited |
| **Learn** | What body of knowledge do I want to integrate? | I understand this enough to apply or explain it | Reading, note-taking, integrating |
| **Action** | What discrete practice or experiment will I run? | The cycle is complete | Actually doing the thing |
| **Resource** | What external material am I consuming? | I've absorbed it | Reading, watching, studying |
| **Milestone** | What measurable achievement am I targeting? | I hit the target | None — work happens upstream |

### A decision tree

Walk these questions in order — the first "yes" wins:

1. **Is it external material I'll consume?** (book, course, set of notes, video) → **Resource**
2. **Is it a discrete practice or experiment with a definite end?** (a 6-week PIMLI cycle, a specific protocol, a one-shot integration task) → **Action**
3. **Is it a measurable, verifiable single-event achievement?** (a weight target, a time, a count) → **Milestone**
4. **Does it decompose into multiple things I'd track separately?** → **Goal**
5. **Otherwise — it's an atomic body of knowledge or skill.** → **Learn**

### The hard call: Goal vs Learn

This is where most misclassifications happen. Both Goals *and* Learns can have children — there are "Learn containers" (a Learn with sub-Learns underneath, set to inherited mode) just as there are Goals with children. So "does it decompose" isn't the cleanest test.

The cleaner distinction is **scope and abstraction**:

- A **Goal** is a *domain*, an *area*, or a *capacity*. You'd describe it as "what I'm trying to achieve here."
  *Examples: Sleep, Strength, Stoicism, Character, Body Composition.*
- A **Learn** is a *topic* or a *body of knowledge*. You'd describe it as "what I'm trying to understand."
  *Examples (atomic): Sleep Pressure, Stretching, Movement Patterns. Examples (container): Sleep Theory, Biology of Stress.*

Heuristic: **if you'd describe it as "an area of my life" or "a major capacity," it's a Goal. If you'd describe it as "a thing I want to understand," it's a Learn.**

A Learn-container is fine when the topic naturally splits into sub-topics worth tracking individually but the whole still reads as one body of knowledge — *Sleep Theory* containing *Sleep Pressure*, *Sleep Stages*, *Chronotypes*, etc. is a topic; the children are sub-topics. *Sleep* itself is a Goal because it spans theory + hygiene + experiments + targets — it's an area, not a topic.

### Goal vs Milestone

The other common confusion. The test is **measurability**:

- **Goal** = "develop strength" — no single moment marks it Done; you decide when the area is "good enough."
- **Milestone** = "squat 1.5× bodyweight" — you either did it or you didn't. Verifiable, single-event.

Milestones also behave differently in scoring: they're excluded from "what should I do next?" recommendations, because the work isn't *on* the milestone — it's on the upstream training that produces the capacity. The milestone is the checkpoint, not the practice.

If you find yourself saying "I want a target to motivate me," that's a Milestone. If you find yourself saying "I want to develop this area," that's a Goal.

### Common misclassifications to watch for

- **Goal-flavored Learn** — a topic dressed up as a Goal because it felt important. Sign: thin decomposition (1-2 children that are all atoms with no sub-area structure). Fix: demote to Learn (use inherited mode for Ratings if you still want it to act as a container header).
- **Goal-flavored Milestone** — a measurable achievement (squat target, time, count, draft completion) treated as a Goal. Fix: convert to Milestone. The graph stops treating it as work-to-be-done while keeping it visible as motivation.
- **Goal-flavored Action** — a thing you'll *do* for a fixed period, not an area. Sign: clear start/end, time-on-task is "the practice itself." Fix: convert to Action.
- **Action-flavored Learn** — a topic where you only have notes-integration work to do. Notes-integration is itself an Action (a one-shot task), so a *Notes Integration* Action under the Learn is often the right shape, not bundling the integration work into the Learn.

### Quick rule

When in doubt, ask: *what verb describes finishing this?*

- *understand* → Learn
- *do* → Action
- *consume* → Resource
- *develop* → Goal
- *hit* → Milestone

When the list surprises you — "wait, why is *that* #1?" — click its priority score to see the breakdown. Usually it's because that node sits upstream of a bunch of valuable stuff you hadn't considered connected.

---

## For developers

Curious about the internals? Read [`technical_overview.md`](technical_overview.md) for the architecture and data flow. UI conventions are in [`STYLE_GUIDE.md`](STYLE_GUIDE.md).
