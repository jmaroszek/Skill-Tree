# Skill Tree

![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

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

---
# Why This Exists
## The Five Key Factors of Every Project
To me, two things make a project worth doing: **value**, meaning the results matter, and **interest**, meaning I will enjoy the work itself. Scoring high on one means a project is a candidate. Scoring high on both means a project is on my mind at 1 am when I should be sleeping.

[example]

If those were the only two factors, project management would be simple. But if you have been an adult for more than five minutes, you know it is not. There is also **time**: how long the project will take, and furthermore, whether each hour is valuable enough to earn its keep. Then there is **effort**: or how hard the project is, and whether taking it on will leave you too drained to handle everything else. Finally, there is the question of **relationships**: what this project depends on, and what it unlocks.

[example]

Five factors, three roles. Value and interest are the benefits. Time and effort are the costs. Relationships are the order. Each role has its own failure mode. Weigh only the benefits and you will chase shiny projects into ruin. Weigh only the costs and you will shy away from the arduous work most worth doing. Ignore relationships and you will climb every hill from the bottom, never acquiring the fundamental tools that would have made the next climb easier.

My advice: start at the fundamentals or you will have to start over. And there is nothing more fundamental than deciding what you should do and why. That is the one and only purpose of Skill Tree. 

## The Failure of Other Project Management Tools
Every project management tool I've used has assumed the hard part is execution. It is not. The hard part is deciding what to do. 

[example]

To-do lists treat every item as equal weight. *Buy milk* sits beside *write a novel* with no way to tell them apart. They have no model of value, no model of cost, and no model of how items relate. They reward crossing things off — which is why so many people end their day having checked five boxes and feeling like they did nothing that mattered.

[example]

Bigger tools — Notion, Asana, Jira, Linear — go further. They track dependencies, assign owners, schedule sprints. But they take the strategic question as already settled. They ask *how* and *when*; they do not ask *what* and *why*. They are built to execute decisions, not to make them.

[example]

That is the gap that Skill Tree solves. Here, judgment is a first class citzen. It scores projects against all five factors and surfaces the ones worth doing *now.* Once that question is answered (and explained!) your to-do list will be more than happy to track the rest.

# Core Features
## Node Types
| Type | What | Examples |
|---|---|---|
| Goal | A domain, area, or capacity you're developing | Flexibility, Machine Learning, Self Awareness |
| Learn | A topic you want to understand | Statistics, Negotiation, Confucian Ethics |
| Action | A clear, discrete action with a definite end | Find a Piano Teacher, Develop a Reading Habit, Setup Roth IRA |
| Resource | An external resource you'll consume (book, course, video). | Why We Sleep, The Art of Learning, Cosmos |
| Milestone | An objective, measurable achievement, used to mark progress towards goals. | 10 Strict Pull-ups, 10k Emergency Fund, 10 minute mile |



# Next Steps
| If you want… | Go to |
|---|---|
| To understand the app's architecture | [`docs/app_architecture.md`](docs/app_architecture.md) — modules, tab callbacks, Cytoscape pipeline, persistence and caching |
| To understand the math behind the recommendations | [`docs/scoring.md`](docs/scoring.md) — scoring, profiles, goal ranking, explainability, status cascade |
| To understand how time estimates are computed | [`docs/time.md`](docs/time.md) — the PERT blend and the Monte Carlo simulator |
| The math at full precision | The [scoring](#the-scoring-algorithm) section above is the user-facing version; the canonical reference is the docstrings in [`scoring.py`](scoring.py). |

---

<table width="100%"><tr>
<td align="right"><a href="docs/features.md">Next: Features →</a></td>
</tr></table>
