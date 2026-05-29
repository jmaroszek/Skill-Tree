# Modeling Guide

This document covers how to make a graph that Skill Tree can rank effectively. This requires nailing **nodes, relationships** (recognizing that directed prerequisites cascade value downstream while bidirectional synergies are categorically different and do not cascade), and **contexts.** This document walks through helpful tips for each that I have learned through trial and error. As an added bonus, these tips will produce a more visually pleasing graph that resembles a true skill tree rather than a "dense hairball" that encumbers many large graphs. 

# Nodes

## Node Types
The five node types in Skill Tree are not just cosmetic labels. Each answers a distinct conceptual question and behaves differently under the scoring algorithm. 

### An Overview of the Node Types

| Type | Core Question | "Done" Means | Time-on-Task | Algorithmic Role |
|---|---|---|---|---|
| **Learn** | What do I want to understand? | I understand this enough to use it | Reading, writing, thinking, building, etc. | Scored for priority. Competes with Resource and Action Nodes directly. |
| **Action** | What do I want to do? | I've done the action | Actually doing the practice | Scored for priority. The primary driver of "doing." |
| **Resource** | What do I want to consume? | I have absorbed the material, and feel confident that I won't promptly forget it | Reading, watching, studying | Scored for priority. Competes with Learn and Action Nodes directly. |
| **Milestone** | What objective and measureable benchmark do I want to hit? | I hit the target | Time spent on child nodes | Excluded from scoring. Pass-through node for other nodes |
| **Goal** | What domain, area, or capacity am I developing? | All Hard children are Done | Time spent working on child nodes | Sink node; ranked in the sidebar and Analyze tab using the inverted cascade. |

### Key Distinctions

While the five node types are conceptually distinct, first-time modelers often struggle with boundary cases where nodes seem to overlap. Understanding the subtle boundaries between the node types ensures that your graph accurately reflects your intuition and interfaces correctly with the recommendation engine.

### Learn vs. Resource

If you are reading a book to learn something, you may wonder whether you should create a Learn or a Resource node. I recommend creating two nodes, actually: a Learn for the underlying intent, and a Resource for the material you think will help you fulfill your intent. You can model this as a hard or soft edge depending on whether you think the resource is essential for your understanding, or merely supportive.

```
Resource -> Learn
```

As an example, suppose you want to go through Gilbert Strang's Linear Algebra Course. You would only do that, of course, if you want to learn linear algebra, so it seems redundant to create two nodes, but by doing so, you remind yourself that there is more than one perspective on the topic, and enable yourself to add more Resources later (such as alternative introductory resources, or intermediate and advanced ones too.)

### Goal vs Learn 
Although both Goals and Learns can be containers, they serve different purposes, and operate under different rules in Skill Tree. 

The first major distinction is scope. A Goal represents a broad, often ambitious capacity that you want to develop. Examples include Strength, Eastern Philosophy, and Software Engineering. A Learn node, on the other hand, represents a specific topic within each discpline, such as Compound Lifts, Buddhism, or Agentic Coding. 

This difference in scope dictates how the two node types estimate value and cost. A Learn node's value is determined by its own interest and utility, plus whatever it unlocks next in your tree. Learning Chords, for instance, is useful in its own right (for music appreciation), but it also unlocks the ability to compose your own music one day. And the cost of learning Chords is simply the cost of the task itself, its direct time and effort. 

Goals have instrisic and total value too, computed in a simliar way as learn nodes, but they don't have their own cost. Costs are soley derived from child nodes. And crucially, only the remaining time of unfinished subtasks are considered; the goal's own effort is omitted from the cost calculation entirely, as effort is implicitly considered on a per-node basis when subtasks are recommended on the Next Tab.

Learn and Goal nodes also use different algorithms for ranking. Learn nodes compete directly alongside Action and Resource nodes for spots on the Next Tab's suggestion table. Goals never show up here (only their subtasks do). Instead, they are ranked in the goals sidebar using a different algorithm. If you want a goal's subtasks to surface higher on the Next Tab's suggestion table, you can assign it a priority boost. 

