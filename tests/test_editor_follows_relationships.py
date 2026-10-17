"""The editor's relationship pickers follow links changed elsewhere.

The pickers were filled only when the editor loaded a node, and Save rewrote
every link the node has from them. A link removed, reversed or made Soft from
the link menu while the editor was open came back on the next Save, even a
Save that only changed the description.
"""
import dash

from skilltree.services import AppServices
import pytest

from skilltree.engine import callbacks
from skilltree.features.editor.form import (
    NEW_NODE_SNAPSHOT, RELATIONSHIP_FIELDS, build_editor_snapshot,
    follow_relationships, merge_relationships, resolve_relationship_intent,
)
from editor_forms import call
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Node, STATUS_BLOCKED, STATUS_OPEN
from skilltree.store.commands import change_link
from skilltree.store.events import EventManager


def _node(name):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status=STATUS_OPEN, context="Mind")


@pytest.fixture(scope="module")
def handlers():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app, AppServices())
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


@pytest.fixture
def manager():
    """Basics unlocks Advanced and Applied. Extra stands alone."""
    manager = GraphManager()
    for name in ("Basics", "Advanced", "Applied", "Extra"):
        manager.add_node(_node(name))
    manager.add_edge("Basics", "Advanced", EDGE_NEEDS_HARD)
    manager.add_edge("Basics", "Applied", EDGE_NEEDS_HARD)
    return manager


def _loaded(manager, name):
    """The editor as populate_editor leaves it for ``name``: form and snapshot."""
    snapshot = build_editor_snapshot(manager, EventManager(), name)
    form = {key: list(snapshot[key]) for key in RELATIONSHIP_FIELDS}
    return form, snapshot


def _save(handlers, monkeypatch, **state):
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-save")
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {"btn-save"})
    values = dict(n_type="Learn", desc="edited", context="Mind", status_done=[],
                  val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit="hours", link_values=[], link_ids=[], aliases=[],
                  ed_style={"transform": "translateX(0px)"})
    values.update(state)
    return callbacks.CoreResponse(*call(handlers["core_engine"], **values))


def _save_loaded(handlers, monkeypatch, name, snapshot, form):
    return _save(handlers, monkeypatch, name=name, original_name=name,
                 pristine_snapshot=snapshot, **form)


def _links(manager):
    return sorted((e["source"], e["target"], e["type"]) for e in manager.get_edges())


# --- Save writes the user's edits on top of what is stored -------------------------

@pytest.mark.parametrize("action, expected", [
    ("remove", [("Basics", "Applied", EDGE_NEEDS_HARD)]),
    ("soft", [("Basics", "Advanced", EDGE_NEEDS_SOFT),
              ("Basics", "Applied", EDGE_NEEDS_HARD)]),
    ("reverse", [("Advanced", "Basics", EDGE_NEEDS_HARD),
                 ("Basics", "Applied", EDGE_NEEDS_HARD)]),
])
def test_a_save_keeps_a_link_menu_change(handlers, monkeypatch, manager, action, expected):
    form, snapshot = _loaded(manager, "Basics")
    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, action)

    response = _save_loaded(handlers, monkeypatch, "Basics", snapshot, form)

    assert response.save_result["name"] == "Basics"
    assert manager.get_node("Basics").description == "edited"
    assert _links(manager) == expected


def test_a_save_after_removing_a_hard_link_leaves_its_target_unblocked(
        handlers, monkeypatch, manager):
    form, snapshot = _loaded(manager, "Basics")
    assert manager.get_node("Advanced").status == STATUS_BLOCKED
    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, "remove")

    _save_loaded(handlers, monkeypatch, "Basics", snapshot, form)

    assert manager.get_node("Advanced").status == STATUS_OPEN


def test_the_users_own_edits_land_on_top_of_an_outside_change(handlers, monkeypatch, manager):
    form, snapshot = _loaded(manager, "Basics")
    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, "remove")
    form["e_supp_h"].remove("Applied")
    form["e_supp_s"].append("Extra")

    _save_loaded(handlers, monkeypatch, "Basics", snapshot, form)

    assert _links(manager) == [("Basics", "Extra", EDGE_NEEDS_SOFT)]


