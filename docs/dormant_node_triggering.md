# Dormant Node Triggering — Decision Memo

This document captures the current behavior, conceptual tension, and design
options for triggering dormant nodes. It is a pre-decision design note, not a
description of settled future behavior.

## The cleanest mental model

An Event represents a one-time transition: something happens, the Event fires,
and its dormant work begins becoming available.

Each dormant node may then have an activation delay measured from that single
firing time:

- No delay → wakes immediately.
- Two weeks → wakes two weeks after the Event fires.
- Three months → wakes three months after the Event fires.

That gives every node one shared reference point while still supporting
staggered activation.

## What the app currently does

Automatic Event triggers always process every dormant node.

Manual triggering offers:

- **Trigger All**
- **Trigger Checked**

Either button immediately marks the entire Event as **Triggered**. For checked
nodes:

- Zero-delay nodes become Awake immediately.
- Delayed nodes remain Dormant but receive a future activation date.

Unchecked nodes remain Dormant with no activation date. Because the Event is
already Triggered, its Trigger button disappears. Those unchecked nodes
therefore cannot be released through that Event later.

This conflicts with the documented rationale that Trigger Checked is useful
when an Event has “more dormant nodes than you’re ready to release at once.”
The interface suggests staged releases, but the implementation is a one-shot
selective release that strands the remainder.

## Three coherent models

### 1. One-shot Event, all nodes participate — recommended

When an Event fires, every attached node is either activated or scheduled
according to its delay. Manual triggering has one confirmation action:
**Trigger Event**.

If a node should not participate yet, the user changes its delay, removes it,
or moves it to another Event before triggering.

Advantages:

- Matches the natural meaning of an Event.
- Every delay has one unambiguous origin.
- Automatic and manual triggers behave identically.
- No dormant nodes are accidentally stranded.
- Event status remains simply Pending or Triggered.
- The existing delay feature already handles staged releases.

The cost is reduced last-minute flexibility: you cannot fire only half an
Event without reorganizing it first.

### 2. One-shot selective Event

Trigger Checked remains, but unchecked nodes must receive an explicit
disposition because the Event is finished. For example:

- Move unchecked nodes into a new Event.
- Return them to a general dormant holding area.
- Wake them too.
- Delete them.

This preserves selective commitment without pretending the same Event can fire
again. It is coherent, but the confirmation flow becomes considerably heavier.

A potentially elegant variation would be:

> Trigger checked nodes and move the remainder to a new Event…

That could be introduced later if selective triggering proves genuinely useful.

### 3. Multi-release Event

An Event becomes a staging container that can be triggered repeatedly. Checked
nodes use the date of their individual release as the origin for their delays.

This requires more state:

- Event: Pending / Partially Triggered / Triggered
- Node: Dormant / Scheduled / Awake, perhaps Skipped
- A per-node trigger date in addition to its activation date
- Rules for what automatic triggering does after a partial manual trigger
- Rules for editing triggers after part of an Event has fired
- Clear completion criteria for the Event

This is the most flexible model, but it weakens “Event” as a single occurrence.
It starts behaving more like a project backlog or release queue.

## Recommendation

Use the first model: **an Event fires once, and all attached nodes participate**.

Delays should provide the staging:

- “Review adoption requirements” — no delay
- “Buy supplies” — one week
- “Begin training course” — one month

If two groups genuinely become relevant at different real-world moments, they
are probably two Events. That preserves clarity in both the data and the
interface.

Under this model, remove the row checkboxes and the Trigger Checked / Trigger
All distinction. The confirmation can instead summarize what will happen:

> 3 nodes will wake now.  
> 2 nodes will be scheduled for later.

## Row presentation under that model

“Triggered” should remain an Event-level status. Each node row should use:

- **Dormant** — Event has not fired.
- **Scheduled** — Event fired, but the activation date has not arrived.
- **Awake** — Node has activated.

The Delay column should remain the configured offset:

- None
- 2 weeks
- 3 months
- 1 year

For scheduled nodes, the calculated date could appear in a tooltip or compact
secondary label such as `Wakes Oct 1`. That is clearer and fits the narrower
column better than `Scheduled: 2026-10-01`.

The current duration formatter should also be unified so a one-year delay
displays as `1 year`, rather than becoming `365 days` in the table.

## Questions worth settling

1. Does an Event represent one real-world occurrence or an ongoing release
   container?
2. If unchecked nodes survive a trigger, what should the user reasonably
   expect to happen to them?
3. Should automatic and manual triggering have identical node-selection
   semantics?
4. Is changing a node’s delay enough flexibility, or is selective release a
   real recurring need?
5. Should a dormant node belong to multiple Events, and if so, does the first
   Event to wake it win?

The recommended default answers are: one occurrence, no unchecked leftovers,
identical trigger semantics, delays provide staging, and one owning Event per
dormant node.
