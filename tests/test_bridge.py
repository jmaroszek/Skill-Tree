"""Bridges: a new node put between two nodes you already have.

The dialog (bridge_callbacks) plans the bridge, Create fills the node editor in
(populate_editor), and the save that makes the node removes the direct link the
bridge replaces (finish_bridge, run inside core_engine's transaction).
"""
import dash
import pytest

from skilltree.features.links import bridge as bridge_callbacks
from skilltree.ui import payloads as bridge_payloads
from skilltree.engine import callbacks
from skilltree.features.editor.form import NEW_NODE_SNAPSHOT
from editor_forms import call
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Node
from skilltree.store.commands import bridge_form, finish_bridge, plan_bridge
from support.triggers import fire


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("A", "B", "C"):
        manager.add_node(_node(name))
    return manager


def _edges(manager):
    return {(e["source"], e["target"], e["type"]) for e in manager.get_edges()}


# --- Planning -------------------------------------------------------------

def test_a_bridge_replaces_the_direct_prerequisite_link(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_SOFT)

    plan = plan_bridge(manager, "A", "B", "hard")

    assert plan == {"problem": None, "replaces": ["A", "B", EDGE_NEEDS_SOFT]}


def test_unlinked_nodes_have_nothing_to_replace(manager):
    assert plan_bridge(manager, "A", "B", "hard") == {"problem": None, "replaces": None}


