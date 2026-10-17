"""Early exits must return one value per Output.

Removing the priority override dropped an Output from four modal openers but
left their no-op returns one value too long. Dash rejects a return of the wrong
length, so each fired a callback error whenever it had nothing to do, such as
when an event's dormant-node table rendered its edit buttons.
"""

import dash

from skilltree.features.details import callbacks as details_callbacks
from skilltree.features.events import callbacks as event_callbacks
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from support.callbacks import app_with, unwrapped


def _callbacks(register):
    found = {}
    for key, spec in app_with(register).callback_map.items():
        if "callback" in spec:
            fn = unwrapped(spec["callback"])
            outputs = len(key.strip(".").split("...")) if key.startswith("..") else 1
            found[fn.__name__] = (fn, outputs)
    return found


def test_event_modal_callbacks_do_nothing_with_the_right_arity():
    found = _callbacks(event_callbacks.register_events_callbacks)
    for name, args in (("open_add_to_event_modal", ("", None, None)),
                       ("save_add_to_event", (None, None, None, 0, "days", []))):
        fn, outputs = found[name]
        assert len(fn(*args)) == outputs, name


def test_details_link_node_opener_does_nothing_with_the_right_arity():
    fn, outputs = _callbacks(details_callbacks.register_details_callbacks)["open_link_node_modal"]
    assert len(fn(None, None)) == outputs


def test_details_link_save_does_nothing_with_the_right_arity():
    fn, outputs = _callbacks(details_callbacks.register_details_callbacks)["link_existing_node"]
    assert len(fn(None, None, None, None)) == outputs
    assert len(fn(1, "Voice", None, "hard")) == outputs


def _node(name, *, dormant=0):
    return Node(
        name=name, type="Goal", description="", value=5,
        time_o=1, time_m=2, time_p=3, interest=5, difficulty=5,
        status="Open", context="Mind", dormant=dormant,
    )


def test_details_link_search_includes_dormant_nodes():
    manager = GraphManager()
    manager.add_node(_node("Voice"))
    manager.add_node(_node("Music", dormant=1))
    fn, _ = _callbacks(details_callbacks.register_details_callbacks)["open_link_node_modal"]

    result = fn("existing|123", "Voice")

    assert "Music" in {option["value"] for option in result[1]}


def test_details_link_existing_node_adds_selected_edge():
    manager = GraphManager()
    manager.add_node(_node("Voice"))
    manager.add_node(_node("Music"))
    fn, _ = _callbacks(details_callbacks.register_details_callbacks)["link_existing_node"]

    is_open, refresh, error, asks, _body, _pending = fn(1, "Voice", "Music", "soft")

    assert (is_open, error, asks) == (False, "", dash.no_update)
    assert refresh.startswith("link-")
    assert any(e["source"] == "Music" and e["target"] == "Voice"
               and e["type"] == "Needs_Soft" for e in manager.get_edges())