### Goal vs. Milestone
The difference between a Goal and a Milestone is objectivity. A Goal is subjective, while a milestone is objective. In short, *you* decide if you met your goal, but the world -- and all its brutally honest feedback mechanisms -- decide if you met your a Milestone. For a goal, you can mark it done whenever you want; maybe you finish all the work you had planned, or you just feel that what you've done is good enough already. Milestones, in constrast, are objective, verifiable, and binary. There is no fooling yourself. You just run the test that you defined beforehand, and you either pass or fail. 

A couple examples to show the difference. 

| Context | Goal (Capacity/Domain) | Milestone (Measurable Checkpoint) |
|---|---|---|
| **Body** | Cardiovascular Health | Run a sub-10 minute mile |
| **Money** | Financial Independence | Create a 10k emergency fund |
| **Creation** | Songwriting | Release a 10-track album on Spotify |
| **STEM** | Machine Learning | Place in the top 10% of a Kaggle competition |
| **Social** | Public Speaking | Deliver a 10-minute speech (without wetting yourself) |

**You should use both Goals and Milestones.** Goals help you cluster a bunch of related work together using all node types: Learn, Resource, Action -- and of course: Milestones. Milestones are essential because they provide feedback about whether you are developing the competence that you think you are through these other activities.

### Action vs. Milestone 
Both Actions and Milestones represent objective, externally verifiable events, but they serve different purposes. An Action represents the practice or execution itself. It has a clear duration and effort, and completing it means you finished some clearly-defined work. For example, "Complete a 6-Week Squat Program" is an Action. A Milestone, in contrast, is a checkpoint or threshold of achievement that has no duration of its own. For example, "Squat 1.5x Bodyweight" is a Milestone. 

The primary difference lies in the verb: you *do* an Action, but you *hit* a Milestone. 

Because you don't *do* a Milestone directly, the algorithm excludes Milestones from the Next tab suggestions list. If you incorrectly classify a Milestone as an Action, the app will try to recommend it to you as something to work on next, even though the actual work will be composed of Learn, Action, or Resource nodes, depending on the nature of the milestone. 

## Node Size

Choosing the right node type is half the battle; the other half is choosing the right node **size** (or level of abstraction). For Skill Tree to rank and sequence your work effectively, nodes should represent **high-level projects** -- typically spanning at least a couple weeks.

Skill Tree's job is to tell you which project deserves your attention this month — not to track every step within it.


### When Nodes Are Too Big
A single node that says *Master Cooking* or *Start a Blog* is too open-ended. Monolithic nodes have massive time estimates, or at least they should, which compresses their ROI score ($\text{Value} / \text{Cost}$), and pushes them to the bottom of your suggestion list. They also remove the whole value proposition of Skill Tree, which is to help you sequence work effectively.

By breaking down a large project into smaller components, you are using the most fundamental problem solving technique there is. The Divide and Conquer technique empowers both you and Skill Tree. It helps you because what was once an ambiguous mountain of uncertain tasks is now a set of concrete actionable steps. And by going through this process, you will naturally uncover the elements and the relationships that will be essential for your understanding later on. But you don't have to keep all that in your head. Let Skill Tree's unasailabe memory and smart algorithms figure out what all that implies for you. You have done the hard work: you've figured out what elements matter, how they relate to each other, and estimated their important characteristics (such as value, interest, effort, and time); now, in comparison, Skill Tree has the relatively easy job of simply choosing the order, based on what you told it. As long as you tell it what you truly believe, it will help you work on what you think truly matters. 

### When Nodes Are Too Small
A thousand nodes -- each representing a microstep in a project -- is not helpful either. "It is useful that a subject should be divided into parts," says Seneca, "but not chopped into bits. Just as it is hard to take in what is indefinitely large, it is hard to take in what is infinitely small." 

