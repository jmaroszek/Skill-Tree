"""The dormant-nodes table's Delete action deletes the node, after a confirm.

It used to be an ✕ labelled "Remove" that deleted on the first click. The
label read as "take it out of this event", which is Move's job, so the
action now says Delete and waits for the confirm modal.
"""

import json

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict

import event_callbacks
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, Node


def _callbacks():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def _with_trigger(fn, prop_id, value, *args):
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": prop_id, "value": value}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


def _delete_button(node_name):
    return json.dumps({"index": node_name, "type": "btn-delete-dormant-node"},
                      separators=(",", ":"), sort_keys=True) + ".n_clicks"


def _node(name):
    return Node(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", context="Mind", dormant=1,
    )


def _text(component):
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return "".join(_text(c) for c in component)
    return _text(getattr(component, "children", None))


def _setup(*events):
    em = EventManager()
    for name in events:
        em.add_event(Event(name=name))
    GraphManager().add_node(_node("Audio Engineering"))
    for name in events:
        em.add_node_to_event(name, "Audio Engineering")
    return em


def test_clicking_delete_opens_the_confirm_and_deletes_nothing():
    em = _setup("Music")
    fn = _callbacks()["open_delete_dormant_modal"]

    is_open, body, stored = _with_trigger(
        fn, _delete_button("Audio Engineering"), 1, [1], "Music")

    assert is_open is True
    assert stored == "Audio Engineering"
    assert "Audio Engineering" in _text(body)
    assert "permanently deleted" in _text(body)
    assert GraphManager().get_node("Audio Engineering") is not None
    assert em.get_events_for_node("Audio Engineering") == ["Music"]


def test_the_confirm_names_other_events_that_hold_the_node():
    _setup("Music", "Studio")
    fn = _callbacks()["open_delete_dormant_modal"]

    _, body, _ = _with_trigger(
        fn, _delete_button("Audio Engineering"), 1, [1], "Music")

    assert 'also leave "Studio"' in _text(body)
    assert '"Music"' not in _text(body)


def test_a_table_rerender_does_not_open_the_confirm():
    """Re-rendering the rows fires the pattern Input with n_clicks None."""
    _setup("Music")
    fn = _callbacks()["open_delete_dormant_modal"]

    assert fn([None], "Music") == (dash.no_update,) * 3


def test_cancel_closes_without_deleting():
    _setup("Music")
    assert _callbacks()["close_delete_dormant_modal"](1) is False
    assert GraphManager().get_node("Audio Engineering") is not None


def test_confirm_deletes_the_node_from_the_graph_and_every_event():
    em = _setup("Music", "Studio")
    fn = _callbacks()["confirm_delete_dormant_node"]

    is_open, table, refresh = fn(1, "Audio Engineering", "Music")

    assert is_open is False
    assert refresh.startswith("delete-Audio Engineering-")
    assert GraphManager().get_node("Audio Engineering") is None
    assert em.get_events_for_node("Audio Engineering") == []
    assert em.get_event_nodes("Music") == []
    assert em.get_event_nodes("Studio") == []
    assert "Audio Engineering" not in _text(table)


def test_confirm_without_a_stored_node_does_nothing():
    _setup("Music")
    fn = _callbacks()["confirm_delete_dormant_node"]

    assert fn(1, None, "Music") == (dash.no_update,) * 3
    assert GraphManager().get_node("Audio Engineering") is not None
