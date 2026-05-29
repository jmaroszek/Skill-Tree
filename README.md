# Skill Tree

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

> A task-prioritization app that models your projects as a graph, scores them by return on investment, and tells you what to work on next — and why.

**[Hero screenshot: the full graph sprawling across the Nodes tab.]**

# A Skill Tree for Your Life

In a video game, a skill tree gates the powerful abilities behind the basic ones. You master the fundamentals, and new branches open up. Every "skill point" you spend is a small strategic bet about what is most valuable — both now and later.

Skill Tree applies this idea to real life. Each project you might take on becomes a node. Finishing one is useful on its own, but even more importantly, it can unlock others. The app's job is to tell you where to spend your next hour so it does the most good.

A game usually lays out up to three sensible paths. Real life lays out hundreds, with no glowing marker over the "right" one. Choosing what to do next, out of everything you could, is the hard part of productivity. That choice is *the only thing* Skill Tree focuses on. 

# The Five Factors That Make a Project Worth Doing

So which branch do you unlock next? It comes down to five factors. Two are benefits. Two are costs. And one ties everything together.

Starting with the benefits, **value** is how much the results matter, and **interest** is how much you enjoy the work itself. These two often diverge: a project can be important but dull, or a joy but pointless. Score high on one, and a project is a candidate; score high on both, and it is the thing on your mind at 1 a.m. when you should be asleep.

If those were the only factors to consider, time management would be easy, but if you have been an adult for more than 5 minutes, you know that it is not. Two more things complicate the process. The first is **time**: a project might be valuable and interesting, yet still not worth the hours it demands. The second is **effort**: a project might be valuable and quick, yet so draining it leaves you behind on everything else.

The fifth and final factor is **relationships**: what a project depends on, and what it unlocks. Clear a prerequisite, and everything behind it opens up — like the branches of a tree. 

Five factors, three roles. Value and interest are the benefits. Time and effort are the costs. Relationships decide the order. 

Each role has its own failure mode: weigh only the benefits, and you'll chase shiny projects into ruin. Weigh only the costs, and you'll avoid the hard work most worth doing. Ignore the relationships, and you'll climb every hill from the bottom, never picking up the tools that would make the next climb easier.

# Judgment Doesn't Scale

Weighing five factors for one project is easy enough. But projects do not live alone. Finishing one changes the value of others. The best move depends on a chain of unlocks two or three steps deep, and that chain shifts every time you complete something. If you try to weigh all of that, for every project at once, you will quickly leave the territory that human working memory was built for.

My own tree has grown past 750 projects and a thousand relationships between them. I cannot hold that in my head, and before I had Skill Tree, it was painful to try. Left to my own intuition, I simply worked on whatever felt loudest that morning — the recent, the urgent, the alluring. But I soon realized that wasn't working, which is why I looked for a tool that could help share the load.

# The Failure of Other Tools

While holding the five factors of every project in mind, look at the tools built to help us get things done. Do *any* of them handle all the factors adequately? I don't think so. All of them are built for execution: they track, schedule, and remind you about work you have already chosen. The decision is taken as a given, but weighing the five factors is left entirely to you. But that, I think, is the hard part.

At the simple end, to-do lists treat every item as equal. *Buy milk* sits beside *write a novel* with nothing to tell them apart. A list has no model of value, no model of cost, and no model of how items relate. It rewards crossing things off, which is why you can check five boxes in a day and still feel like you did nothing that mattered.  

The bigger tools — Notion, Asana, Jira, and Linear — track (simple) dependencies, assign owners, and schedule sprints. But they treat the strategic question as already settled. They ask *how* and *when*, never *what* and *why*. They are built to execute decisions, not to make them. 

# Enter Skill Tree
Skill Tree is here to augment your judgment, not replace it. The process is simple: you tell Skill Tree what matters, how enjoyable it is, and how it fits into the rest of your life. That part doesn't change; what does change, however, is the speed and ease with which you can choose projects. Now, your collective judgment on thousands of projects — with value, interest, time, effort, and relationships all considered — is available, sorted by priority, across every area of your life, right now.

This is freeing. You no longer start your day torn between this project and that one, unsure which matters more. You can simply trust the ranking — at least, to the extent you trust yourself, because you have full control over every input, and how they combine to form a priority score. But Skill Tree is far from a black box. It will explain every recommendation, upon request, so you know why a task rose to the top. Indeed, after you enter a project, the deliberation is done. The only thing that remains to be done is the next most essential thing.

No other tool provides this level of control or insight into the decision making process itself. No other tool has even tried. That is, not until Skill Tree.

# All Aboard the Magical Mystery Tour

You will meet Skill Tree through five documents. You have already read the first. The next four go deep on one aspect of the app. 

- **[Features](docs/features.md)** walks through every tab and panel: the graph canvas, the recommendation list, goal tracking, events for planning the future, reflection for learning from the past, and an Analyze tab full of diagnostics.
- **[Scoring](docs/scoring.md)** opens up the ranking math. How value cascades through the tree, how synergies reward cross-disciplinary work, and how scoring profiles re-weight everything to match your mood, from open curiosity to focused execution.
- **[Time](docs/time.md)** explains how the app turns a rough guess into an honest estimate, and how it simulates when a sprawling goal will actually be finished.
- **[Modeling](docs/modeling.md)** is the field guide to building a tree worth ranking. How big a node should be, when an edge earns its place, and how to keep the whole thing from collapsing into a hairball.

```mermaid
flowchart LR
    R(["README"]) --> F(["Features"]) --> S(["Scoring"]) --> T(["Time"]) --> M(["Modeling"])
    classDef current fill:#ffd966,stroke:#b58900,stroke-width:2px,color:#000;
    classDef other fill:#2b2b2b,stroke:#555,color:#bbb;
    class R current
    class F,S,T,M other
    click F "docs/features.md"
    click S "docs/scoring.md"
    click T "docs/time.md"
    click M "docs/modeling.md"
```

Follow the path at the footer of each page, and by the end, you will know how to use Skill Tree, and why it works the way it does.

P.S. notice that each cell in the diagram above is clickable!