If you create too many nodes, you will spend more time doing meta-work than actually working. Remember, for every project you create, you need to estimate its attributes and relationships to other, similar projects -- and do so accurately -- otherwise Skill Tree has nothing to go on. I recommend keeping things at a high, strategic level in Skill Tree, and only breaking down a project into granular, concrete steps once you have decided what to work on (and marked the project as "now" in Skill Tree).

There is also a pragmatic and philosophically less elegant reason you should not break down a project excessively. Recall that a project's value cascades through the edges (relationships) in Skill Tree. Each edge a project has to traverse dilutes its value more. This is by design, and it works beautifully if you treat each node as a high level chunk of work, but it backfires if you break down the project beyond all reasonable measure. 

In essence, if managing a task in Skill Tree (estimating time, setting ratings, linking edges) takes a noticeable fraction of the time it takes to actually *do* the task, the node is too small. Keep Skill Tree focused on strategic sequencing of larger blocks of effort, and let your daily checklist handle the micro-tasks once the project actually starts.

### When Nodes Are Just Right
The sweet spot lies in applying a **Divide and Conquer** strategy to create a clean hierarchical tree of relatively independent elements.

* **Workload-Based Leaf Nodes**: Each leaf node should represent a meaningful but manageable chunk of effort. For me, this is several weeks of work, but you may choose a different unit if you want. 
* **The Rule of Three**: For complex or unfamiliar domains, aim for three levels of abstraction and three children per parent. This limits your tree to 27 leaves, meaning you never focus on more than 4% of the problem at once. This constraint aids focus, forces priority, and prevents scope creep.
* **Target Independence**: Divide your goals into sub-problems that are as independent as possible. Independence allows you to parallelize work or switch tasks flexibly without breaking other dependencies.
* **Divide to Learn**: If you know nothing about a domain, guess. Deconstruct the problem as best as your current intuition allows; methodically working through even a flawed division will teach you enough to restructure the tree intelligently later.

### Leveraging Containers to Manage Abstraction
When you have a group of related topics or materials that you want to track individually, do not chain them together with endless Soft or Hard prerequisite links. Doing so creates visual clutter and dilutes priority scores. Instead, use a **container** to group them under a single parent. As a reminder, a container is a node who inherits their ratings or time estimate from its children (the nodes that point to it.)

Using containers lets you maintain a clean hierarchy while preserving detail. In Skill Tree, containers operate along two dimensions:

* **Pure Containers (Inherit Time = On, Inherit Ratings = On)**: These nodes have no manual ratings or time of their own. They act as pure structural wrappers, and their priority score is derived entirely from their children. Use these to bundle small, related tasks together without creating peer-to-peer links.
* **Value Containers (Inherit Time = On, Inherit Ratings = Off)**: The parent carries its own manual Value and Interest ratings (reflecting why the overall domain matters to you), but inherits its perceived cost and time from its children. This is the ideal setup for a parent **Learn** node (e.g., *Machine Learning Basics*) that sits above a collection of specific courses and actions.
* **Locked Containers**: Goals and Milestones are time-containers by design. Their duration is always the sum of their children's remaining time, preventing time estimation mismatches.

# Relationships
If nodes are the stages of your journey, relationships (edges) are the pathways connecting them. They dictate how value propagates, how status changes, and ultimately, what the Next tab recommends. Crucially, edges are divided into two categories: **directed prerequisites** (Hard and Soft Needs) and **bidirectional synergies** (Helps relationships). 

## Edge Types
Skill Tree uses three distinct edge types to model your plan:

