"""Hidden-input payloads decode correctly even when a name contains "|".

The JS bridges append "|<ms>" (sometimes a field and then the stamp). Reading
them by splitting on the first "|" cut a name like "A|B" down to "A", and the
action then landed on a different node.
"""
import inspect
from contextvars import copy_context

import dash
import pytest

import bridge_payloads as bridge
import callbacks
import details_callbacks
import sidebars_callbacks
from callback_helpers import resolve_active_node_id
from config import ConfigManager
from graph_manager import GraphManager
from models import Node, STATUS_DONE, STATUS_OPEN
from node_commands import handle_group_delete

STAMP = "1700000000000"


class TestCodec:
    def test_strip_stamp_keeps_pipes_inside_the_name(self):
        assert bridge.strip_stamp(f"A|B|{STAMP}") == "A|B"
        assert bridge.strip_stamp("A|B") == "A|B"
        assert bridge.strip_stamp("Plain") == "Plain"
        assert bridge.strip_stamp(None) == ""

    def test_fields_are_read_from_the_right(self):
        assert bridge.fields(f"Goal|A|2|{STAMP}", 2) == ["Goal|A", "2"]
        assert bridge.fields(f"Trip|2027|edit|{STAMP}", 2) == ["Trip|2027", "edit"]
        assert bridge.fields(f"Solo|{STAMP}", 2) is None

    def test_names_from_a_json_list_whatever_follows_it(self):
        assert bridge.names(f'["A|B", "C"]|{STAMP}|{STAMP}') == ["A|B", "C"]
        # perform_group_delete stamps with str(time.time()).
        assert bridge.names('["A|B"]|1700000000.25') == ["A|B"]

    def test_names_from_a_single_bare_name(self):
        assert bridge.names(f"A|B|{STAMP}") == ["A|B"]
        assert bridge.names(f"42|{STAMP}") == ["42"]
        assert bridge.names("") == []
        assert bridge.names(None) == []

    def test_edge_keys_round_trip_names_with_pipes(self):
        key = bridge.edge_key("A|B", "C|D", "Needs_Hard")
        assert bridge.parse_edge_key(key) == ("A|B", "C|D", "Needs_Hard")
        assert bridge.parse_edge_key("A|B|Needs_Hard") is None


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    """Two nodes whose names share a prefix up to the "|"."""
    manager = GraphManager()
    manager.add_node(_node("A", type="Goal"))
    manager.add_node(_node("A|B", type="Goal"))
    return manager


def _callback(register, name):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if getattr(fn, "__name__", None) == name:
            return fn
    raise LookupError(name)


def test_set_priority_on_a_goal_whose_name_has_a_pipe(manager):
    ConfigManager.set_priority_goals(["A"])
    handle = _callback(sidebars_callbacks.register_sidebars_callbacks,
                       "handle_goal_priority_change")

    handle(f"A|B|1|{STAMP}")

    # It used to read goal "A" with rank "B", and un-prioritize "A".
    assert ConfigManager.get_priority_goals() == ["A|B", "A"]


def test_group_delete_removes_only_the_named_node(manager):
    handle_group_delete(manager, f'["A|B"]|{STAMP}')

    assert manager.get_node("A|B") is None
    assert manager.get_node("A") is not None


def test_edit_trigger_opens_the_named_node():
    assert resolve_active_node_id({"edit-trigger-input"}, "edit-trigger-input",
                                  f"A|B|{STAMP}", None, None, None) == "A|B"


def test_details_navigation_selects_the_named_node():
    navigate = _callback(details_callbacks.register_details_callbacks,
                         "context_menu_details_navigate")
    assert navigate(f"A|B|{STAMP}", "tab-next") == ("tab-details", "A|B")


def test_context_menu_done_toggles_only_the_named_node(monkeypatch, manager):
    core_engine = _callback(callbacks.register_callbacks, "core_engine")
    trigger = "toggle-done-trigger-input"
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    kwargs = dict.fromkeys(inspect.signature(core_engine).parameters)
    kwargs["toggle_done_trigger_data"] = f'["A|B"]|{STAMP}|{STAMP}'

    copy_context().run(core_engine, **kwargs)

    assert manager.get_node("A|B").status == STATUS_DONE
    assert manager.get_node("A").status == STATUS_OPEN
