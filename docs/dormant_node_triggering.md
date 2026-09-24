# Dormant Node Triggering — Design Record

This document records how event triggering works and why. It began as a
pre-decision memo weighing three models. The decision has been taken and
implemented; the alternatives are kept at the end for the reasoning, not as
live options.

## The model

An Event represents a one-time transition. Something happens, the Event fires,
and **every node attached to it participates**. There is no way to fire half
an Event.

Each dormant node may carry an activation delay measured from that single
firing:

- No delay → wakes immediately.
- Two weeks → wakes two weeks after the Event fires.
- Three months → wakes three months after the Event fires.

That gives every node one shared reference point while still supporting
staggered activation. Delays are the staging mechanism.

Manual triggering has one confirmation action: **Trigger Event**. The
confirmation summarizes what will happen, names the nodes waking now, and
lists the wake dates of the ones being scheduled. That summary is the last
place to notice something you did not mean to release.

## What this replaced

Manual triggering used to offer **Trigger All** and **Trigger Checked**, with
a checkbox on every row.

Either button marked the entire Event as Triggered. Checked nodes woke or were
scheduled. Unchecked nodes stayed Dormant with no activation date. Because the
Event was already Triggered, its Trigger button disappeared, and so did the
row's own edit and remove controls.

Those unchecked nodes could not be released through that Event again. The only
escape was the node editor's Dormant toggle, which woke the node immediately
and severed it from the Event — precisely the outcome unchecking it was meant
to avoid.

So the interface suggested a staged release and delivered a one-shot selective
release that stranded the remainder.

## The awake/dormant rule

`Nodes.dormant` is one bit per node. Event membership is a set: a node may
belong to several Events. Nothing keeps the two agreeing unless every writer
says so, which makes this a policy the code installs rather than a fact it can
read:

> A node with at least one `EventNodes` row is awake (`dormant = 0`) exactly
> when one of those rows has `activated = 1`.

`EventManager._sync_dormant_flag` enforces it, and it is deliberately
asymmetric. Waking is mechanical: an activated row means the node is live.
Sleeping is a decision, so the sleep half runs only where putting the node
back under an Event is what the user asked for, and refuses while any row
still holds it awake. A node with no rows at all is untouched by both halves.

Every path that writes `EventNodes` goes through it: `add_node_to_event`,
`delete_event(delete_nodes=False)`,
`move_node_to_event`, `trigger_event`, and `check_pending_activations`. The
one exception is `detach_node_from_all_events`, whose `dormant = 0` is the
user's explicit instruction.

`reconcile_dormant_flags` runs at startup beside `recompute_all_statuses`. It
only wakes nodes whose rows say they already woke, because only that direction
is unambiguous and cannot lose information. It is deliberately not a schema
migration: a migration runs once at a version bump, while this runs every
launch and so still catches drift introduced afterwards.

## Multi-event membership: first fire wins

A dormant node may belong to more than one Event. The first Event to fire
wakes it. The others still cover the node, so their rows close out too, but
they report it honestly rather than claiming it is still dormant.

`get_event_nodes` returns a `woken_by` key naming the Event that got there
first, ordered by activation date so "first to fire" is literal. The table
shows `Awake · via Music`, or `Awake · woken outside this event` when no
sibling row fired.

Two consequences worth stating:

- An already-awake row is closed out with today's date and **no** future
  activation date. A future date on a live node would send the delayed sweep
  off to wake it a second time and announce the wake.
- The trigger confirmation counts these separately. Without that line the
  summary claims wakes that are not going to happen.

## Moving a node between Events

`move_node_to_event` re-homes a dormant node. It is what replaced staged
release: firing takes everything, so "not this one yet" is said by moving the
node somewhere that has not fired.

The destination row always starts unfired. A delay measures from its own
Event's firing, which is what keeps one unambiguous origin per delay.

It refuses in five cases: moving to the same Event, a node not in the source
Event, a destination that does not exist, a destination that has already
fired, and a node that is already awake. That last one matters — a move that
re-sleeps a live node is an un-trigger by another name.

If the destination already holds the node, the two rows merge rather than
colliding on the primary key.

## Offsets before firing, dates after

Before an Event fires there is no date to speak of, so a delay is an offset:
"two weeks after". Once it fires, the wake date is written to
`EventNodes.activation_date` and the offset has nothing left to measure from,
because `Events` records no firing time.