| Edge Type | Visual Style | Blocking? | Core Question | Math Effect |
|---|---|---|---|---|
| **Hard Need** | Solid Gray | **Yes** | Can I start the target without completing the source? | Blocks target eligibility. Strongest cascade (60% by default). |
| **Soft Need** | Dashed Gray | **No** | Will doing the source first make the target easier or better? | Does not block. Moderate value cascade (40% by default). |
| **Helps (Synergy)** | Bidirectional Blue | **No** | Do these two tasks mutually reinforce and amplify each other? | Does not block. Does not cascade. Uses a different mechanism of supplying value. |

### Edge Direction for Hard and Soft Needs
For directed prerequisites, edge direction is the single most important thing to get right. Arrows always flow from source to target, from step one to step two. The relationship defined here ($A \rightarrow B$) can be read as "A supports, leads to, or unlocks B." If you get this backwards, the status cascade will lock you out of your more fundamental tasks. 

### The Two Roles of Hard Edges
Hard edges act as strict blockers, serving two distinct purposes. The first is logical necessity, representing a true structural dependency where the target is physically impossible to start without completing the source (such as *Boil Water* ➔ *Cook Pasta*). The second is personal preference. While I could've technically started *Beyond Good and Evil* before reading *How to Take Smart Notes*, I just wanted to read the note-taking book first, so I could retain what I read. Either way, the purpose of a hard edge is the same: to say that $A$ *must* come before $B$.

### When to Use Soft Edges
Soft edges represent helpful prep work rather than strict logical barriers. You should use a soft edge when completing the source node will make the target easier, faster, or higher quality -- but you still want the flexibility to start the target early if inspiration strikes. 

For example, purchasing a sturdy tripod will make capturing sharp landscape photographs at sunset much easier and prevent blurry images, but a soft edge ensures you aren't blocked from shooting handheld if you spot a beautiful scene on your walk.

### Synergies: Bidirectional Reinforcement
Do not treat synergy edges as a weaker version of a Soft prerequisite, as they operate on an entirely different axis. Prerequisites are focused on chronological order, establishing that one node should precede another.Synergies, in contrast are about **mutual reinforcement.** This is why synergies are the only bidirectional edges in Skill Tree.

To decide whether a pair genuinely qualifies, ask whether the combination is *more than the sum of its parts* -- if doing both lands harder than doing each alone, it's a synergy. Next, sanity-check the symmetry: you should be able to state the reinforcement in both directions and have each feel true. Recall that a synergy edge says that $X \leftrightarrow Y$. If only one direction holds (X helps Y, but Y doesn't help X), what you actually have is a Soft prerequisite. 

The strongest synergies tend to bridge contexts. A good example is Gardening ↔ Biology: each one materially changes how you experience the other -- biology explains why a plant wilts or thrives in a given soil, and gardening gives biology a slow, living laboratory in your backyard. Neither node is a prerequisite for the other, but doing both turns each into something richer than it would be on its own. 

A few patterns that look like synergy but aren't:

- **Shared topic** -- You don't need a synergy edge just because both nodes cover similar content. Group them under a common parent instead.
- **Both are just interesting** -- Synergies are about the relationships between topics themselves, not your interest in them. The app already considers your personal interest through a different mechanism, so you don't need to encode that here. 
- **I want to work on these around the same time** -- that's a sequencing preference; use hard or soft edges instead.

Also resist piling many synergies onto a single "hub" node; the boost has diminishing returns, so two or three genuine partners beat a fan of weak ones.

# Contexts & Subcontexts

Contexts and subcontexts are the tags you use to divide your life into distinct domains (e.g. `Career`, `Health`, `Relationships`). Definining contexts and subcontexts is helpful for a few reasons. 

First, it allows you to fine tune the recommendation algorithm using user-defined context weights. You can mark a context as more or less important, changing how often Skill Tree recommends content from that context. There is also a clever behind-the-scenes trick that ensures that Skill Tree won't automatically recommend more from a context just because you've defined more projects for it. It is natually easier to Divide and Conquer a context you know more about, but that does not mean the context is inheritly more important than others -- it just means you know more about it. Skill Tree takes this into account and is sure to recommend content from sparse contexts on occasion so that you can develop yourself across all domains. 

