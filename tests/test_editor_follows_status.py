"""The editor's Done switch follows a status changed elsewhere.

The switch was written only when the editor loaded a node. Toggling Done from
the node menu, or a cascade re-blocking a Done node, left it showing the old
status, and the next Save wrote that back: a node marked Done from the menu
was quietly reopened by saving an unrelated edit to it.
"""
import inspect

import dash
import pytest

import callbacks
from callback_helpers import follow_done_status
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, Node, STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _core_engine():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    target = next(k for k in app.callback_map
                  if k.startswith("..elements-pending-store.data"))
    fn = app.callback_map[target]["callback"]
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _run(monkeypatch, trigger, **state):
    core_engine = _core_engine()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    kwargs = dict.fromkeys(inspect.signature(core_engine).parameters)
    kwargs.update(n_type="Learn", desc="", context="Mind", status_done=[],
                  val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit="hours", link_values=[], link_ids=[], alias_values=[],
                  ed_style={"transform": "translateX(0px)"})
    kwargs.update(state)
    return callbacks.CoreResponse(*core_engine(**kwargs))


def _editing(name, done, **snapshot):
    """The editor's state for ``name`` as loaded, untouched."""
    switch = [STATUS_DONE] if done else []
    return dict(original_name=name, name=name, status_done=switch,
                pristine_snapshot={"name": name, "desc": "", "status_done": switch,
                                   **snapshot})


@pytest.fixture
def manager():
    """Basics unlocks Advanced; nothing is Done yet."""
    manager = GraphManager()
    manager.add_node(_node("Basics"))
    manager.add_node(_node("Advanced"))
    manager.add_edge("Basics", "Advanced", EDGE_NEEDS_HARD)
    return manager


def _mark_done(manager, *names):
    for name in names:
        node = manager.get_node(name)
        node.status = STATUS_DONE
        manager.update_node(node)


def test_done_from_the_menu_shows_in_the_open_editor(monkeypatch, manager):
    response = _run(monkeypatch, "toggle-done-trigger-input",
                    toggle_done_trigger_data='["Basics"]|1',
                    **_editing("Basics", done=False))

    assert manager.get_node("Basics").status == STATUS_DONE
    assert response.editor_done == [STATUS_DONE]
    assert response.editor_snapshot == {"name": "Basics", "desc": "",
                                        "status_done": [STATUS_DONE]}


def test_a_save_after_that_keeps_it_done(monkeypatch, manager):
    response = _run(monkeypatch, "toggle-done-trigger-input",
                    toggle_done_trigger_data='["Basics"]|1',
                    **_editing("Basics", done=False))

    _run(monkeypatch, "btn-save", name="Basics", original_name="Basics",
         desc="an unrelated edit", status_done=response.editor_done,
         e_supp_h=["Advanced"])

    assert manager.get_node("Basics").status == STATUS_DONE
    assert manager.get_node("Basics").description == "an unrelated edit"


def test_a_cascade_re_blocking_it_shows_too(monkeypatch, manager):
    _mark_done(manager, "Basics", "Advanced")

    response = _run(monkeypatch, "btn-undo-done-confirm",
                    pending_undo_done=["Basics"], **_editing("Advanced", done=True))

    assert manager.get_node("Advanced").status == STATUS_BLOCKED
    assert response.editor_done == []
    assert response.editor_snapshot["status_done"] == []


def test_the_users_own_unsaved_flip_stays(monkeypatch, manager):
    state = _editing("Basics", done=False)
    state["status_done"] = [STATUS_DONE]      # flipped on, not saved yet

    response = _run(monkeypatch, "toggle-done-trigger-input",
                    toggle_done_trigger_data='["Basics"]|1', **state)

    assert response.editor_done is dash.no_update
    assert response.editor_snapshot["status_done"] == [STATUS_DONE]


def test_nothing_changes_when_the_editor_already_agrees(monkeypatch, manager):
    response = _run(monkeypatch, "toggle-done-trigger-input",
                    toggle_done_trigger_data='["Advanced"]|1',
                    **_editing("Basics", done=False))

    assert (response.editor_done, response.editor_snapshot) == (
        dash.no_update, dash.no_update)


@pytest.mark.parametrize("trigger", ["btn-save", "btn-save-close", "btn-unsaved-save"])
def test_an_editor_save_keeps_its_own_form(monkeypatch, manager, trigger):
    """sync_original_name_after_save snapshots the form after a save."""
    state = _editing("Basics", done=False)
    state["status_done"] = [STATUS_DONE]

    response = _run(monkeypatch, trigger, e_supp_h=["Advanced"], **state)

    assert manager.get_node("Basics").status == STATUS_DONE
    assert (response.editor_done, response.editor_snapshot) == (
        dash.no_update, dash.no_update)


def test_loading_another_node_leaves_the_switch_to_the_loader(monkeypatch, manager):
    """Picking a node runs populate_editor alongside core_engine, and
    core_engine's editor state is still the previous node's: an answer from it
    could land on the node being loaded."""
    _mark_done(manager, "Basics")
    stale = _editing("Basics", done=False)

    response = _run(monkeypatch, "search-node", search_val="Advanced", **stale)

    assert (response.editor_done, response.editor_snapshot) == (
        dash.no_update, dash.no_update)


@pytest.mark.parametrize("node, snapshot", [
    (None, {"status_done": []}),                              # deleted
    (_node("Basics", status=STATUS_DONE), None),              # nothing loaded
    (_node("Basics", status=STATUS_DONE), {"name": "Basics"}),  # no status kept
])
def test_follow_done_status_leaves_what_it_cannot_judge(node, snapshot):
    assert follow_done_status(node, [], snapshot) == (dash.no_update, dash.no_update)