So the node editor's Events section changes field with the row. A row whose
Event has not fired edits its offset; a scheduled row edits its wake date
directly, via `set_node_wake_date`. Moving the node to a pending Event clears
the date and puts it back on an offset.

## One node editor

Dormant nodes used to have their own editor, a modal on the Events tab that
copied every field of the node editor. The two drifted. The modal rebuilt the
node from its form, so a save dropped the fields it did not show, such as the
Now flag, lifecycle dates and recorded actual time. The node editor refused
dormant nodes, yet its search listed them.

Now there is one editor. Dormant is a field of it, applied on Save by
`node_commands.apply_dormancy`. While Dormant is on, the editor lists the
node's waiting rows (delay or wake date, and Add to Now on wake) and offers
an Event to join. Turning it on for a live node requires an Event, either a
pending one or a new one created with a manual trigger.

Putting a node to sleep refuses a node that an Event has already woken. A
woken row keeps its node awake under the rule above, so adding a second row
would change nothing. The old flow added the row anyway and left the node
live without saying so.

Adding existing nodes in bulk, from the Events tab or the canvas menu, goes
through a small Add to Event modal with no node fields.

## Row presentation

The table is `Name · Type · Delay · Wakes · Actions`. There is no Status
column: before an Event fires every row is dormant, so Status carried nothing,
and the Wakes column answers both "when" and "has it" in one place.

| Row state | Wakes column |
|---|---|
| Dormant under a Date-triggered Event | the projected date, muted |
| Dormant under a Manual or Completion Event, no delay | `On trigger`, muted |
| Dormant under a Manual or Completion Event, with a delay | `2 weeks after`, muted |
| Scheduled | the committed date, full contrast |
| Awake | an `Awake` badge, with `via <event>` beneath when another Event woke it |

A projected date is muted because the Event has not fired and the date can
still move. A date written at firing is full contrast because it is committed.

Actions are gated per row, not per Event. An awake row has none. Under the old
per-Event gate a pending Event could show actions on an awake row, and a fired
Event showed none on rows still waiting.

## Sidebar

An Event leaves the active list when it is *finished*, not merely fired:
triggered, with every node activated. A fired Event that still holds scheduled
nodes stays in the list, and its card says `5 nodes · 2 waking later`.

The divider below reads "finished events" for the same reason.

## Not doing: un-trigger

There is no operation to revert a fired Event to Pending.

It was considered as the recovery path for "that fired too early". Moving a
node to another Event covers the same ground one node at a time, without a
second way for a node's awake state to change underneath the graph. If
recovery at Event scale turns out to be a recurring need, this is the obvious
thing to add.

## The questions this settled

1. **Does an Event represent one occurrence or an ongoing container?**
   One occurrence.
2. **What happens to nodes not released by a trigger?** The question does not
   arise. Every attached node participates.
3. **Should automatic and manual triggering behave identically?** Yes. All
   four paths — manual, date, node-completion, and delayed wake — go through
   the same code and queue the same kind of announcement.
4. **Is changing a delay enough flexibility?** Delays provide the staging, and
   `move_node_to_event` covers the rest.
5. **Should a dormant node belong to multiple Events?** Yes, and the first to
   fire wins. This overrules the original memo's recommended default of one
   owning Event per dormant node. The production graph already had a node in
   two Events on purpose, and one ownership rule would have forced a data
   change to satisfy the code.

## Alternatives considered

### One-shot selective Event

Trigger Checked survives, but unchecked nodes need an explicit disposition
because the Event is finished — moved to a new Event, returned to a holding
area, woken, or deleted.

This is coherent, and a variation reading "trigger checked nodes and move the
remainder to a new Event" would have been elegant. It was rejected because the
confirmation flow becomes considerably heavier for a need that delays and a
move operation already cover.

### Multi-release Event

An Event becomes a staging container that can be triggered repeatedly, with
checked nodes using their individual release date as the origin for their
delays.

Rejected for the state it requires: Pending / Partially Triggered / Triggered
on the Event, a per-node trigger date alongside the activation date, rules for
what automatic triggering does after a partial manual one, rules for editing
triggers mid-flight, and a definition of completion. It is the most flexible
model, but it stops an Event being a single occurrence and starts behaving
like a release queue.

The deeper objection is that it conflicts with how delays work. A delay is an
offset from *the Event's* firing. Selective release implies a per-node firing.
Supporting both means storing both.