Additonally, contexts allow you to filter your graph, so you can focus on exactly what you want to see when you want to see it. You can filter recommendations and most visuals in Skill Tree to only include information from the contexts that you want to examine. Also, there are many visualizations on the Analyze tab that tell you how your effort is distributed across contents. 

## Picking Your Contexts
Treat top-level contexts as the major pillars of your life and aim for somewhere between four and eight of them. Too few and unrelated work gets lumped together; too many and the partitions stop meaning anything. A useful test: if you imagined ignoring one of your contexts for six months, would something important in your life clearly suffer? If not, it probably belongs as a subcontext under another pillar instead.

I recommend making your life contexts as independent as possible. Each new project should have a clear home. If you have two over-lapping contexts, then you will put some related ideas in context A, and the others in B. Go for pragmatic classification here, not philosophical elegance. 

There is no penalty for defining contexts poorly on your first attempt, because there is a Context Migration feature that allows you to re-assign each node a new context easily. This feature shows up any time you change the context list in Settings. It will ask you how you want to assign contexts for the now-invalid nodes. 

## Using Subcontexts
Subcontexts let you organize sub-themes inside a pillar without splitting it into separate top-level domains. For example, `Health/Nutrition` and `Health/Exercise` both live under Health, so they stay grouped as one life area while still being distinguishable from each other. Reach for a subcontext whenever you notice a context starting to contain two clearly different kinds of work. 

## Cross-Context Work
Once your contexts are set up, actively look for projects that sit at the intersection of two of them. A software tool that solves a personal health problem, or a writing project that draws on a hobby, tends to be more valuable than work that lives entirely inside one pillar. This is often the best place to look for synergistic edges. 

# Common Problems and Fixes 
After using Skill Tree for awhile, I noticed things that make my modeling less effective. This has nothing to do with the features of Skill Tree, and everything to do with how I choose to use them. 

| Problem | What it Looks Like | Why it's Bad | How to Fix |
|---|---|---|---|
| **Unloved Orphans** | A node with no incoming or outgoing edges. | Because it does not receive cascade value, it will never get recommendeded, and it is easily forgotten. | Find a relationship for your orphan -- or kill it. (Use the **Orphans** community filter to find these). |
| **Spiderwebs** | A dense mesh of criss-crossing edges within a single context | Visual clutter; less meaningful priority scores | Build clean, hierarchical relationships using containers and thoughtful edges. Topical relatedness does not deserve an edge. Use contexts and subcontexts for high level grouping. |
| **Indefinite Actions** | An Action node representing a permanent habit (e.g., Exercise, Meditate, Read). | Action nodes are meant to be completed. A habit, one that is truly never done, will either sit on your list indefinitely, or may have its Done state reversed (if you ever stop doing the habit) | Model starting and stopping habits as fixed-period experiments (e.g., "6-Week Running Protocol", or "Fast 3 hours before bed"). After completing the experiment, mark it as Done, and reflect on whether you want to keep the habit. |

# Navigation
## Tutorial
Each cell is clickable.
```mermaid
flowchart LR
    R(["README"]) --> F(["Features"]) --> S(["Scoring"]) --> T(["Time"]) --> M(["Modeling"])
    classDef current fill:#ffd966,stroke:#b58900,stroke-width:2px,color:#000;
    classDef other fill:#2b2b2b,stroke:#555,color:#bbb;
    class M current
    class R,F,S,T other
    click R "../README.md"
    click F "features.md"
    click S "scoring.md"
    click T "time.md"
```

## Other Resources

| Resource | What's there |
|---|---|
| [graph_manager.py](../graph_manager.py) | Edge creation, cycle detection, and the status cascade that the rules in this guide rely on. |
| [app_architecture.md](app_architecture.md) | How the graph you build flows through the app, from mutation to re-rank. |








