# Modeling Guide

This doc is for someone who has decided to build out a Skill Tree graph in earnest and wants to model their world correctly the first time. It covers the two decisions that drive everything else: **which type of node to use** and **which edges to draw between them**. Get those right and the algorithm rewards you with rankings that match your gut. Get them wrong and the rankings drift in ways that are hard to diagnose later.

If you're new to the app, read the [README](../README.md) first — it covers the five node types, three edge types, and the basic mental model. This doc builds on that foundation.

For a hands-on walkthrough of adding a small new domain step by step, see [tutorial.md](tutorial.md).

---

## Choosing the right node type

The five types aren't just visual labels. Each one answers a *different question* and behaves differently under the scoring algorithm. Picking the wrong type doesn't break anything, but it does muddy the rankings — a node typed as a Goal that should really be a Learn pollutes the cascade with a value rating that doesn't belong there; a Goal that should really be a Milestone competes for "next up" recommendations even though there's nothing to *do* on it directly.

Get the type right and the algorithm rewards you with rankings that match your gut.

### The five types at a glance

| Type | Core question it answers | "Done" means | Time-on-task |
|---|---|---|---|
| Goal | What domain, area, or capacity am I developing? | All Hard children Done (cascade) | None of its own — typically inherited |
| Learn | What body of knowledge do I want to integrate? | I understand this enough to apply or explain it | Reading, note-taking, integrating |
| Action | What discrete practice or experiment will I run? | The cycle is complete | Actually doing the thing |
| Resource | What external material am I consuming? | I've absorbed it | Reading, watching, studying |
| Milestone | What measurable achievement am I targeting? | I hit the target | None — work happens upstream |

### A decision tree

Walk these questions in order — the first "yes" wins:

1. Is it external material I'll consume? (book, course, set of notes, video) → **Resource**
2. Is it a discrete practice or experiment with a definite end? (a 6-week PIMLI cycle, a specific protocol, a one-shot integration task) → **Action**
3. Is it a measurable, verifiable single-event achievement? (a weight target, a time, a count) → **Milestone**
4. Does it decompose into multiple things I'd track separately? → **Goal**
5. Otherwise — it's an atomic body of knowledge or skill. → **Learn**

### The hard call: Goal vs Learn

This is where most misclassifications happen. Both Goals *and* Learns can have children — there are "Learn containers" (a Learn with sub-Learns underneath, set to inherited mode) just as there are Goals with children. So "does it decompose" isn't the cleanest test.

The cleaner distinction is **scope and abstraction**:

| Type | What it is | Sandbox examples |
|---|---|---|
| Goal | A domain, an area, or a capacity. "What I'm trying to achieve here." | Strength, Stoicism, Body Composition, Character, Financial Independence, Eastern Philosophy. |
| Learn | A topic or a body of knowledge. "What I'm trying to understand." | Atomic: Compound Lifts, Stretching, Sleep Pressure, Hip Biomechanics. Container: Sleep Theory (holds Sleep Pressure, Sleep Stages, Chronotypes); Biology of Stress. |

Heuristic: if you'd describe it as "an area of my life" or "a major capacity," it's a Goal. If you'd describe it as "a thing I want to understand," it's a Learn.

A Learn-container is fine when the topic naturally splits into sub-topics worth tracking individually but the whole still reads as one body of knowledge — *Sleep Theory* containing *Sleep Pressure*, *Sleep Stages*, *Chronotypes* etc. is a topic; the children are sub-topics. *Sleep* itself is a Goal because it spans theory + hygiene + experiments + targets — it's an area, not a topic.

### Goal vs Milestone

The other common confusion. The test is **measurability**:

| Type | Test | Example |
|---|---|---|
| Goal | No single moment marks it Done — you decide when the area is "good enough." | "Develop strength." |
| Milestone | You either did it or you didn't. Verifiable, single-event. | "Squat 1.5× bodyweight." |

The sandbox has both side by side: *Strength* is a Goal (the ongoing capacity), and underneath it sit Milestones like *5 Strict Pull-ups*, *10 Strict Pull-ups*, *Squat 1× Bodyweight*, *Squat 1.5× Bodyweight*, *Bench 1× Bodyweight*, *Deadlift 2× Bodyweight*. The work to achieve those Milestones lives on the Goal's upstream Learns and Actions (training programs, mobility, recovery) — the Milestone is the checkpoint, not the practice.

Milestones also behave differently in scoring: they're excluded from "what should I do next?" recommendations, because the work isn't on the milestone — it's on the upstream training that produces the capacity. The milestone is the checkpoint, not the practice.

If you find yourself saying "I want a target to motivate me," that's a Milestone. If you find yourself saying "I want to develop this area," that's a Goal.

### Common misclassifications to watch for

| Pattern | Sign | Fix |
|---|---|---|
| Goal-flavored Learn | Topic dressed up as a Goal because it felt important. Thin decomposition (1–2 children that are all atoms with no sub-area structure). | Demote to Learn. Use inherited mode for Ratings if you still want it to act as a container header. |
| Goal-flavored Milestone | A measurable achievement (squat target, time, count, draft completion) treated as a Goal. | Convert to Milestone. The graph stops treating it as work-to-be-done while keeping it visible as motivation. |
| Goal-flavored Action | A thing you'll *do* for a fixed period, not an area. Clear start/end; time-on-task is "the practice itself." | Convert to Action. |
| Action-flavored Learn | A topic where you only have notes-integration work to do. | Move the integration into a separate *Notes Integration* Action sitting under the Learn — don't bundle it into the Learn itself. |

### Quick rule

When in doubt, ask: *what verb describes finishing this?*

