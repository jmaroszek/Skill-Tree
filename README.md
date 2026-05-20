# Skill Tree


![Python 3.10](https://img.shields.io/badge/Python-3.10-blue) ![Dash](https://img.shields.io/badge/Dash-Plotly-purple) ![SQLite](https://img.shields.io/badge/Database-SQLite-green)

# Meta 
- I have not talked about the goals sidebar yet. I am not sure where to introduce that. 
  - Also the annoucement feature where the app asks you if you want to mark a goal done after its last hard prereq is done

---

# Contents

# Why This Exists
## The Five Key Factors of Every Project
To me, two things make a project worth doing: **value**, meaning the results matter, and **interest**, meaning I will enjoy the work itself. Scoring high on one means a project is a candidate. Scoring high on both means a project is on my mind at 1 am when I should be sleeping.

[example]

If those were the only two factors, project management would be simple. But if you have been an adult for more than five minutes, you know it is not. There is also **time**: how long the project will take, and furthermore, whether each hour is valuable enough to earn its keep. Then there is **difficulty**: or how hard the project is, and whether taking it on will leave you too drained to handle everything else. Finally, there is the question of **relationships**: what this project depends on, and what it unlocks.

[example]

Five factors, three roles. Value and interest are the benefits. Time and difficulty are the costs. Relationships are the order. Each role has its own failure mode. Weigh only the benefits and you will chase shiny projects into ruin. Weigh only the costs and you will shy away from the arduous work most worth doing. Ignore relationships and you will climb every hill from the bottom, never acquiring the fundamental tools that would have made the next climb easier.

My advice: start at the fundamentals or you will have to start over. And there is nothing more fundamental than deciding what you should do and why. That is the one and only purpose of Skill Tree. 

## The Failure of To-Do Lists and Other Project Management Tools
Every project management tool I've used has assumed the hard part is execution. It is not. The hard part is deciding what to do. 

[example]

To-do lists treat every item as equal weight. *Buy milk* sits beside *write a novel* with no way to tell them apart. They have no model of value, no model of cost, and no model of how items relate. They reward crossing things off — which is why so many people end their day having checked five boxes and feeling like they did nothing that mattered.

[example]

Bigger tools — Notion, Asana, Jira, Linear — go further. They track dependencies, assign owners, schedule sprints. But they take the strategic question as already settled. They ask *how* and *when*; they do not ask *what* and *why*. They are built to execute decisions, not to make them.

[example]

That is the gap that Skill Tree solves. Here, judgment is a first class citzen. It scores projects against all five factors and surfaces the ones worth doing *now.* Once that question is answered (and explained!) your to-do list will be more than happy to track the rest.

# All Aboard the Magical Mystery Tour
Next, we are going to walk through the various features of the app, and learn how to use it well in the process.

**INSERT PICTURE**

# Node Editor
No matter where you are in the app, the node editor is never more than a click away. You can access it at any time by clicking this icon in the top left corner. This will open a side bar that allows you to edit the node's attributes, and its relationships to other nodes. Filling out these fields with care clarifies your thinking and allows the app to recommend work intelligently. 

## Name
A node's name is how you identify it, find it, and refer to it from other nodes. There are a few things to know about names. **Each node name must be unique.** If you type a name that already matches another node — exactly, or after stripping connector words like *the,* *of,* and *is* — the editor surfaces a **duplicate warning** so you can decide whether to rename or merge the two nodes. Still, you may refere to a node by multiple names in your head. As an example, you may have a resource node that you sometimes refer to as *4000 Weeks* and other times as *Four Thousand Weeks.* This is the perfect case for **aliases.** Each node can have as many aliases as you want, and the app will still work beautifully. As a final quality of life feature, renaming nodes is seamless: simply type over the old name, and everything will work like magic behind the scenes. All the arrows pointing at the node, the events referencing it, the overrides set on it, and the Goal orderings that mention it follow automatically. You don't have to update anything by hand.

**Add the name linter feature here**

**INSERT PICTURE OF NODE EDITOR SECTION**

## Type
There are five node types in Skill Tree.

| Type | What | Examples |
|---|---|---|
| Goal | A domain, area, or capacity you're developing | Flexibility, Machine Learning, Self Awareness |
| Learn | A topic you want to understand | Statistics, Negotiation, Confucian Ethics |
| Action | A clear, discrete action with a definite end | Find a Piano Teacher, Develop a Reading Habit, Setup Roth IRA |
| Resource | An external resource you'll consume (book, course, video). | Why We Sleep, The Art of Learning, Cosmos |
| Milestone | An objective, measurable achievement, used to mark progress towards goals. | 10 Strict Pull-ups, 10k Emergency Fund, Beat Elden Ring |

Each node type has a distinct shape and color on the canvas. The defaults are show below, but you can adjust the apperance in the Settings tab. 

**[SCREENSHOT: the five node types side by side on a neutral background, each labeled — yellow star Goal, blue circle Learn, orange triangle Action, purple pentagon Resource, orange diamond Milestone.]**

The types are mostly intuitive, but because each one behaves differently in the app, picking the right type is more important than it seems. The most crucial distinction is between *Learn*, *Goal*, and *Milestone* nodes. You will pick up the difference naturally through the following examples, but for full, explicit guidance, see  [`docs/modeling_guide.md`](docs/modeling_guide.md), which contains tips for structuring your graph.

## Description

The description area is a free-form text input field that allows you to type notes to your feature self. This section has no influence on the app, but I find it is helpful to write details when you create a project, such as what it is, why you added it, and what "done" means for you.

**SCREENSHOT**

## Context

Every project *must* belong to a context, and optionally, a subcontext. Contexts are necessary for three reasons. First, it enables powerful filter features that make it easier to examine subportions of your graph. Second, the Analyze tab shows you details about your projects by context, allowing you to see if you are over or under concentrated in any particular area. Finally, context influences project recommendations through two methods.

 The Creator and Explorer scoring profile boost synergistic edges across contexts, since that fits the nature of inspiration and curiosity. The algorithm will also intelligently adjust its recommendations based on the size of the context for any profile. Without this feature, a strongly decomposed context will always outweigh one with fewer but more important nodes. For technical details on how contexts influence scoring, you can see [`docs/technical_overview.md`](docs/technical_overview.md).

**INSERT THE SVG VISUALATION HERE, AND TRIM THE CONENT BELOW**

## Ratings
Three of the five factors discussed in the introduction have sliders, ranging from 1-10.

| Rating | Meaning |
|---|---|
| Value | How much this contributes to your broader goals. |
| Interest | How much you enjoy the work itself. |
| Difficulty | How hard the task is. |

All of these influence scoring, with value and interesting obviously boosting the appeal of a project, and difficulty reducing it. But just exactly how much each attribute influences scoring is different between the scoring profiles.

You can use your own personal ranking to adjust the sliders, but I have added a helpful reminder of the scale I use in app, which is available by clicking the info icon by the ratings header.

**SCREENSHOT: NODE RATING TABLE**

**SCREENSHOT: Ratings Sliders**

This popup is fully editable, so you can overwrite my system if you have a better one.

### Time
Each project will take some time, and the app lets you estimate that using exactly as much precision as you actually have.

| You provide | Time Estimation Method |
|---|---|
| One number (expected) | **As-is.** Provide one number only when you can call the duration closely. This may be true for small projects, but even then, I prefer to use one of the two methods below |
| Two numbers (optimistic + pessimistic) | **Geometric mean** of your endpoints. This method is superior to the arithmetic average you'd naturally reach for, because it accounts for biases in human time estimation. This method also allows the app to estimate the time uncertainty associated with a project (see [Time Simulation]()) **INSERT HEADER HERE WHEN SECTION DONE**
| Three numbers (optimistic, expected, pessimistic) | **Blended PERT**. A weighted average of your three numbers that leans on your typical case. PERT was developed by the US Navy to manage uncertainty across massive defense programs — projects too big and interdependent for anyone to pin down exact durations, but where any single task could usually be bracketed by best, typical, and worst case. My twist: when your range is wide, the formula tilts toward the geometric mean from the row above, so the long tail doesn't get drowned by an over-confident typical case. When the range is tight, the formula stays with the standard average, so confident estimates aren't dragged lower than they deserve to be. A tight range barely shifts the result; a wide range pulls it 
lower. |

**SCREENSHOT**

#### Habits
The methods described above are great for projects where only the cummulative time matters. For example, if you want to read a book, you can reasonably assume that it will take the same amount of time no matter how the work is split up. You could do three one-hour sessions, or one three-hour session. The net effect is the same. This is not true with everything that you might want to do though. Suppose your project is to build a running habit three times per week. It is less intuitive to think about the total time required up front. "Okay, so if I run a 10 minute mile, and I want to do that three times per week, and I think it will take me 8 weeks to develop the habit, then..." The same complexity arises for any type of habit. This is why there is a **Habit Mode.** Switch this toggle on and you will see a more natural estimation method for time estimation involving duration and frequency, rather than total time.

**SCREENSHOT**

## Relationships

There are three types of relationships in Skill Tree.

| Concept | Meaning | Example | Edge Name |
| --- | --- | --- | --- |
| Hard Prerequisite | You can not do the destination until the source is Done. | `Algebra → Calculus`. Calculus will not make sense if you don't understand algebra, therefore, you need to do algebra first. | Hard Need |
| Soft Prerequisite | Nice to have, but not strictly required. | `UX Design → Personal Website`. The website will be better if you've studied UX, but you can build one without it. | Soft Need |
| Synergy | Two tasks that mutually amplify each other. | `Rhetoric ↔ Writing`. Each one makes the other more useful. | Helps |

**Direction matters** for hard and soft prerequisites. `A → B` means A unlocks or supports B. — A is the source, and B is the destination. Synergistic edges are different. They have no direction. A helps B, and B helps A. We can represent this with a bi-directional arrow, $A\leftrightarrow B$, and that is exactly how the edges are protrayed in the app.

## State

Every node has one of four states:

| State | Meaning |
|---|---|
| Open | Eligible to work on. All its hard prerequisites are Done (or it has none). |
| Blocked | At least one hard prerequisite isn't Done yet. The app sets this automatically; you can't accidentally start a thing whose foundations aren't laid. |
| Done | Finished. Counts toward unblocking its dependents and contributes Synergy multipliers to its partners. |
| Dormant | Hidden, not scored, waiting on an Event to wake it up (more on this later). |

On the canvas, status shows as a colored overlay on top of the node's type color — red for Blocked, green for Done — so you can spot the state of any node at a glance. Open nodes keep their type's native color; Dormant nodes don't appear on the canvas at all, unless you explicitly toggle it on in the Filters sidebar. If you do that, then dormant nodes are transparent to let you know they are not active yet.

## Containers

A container, simply stated, groups related nodes together. But it is itself a node on the canvas — a container is just a regular node with a switch flipped.

Two switches, actually. The node editor has two Inherit toggles — one for ratings, and one for time. Turning either on makes the node a container along that dimension. You can turn either toggle on alone, or both together — each combination is useful in different situations:

| Inherit Time | Inherit Ratings | What you get | When to use |
|---|---|---|---|
| Off | Off | Standard node. Has its own ratings and time. | The default for *Learn*, *Resource*, and *Action* |
| On | Off | The node still has its own ratings, but its time is the sum of what points to it. | A *Mastery* Learn header you genuinely care about (V=7, I=7) sitting above a stack of books. |
| Off | On | I have never used this, and can't imagine why you would either. Let me know if you think of an application for this combination. | Never. |
| On | On | Pure container. No work of its own at all — its score is exactly the rolled-up score of its children. Mark it Done when all the children are done. | A *Transcendentalism* Learn that just groups *Walden* and *Emerson Essays*. |

**Screenshot of toggles**

### Defaults by Type

Goals and Milestones are time-containers by design: the inherit-time toggle is locked on, and the editor won't let you turn it off. The reasoning is that a Goal's duration is whatever the work underneath it adds up to. If this were not the case, a goal's time estimate might be different from the sum of its children, which does not make sense. Similarly, milestones are intended to be monumental events on the way to goals where duration estimation is difficult.

For example, if your goal is to develop upper body strength, and your milestone events are 10, 20, and 30 pushups, you have no reasonable way of estimating how long that will take, given the numerous factors involved. Is it 2 months? 5 months? 1 year? You will definitely know, however, when you hit the milestone, because it is a single, verifiable event. That is why time is fixed for both milestones and goals.

Inherit-Ratings, in contrast, is *never* on by default for any type. Most of the time you do want a node to carry its own value and interest scores even when it has children — those scores tell the algorithm that the node is worth doing for its own sake, not just as a structural wrapper. Turn Inherit-Ratings on only when the node really has no independent identity — a pure visual grouping to make the graph easier to examine. 

**Screenshot of container behavior on a small graph**

## External Links

A node can be connected to **external material** that lives outside the app — your notes, your files, or a relevant web page.

| Link type | What it does |
|---|---|
| Website | Any URL. When you revist this node later, you can open the website easily from the node editor, or a right-click context menu available wherever the node surfaces.  |
| Obsidian | A path relative to your configured Obsidian vault. Useful when a node already has a note started in Obsidian |
| Google Drive | Either a Drive URL or a local path to a Drive-synced file. Opens the file when clicked. |

The first entry, a website, is self-explanatory and universally applicable, but the next two, an obsidian vault and locally mounted Google Drive, or probably more niche to me, and I wouldn't expect many people to use those. If this ever becomes a "real" app, I will make those optional features.

# Scoring

## Intrinsic Value

**Value** and **interest**  combine to estimate a projects **intrinsic value**, or how appealing the project is in isolation. Intrinsic value is the foundation, but on its own it misses real world complications that must be considered, including time, difficulty, and the project's relationship to your other goals. The sections below explain how those factors are considered. 

## Total Value

A project's **total value** is its intrinsic value plus all future value it unlocks. Two mechanisms produce those additions — the **cascade** (Hard and Soft edges) and **synergies** (Helps edges).

### The cascade

Every project a node unlocks contributes something to its total value — but **the contribution fades with distance**. A direct prerequisite passes along most of its dependents' value. Two hops away, the value gets multiplied by the discount a second time, so it counts for less. Three hops, less still. The reasoning: distant downstream isn't as motivating as immediate downstream, and your ratings on far-away projects are more likely to drift before you ever get to them, so the algorithm is less confident about them.

Hard edges carry a stronger per-hop signal than Soft edges. Hard says "this *must* happen before that"; Soft says "this *helps* that happen." The cascade respects the distinction by discounting Soft hops more aggressively than Hard hops.

### Synergies

Synergy edges work differently from the cascade. They produce two distinct effects:

1. **Pair bonus.** Each synergy partner contributes a small portion of its total value to the node it's linked with, even before either project is started — node A picks up some of B's value, and B picks up some of A's. This makes it more likely that synergistic projects will be recommended together, allowing you to decide which one to tackle first. This bonus, however, is additive, and not always enough to outweigh other high-priority projects.
2. **Completion multiplier.** Once a synergy partner is marked Done, the surviving partner's intrinsic value gets a multiplicative boost (larger than the pair bonus above). The boost grows with the number of Done partners, but with diminishing returns — completing the second synergy partner gives a bigger relative jump than the tenth.

Together, these formalize the intuition that doing synergistic projects together is worth more than the sum of each project in isolation.

## Perceived Cost

Total value is the numerator of the priority score. It is produced by considering **value**, **interest**, and **relationships**. The denominator — or **perceived cost** — is built from the remaining two factors: **difficulty** and **time**. Difficulty is weighted somewhat more heavily than time, because a short daunting task feels worse than a long easy one (human psychology backs this up). Time also scales sub-linearly: a 100-hour project doesn't feel ten times as costly as a 10-hour one. Various parameters in the apps scoring algorithm control how aggressive these discounts are, and they vary between the scoring profiles. 

The base priority score is the ratio of the two:

```
priority score = total value / perceived cost
```

High value, low cost, top of the list. That's the whole ROI calculation, before any of the modifications below.

## Eligibility

A node must be elligible to recieve a priority score. There are several cases it might not be:

| Excluded | Why |
|---|---|
| Done | Already complete |
| Blocked Nodes | This project is blocked by a hard prerequisite, and can't be recommended until it is done.|
| Containers | A node is called a container if both its ratings and time mode are set to inherited. Container nodes are for structural organization; the real work comes from the children.|
| Goals | Only the children of goals are recommended. You will naturally complete a goal by completing its children. |
| Milestones | Same logic as goals. Children are recommended rather than the milestones themselves. | 

The table above implies that only open *Learn*, *Action* and *Resource* nodes compete for what you should do next. These nodes represent the work that supports everything else. 


## Score Adjustments

Three levers can shift a node's score after the base calculation. Each one answers a different question.

### Context Boosts

Contexts can shape the ranking in two ways:

| Lever | What it does | 
|---|---|
| Context Weight | A context weight multiplies every priority score in a given context. You can change context weights to match your life prorities. By default, all contexts are given equal weight, except for the consideration below. | 
| Density Normalization | Counteracts the bias where a heavily-decomposed context would crowd out a sparser one just because it has more nodes competing for the top-N slots. Dense contexts automatically get a penalty proportional to their size. This ensures that you won't overdevelop one area (e.g. learning a lot about ornithology but being unable to do your taxes) | 

**SCREENSHOT OF CONTEXT WEIGHTS IN SETTINGS**

### Goal Priority Boosts

Mark a Goal as your #1, #2, or #3 priority — via the **Priority Rank** field on the node editor, or the goals sidebar. This will increase the value of all the goal's hard dependents. Soft dependents and synergistic connections are unaffected by the goal priority boost. These edges are viewed as nice to have, but not strictly necessary for the achievement of the goal. They will, however, still contribute value via the cascade discussed in a previous section.  Your #1 priority gets the largest boost, #2 a smaller one, and #3 smaller still.

The default multipliers (under the Sage profile) are:

| Rank | Multiplier |
|---|---|
| #1 | 1.50× |
| #2 | ≈ 1.33× |
| #3 | ≈ 1.17× |

Ranks #2 and #3 share two-thirds and one-third of the #1 boost premium, so they always sit proportionally between 1× and the full #1 multiplier. If a node appears in more than one priority subtree, the highest-ranked one wins.

You are limited to three priorities at a time. Why? Because if everything is a priority, nothing is.

**Screenshot of priority boost**

### Manual Override

Some days the algorithm's ranking doesn't match your gut. The **Override** toggle in the node editor manually forces a node to the top of the Next tab's suggestions, regardless of what the math says. You have the option of applying the override to a single node, the node and all its hard dependents, or the node and all of its dependents (including soft).

Only one override can be active at a time; setting a new one prompts you to swap out the old one.

## The Full Formula

Pulling all of this together, here is the complete priority score:

```
priority score = (total value / perceived cost) × goal boost × context adjustment
```

That's what the app computes for every eligible node. It then normalizes the prority scores on a 0-100 scale, and sorts them, for your viewing pleasure, on the next tab. Due to intelligent algorithm design by yours truly, a graph of ~750 nodes and 1000 edges only takes 5ms to score. Therefore, there is no practical limit to how many projects and relationships you can add to Skill Tree. 

## The Explain Feature
 
If you ever want to see exactly how the score for a given node was put together, right-click it, then hit **Explain**. This will open a window that tells you how this node earned its value. 

**SCREENSHOT: EXPLAIN MODAL** 

### Top Contributors - A Visual Approach
Below the contributor table there's a counter and a **Focus** button. You can select up to 5 contributors, then click Focus, and the app will:

1. Picks the top 3 contributors to this node's score.
2. Computes the shortest path through Hard, Soft, and Helps edges from this node to each of them.
3. Switches you to the Nodes tab with those three paths highlighted in distinct rank colors. Shared segments (places where two or more paths overlap) adopt the higher-ranked color so the most important route stays visible.

**Screenshot**

In a large network, this is the most effective way to visually answer "why is this node worth doing?"  

## A Worked Example

Let's run a real project through the math end-to-end. *Compound Lifts* is a Learn node with V=9, I=8, D=5, and a blended time estimate of about 83 hours. It has one Hard edge pointing up to *Strength* (a Goal) and one Helps edge to *Functional Exercise* (another Goal). It has no incoming Hard edges, so it's eligible.

For this walkthrough, assume **Health is currently marked as Priority Goal #1**. *Compound Lifts* sits in Health's Hard-prereq subtree (Compound Lifts → Strength → Exercise → Health), so the goal boost will apply at the end.

**Intrinsic value** is just V + I = 17.

**Cascade**: *Strength* $\rightarrow$ *Exercise* $\rightarrow$ *Health*. Each hop applies a discount, so the contribution shrinks as we walk further away.

| Hop | Node | Intrinsic | Discount | Contribution |
|---|---|---|---|---|
| 1 (Hard) | Strength | 14 | × 0.6 | ~8.4 |
| 2 (Hard) | Exercise | 20 | × 0.6² | ~7.2 |
| 3 (Hard) | Health | 17 | × 0.6³ | ~3.7 |

Cascade total: about 19. 

**Synergy pair bonus** from *Functional Exercise* adds about 4 more (it's a Helps partner with a sizable total value of its own, so 10% of that comes through). No Done synergy partners, so the completion multiplier doesn't kick in. 

**Total value** lands around 40.

**Perceived cost** is a weighted blend of D=5 and 83 hours — difficulty counts somewhat more, and time scales sub-linearly — and works out to about 56. The exact formula lives in [`docs/technical_overview.md`](docs/technical_overview.md) for the curious.

The **base score** is total value ÷ perceived cost: 40 / 56 ≈ **0.71**. One thing worth flagging here: the absolute value of this number isn't meaningful. It isn't a percentage and it isn't bounded to a 0-to-1 range — only its size *relative to other nodes' base scores* matters. A node with a base score of 1.4 ranks above a node with a base score of 0.71; the gap is what tells you something, not the number on its own.

Two adjustments then transform the base score into the final priority score shown on the Next tab.

**Goal boost.** Health is Priority #1, so every node in its Hard-prereq subtree gets a 1.5× multiplier. *Compound Lifts* sits in that subtree, so:

```
0.71 × 1.5 ≈ 1.07
```

**Context adjustment.** Health / Exercise is a dense subcontext, so the density-normalization term shrinks each Health / Exercise node's score to make room for sparser contexts. After that haircut, the adjusted score lands around **0.44**.

**The final display step.** The number you see on the Next tab isn't 0.44 — the app then divides every eligible node's adjusted score by the *top-ranked* eligible node's adjusted score and multiplies by 100. The top of the list is always **100**; everything else is its share of that. So if the top-ranked node in your graph has an adjusted score around 1.0, *Compound Lifts* would show up as **44**. This last step is purely cosmetic — the math above is what determines ordering. The Explain modal shows both numbers side by side (labeled **Raw** and **Normalized**), so you can always reconcile the displayed integer with the underlying ratio.

A few things worth taking away from this example:

- **The cascade carries most of the weight.** Nineteen of the forty total value points came from downstream nodes. *Compound Lifts* ranks because of what it unlocks, not just its own ratings.
- **Context density matters a lot.** Even with strong raw numbers, a dense subcontext gets compressed to make room for sparser contexts. The intention behind this is to help you become a well-rounded person, and get to all the projects in all areas of your life (you are free to change this penalty in settings).
- **The Priority Goal boost compounds with the cascade.** A node already strong because it unlocks valuable downstream Goals gets lifted further when one of those Goals is marked a priority.

## Scoring Profiles

You don't always want the algorithm to weigh things the same way. Some days you want to grind toward a single Goal. Other days you want to chase whatever's interesting. Other days you want quick wins; other days you want to invest in foundations. **Scoring profiles** are pre-tuned configurations of the algorithm, each leaning into one of these moods. Six are built in, with descriptions available for view in the app:

| Profile | The lean | Use when |
|---|---|---|
| Sage | Balanced across all five factors. The sensible baseline. | No strong reason to pick something else. |
| Explorer | Interest weighted over Value. Synergies hit harder. Cross-context links are rewarded. Sparser corners of the graph get a fairer shot at surfacing. | You want to follow rabbit holes and let enjoyable, exploratory work surface. |
| Compounder | The cascade is amplified; time is less punishing. | You're willing to invest now for downstream payoff — sabbatical months, quiet quarters. |
| Pragmatist | Value beats Interest. Priority-Goal boost is dialed up; synergies and Soft edges are minimized. | You have a clear Goal and want the algorithm to drive everything toward it. |
| Creator | Synergies are massively amplified, especially across contexts. | You want to do original work. You're synthesizing across domains — writing, designing, building something new. |
| Glider | Time and effort weigh more heavily, so short and easy work rises. Cascade, synergies, and the Priority-Goal boost are all dialed back — non-priority work gets a fair chance to surface. | Light-effort days. You still want to move, but you want a break from the priority grind — recovering between intense pushes, or just doing a lap through small things. |

A **Custom** profile is also available if you want to tune every knob yourself.

I pick sage as my baseline and switch profiles as the mood strikes. 

The full numerical knob table for each profile lives in [`docs/technical_overview.md`](docs/technical_overview.md). 

# A Tour Through the Tabs

Across the top of the window there are six tabs: **Next**, **Nodes**, **Details**, **Events**, **Analyze**, and **Settings**. They each provide a unique view on the projects that you've added to the app. 

**[SCREENSHOT: close-up of the top tab bar with all six tabs visible.]**

---

# Next Tab

This is the tab the app opens on. If you only ever look at one screen, this is the one. It answers a single question — *what should I do next?* — with a ranked list of your most worthwhile eligible tasks, best at the top.

**[SCREENSHOT: the Next tab showing the ranked suggestion list.]**

Each row is one task. Reading it left to right:

| Element | What it tells you |
|---|---|
| Rank | Its place in the ranking — 1 is the top recommendation. |
| Name | The task, with its context · subcontext on the line beneath. |
| Colored bar | Two things at once. Its **color** is the node type — blue for Learn, orange for Action, purple for Resource, the same color language as the graph. Its **length** is the priority score: the #1 task is always a full bar, and every other bar is drawn as a proportion of it. The number at the bar's right end is that score. |
| Time | How long the project is expected to take. |
| Ratings glyph | Three little bars — your Value, Interest, and Effort ratings — drawn so you can eyeball how the task was rated without opening it. |
| Three dots | External links, in the order Obsidian · Drive · Website. A dot is filled in when that link exists on the node. |
| Description | Left click any row to see its description beside the table |

As a reminder, you'll only ever see *Learn*, *Action*, and *Resource* nodes as suggestions. Goals and Milestones are excluded from scoring, as you will naturally complete them as you complete their subtasks.

**Screenshot of the Next Tab with a row clicked**

## Context Menu
Right-click any row to open a context menu. The context menu is available anywhere a node surfaces, including the Nodes, Details, and Events tabs (coming up next).

**Screenshot of the context menu open**

| Option | What it does |
|---|---|
| Edit | Opens the node editor for this node. |
| Explain | Opens the score breakdown popup. |
| Details | Jumps to the Details tab with this node's details pre-filled. |
| Event | Adds the node to an event. |
| Obsidian | Opens the node's linked Obsidian note. Only appears when the node has an Obsidian link. |
| Drive | Opens the node's linked Google Drive file. Only appears when the node has a Drive link. |
| Done | Toggles the node's Done status — marks it complete, or re-opens it if it was already Done. |
| Delete | Deletes the node, after a confirmation prompt. |

## Other Small Features
**Fill this out later**
- Information in the bottom right of the app
- Filter warning in bottom left

# Nodes Tab

Click **Nodes** and you're looking at your entire task network as one graph — every node, every edge, all at once. A physics engine arranges it automatically, pulling connected nodes together so related work clusters visually.

**[SCREENSHOT: the full Nodes tab with the graph sprawling out, sidebars collapsed.]**

## The Visual Code

### Nodes

Every node's shape and color has meaning. 

| Shape | Color | Type | 
|---|---|---|
| Star | Yellow | Goal | 
| Circle | Blue | Learn | 
| Triangle | Orange | Action | 
| Pentagon | Purple | Resource | 
| Diamond | Teal | Milestone | 

The colors above only apply if the node is Open. If the node is Done or Blocked, it will be green or red respectively, regardless of the node type. But there is one important exception: goals are never red, even if they are technically blocked because they have incomplete tasks. Since goals are [containers](#containers) for tasks, they will almost always have incomplete hard tasks, meaning they would always be red, and difficult to distinguish from other blocked node types on the canvas.

P.S: Don't like these colors and shapes? Adjust them to your liking in Settings.

### Edges

[Relationships](#relationships) are encoded with arrows between nodes. 

|Arrow Style | Meaning |
|---|---|
| Solid Gray | Hard Need | 
| Dashed Gray | Soft Need | 
| Bidirectional Blue | Synergy |  

**Screenshot showing edge types**

## Interacting with the Graph
The canvas supports many intuitive interactions. These features are shared by all tabs with network visualizations, including the Details and Events tabs.

### Mouse & Keyboard Interactions

#### Working with Nodes

| Gesture | Effect |
|---|---|
| Hover over a node | Tooltip with key stats. Shows different things for different node types. |
| Left-click a node | Select a node, surrounding it with a white halo. If the node editor is open, it will be populated with the selected node's data |
| Ctrl + left-click multiple nodes | Multi-select. Allows bulk move, delete, and done toggling. |
| Drag a node | Reposition it on the canvas |
| Right-click a node | Open the [Context Menu](#context-menu). Especially useful for opening the node editor quickly with the correct data. |
| Delete / Backspace | Remove the selected node(s) with a confirmation prompt |

#### Navigating the Canvas

| Gesture | Effect |
|---|---|
| Left-click empty canvas | Deselect everything |
| Left-click + drag, starting on the canvas | Group select with a box, like your OS desktop |
| Right-click + drag (on empty canvas) | Pan the viewport |
| Scroll wheel | Zoom in and out |

### Graph Layout Controls
The gear icon in the bottom right corner of the canvas opens the **Graph Settings** panel. It controls how the physics engine arranges the graph. 

| Control | What it does |
|---|---|
| Edge Length | The length of the springs between connected nodes. |
| Gravity | How strongly nodes are pulled toward the center. |
| Repulsion | How hard nodes push away from each other. |
| Max Depth | Limit the view to a set number of hops out from the selected node. |
| Neighbors | With a node selected, show or hide the links between its neighbors — the edges that don't touch the selected node itself. Hiding them leaves a clean subtree radiating from the selection. |
| Smooth | Animate layout changes instead of snapping. Most elegant for smaller networks. |
| Freeze | Pause re-layout so hand-placed nodes stay put (see below).|
| Settle | Re-run the layout physics to untangle the graph. |

The **↺** button beside the panel title restores the canvas's saved defaults. You can save your preferred parameters in Settings (with unique profiles for each tab). 

**[SCREENSHOT: the Graph Settings panel.]**

### Lower Right Icons

#### Freeze
The freeze feature stops the graph from moving until you turn it off again. You will it is active because the canvas will be surrounded by a blue outline, and there will be a snowflake in the top right corner. This feature is extremely useful for updating edges with visual feedback. Without this feature, the graph re-arranges after each edit, making it difficult to track the subset of nodes you are working on. 

You are still able to manually drag the nodes while this feature is on. 

**Note to self: I wrote this section with the expectation that freeze will be moved out of the graph settings panel in the future. It is not currently implemented that way**

#### Fullscreen

The fullscreen button expands the graph to fill the whole window. This doesn't make a huge difference on the Nodes tab, which is almost fullscreen already, but it is helpful on the Details and Events tabs. To exit fullscreen mode, you can hit the same button again, or the escape key.

## Helpful Features for Large Networks
The Nodes tab works fine as-is for a small network — say 250 nodes or fewer, but past that, and it becomes a "dense hairball," which makes examining the nodes you want difficult. There are several features in the app that help you effectively work with large networks. We talked about one already: the max-depth parameter in the graph settings creates a "local graph" surrounding the active node. There are three others to be aware of: the locate feature, filters, and the details tab -- all coming up next. 

## Locate
The Search box at the top of the Node Editor finds any node by name (or alias). After you select it from the dropdown menu, the **crosshair** button beside the search by becomes active. Clicking this button temporarily enlarges and highlights the node on the canvas, making it easy to find. From there, you can do any number of things, such as open the local graph, or jump to the details tab, allowing you to examine a subnetwork easily. 

## Filters

The filters panel -- available in the top right corner of the app -- applies filters **globally**. That is to say all tabs respond to the filters. I am introducing this here because it is especially useful for the Next and Nodes tab. The former allows you to control which projects compete for the top N slots, and the latter allows you to filter the graph down to a meaningful subset. 

### Filter Controls

| Filter | Function |
|---|---|
| Node Type | Show only certain node types (e.g. learns + resources) |
| Context-Subcontext dropdowns | Restrict to one or more life areas |
| Min Value | Hide anything rated below a threshold. |
| Min Interest | Hide anything rated below a threshold. |
| Max Effort | Hide anything more difficult than a threshold. |
| Max Time | Hide anything longer than a time limit, using your preferred units |
| Communities | Filter to an algorithmically-detected group of nodes (see [communities](#communities)).|
| Done Toggle | Show or hide complete nodes. Hidden by default. |
| Dormant Toggle | Show or hide dormant nodes. Hidden by default. (Dormant nodes are discussed in events). |
| Memory | When on, your filter selections persist across sessions; when off, they reset on restart. |
| Clear filters | Reset all filters to their default state |
| Settle | Re-run the layout algorithm with selected filters. This happens automatically, but sometimes running it manually gives more aesthetic results. | 

### Filter Reminders
When any filter is active, the node-count readout in the lower left of the nodes tab adds a "· filtered" note, so you don't forget filters are on. The Next tab also has a reminder. There is a world where you have the memory toggle on, and hammer out one context continually, without realizing that is what you are doing. It happened to someone I know. 

Me. It was me.

**[SCREENSHOT: the filters panel open with several filters applied, and the filtered node count visible.]**

### Communities
The communities function in the fitlers sidebar deserves special mention. The communitities function algorithmically groups nodes together into a community, or a group of related nodes. There are three methods available. 

| Method | Description | 
|---|---|
| Islands | Finds groups of nodes with no relationships (edges) between them. Useful for discovering independent projects, or accidently disconnected ones. | 
| Clusters | Identifies densely connected groups. Useful for discovering cross-context groups that don't fit your mental taxonomy |  
| Orphans | Nodes with no edges of any type. Almost always a missing link, or a node that should be deleted. |

Pick a detection method, then a specific community from the list. Community names are automatically generated by the most common context in the group. This is slightly more descriptive than "communitity one, two, and three," but you will still need to click on the group to see the nodes in it. (Some are quite large). 

# Details Tab
The Next tab tells you *what* to work on. The Details tab is where you go afterward to actually understand the thing — what it depends on, how far along it is, how long it will take, and why the algorithm scored it the way it did.

## Populating the Details Tab with Data
The Details tab is empty by default, because it doesn't know what you want details *for*. There are three ways to tell it:

| Path | How it works |
|---|---|
| Search | Type a node name into the search bar at the top of the left panel. Best when you already have a specific project in mind. |
| Click a suggestion | When nothing is selected, the left panel shows a suggestion list so you always have a starting point. It has up to three sections: a **Manual Override** (if one is active), your top three **Priority Goals**, and five **Top Recommendations** — the [containers](#containers) with the highest total value. |
| Jump from another tab | On the Next or Nodes tab, open a node's [context menu](#context-menu) and click **Details**. The app switches here with that node already loaded. |

**Big Picture Screenshot of the details tab with a node selected**

Once a node is loaded, the tab is divided into four panels: the **Node Information** panel and **Mini-Canvas** on top, the **Subtasks** table and **Time Simulation** chart below. Let's go through them one by one.

## Node Information Panel
The left panel provides a summary for the selected node. Most of the information is self explanatory, but there are a few unique things to point out. 

First, there are **badges** describing a node under its name. There will always be at least two — its **status** and **type** — but there will be more if a node is related to a [Priority Goal](#priority-goals). The top-level goals themselves have badges reminding you of how you ranked them (Priority 1, 2, or 3), and a progress bar displaying how close you are to finishing it. Goal dependents also have badges. Examples include `Hard 1` and `Soft 2`. The number is which priority Goal it feeds, and Hard / Soft is whether it does so through a hard or soft chain. So `Soft 2` reads as "this node contributes, via a soft path, to your second priority Goal".

The rest of the panel is self explanatory. There is node stats, and three buttons at the bottom that reuse functions introduced elsewhere. 

| Button | What it does |
|---|---|
| Edit | Opens the node editor for this node. |
| Explain | Opens the [Explain](#the-explain-feature) window. |
| Locate | Briefly pulses the node on the mini-canvas, so you can find it in a busy graph. This is same function as the the cross-hair icon in the node editor. |

## Canvas Panel
The canvas on the right behaves exactly like the Nodes tab canvas, with one important difference: it is scoped to the selected node and everything related to it, rather than the whole graph. All of the gestures and graph settings covered in the [Nodes Tab](#nodes-tab) walkthrough work the same way here. There is one new button in the bottom right corner though: the magnifying glass. This is a fun and useful feature. It switches you to the Nodes Tab, and highlights your currently active network from the Details Tab, while dimming everything else. This shows you the broader context of the project. To exit this mode, click the "Clear Focus" button at the top of the canvas

Lastly, there is one quality of life feature built into the Details tab. Clicking on a node in the canvas will populate the Details panel with that nodes information. Because you may hop from node to node — clicking a subtask, following a dependency, etc. — the Details tab remembers where you've been. You can step forward and backward through your history using the two arrows by the search bar in the Node Information Panel, just like a web browser. 

**Screenshot of the feature active**

## Subtasks Panel
The Subtasks table, in the lower-left, lists every node in the dependency subtree. Some important columns include the relationship of this task to the selected node (displayed in the Node Information Panel), and its priority score. Notice that the most important subtask will always have a value of 100, and every other task's importance is assessed relative to that one. This score is **not** the same as what would appear on the Next tab; the Next tab is global, the details tab is local. Blocked and Done nodes do not have a priority, because they are not [elligible](#eligibility) for ranking.  

If a subtask has a *direct* edge to the selected node, an **×** appears at the end of its row. Clicking it opens a small **Remove Subtask** modal with two choices: **Remove Edge** severs just the link (the node stays in the graph), or **Delete Node** removes the node entirely. The **+** next to the "Subtasks" header opens a modal to add a new subtask, either creating a fresh node or linking an existing one.

If the subtree contains any Milestones, they get their own horizontal strip of tiles above the table — Milestones are checkpoints rather than work, so they're kept visually separate from the subtasks you actually grind through.

### Controlling how much you see
This is the panel's most useful trick. The row of toggles in the top-right, combined with the **Max Depth** slider in the graph-settings panel, lets you dial the view to the level of detail you want. As you would expect, every panel is responsive to these toggles: the network and simulation will update instantly when you change a setting. (And as a reminder, Filters apply to the Details tab too.)

| Control | What it does |
|---|---|
| Soft Needs | Include or exclude `Needs_Soft` subtasks — the helpful-but-not-blocking prerequisites. |
| Transitive | When off, shows only *direct* children. When on, shows the entire subtree. |
| Synergies | Include or exclude `Helps`-linked nodes. |
| Show Done | Whether completed subtasks appear. Off by default to keep the focus on open work. (This feature is linked to the global filter state)|
| Hide Blocked | Drop subtasks that are currently blocked by an incomplete prerequisite. |
| Max Depth | (In graph settings) Caps how many hops out from the selected node the subtree extends. |

For a sprawling Goal with hundreds of descendants, this is the difference between an unreadable wall of rows and a clean list of actionable items. 

## Time Simulation Panel
Because most nodes carry an optimistic, expected, and pessimistic time estimate, rather than a single number, the app can estimate how long it will take you to complete a project. The technique used is called **Monte Carlo Simulation**: every time you adjust a filter, the app runs *10,000* simulations of you completing every subtask, while acknowledging your uncertainty for how long each subtask might take. Worried this will take a long time? Don't be. Each simulation only takes a few milliseconds, so it is effectively instantaneous. If, however, you can't wait that long, you can reduce the number of trials per simulation in Settings.

This feature, I think, is very useful for large, vague, long-horizon Goals. It allows you to confidently say "there is a 10% chance I will have this done in 2 months, a 50% chance I will have it done in 3 months, and a 90% chance I will have it done in 4 months." This helps set expectations and helps you plan better. 

| Output | What it tells you |
|---|---|
| Histogram | The full distribution of how long the chain might take across all 10,000 runs. |
| P10 line | Optimistic case — only 10% of runs finish faster than this. |
| P50 line | The median — half of runs finish faster, half slower. |
| P90 line | Pessimistic case — 90% of runs finish faster than this; a sensible "worst realistic" figure. |

# Events
In Skill Tree, Events let you plan for the future without cluttering today. Some things genuinely matter, but you don't want to think about them yet. For example, suppose you want to learn to care for a dog, but you are not ready to adopt until your bonus comes in. You expect that bonus on a certain day, so you wrap all the pet-care tasks in an event set to wake up on that date. In the sandbox this is the **Adopt a Dog** event — a whole pet-care cluster (Dog Care, Canine Behavior, Dog Training, Find a Vet) stays tucked away until the day a dog could actually come home.

Sometimes, though, the right moment isn't a date but a milestone. Maybe you'd like to train for a half marathon, but only after you've run a 5k with a certain time. There's no calendar date for that — it just depends on finishing other work first. So instead of a date, you tie the event to a node: the sandbox's *Train for a Half Marathon* event wakes up the moment *5k in 25 min* is marked Done. And sometimes there's no condition at all, just a decision you haven't made yet. *Write a Book* is exactly that — an event with no date and no prerequisite, waiting quietly until you personally decide you're ready to commit. 

In every one of these cases, the tasks bundled inside the event sit out of sight until it triggers. The app has a name for tasks in that state.

## Dormant Nodes
So far we have discussed three states a node can be in: Open, Blocked, or Done, but there is another possibility: **Dormant.** A dormant node is not shown on the canvas or scored by the algorithm. It is effectively in hibernation until its Event is triggered. 

## Trigger Types
Every Event has a trigger — the rule that decides when its dormant nodes wake up. I already hinted at them, but here they are explicitly.

| Trigger | When it fires | Sandbox example |
|---|---|---|
| Date | Automatically, on or after a date you set. | *Adopt a Dog* — fires on 2027-06-01. |
| Node Completion | Automatically, when a specific node you choose is marked Done. | *Train for a Half Marathon* — fires when *5k in 25 min* is completed. |
| Manual | Whenever you click the **Trigger** button. No automatic condition. | *Write a Book* fires when you are ready |

Date and Node-Completion events still keep their **Trigger** button, so you can always wake an event early if life moves faster than you planned.

## Managing Events
The Events tab is where you create, edit, and trigger events. It has two halves: the **event editor** on the left, and an **event mini-graph** on the right. Events themselves are managed from the **Events sidebar**, which — like the Filters sidebar — slides out over the left edge of the app and is available from any tab.

**[SCREENSHOT: the Events tab with the Events sidebar open showing events listed.]**

## Events Sidebar
Open the sidebar from the calendar icon in the top-left of the app. It lists every event as a card showing the event's name, its description, and trigger information. You can do many quick actions from the side bar, such as search, sort, add, or trigger. Click any card to automatically switch to the event tab and load the relevant information into the editor. 

### The Event Editor
The left panel of the tab is a straightforward editor. At the top is the event **name**, with **Save** and **Delete** buttons. Below that: a **Description**, the **Trigger Type** selector (which reveals a date picker or a node dropdown depending on your choice), and the **Dormant Nodes** table.

The Dormant Nodes table lists every task waiting on this event, with its type, [activation delay](#dormant-nodes), and status. The **+** above the table opens the add-dormant-node modal; the pencil and **×** on each row edit or remove a node. A checkbox on each row feeds the trigger flow below.

The **Trigger** button fires the event manually. It opens a small confirmation modal where you choose **Trigger Checked** (wake only the checked rows) or **Trigger All** (wake everything) — handy when an event has accumulated nodes you're not ready to release all at once.

### The Event Canvas
The right side of the tab shows a mini-graph of the selected event's dormant nodes and how they connect to each other and to the live graph. It carries the same gear (graph settings) and fullscreen controls as the other canvases. It's a quick sanity check that the dormant cluster is wired up the way you intended before it goes live.

## Event Announcements
When an event triggers — whether on its own (a date arrives, a node is completed) or because you clicked **Trigger** — an **Announcements modal** pops up the next time you open the app, confirming what just woke up and which nodes were activated or scheduled. It's a gentle nudge rather than a silent change, so you always know when the graph has shifted under you.

# Analyze Tab

The Analyze tab gives you a bird's eye view of your entire network. Here, you can find helpful information such as your goal progress, time allocation, and much more. These charts are intended to be diagnostic, allowing you to catch mistakes early, and avoid spending your time unwisely. 

## The Overview strip

At the top, an Overview strip summarizes the current non-dormant graph: total Goals, Milestones, active nodes, Done nodes, and the percentage of active nodes that are Blocked. This gives you a quick overview of the size and status of your graph. 

**Screenshot**

## Goals

The Goals section puts two views side by side. The gear icon next to the section title opens a small display-limit control, letting you choose how many top-ranked Goals are rendered without leaving the Analyze tab.

**Screenshot**

On the left, **Completion** shows each Goal's hard-prerequisite progress as a stacked horizontal bar: Done work in green, remaining work as a faint gray. The hover text gives the hard-prerequisite count, remaining estimated time, blocked count, and priority rank when the Goal is promoted. 

The order is not alphabetical. Goals are ranked intelligently according to their total value and the remaining time required to finish it. Milestones are treated as transparent checkpoints for this ranking, so they pass value through without pretending that the checkpoint itself is the work.

On the right, **Shared Prerequisites** is a heatmap over those same ranked Goals. It counts the number of shared hard and soft prerequisites, so bright cells imply that two Goals are drawing from the same body of work. This suggests two goals share a set of foundational skills. 

## Time

The first Time chart is **Hours by Context**. Each context is one horizontal stacked bar, and each segment is a subcontext. Hover a segment to see its subcontext name, node count, and estimated time. This makes the context view more useful than a plain context-total chart: you can see not only that STEM or Health is large, but which internal area is creating the mass.

**Screenshot**

Below that are the calibration charts, populated from completed nodes with actual-time data. The first chart shows a scatter plot with a dashed $y = x$ reference line. Points above the line took longer than expected, and points below the line were completed faster than expected. The plot on the right rolls those same ratios up into per-context box plots (once a context has enough completed nodes) making chronic context bias clear. Perhaps, for example, you are good at estimating STEM work, but not humanities work. 

**Screenshot**

## Graph Structure

The sole visual in this section shows which nodes unlock the most downstream work. The gear icon next to the section title controls how many bottleneck nodes are shown.

The chart distinguishes direct unlocks from the full downstream cascade in hover text, and it colors Blocked bottlenecks red so you can separate "high leverage and available" from "high leverage but waiting on something else."

This is the leverage view. A large bottleneck may not be the highest ROI item by itself, but clearing it changes the frontier: whole chains become eligible, and the Next tab has better candidates to choose from.

## Contexts

The Contexts section shows a **Ratings** heatmap for active nodes grouped by context. This is a quick taste check. A context with high Value and low Interest may represent duty-heavy work. A context with high Interest and low Value may be a play/exploration area. A high Difficulty column is not a problem by itself, but it is a warning that the app may be accurately recommending less from that context unless the value, interest, or prerequisite cascade compensates.

# Settings Modal

# Next Steps
| If you want… | Go to |
|---|---|
| To understand the technical details | [`docs/technical_overview.md`](docs/technical_overview.md) — covers the app's architecture and math |
| The math at full precision | The [scoring](#the-scoring-algorithm) section above is the user-facing version; the canonical reference is the docstrings in [`scoring.py`](scoring.py). |
