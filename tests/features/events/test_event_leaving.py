"""Leaving an event with unsaved edits asks first, and a fired event's panel."""
import dash
import pytest

from skilltree.domain.models import Event
from skilltree.features.events.callbacks import register_events_callbacks
from skilltree.features.events.layout import event_form_is_dirty
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from support.callbacks import app_with, registered
from support.graphs import make_node
from support.triggers import fire

CARD = '{"index":"%s","type":"event-card"}.n_clicks'
OUTPUTS = 14  # _DETAIL_OUTPUTS


def _form(**fields):
    return {**dict(name="", description="", trigger_type="manual", trigger_date="",
                   trigger_nodes=[], trigger_mode="any"), **fields}


@pytest.fixture
def events():
    manager = EventManager(GraphManager())
    manager.add_event(Event(name="Trip", description="Pack"))
    manager.add_event(Event(name="Move"))
    return manager


@pytest.fixture
def handlers(events):
    return registered(register_events_callbacks)


def _open(handlers, trigger, *, cards=(), action=None, form=None, selected=None, pending=None,
          after_save=None):
    fire(trigger)
    return handlers["open_event_detail"](None, None, list(cards), action, None, after_save,
                                         form or _form(), selected, pending, "tab-events")


def test_nothing_is_dirty_when_the_form_shows_what_is_saved(events):
    saved = events.get_event("Trip")
    assert not event_form_is_dirty(_form(name="Trip", description="Pack"), saved)
    assert event_form_is_dirty(_form(name="Trip", description="Pack more"), saved)
    assert event_form_is_dirty(_form(name="Trip", description="Pack", trigger_type="date",
                                     trigger_date="2030-01-01"), saved)


def test_fields_of_another_trigger_type_dont_count(events):
    saved = events.get_event("Trip")
    assert not event_form_is_dirty(
        _form(name="Trip", description="Pack", trigger_date="2030-01-01"), saved)


def test_a_blank_new_event_has_nothing_to_lose():
    assert not event_form_is_dirty(_form(), None)
    assert event_form_is_dirty(_form(name="Half typed"), None)


@pytest.mark.parametrize("trigger, cards, action, target", [
    ("btn-event-close", (), None, {"kind": "close"}),
    ("btn-new-event", (), None, {"kind": "new"}),
    (CARD % "Move", (1,), None, {"kind": "event", "event": "Move", "action": "edit"}),
    ("event-ctx-action-input.value", (), "Move|delete|1",
     {"kind": "event", "event": "Move", "action": "delete"}),
])
def test_leaving_with_edits_asks_and_remembers_where(handlers, trigger, cards, action, target):
    result = _open(handlers, trigger, cards=cards, action=action,
                   form=_form(name="Trip", description="Edited"), selected="Trip")
    assert result[:OUTPUTS + 2] == (dash.no_update,) * (OUTPUTS + 2)
    assert result[-2:] == (True, target)


def test_leaving_a_clean_event_just_goes(handlers):
    result = _open(handlers, CARD % "Move", cards=(1,),
                   form=_form(name="Trip", description="Pack"), selected="Trip")
    assert result[0] == "Move"
    assert result[-2:] == (False, None)


def test_the_open_card_with_edits_does_nothing(handlers):
    result = _open(handlers, CARD % "Trip", cards=(1,),
                   form=_form(name="Trip", description="Edited"), selected="Trip")
    assert result == (dash.no_update,) * (OUTPUTS + 4)


def test_a_rebuilt_list_is_not_a_click(handlers):
    result = _open(handlers, CARD % "Move", cards=(None,),
                   form=_form(name="Trip", description="Edited"), selected="Trip")
    assert result == (dash.no_update,) * (OUTPUTS + 4)


def test_discard_goes_where_the_click_was_going(handlers):
    pending = {"kind": "event", "event": "Move", "action": "edit"}
    result = _open(handlers, "btn-event-unsaved-discard",
                   form=_form(name="Trip", description="Edited"), selected="Trip", pending=pending)
    assert result[0] == "Move" and result[4] == "Move"
    assert result[-2:] == (False, None)


def test_discard_can_close(handlers):
    result = _open(handlers, "btn-event-unsaved-discard",
                   form=_form(name="Trip", description="Edited"), selected="Trip",
                   pending={"kind": "close"})
    assert result[0] is None and result[3] == {"display": "none"}


def test_the_dialogs_save_goes_on_only_after_it_saved(handlers, events):
    save = handlers["save_event"]
    pending = {"kind": "close"}
    done = save(None, "Trip", "Trip", "Edited", "manual", "", [], "any", 1, pending)
    assert events.get_event("Trip").description == "Edited"
    assert done[-1]["kind"] == "close" and done[4] is False and done[5] is None

    refused = save(None, "Trip", " ", "Edited", "manual", "", [], "any", 2, pending)
    assert refused[-1] is dash.no_update
    assert refused[4] is False  # the dialog closes, so the refusal can be read


def test_the_dialogs_save_goes_where_the_click_was_going(handlers):
    result = _open(handlers, "event-leave-after-save",
                   after_save={"kind": "event", "event": "Move", "action": "edit", "saved": 1})
    assert result[0] == "Move" and result[4] == "Move"
    assert result[-2:] == (False, None)


def test_going_on_comes_in_apart_from_the_cards(events):
    """The save rebuilds the list, and each new card fires its callback. Dash
    throws away a run's answer if the callback fires again first, which left the
    event saved and the form where it was."""
    app = app_with(register_events_callbacks)
    going_on = [spec for spec in app._callback_list
                if any(i["id"] == "event-leave-after-save" for i in spec["inputs"])]
    assert len(going_on) == 1
    assert not any("event-card" in str(i["id"]) for i in going_on[0]["inputs"])


