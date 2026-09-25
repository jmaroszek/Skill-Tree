"""The node editor edits dormant nodes: its Dormant switch and Event section.

There used to be a second editor, a modal on the Events tab, for dormant
nodes. It rebuilt the node from its own form and dropped every field it did
not show. Dormancy is now one more field of the one editor, applied on Save by
node_commands.apply_dormancy. A dormant node belongs to one event.
"""

import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

import database
import event_callbacks
from callback_helpers import (NEW_EVENT_OPTION, NEW_NODE_SNAPSHOT,
                              build_dormancy_snapshot, build_editor_snapshot,
                              dormancy_for_save, is_form_dirty_vs_snapshot)
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node
from node_commands import apply_dormancy, handle_save


@pytest.fixture
def mgr():
    return GraphManager()


@pytest.fixture
def em():
    return EventManager()


def _node(name, **overrides):
    fields = dict(name=name, type="Action", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _form(dormant=True, event=None, event_name="", delay=0, unit="days",
          wake_date=None, now=False):
    """A node-dormancy-form dict as the clientside collector builds it."""
    return {"dormant": dormant, "event": event, "event_name": event_name,
            "delay_value": delay, "delay_unit": unit, "wake_date": wake_date,
            "now": now}


def _apply(mgr, em, name, form, was_dormant):
    apply_dormancy(mgr, em, name, dormancy_for_save(form), was_dormant)


# --- Putting a node to sleep ------------------------------------------------

def test_a_live_node_sleeps_under_the_chosen_event(mgr, em):
    mgr.add_node(_node("Voice"))
    em.add_event(Event(name="Move"))

    _apply(mgr, em, "Voice", _form(event="Move", delay=2, unit="weeks", now=True),
           was_dormant=False)

    assert mgr.get_node("Voice").dormant == 1
    row = em.get_node_membership("Voice")
    assert row["event"] == "Move"
    assert row["delay_days"] == 14
    assert row["now_on_trigger"] is True


def test_new_event_is_created_manual_by_name(mgr, em):
    mgr.add_node(_node("Voice"))

    _apply(mgr, em, "Voice", _form(event=NEW_EVENT_OPTION, event_name="  After Move "),
           was_dormant=False)

    event = em.get_event("After Move")
    assert event is not None
    assert event.trigger_date is None and not event.trigger_nodes
    assert em.get_event_for_node("Voice") == "After Move"


def test_new_event_needs_a_name(mgr, em):
    mgr.add_node(_node("Voice"))
    with pytest.raises(ValueError, match="Name the new event"):
        _apply(mgr, em, "Voice", _form(event=NEW_EVENT_OPTION), was_dormant=False)


def test_sleeping_needs_an_event(mgr, em):
    mgr.add_node(_node("Voice"))
    with pytest.raises(ValueError, match="Pick an event"):
        _apply(mgr, em, "Voice", _form(), was_dormant=False)
    assert mgr.get_node("Voice").dormant == 0


def test_a_node_its_event_already_woke_says_so_and_nothing_is_saved(mgr, em):
    """A woken row keeps a node awake for good, so the editor refuses and
    the transaction rolls the save back."""
    mgr.add_node(_node("Voice"))
    em.add_event(Event(name="First"))
    em.add_event(Event(name="Second"))
    em.add_node_to_event("First", "Voice")
    em.trigger_event("First")

    with pytest.raises(ValueError, match="already woke from 'First'"):
        with database.transaction():
            _apply(mgr, em, "Voice", _form(event="Second"), was_dormant=False)

    assert mgr.get_node("Voice").dormant == 0
    assert em.get_event_for_node("Voice") == "First"


def test_sleeping_takes_the_node_off_now(mgr, em):
    mgr.add_node(_node("Voice", now=1))
    em.add_event(Event(name="Move"))

    _apply(mgr, em, "Voice", _form(event="Move"), was_dormant=False)

    assert mgr.get_node("Voice").now == 0


def test_a_new_dormant_node_is_saved_in_one_transaction(mgr, em):
    """handle_save creates the node live, then apply_dormancy sleeps it. A
    refusal in the second half must not leave a live node behind."""
    with pytest.raises(ValueError):
        with database.transaction():
            handle_save(mgr, "Fresh", "Action", "", 5, 1.0, 2.0, 4.0, 5, 5,
                        [], "Mind", None, None, [], [], [], [], [])
            _apply(mgr, em, "Fresh", _form(), was_dormant=False)
    assert mgr.get_node("Fresh") is None


# --- Editing, moving and waking a dormant node ------------------------------

def test_editing_the_delay_and_now_flag(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=7)

    _apply(mgr, em, "Voice", _form(event="A", delay=1, unit="months", now=True),
           was_dormant=True)

    row = em.get_node_membership("Voice")
    assert row["delay_days"] == 30 and row["now_on_trigger"] is True


def test_choosing_another_event_moves_the_node(mgr, em):
    em.add_event(Event(name="A"))
    em.add_event(Event(name="B"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=7)

    _apply(mgr, em, "Voice", _form(event="B", delay=3, now=True), was_dormant=True)

    assert em.get_event_nodes("A") == []
    row = em.get_node_membership("Voice")
    assert row["event"] == "B"
    assert row["delay_days"] == 3 and row["now_on_trigger"] is True
    assert mgr.get_node("Voice").dormant == 1


def test_a_node_on_a_wake_date_can_move_to_a_pending_event(mgr, em):
    em.add_event(Event(name="Fired"))
    em.add_event(Event(name="Later"))
    em.create_dormant_node(_node("Voice"), "Fired", delay_days=90)
    em.trigger_event("Fired")

    _apply(mgr, em, "Voice", _form(event="Later"), was_dormant=True)

    row = em.get_node_membership("Voice")
    assert row["event"] == "Later"
    assert row["activation_date"] is None


def test_a_fired_event_edits_its_wake_date(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=90)
    em.trigger_event("A")

    _apply(mgr, em, "Voice", _form(event="A", wake_date="2027-03-01"),
           was_dormant=True)

    assert em.get_node_membership("Voice")["activation_date"] == "2027-03-01"


def test_a_cleared_wake_date_is_refused(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=90)
    em.trigger_event("A")

    with pytest.raises(ValueError, match="wake date"):
        _apply(mgr, em, "Voice", _form(event="A", wake_date=""), was_dormant=True)


def test_unchecking_dormant_wakes_the_node_and_leaves_its_event(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A")

    _apply(mgr, em, "Voice", _form(dormant=False), was_dormant=True)

    assert mgr.get_node("Voice").dormant == 0
    assert em.get_event_for_node("Voice") is None


def test_saving_a_dormant_node_keeps_fields_the_form_does_not_show(mgr, em):
    """The regression the old modal had: it rebuilt the node and dropped these."""
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A")
    stored = mgr.get_node("Voice")
    stored.start_date = "2026-01-02"
    stored.actual_time_point = 12.0
    stored.calibration_dismissed = 1
    mgr.update_node(stored)

    handle_save(mgr, "Voice", "Action", "edited", 5, 1.0, 2.0, 4.0, 5, 5,
                [], "Mind", None, None, [], [], [], [], [])
    _apply(mgr, em, "Voice", _form(event="A"), was_dormant=True)

    after = mgr.get_node("Voice")
    assert after.description == "edited"
    assert after.dormant == 1
    assert after.start_date == "2026-01-02"
    assert after.actual_time_point == 12.0
    assert after.calibration_dismissed == 1


# --- What the section shows, and the unsaved-changes check -------------------

def test_a_woken_row_is_not_a_membership(mgr, em):
    mgr.add_node(_node("Voice"))
    em.add_event(Event(name="First"))
    em.add_node_to_event("First", "Voice")
    em.trigger_event("First")

    assert em.get_node_membership("Voice") is None


def test_set_now_on_trigger(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A")
    em.set_now_on_trigger("A", "Voice", True)
    assert em.get_node_membership("Voice")["now_on_trigger"] is True


def test_snapshot_of_a_dormant_node_shows_its_event(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=14, now_on_trigger=True)

    snap = build_dormancy_snapshot(mgr.get_node("Voice"), em)

    assert snap == {"dormant": True, "event": "A", "event_name": "",
                    "delay_value": 2, "delay_unit": "weeks",
                    "wake_date": None, "now": True}
    assert build_editor_snapshot(mgr, "Voice")["dormancy"] == snap


def test_snapshot_of_a_scheduled_node_shows_its_wake_date(mgr, em):
    em.add_event(Event(name="A"))
    em.create_dormant_node(_node("Voice"), "A", delay_days=14)
    em.trigger_event("A")

    snap = build_dormancy_snapshot(mgr.get_node("Voice"), em)

    assert snap["event"] == "A"
    assert snap["wake_date"] == em.get_node_membership("Voice")["activation_date"]


def test_a_live_node_snapshot_is_not_dormant(mgr):
    mgr.add_node(_node("Voice"))
    assert build_dormancy_snapshot(mgr.get_node("Voice"))["dormant"] is False


def test_delays_compare_in_days():
    snap = dict(NEW_NODE_SNAPSHOT, dormancy=_form(event="A", delay=1, unit="weeks"))
    form = dict(snap, dormancy=_form(event="A", delay=7, unit="days"))
    assert not is_form_dirty_vs_snapshot(snap, form)


def test_changing_the_event_is_an_unsaved_change():
    snap = dict(NEW_NODE_SNAPSHOT, dormancy=_form(event="A"))
    form = dict(snap, dormancy=_form(event="B"))
    assert is_form_dirty_vs_snapshot(snap, form)


def test_the_section_is_ignored_while_dormant_is_off():
    form = dict(NEW_NODE_SNAPSHOT, dormancy=_form(dormant=False, event="A", delay=3))
    assert not is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, form)


def test_flipping_dormant_is_an_unsaved_change():
    form = dict(NEW_NODE_SNAPSHOT, dormancy=_form(dormant=True))
    assert is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, form)


def test_an_unset_store_matches_a_live_node():
    form = dict(NEW_NODE_SNAPSHOT, dormancy=None)
    assert not is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, form)


# --- The Events tab's "+" menu and the Add to Event modal --------------------

def _callback(name):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None and fn.__name__ == name:
            return fn
    raise KeyError(name)


def _with_trigger(fn, prop_id, *args):
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": prop_id, "value": args[0]}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


def test_existing_nodes_offers_only_nodes_without_an_event(mgr, em):
    mgr.add_node(_node("Free"))
    mgr.add_node(_node("Woken"))
    em.add_event(Event(name="Move"))
    em.add_event(Event(name="Fired"))
    em.add_node_to_event("Fired", "Woken")
    em.trigger_event("Fired")

    result = _with_trigger(_callback("open_add_to_event_modal"),
                           "dormant-add-choice-input.value",
                           None, "existing|123", "Move")

    assert result[0] is True
    assert [o["value"] for o in result[1]] == ["Free"]
    assert result[4] == "Move"


def test_new_node_choice_does_not_open_the_modal(mgr, em):
    em.add_event(Event(name="Move"))

    result = _with_trigger(_callback("open_add_to_event_modal"),
                           "dormant-add-choice-input.value",
                           None, "new|123", "Move")

    assert result == (dash.no_update,) * 9


def test_add_to_event_puts_several_nodes_to_sleep(mgr, em):
    mgr.add_node(_node("Voice"))
    mgr.add_node(_node("Piano"))
    em.add_event(Event(name="Move"))

    result = _callback("save_add_to_event")(
        1, ["Voice", "Piano"], "Move", 1, "weeks", ["on"])

    assert result[0] is False
    rows = {en["node"].name: en for en in em.get_event_nodes("Move")}
    assert set(rows) == {"Voice", "Piano"}
    assert all(r["delay_days"] == 7 and r["now_on_trigger"] for r in rows.values())


def test_add_to_event_refuses_a_node_in_another_event_and_adds_none(mgr, em):
    mgr.add_node(_node("Voice"))
    mgr.add_node(_node("Piano"))
    em.add_event(Event(name="First"))
    em.add_event(Event(name="Move"))
    em.add_node_to_event("First", "Piano")

    result = _callback("save_add_to_event")(
        1, ["Voice", "Piano"], "Move", 0, "days", [])

    assert "Piano" in result[1]
    assert em.get_event_nodes("Move") == []
    assert mgr.get_node("Voice").dormant == 0