def test_a_synergy_bridge_replaces_nothing(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    assert plan_bridge(manager, "A", "B", "synergy") == {"problem": None, "replaces": None}


def test_the_reverse_order_would_make_a_circle(manager):
    manager.add_edge("B", "A", EDGE_NEEDS_HARD)

    plan = plan_bridge(manager, "A", "B", "hard")

    assert "circular dependency" in plan["problem"]
    assert plan["replaces"] is None


def test_a_longer_route_back_would_also_make_a_circle(manager):
    manager.add_edge("B", "C", EDGE_NEEDS_HARD)
    manager.add_edge("C", "A", EDGE_NEEDS_SOFT)

    assert plan_bridge(manager, "A", "B", "soft")["problem"]
    assert plan_bridge(manager, "B", "A", "soft")["problem"] is None


def test_a_synergy_between_linked_nodes_makes_no_circle(manager):
    manager.add_edge("B", "A", EDGE_NEEDS_HARD)

    assert plan_bridge(manager, "A", "B", "synergy")["problem"] is None


def test_a_missing_node_or_kind_is_a_problem(manager):
    assert plan_bridge(manager, "A", "Gone", "hard")["problem"]
    assert plan_bridge(manager, "A", "A", "hard")["problem"]
    assert plan_bridge(manager, "A", "B", None)["problem"]


@pytest.mark.parametrize("kind, expected", [
    ("hard", {"e_needs_h": ["A"], "e_supp_h": ["B"]}),
    ("soft", {"e_needs_s": ["A"], "e_supp_s": ["B"]}),
    ("synergy", {"e_helps": ["A", "B"]}),
])
def test_the_editor_fields_a_bridge_fills_in(kind, expected):
    fields = bridge_form("A", "B", kind)

    assert {key: value for key, value in fields.items() if value} == expected


# --- The dialog -----------------------------------------------------------

def test_a_request_names_its_nodes_and_an_edge_type():
    assert bridge_payloads.bridge_request('["A","B"]|1700000000000') == ("A", "B", None)
    assert bridge_payloads.bridge_request(
        '["A|x","B","Needs_Hard"]|1700000000000') == ("A|x", "B", "Needs_Hard")
    assert bridge_payloads.bridge_request('["A"]|1') is None
    assert bridge_payloads.bridge_request("") is None


def test_the_dialog_opens_in_the_order_and_type_of_an_existing_link(manager):
    manager.add_edge("B", "A", EDGE_NEEDS_SOFT)

    assert bridge_callbacks.opening_ends(manager, "A", "B") == ("B", "A", "soft")
    assert bridge_callbacks.opening_ends(manager, "A", "C") == ("A", "C", "hard")
    # An edge names its own order and type, whatever else links the pair.
    assert bridge_callbacks.opening_ends(manager, "A", "B", EDGE_NEEDS_HARD) == ("A", "B", "hard")
    # A Synergy link opens as one, though a prerequisite links the pair too.
    assert bridge_callbacks.opening_ends(manager, "A", "B", EDGE_HELPS) == ("A", "B", "synergy")


def _bridge_callbacks():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    bridge_callbacks.register_bridge_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found[getattr(fn, "__name__", None)] = fn
    return found


def test_the_dialog_opens_for_two_nodes(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    open_modal = _bridge_callbacks()["open_bridge_modal"]

    is_open, kind, ends = open_modal('["B","A"]|1')

    assert is_open is True
    assert kind == "hard"
    assert ends == {"start": "A", "end": "B"}


def test_the_dialog_ignores_a_request_for_a_missing_node(manager):
    open_modal = _bridge_callbacks()["open_bridge_modal"]

    assert open_modal('["A","Gone"]|1') == (dash.no_update,) * 3


def test_swap_reverses_start_and_end(manager):
    swap = _bridge_callbacks()["swap_bridge_ends"]

    assert swap(1, {"start": "A", "end": "B"}) == {"start": "B", "end": "A"}


def test_the_dialog_says_what_a_bridge_replaces_and_blocks_a_circle(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    render = _bridge_callbacks()["render_bridge_modal"]

    *_, notice, _style, disabled, _swap = render({"start": "A", "end": "B"}, "hard")
    assert "replaced" in notice and not disabled

    *_, notice, _style, disabled, _swap = render({"start": "B", "end": "A"}, "hard")
    assert "circular dependency" in notice and disabled


def test_a_synergy_hides_the_swap(manager):
    render = _bridge_callbacks()["render_bridge_modal"]

    start, end, start_label, end_label, *_rest, swap = render(
        {"start": "A", "end": "B"}, "synergy")

    assert (start_label, end_label) == ("Node", "Node")
    assert swap == {"display": "none"}


# --- Saving ---------------------------------------------------------------

def test_the_save_that_makes_the_bridge_removes_the_link_it_replaces(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    manager.add_node(_node("M"))
    manager.sync_edges("M", ["A"], [], ["B"], [], [])
    pending = {"replaces": ["A", "B", EDGE_NEEDS_HARD]}

    assert finish_bridge(manager, "M", pending) == ("A", "B")

    assert _edges(manager) == {("A", "M", EDGE_NEEDS_HARD), ("M", "B", EDGE_NEEDS_HARD)}


def test_a_node_that_no_longer_sits_between_leaves_the_link(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    manager.add_node(_node("M"))
    manager.sync_edges("M", ["A"], [], [], [], [])  # the user dropped the End
    pending = {"replaces": ["A", "B", EDGE_NEEDS_HARD]}

    assert finish_bridge(manager, "M", pending) is None

    assert ("A", "B", EDGE_NEEDS_HARD) in _edges(manager)


def test_no_pending_bridge_changes_nothing(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    assert finish_bridge(manager, "A", None) is None
    assert finish_bridge(manager, "A", {"replaces": None}) is None
    assert finish_bridge(manager, "A", {"replaces": ["A", "B"]}) is None


def _registered():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found.setdefault(getattr(fn, "__name__", None), fn)
    return found


def _save(monkeypatch, bridge_pending, original_name=None, **form):
    core_engine = _registered()["core_engine"]
    fire("btn-save")
    values = dict(n_type="Learn", desc="", context="Mind", status_done=[],
                  val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit="hours", link_values=[], link_ids=[], aliases=[],
                  ed_style={"transform": "translateX(0px)"})
    values.update(form)
    return callbacks.CoreResponse(*call(
        core_engine, bridge_pending=bridge_pending, original_name=original_name,
        **values))


def test_saving_the_new_node_replaces_the_link(monkeypatch, manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    pending = {"start": "A", "end": "B", "kind": "hard",
               "replaces": ["A", "B", EDGE_NEEDS_HARD]}

    response = _save(monkeypatch, pending, name="Middle",
                     e_needs_h=["A"], e_supp_h=["B"])

    assert "replacing the link from 'A' to 'B'" in response.message
    assert _edges(manager) == {("A", "Middle", EDGE_NEEDS_HARD),
                               ("Middle", "B", EDGE_NEEDS_HARD)}


def test_a_refused_save_keeps_the_link(monkeypatch, manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    pending = {"replaces": ["A", "B", EDGE_NEEDS_HARD]}

    # Saving under an existing node's name is refused before anything is written.
    response = _save(monkeypatch, pending, name="C", e_needs_h=["A"], e_supp_h=["B"])

    assert response.message.startswith("Error:")
    assert ("A", "B", EDGE_NEEDS_HARD) in _edges(manager)


def test_later_saves_of_the_same_node_leave_the_relationships_alone(monkeypatch, manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    manager.add_node(_node("Middle"))
    manager.sync_edges("Middle", ["A"], [], ["B"], [], [])
    pending = {"replaces": ["A", "B", EDGE_NEEDS_HARD]}
    # The bridge was already saved once, so Middle is an existing node now.
    _save(monkeypatch, pending, original_name="Middle", name="Middle",
          e_needs_h=["A"], e_supp_h=["B"])
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    _save(monkeypatch, pending, original_name="Middle", name="Middle",
          e_needs_h=["A"], e_supp_h=["B"])

    assert ("A", "B", EDGE_NEEDS_HARD) in _edges(manager)


# --- The editor -----------------------------------------------------------

def _populate(monkeypatch, trigger, **values):
    fire(trigger)
    return call(_registered()["populate_editor"], **values)


def test_create_fills_the_editor_in_with_the_bridge(monkeypatch, manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    out = _populate(monkeypatch, "btn-bridge-create", bridge_clicks=1,
                    bridge_ends={"start": "A", "end": "B"}, bridge_kind="hard")

    needs_hard, needs_soft, supports_hard, supports_soft, helps = out[13:18]
    assert (needs_hard, needs_soft, supports_hard, supports_soft, helps) == (
        ["A"], [], ["B"], [], [])
    assert out[0] == ""  # a new node, with no name yet
    assert out[26] is None  # no original name: saving creates it
    assert out[33]["e_needs_h"] == ["A"] and out[33]["e_supp_h"] == ["B"]
    assert out[43] == {"start": "A", "end": "B", "kind": "hard",
                       "replaces": ["A", "B", EDGE_NEEDS_HARD]}


def test_a_synergy_bridge_fills_the_helps_field(monkeypatch, manager):
    out = _populate(monkeypatch, "btn-bridge-create", bridge_clicks=1,
                    bridge_ends={"start": "A", "end": "B"}, bridge_kind="synergy")

    assert out[17] == ["A", "B"]
    assert out[43]["replaces"] is None


def test_a_bridge_that_no_longer_holds_leaves_the_editor_alone(monkeypatch, manager):
    manager.add_edge("B", "A", EDGE_NEEDS_HARD)

    out = _populate(monkeypatch, "btn-bridge-create", bridge_clicks=1,
                    bridge_ends={"start": "A", "end": "B"}, bridge_kind="hard")

    assert out[0] is dash.no_update
    assert out[43] is dash.no_update


def test_unsaved_edits_ask_before_the_bridge_replaces_them(monkeypatch, manager):
    out = _populate(monkeypatch, "btn-bridge-create", bridge_clicks=1,
                    bridge_ends={"start": "A", "end": "B"}, bridge_kind="hard",
                    ed_style={"transform": "translateX(0px)"},
                    pristine_snapshot=NEW_NODE_SNAPSHOT, name="Half-typed")

    assert out[31] == "__bridge__"  # pending-navigation-store
    assert out[32] is True  # modal-unsaved-changes
    assert out[0] is dash.no_update


def test_the_unsaved_dialog_continues_into_the_bridge(monkeypatch, manager):
    out = _populate(monkeypatch, "btn-unsaved-discard", discard_clicks=1,
                    pending_nav="__bridge__",
                    bridge_ends={"start": "A", "end": "B"}, bridge_kind="soft")

    assert out[16] == ["B"] and out[14] == ["A"]
    assert out[43]["kind"] == "soft"


def test_loading_any_node_clears_the_pending_bridge(monkeypatch, manager):
    out = _populate(monkeypatch, "edit-trigger-input", edit_trigger_val="A|1")

    assert out[0] == "A"
    assert out[43] is None


def test_a_new_node_clears_the_pending_bridge(monkeypatch, manager):
    out = _populate(monkeypatch, "btn-editor-new", editor_new_clicks=1)

    assert out[43] is None


def test_every_hard_and_soft_edge_type_has_a_bridge_kind():
    assert {EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS} == set(
        __import__("importlib").import_module("skilltree.store.commands").BRIDGE_KINDS.values())
