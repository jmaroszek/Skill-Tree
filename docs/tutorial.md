# Tutorial: building your first graph

This walkthrough builds a small new domain — Photography — from an empty canvas, so you can see every part of the app in use without overthinking the modeling decisions. It's meant to take about fifteen minutes. The graph grows over time; you don't need to get it right the first day.

Read [`README.md`](../README.md) first if you haven't — it covers node types, edges, and the scoring algorithm at a level this tutorial assumes.

---

### Step 1: Create the umbrella Goal

Right-click the empty canvas → *New Node*. The Node Editor opens.

| Field | Value |
|---|---|
| Name | Photography |
| Type | Goal |
| Context | Humanities (or wherever you want to slot it) |
| Subcontext | (leave blank — *(Humanities, None)* is a valid bucket meaning "broad area, not a specific subarea") |
| Description | "Develop the capacity to compose and produce photographs I'm proud of." |
| Ratings (V / I / D) | 7 / 8 / 5 (or whatever feels right) |
| Inherit Ratings | Off — *Photography* feels like a topic you genuinely care about, not just a header. |
| Time Estimates | Switch to **Inherit** — the time investment will be the sum of what's underneath. |
| Status | Open |

Save. You now have a yellow star floating alone on the canvas.

**[SCREENSHOT: a single yellow Photography star on the empty canvas, node editor still open.]**

### Step 2: Decompose into sub-areas

Photography breaks down naturally into a few sub-areas you'd track separately:

| Sub-area | What it covers |
|---|---|
| Composition | The visual / artistic side. |
| Camera Operation | The technical side — settings, lenses, lighting. |
| Post-Processing | Lightroom, color grading, retouching. |

These each feel like topics you want to *understand*, not areas that themselves decompose into sub-areas. So they're Learns, not Goals.

Add them as three new nodes:

| Name | Type | Context | Ratings (V / I / D) |
|---|---|---|---|
| Composition | Learn | Humanities | 7 / 8 / 5 |
| Camera Operation | Learn | Humanities | 6 / 6 / 4 |
| Post-Processing | Learn | Humanities | 5 / 4 / 3 |

**[SCREENSHOT: four nodes on the canvas: the Photography star plus three Learn circles, unconnected.]**

### Step 3: Link the sub-areas to the umbrella with Hard edges

Open *Composition*'s editor. In the Relationships → Hard section, add *Photography* as the dependent (meaning *Composition* is a prerequisite of *Photography*).

Wait — that direction sounds backward. Let's check. *A → B (Hard)* means "A must be Done before B is eligible." Here, A = *Composition*, B = *Photography*. So *Photography* won't be marked Done until *Composition* is Done. That's the right direction: the umbrella Goal "completes" when its sub-areas complete.

Repeat for *Camera Operation* and *Post-Processing*. Each Learn now has a Hard edge pointing up to *Photography*.

**[SCREENSHOT: the four nodes now connected — three solid arrows fanning up into the Photography star.]**

### Step 4: Add a Resource

You want to read Susan Sontag's *On Photography* as background. That's external material — a Resource.

Add: *Read "On Photography" by Susan Sontag*

| Field | Value |
|---|---|
| Type | Resource |
| Context | Humanities |
| Ratings (V / I / D) | 5 / 7 / 3 |
| Time Estimates (O / M / P) | 5h / 8h / 15h |
| Status | Open |

Link it to *Composition* with a **Soft** edge: `Read "On Photography" → Composition`. Sontag isn't a strict prerequisite for understanding composition, but reading her sharpens the way you think about it.

**[SCREENSHOT: the resource added, dashed arrow flowing into Composition.]**

### Step 5: Add an Action

You commit to carrying your camera daily for 4 weeks and shooting at least 10 frames a day. That's a discrete practice with a definite end — an Action.

Add: *Daily Photo Practice — 4 Weeks*

| Field | Value |
|---|---|
| Type | Action |
| Context / Subcontext | Humanities / (blank) |
| Ratings (V / I / D) | 7 / 9 / 4 |
| Time Estimates | **Habit** mode |
| Habit duration | 4 weeks |
| Habit intensity (O / M / P) | 10 / 15 / 30 min/day |
| Link | Hard edge: `Daily Photo Practice → Composition` |

The Habit-mode math converts duration × intensity into the hours that scoring sees (4 weeks × ~15 min/day ≈ 7 hours expected).

### Step 6: Add a Milestone

You want a target: *Print and frame a photograph you're genuinely proud of*. That's a measurable, single-event achievement — a Milestone.

Add: *Print and Frame a Photograph I'm Proud Of*

| Field | Value |
|---|---|
| Type | Milestone |
| Context | Humanities |
| Ratings (V / I / D) | 8 / 9 / 3 |
| Time Estimates (O / M / P) | 1 / 1 / 1 (Milestones use minimal placeholders — the work happens upstream) |
| Links | Hard edges from *Composition*, *Camera Operation*, and *Post-Processing* — all three are prereqs to the Milestone. |

**[SCREENSHOT: the Photography sub-graph now showing the Milestone at the top, three Learns flowing into it and into the Goal, with the Resource and Action attached.]**

### Step 7: Draw a synergy

Photography and your *Optics* learning (if you have one) genuinely amplify each other — understanding how light behaves makes you a better photographer, and shooting trains your visual intuition for the physics. Add a Helps edge: `Composition ↔ Optics`. *Optics* lives in STEM/Physics; *Composition* lives in Humanities — this is a **cross-context** synergy.

If you switch to Creator or Explorer profile, this cross-context synergy will get a real visible boost in the rankings (2.0× under Creator, 1.5× under Explorer, applied to the pair bonus).

### Step 8: Promote Photography to Priority Goal

Open the Details tab. Click the Goals sidebar toggle. Drag *Photography* to the top of the list. It's now Priority Goal #1 — the entire prereq subtree (*Composition*, *Camera Operation*, *Post-Processing*, the Resource, the Action) gets a 1.5× score boost (or 2.0× under Pragmatist).

### Step 9: Open the Next tab and see what happens

Switch to Next. Some node from your new Photography subtree should now appear in the top recommendations — probably the cheapest, eligible one (the Action *Daily Photo Practice*, or the Resource *On Photography*). Click its priority score to see exactly how the rank was computed. Notice the Priority Goal multiplier line in the popup — that's the 1.5× you just applied.

**[SCREENSHOT: the Next tab with a Photography-subtree node at the top, its score popup open and the Goal Boost line highlighted.]**

That's the loop. Add nodes, draw edges, set priorities, watch the recommendations adjust. The graph grows organically as you notice gaps — "wait, I should add the lighting course" or "Color Theory should be a synergy with Composition."
