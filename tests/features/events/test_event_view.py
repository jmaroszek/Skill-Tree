"""Opening an event sends everything its panel shows with the fields (view.py).

The panel used to draw an event in two paints: the fields, then the callbacks
that follow them. For a moment a fired event offered trigger fields to edit, and
the previous event's trigger section stayed up. These check the open sends what
those callbacks would, so their later answers change nothing.
"""
import pytest

from skilltree.domain.models import Event
from skilltree.features.events.callbacks import register_events_callbacks
from skilltree.features.events.view import VIEW_OUTPUTS
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from support.callbacks import app_with, registered
from support.graphs import make_node
from support.triggers import fire

FIELDS = 14  # the fields before the view in _DETAIL_OUTPUTS
VIEW = slice(FIELDS, FIELDS + len(VIEW_OUTPUTS))


@pytest.fixture
def events():
    graph = GraphManager()
    graph.add_node(make_node("Cooking"))
    manager = EventManager(graph)
    manager.add_event(Event(name="Dated", trigger_date="2030-01-01"))
    manager.add_event(Event(name="Waiting", trigger_nodes=["Cooking"]))
    manager.add_event(Event(name="Manual"))
    manager.add_event(Event(name="Fired"))
    manager.trigger_event_manually("Fired")
    return manager


@pytest.fixture
def handlers(events):
    return registered(register_events_callbacks)


def _open(handlers, trigger, action=None):
    fire(trigger)
    return handlers["open_event_detail"](None, None, [], action, None, None, {}, None, None,
                                         "tab-events")


def _view(result):
    return dict(zip(VIEW_OUTPUTS, result[VIEW]))


def _opened(handlers, name):
    return _view(_open(handlers, "event-ctx-action-input.value", f"{name}|edit|1"))


def test_a_fired_event_opens_locked(handlers):
    view = _opened(handlers, "Fired")
    assert view[("event-trigger-btn-wrapper", "style")] == {"display": "none"}
    assert view[("dormant-add-btn-wrapper", "style")] == {"display": "none"}
    assert view[("event-trigger-date", "disabled")] is True
    assert view[("event-trigger-node", "disabled")] is True
    assert all(o["disabled"] for o in view[("event-trigger-type", "options")])


def test_a_waiting_event_opens_with_its_trigger_section(handlers):
    view = _opened(handlers, "Waiting")
    assert view[("event-node-section", "style")] == {"display": "block"}
    assert view[("event-date-section", "style")] == {"display": "none"}
    assert "Cooking" in view[("event-trigger-mode-hint", "children")]
    assert view[("event-trigger-btn-wrapper", "style")] != {"display": "none"}
    assert view[("dormant-add-btn-wrapper", "style")] == {}

    dated = _opened(handlers, "Dated")
    assert dated[("event-date-section", "style")] == {"display": "block"}
    assert dated[("event-node-section", "style")] == {"display": "none"}


@pytest.mark.parametrize("trigger", ["btn-new-event", "btn-event-close"])
def test_a_new_or_closed_panel_offers_nothing_saved(handlers, trigger):
    view = _view(_open(handlers, trigger))
    assert view[("event-date-section", "style")] == {"display": "none"}
    assert view[("event-node-section", "style")] == {"display": "none"}
    assert view[("event-trigger-btn-wrapper", "style")] == {"display": "none"}
    assert view[("dormant-add-btn-wrapper", "style")] == {"display": "none"}
    assert view[("event-trigger-date", "disabled")] is False


@pytest.mark.parametrize("name", ["Dated", "Waiting", "Manual", "Fired"])
def test_the_followers_agree_with_the_open(handlers, name):
    """Each callback that follows the fields answers what the open already sent."""
    result = _open(handlers, "event-ctx-action-input.value", f"{name}|edit|1")
    view = _view(result)
    trigger_type, trigger_nodes, trigger_mode = result[10], result[11], result[12]
    assert handlers["toggle_trigger_sections"](trigger_type) == (
        view[("event-date-section", "style")], view[("event-node-section", "style")])
    assert handlers["describe_trigger_mode"](trigger_mode, trigger_nodes) == \
        view[("event-trigger-mode-hint", "children")]
    assert handlers["show_event_state"](name, 0, 0) == tuple(
        view[key] for key in VIEW_OUTPUTS[3:8])
    assert handlers["toggle_add_dormant_button"](name, 0) == view[("dormant-add-btn-wrapper", "style")]


def test_every_view_output_has_a_callback_for_later_changes(events):
    app = app_with(register_events_callbacks)
    opens = [spec["output"] for spec in app._callback_list
             if "event-detail-content.style" in spec["output"]]
    others = " ".join(spec["output"] for spec in app._callback_list if spec["output"] not in opens)
    for component, prop in VIEW_OUTPUTS:
        assert f"{component}.{prop}" in others, (component, prop)
