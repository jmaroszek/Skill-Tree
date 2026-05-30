# Skill Tree

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

Skill Tree is a task-prioritization app that models your projects as a graph, scores them by return on investment, and tells you what to work on next.

**[Hero screenshot: the full graph sprawling across the Nodes tab.]**

## A Skill Tree for Your Life

In a video game, a skill tree gates the powerful abilities behind the basic ones. You master the fundamentals, and new branches open up based on what you've unlocked previously. Every "skill point" you spend is a small strategic bet about what will be most valuable — both now and later.

Skill Tree applies this idea to real life. Each project becomes a node in a tree. Finishing one is useful on its own. But more importantly, it can unlock other, more ambitious projects.

A game usually lays out up to three sensible paths. Real life lays out hundreds. Choosing what to do next, out of everything you could, is the hard part of productivity. That choice is *the only thing* Skill Tree focuses on.

## The Five Factors That Make a Project Worth Doing

So which branch do you unlock next? It comes down to five factors. Two are benefits. Two are costs. And one ties everything together.

Starting with the benefits, **value** is how much the results matter, and **interest** is how much you enjoy the work itself. These two often diverge. A project can be important but dull, or a joy but pointless. Score high on one, and a project is a candidate; score high on both, and it is the thing on your mind at 1 a.m. when you should be asleep.

If those were the only two factors to consider, time management would be easy. But if you have been an adult for more than 5 minutes, you know that it is not. Two more factors complicate the process. The first is **time**: a project might be valuable and interesting, yet still not be worth the hours that it demands. The second is **effort**: a project might be quick and valuable, yet so exhausting that it leaves you drained for everything else.

Those four factors describe a project on its own. The fifth, **relationships,** describes how it connects to every other node in the tree. Some projects gate others: you cannot start one until another is done. Others don't block anything, but make the projects they touch more valuable. This means a project is worth more than its own four factors suggest — it is also worth everything it unlocks and amplifies. 

Five factors, three roles. Value and interest are the benefits. Time and effort are the costs. Relationships decide the order.

Each role has its own failure mode. Weigh only the benefits, and you'll take on every appealing project, blind to what you are really sacrificing. Weigh only the costs, and you'll avoid the hard work most worth doing. Ignore the relationships, and you'll start each project from scratch, never building the foundation that would make the next project easier.

## Judgment Doesn't Scale

Weighing five factors for one project is easy enough. But projects do not live alone. Finishing one changes the value of others. The best move right now depends on a chain of unlocks two or three steps deep — and that chain shifts every time you complete something. If you try to weigh all of that, for every project at once, you will quickly leave the territory that human memory was built for.

My own tree has grown past 750 projects and a thousand relationships between them. I cannot hold that in my head, and before I had Skill Tree, it was painful to try. Left to my own intuition, I simply worked on whatever felt loudest that morning — the most recent, urgent, or alluring. I quickly realized that what I was doing wasn't working, which is why I went in search of tools that could help.

## The Failure of Other Tools

Look at the tools built to help us get things done today. Now think about the Five Factors that make a project worth doing: value, interest, effort, time, and relationships. Do *any* of them handle *all* factors adequately? I don't think so. All of them are built for execution, not decision making. They track, schedule, and remind you about work you have already chosen, but the decision itself is taken as a given.

At the simple end, to-do lists treat every item as equal. *Buy grapes* sits beside *write a novel* with nothing to tell them apart. A list has no model of value, costs, or relationships. Getting groceries is vital for my short-term needs, and meeting those needs is required for lofty goals like writing a novel. But when, exactly, am I supposed to work on the novel? A to-do list rewards crossing things off, which is why you can check five boxes in a day and still feel like you did nothing that mattered.

The bigger tools — like Jira, Notion, Asana, and Linear — track (simple) dependencies, assign owners, and schedule sprints. But they treat the strategic question as already settled. They ask *how* and *when*, never *what* and *why*. They are built to execute decisions, not to make them. Making decisions is the hard part, and that is the part that Skill Tree helps with.

## Enter Skill Tree

Skill Tree is here to augment your judgment, not replace it. You still decide what matters, whether you enjoy the work, and how it fits into the rest of your life. Skill Tree never makes those calls for you. What it changes is what happens next.

Once you've supplied that judgment, it stops living in your head. Your read on thousands of projects — with individual value, interest, time, effort, and relationships all considered — becomes a single ranked list, spanning every area of your life, all at once. And because every project lives in one tree, finishing one re-ranks everything it touches, automatically. 

This is freeing. You no longer start each day torn between this project and that one, unsure which matters more. You can simply trust the ranking — at least to the extent you trust yourself, since every input, and the way they combine, is yours to control. 

And trusting it never means taking it on faith. Ask why a project rose to the top, and Skill Tree shows you the reasons: the factors that scored it, and the projects downstream of it.

No other tool offers this kind of control or insight into the decision itself. No other tool has even tried. That is, not until Skill Tree.

## All Aboard the Magical Mystery Tour

You will meet Skill Tree through five documents. You have already read the first. The next four describe an important aspect of the app. 

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
