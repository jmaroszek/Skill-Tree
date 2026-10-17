"""An editor save that would reopen Done nodes asks first.

A Done node stays Done only while all of its Hard prerequisites are. Giving
one an unfinished Hard prerequisite in the node editor (or through a Hard
bridge, which saves there) used to reopen it, and the Done nodes after it,
without a word. The save now rolls back and asks; Save finishes it.
"""
import dash
import pytest

from skilltree.engine import callbacks
from editor_forms import call
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_NEEDS_HARD, Node, STATUS_DONE, STATUS_OPEN
from skilltree.services import AppServices


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _registered():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app, AppServices())
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found.setdefault(getattr(fn, "__name__", None), fn)
    return found


def _run(monkeypatch, trigger, **state):
    core_engine = _registered()["core_engine"]
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    values = dict(n_type="Learn", desc="", context="Mind", status_done=[],
                  val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit="hours", link_values=[], link_ids=[], aliases=[],
                  ed_style={"transform": "translateX(0px)"})
    values.update(state)
    return callbacks.CoreResponse(*call(core_engine, **values))


@pytest.fixture
def manager():
    """Basics unlocks Advanced, both Done. Extra is Open."""
    manager = GraphManager()
    for name in ("Basics", "Advanced", "Extra"):
        manager.add_node(_node(name))
    manager.add_edge("Basics", "Advanced", EDGE_NEEDS_HARD)
    for name in ("Basics", "Advanced"):
        node = manager.get_node(name)
        node.status = STATUS_DONE
        manager.update_node(node)
    return manager


def _statuses(manager):
    return {n.name: n.status for n in manager.get_all_nodes()}


def _edges(manager):
    return {(e["source"], e["target"], e["type"]) for e in manager.get_edges()}


def _give_basics_a_prerequisite(monkeypatch, trigger="btn-save", **state):
    """Extra's editor, saved with Basics under Supports > Hard."""
    return _run(monkeypatch, trigger, name="Extra", original_name="Extra",
                e_supp_h=["Basics"], **state)


@pytest.mark.parametrize("trigger", ["btn-save", "btn-unsaved-save"])
def test_a_save_that_reopens_done_nodes_asks_and_saves_nothing(monkeypatch, manager, trigger):
    response = _give_basics_a_prerequisite(monkeypatch, trigger, desc="new notes")

    assert response.reopen_open is True
    assert response.reopen_pending == {"via": trigger}
    assert "reopens 2 Done nodes" in str(response.reopen_body)
    # The editor stays open, even for the dialog's Save, and nothing was saved.
    assert response.editor_style["transform"] == "translateX(0px)"
    assert response.save_result is dash.no_update
    assert _edges(manager) == {("Basics", "Advanced", EDGE_NEEDS_HARD)}
    assert manager.get_node("Extra").description == ""
    assert _statuses(manager)["Basics"] == STATUS_DONE


def test_save_in_the_confirmation_finishes_the_save(monkeypatch, manager):
    response = _give_basics_a_prerequisite(
        monkeypatch, "btn-editor-reopen-confirm",
        btn_editor_reopen_confirm=1, editor_reopen_pending={"via": "btn-unsaved-save"})

    assert response.save_result["via"] == "btn-unsaved-save"
    assert ("Extra", "Basics", EDGE_NEEDS_HARD) in _edges(manager)
    assert _statuses(manager) == {"Basics": "Blocked", "Advanced": "Blocked",
                                  "Extra": STATUS_OPEN}


def test_a_confirmation_with_no_held_save_does_nothing(monkeypatch, manager):
    response = _give_basics_a_prerequisite(
        monkeypatch, "btn-editor-reopen-confirm", btn_editor_reopen_confirm=1,
        editor_reopen_pending=None)

    assert response == callbacks.CoreResponse()
    assert _statuses(manager)["Basics"] == STATUS_DONE


def test_saves_that_reopen_nothing_go_straight_through(monkeypatch, manager):
    # A Done prerequisite leaves a Done node Done.
    extra = manager.get_node("Extra")
    extra.status = STATUS_DONE
    manager.update_node(extra)

    response = _give_basics_a_prerequisite(monkeypatch, status_done=[STATUS_DONE])

    assert response.reopen_open is dash.no_update
    assert ("Extra", "Basics", EDGE_NEEDS_HARD) in _edges(manager)
    assert _statuses(manager)["Basics"] == STATUS_DONE


def test_un_marking_a_node_yourself_is_not_asked_about_twice(monkeypatch, manager):
    # Advanced has nothing after it, so un-marking it just reopens it.
    response = _run(monkeypatch, "btn-save", name="Advanced", original_name="Advanced",
                    e_needs_h=["Basics"], status_done=[])

    assert response.reopen_open is dash.no_update
    assert _statuses(manager)["Advanced"] == STATUS_OPEN


def test_renaming_a_done_node_is_not_a_reopen(monkeypatch, manager):
    response = _run(monkeypatch, "btn-save", name="Advanced Topics",
                    original_name="Advanced", e_needs_h=["Basics"],
                    status_done=[STATUS_DONE])

    assert response.reopen_open is dash.no_update
    assert _statuses(manager)["Advanced Topics"] == STATUS_DONE