def test_edit_in_the_dialog_keeps_the_form(handlers):
    assert handlers["keep_editing_event"](1) == (False, None)


def test_a_menu_action_on_an_event_opens_its_confirmation(handlers):
    result = _open(handlers, "event-ctx-action-input.value", action="Move|trigger|1")
    assert result[0] == "Move"
    assert result[OUTPUTS:OUTPUTS + 2] == (True, False)


def test_a_fired_event_locks_its_trigger_and_keeps_delete(handlers, events):
    events.trigger_event_manually("Trip")
    trigger_style, types, date_off, nodes_off, modes = handlers["show_event_state"]("Trip", 0, 0)
    assert trigger_style == {"display": "none"}
    assert date_off is True and nodes_off is True
    assert all(option["disabled"] for option in types + modes)

    result = _open(handlers, CARD % "Trip", cards=(1,))
    assert result[7] != {"display": "none"}  # Delete

    # Its name and description still save.
    handlers["save_event"](1, "Trip", "Trip", "Notes", "manual", "", [], "any")
    assert events.get_event("Trip").description == "Notes"
    assert events.get_event("Trip").status == "Triggered"


def test_a_waiting_event_offers_everything(handlers):
    trigger_style, types, date_off, nodes_off, modes = handlers["show_event_state"]("Move", 0, 0)
    assert trigger_style != {"display": "none"}
    assert date_off is False and nodes_off is False
    assert not any(option["disabled"] for option in types + modes)


def test_no_event_shows_no_trigger_button(handlers):
    assert handlers["show_event_state"](None, 0, 0)[0] == {"display": "none"}


# --- EV-43: loops of events waiting on each other ---

@pytest.fixture
def loop_graph():
    graph = GraphManager()
    for name in ("Alpha", "Beta", "Gamma", "Delta"):
        graph.add_node(make_node(name))
    return graph


def test_two_events_cant_wait_on_each_other(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_nodes=["Alpha"]))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_node_to_event("First", "Beta")

    with pytest.raises(ValueError, match="'First' and 'Second' waiting on each other"):
        events.add_node_to_event("Second", "Alpha")
    assert loop_graph.get_node("Alpha").dormant == 0


def test_a_longer_loop_is_refused_too(loop_graph):
    events = EventManager(loop_graph)
    for name, node in (("One", "Alpha"), ("Two", "Beta"), ("Three", "Gamma")):
        events.add_event(Event(name=name, trigger_nodes=[node]))
    events.add_node_to_event("One", "Beta")
    events.add_node_to_event("Two", "Gamma")
    with pytest.raises(ValueError, match="waiting on each other"):
        events.add_node_to_event("Three", "Alpha")


def test_saving_a_trigger_can_close_the_loop(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_nodes=["Alpha"]))
    events.add_event(Event(name="Second"))
    events.add_node_to_event("First", "Beta")
    events.add_node_to_event("Second", "Alpha")
    with pytest.raises(ValueError, match="waiting on each other"):
        events.update_event("Second", Event(name="Second", trigger_nodes=["Beta"]))
    assert events.get_event("Second").trigger_nodes == []


def test_moving_a_node_can_close_the_loop(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_nodes=["Alpha"]))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_event(Event(name="Spare"))
    events.add_node_to_event("First", "Beta")
    events.add_node_to_event("Spare", "Alpha")
    with pytest.raises(ValueError, match="waiting on each other"):
        events.move_node_to_event("Spare", "Alpha", "Second")


def test_another_way_out_means_no_loop(loop_graph):
    events = EventManager(loop_graph)
    # Any of two triggers will do, and Gamma is awake.
    events.add_event(Event(name="First", trigger_nodes=["Alpha", "Gamma"]))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_node_to_event("First", "Beta")
    events.add_node_to_event("Second", "Alpha")


def test_needing_all_triggers_closes_it_anyway(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_nodes=["Alpha", "Gamma"], trigger_mode="all"))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_node_to_event("First", "Beta")
    with pytest.raises(ValueError, match="waiting on each other"):
        events.add_node_to_event("Second", "Alpha")


def test_a_date_is_a_way_out(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_date="2099-01-01"))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_node_to_event("First", "Beta")


def test_a_loop_saved_earlier_doesnt_hold_up_other_saves(loop_graph):
    events = EventManager(loop_graph)
    events.add_event(Event(name="First", trigger_nodes=["Alpha"]))
    events.add_event(Event(name="Second", trigger_nodes=["Beta"]))
    events.add_node_to_event("First", "Beta")
    # As if saved before the check: no save could make this now.
    with events.get_connection() as conn:
        conn.execute("INSERT INTO EventNodes (event_name, node_name, delay_days) "
                     "VALUES ('Second', 'Alpha', 0)")
        conn.execute("UPDATE Nodes SET dormant=1 WHERE name='Alpha'")
        conn.commit()

    events.update_event("First", Event(name="First", description="Note",
                                       trigger_nodes=["Alpha"]))
    events.update_event("First", Event(name="Renamed", trigger_nodes=["Alpha"]))
    events.add_event(Event(name="Other"))
    assert events.get_event("Renamed") is not None

    # Trigger Now still breaks it.
    events.trigger_event_manually("Renamed")
    assert loop_graph.get_node("Beta").dormant == 0