def test_a_new_node_saves_the_links_it_was_given(handlers, monkeypatch, manager):
    """A new subtask's form arrives with its parent already picked."""
    _save(handlers, monkeypatch, name="Child", original_name=None,
          pristine_snapshot={**NEW_NODE_SNAPSHOT, "e_supp_h": ["Extra"]},
          e_supp_h=["Extra"])

    assert ("Child", "Extra", EDGE_NEEDS_HARD) in _links(manager)


# --- The pickers follow ---------------------------------------------------------------

def test_an_untouched_picker_follows_and_an_edited_one_keeps_its_edits(manager, services):
    form, snapshot = _loaded(manager, "Basics")
    form["e_supp_s"] = ["Extra"]
    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, "soft")
    stored = build_editor_snapshot(manager, services.events, "Basics")

    values, followed = follow_relationships(stored, form, snapshot)

    assert values == {"e_supp_h": ["Applied"], "e_supp_s": ["Extra", "Advanced"]}
    assert followed == {"e_supp_h": ["Applied"], "e_supp_s": ["Advanced"]}


def test_nothing_follows_when_the_snapshot_already_matches(manager, services):
    form, snapshot = _loaded(manager, "Basics")
    stored = build_editor_snapshot(manager, services.events, "Basics")
    assert follow_relationships(stored, form, snapshot) == ({}, {})
    # A snapshot holding no lists gives nothing to judge by.
    assert follow_relationships(stored, form, {"name": "Basics"}) == ({}, {})


def test_the_follow_callback_reports_what_changed(handlers, manager):
    follow = handlers["follow_editor_relationships"]
    form, snapshot = _loaded(manager, "Basics")
    assert call(follow, snapshot=snapshot, original_name="Basics", **form) is dash.no_update

    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, "remove")
    result = call(follow, snapshot=snapshot, original_name="Basics", **form)

    assert result["name"] == "Basics"
    assert result["values"] == {"e_supp_h": ["Applied"]}
    assert result["snapshot"] == {"e_supp_h": ["Applied"]}
    # What it worked from, so the browser can drop it if the editor moved on.
    assert result["seen"] == {"e_supp_h": {"snapshot": ["Advanced", "Applied"],
                                           "form": ["Advanced", "Applied"]}}


def test_the_follow_callback_leaves_another_nodes_form_alone(handlers, manager):
    """The snapshot is still the previous node's while the next one loads."""
    follow = handlers["follow_editor_relationships"]
    form, snapshot = _loaded(manager, "Basics")
    change_link(manager, "Basics", "Advanced", EDGE_NEEDS_HARD, "remove")
    assert call(follow, snapshot=snapshot, original_name="Advanced", **form) is dash.no_update


# --- The merge ------------------------------------------------------------------------

@pytest.mark.parametrize("loaded, edited, stored, expected", [
    (["A"], ["A"], ["A"], ["A"]),            # nobody changed it
    (["A"], ["A"], [], []),                  # removed elsewhere
    (["A"], [], ["A"], []),                  # removed by the user
    ([], ["A"], [], ["A"]),                  # added by the user
    ([], [], ["A"], ["A"]),                  # added elsewhere
    (["A"], [], [], []),                     # removed by both
    ([], ["A"], ["A"], ["A"]),               # added by both
    (["B", "A"], ["B", "A", "C"], ["A", "D"], ["A", "C", "D"]),
])
def test_merge_relationships(loaded, edited, stored, expected):
    assert merge_relationships(loaded, edited, stored) == expected


def test_a_list_the_snapshot_lacks_is_the_forms():
    form = {key: [] for key in RELATIONSHIP_FIELDS}
    form["e_supp_h"] = ["A"]
    merged = resolve_relationship_intent({"e_supp_h": ["B"]}, form, {"name": "N"})
    assert merged["e_supp_h"] == ["A"]