| Verb | Type |
|---|---|
| Understand | Learn |
| Do | Action |
| Consume | Resource |
| Develop | Goal |
| Hit | Milestone |

When the Next-tab list surprises you ("wait, why is *that* #1?") click its priority score to see the breakdown. Usually it's because that node sits upstream of a bunch of valuable stuff you hadn't considered connected.

---

## How to structure edges effectively

Picking the right type is half the job. Picking the right edges is the other half. A graph with the right nodes but wrong edges still mis-ranks.

### Hard vs Soft — what's the actual test?

The test for "should this be Hard" isn't "is the dependent strictly impossible without the source?" — it's broader. Hard edges encode two distinct things, both valid:

1. **Genuine logical prerequisites.** Example: `Calculus → Real Analysis` — you literally cannot do real analysis without calculus first.
2. **The user's personal sequencing preference.** Example: `Supervised Learning → Deep Learning` — technically deep learning is a kind of supervised learning, so it's not a strict prereq. But you've decided you want to do the foundations first, in that order. That's a Hard edge encoding your sequencing.

The shared property: in both cases, you want the dependent to be Blocked until the source is Done. That's what Hard edges enforce.

Soft edges are for "I want this to influence the ranking, but I'm not going to gate eligibility on it." Example: `UX Design → Personal Website`. If UX Design isn't Done, you can still work on the website — but if you want to encode "doing UX first will make the website better," a Soft edge propagates that value without blocking.

### Direction is the most error-prone thing in the app

`A → B` (Hard or Soft) means **A unlocks B**. Read the arrow as "leads to" or "comes before" or "is a prerequisite for." Worked example: `Statistics → Regression` means Statistics is the prereq, Regression is the dependent. Statistics goes first.

If you draw an arrow the wrong way, the scoring goes haywire: a node that should be cascading value forward will instead be sitting at a dead-end with no downstream, and a leaf that should be eligible will be Blocked instead. **When you draw an edge, sanity-check: which one would you do first? That's the source.** The arrowhead in the graph visualization points from source to target.

### Helps is on a different axis — don't treat it as a weaker Soft

The temptation is to think Hard > Soft > Helps as a single "strength" gradient. That's wrong. Helps is a **different kind of relationship**:

| Edge family | Axis it sits on |
|---|---|
| Hard / Soft | The *necessity* axis — must-do vs helpful-to-do. |
| Helps | The *mutual amplification* axis — two Helps-linked nodes both gain value from being adjacent. |

The math reflects this: Helps edges contribute via *two* distinct effects (the pair bonus and the completion multiplier), and they're bidirectional. They don't chain — synergy doesn't transitively cascade the way prereqs do. *A Helps B Helps C* doesn't mean A and C are connected.

Use Helps when: doing both of these is meaningfully more valuable than the sum of doing each alone. Examples from the sandbox:

| Synergy | Span | Why it works |
|---|---|---|
| `Rhetoric ↔ Writing` | People ↔ Humanities (cross-context) | Each makes the other sharper. |
| `Stoicism ↔ Eastern Philosophy` | Both Wisdom (within-context) | Each illuminates the other. |
| `History of Science ↔ STEM` | Humanities ↔ STEM (cross-context) | Historical context deepens technical study. |
| `Economic History ↔ Economics` | Humanities ↔ Money (cross-context) | Theory grounded in history. |
| `Personal Website ↔ Financial Independence` | STEM ↔ Money (cross-context) | The website is a vehicle for the goal. |

Notice how many of these are cross-context: the Creator and Explorer profiles deliberately reward those because they tend to be the most insight-generating.

### How many edges per node?

There's no strict cap, but thin graphs are easier to read and reason about. A node with 20 outgoing edges is hard to interpret visually and tends to dilute the cascade (the per-hop discounts are the same regardless of how many siblings exist).

Practical guidance from the sandbox's evolution:

| Edge type | Guidance |
|---|---|
| Hard edges | Include the actual prerequisites. Don't add extras "because it feels related" — if it's not blocking, it's not Hard. |
| Soft edges | Use *sparingly*. If you're tempted to add a Soft edge between everything that "kind of helps," you'll end up with visual noise and a muddy cascade. Reserve Soft for cases where you'd genuinely want the source's value to leak into the target's ranking. |
| Helps edges | Use *very sparingly*. Two truly synergistic nodes amplify each other; sticking Helps on everything in the same context dilutes the effect. The sandbox has 131 Helps edges across 752 nodes — roughly one for every 5–6 nodes. That's about right. |

### The sub-Goal → umbrella Goal pattern

When you decompose a Goal into sub-Goals, **hard-link each sub-Goal up to the umbrella**. Example: if *Strength* is your umbrella and you split off *Functional Exercise* as its own sub-Goal, draw `Functional Exercise → Strength` (Hard). The umbrella's score then cascades from the sub-area.

The exception is when a sub-area is genuinely standalone and shouldn't roll up — that's rare, and it's worth pausing to confirm before leaving an orphan Goal.

### Cycle detection

The app stops you from creating a cycle (A → B → C → A) at edge-creation time. If you try, you'll get an error modal explaining which cycle would form. This is mostly a safety net against accidentally drawing an edge the wrong way.

If you find yourself wanting a cycle on purpose, ask: is one of the proposed edges actually a Helps (which is bidirectional) rather than a Hard or Soft? Helps doesn't gate eligibility and doesn't cascade through chains, so it's allowed to form what would otherwise look like a cycle. Example: `Rhetoric Helps Writing, Writing Helps Rhetoric` is fine and represented as a single Helps edge between them.

If neither edge wants to be Helps, you probably have a modeling problem — two nodes that each claim to be the prereq of the other. Usually one of them should be a Goal-level container and the other should be the focused topic that contributes to it.
