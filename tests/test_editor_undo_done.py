"""Un-marking Done in the editor asks first, as the node menu does.

Reopening a node re-blocks every Done node after it. The node menu's toggles
asked before doing that, but the editor's Done switch and Save did it without
a word. Now Save keeps the node Done, saves every other edit, and opens the
same confirmation: Un-mark reopens it, Cancel leaves it Done.
"""
import dash
import pytest

import callbacks
from callback_helpers import NEW_EVENT_OPTION
from editor_forms import call
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, Node, STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    fields.update(overrides)
    return Node(**fields)


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


def _save(monkeypatch, name, trigger="btn-save", **form):
    form.setdefault("original_name", name)
    form.setdefault("e_supp_h", ["Advanced"] if name == "Basics" else [])
    return _run(monkeypatch, trigger, name=name, **form)


@pytest.fixture
def manager():
    """Basics unlocks Advanced, and both are Done."""
    manager = GraphManager()
    manager.add_node(_node("Basics"))
    manager.add_node(_node("Advanced"))
    manager.add_edge("Basics", "Advanced", EDGE_NEEDS_HARD)
    for name in ("Basics", "Advanced"):
        node = manager.get_node(name)
        node.status = STATUS_DONE
        manager.update_node(node)
    return manager


def _statuses(manager):
    return {n.name: n.status for n in manager.get_all_nodes()}


@pytest.mark.parametrize("trigger", ["btn-save", "btn-save-close", "btn-unsaved-save"])
def test_saving_it_un_marked_asks_and_keeps_it_done(monkeypatch, manager, trigger):
    response = _save(monkeypatch, "Basics", trigger, desc="new notes", status_done=[])

    assert response.undo_open is True
    assert response.undo_pending == ["Basics"]
    assert _statuses(manager) == {"Basics": STATUS_DONE, "Advanced": STATUS_DONE}
    # Every other edit was saved, and the save is reported as committed.
    assert manager.get_node("Basics").description == "new notes"
    assert response.save_result["name"] == "Basics"


def test_un_mark_then_reopens_it_and_re_blocks_what_follows(monkeypatch, manager):
    _save(monkeypatch, "Basics", status_done=[])

    _run(monkeypatch, "btn-undo-done-confirm", pending_undo_done=["Basics"])

    assert _statuses(manager) == {"Basics": STATUS_OPEN, "Advanced": STATUS_BLOCKED}


def test_nothing_to_re_block_means_nothing_to_ask(monkeypatch, manager):
    response = _save(monkeypatch, "Advanced", status_done=[],
                     e_needs_h=["Basics"])

    assert response.undo_open is False
    assert _statuses(manager)["Advanced"] == STATUS_OPEN


def test_reopening_without_asking_is_recorded_like_any_reopen(monkeypatch, manager):
    _save(monkeypatch, "Advanced", status_done=[], e_needs_h=["Basics"])

    assert manager.get_node("Advanced").done_date is None
    history = [e["event_type"] for e in manager.get_node_lifecycle_events("Advanced")]
    assert history[-1] == "reopened"


def test_dropping_the_requirement_in_the_same_save_asks_nothing(monkeypatch, manager):
    """Whether to ask is decided from the relationships as saved."""
    response = _save(monkeypatch, "Basics", status_done=[], e_supp_h=[])

    assert response.undo_open is False
    assert _statuses(manager) == {"Basics": STATUS_OPEN, "Advanced": STATUS_DONE}


def test_saving_it_still_done_asks_nothing(monkeypatch, manager):
    response = _save(monkeypatch, "Basics", desc="more", status_done=[STATUS_DONE])

    assert response.undo_open is False
    assert _statuses(manager) == {"Basics": STATUS_DONE, "Advanced": STATUS_DONE}


def test_a_rename_asks_about_the_new_name(monkeypatch, manager):
    response = _save(monkeypatch, "Fundamentals", original_name="Basics",
                     status_done=[], e_supp_h=["Advanced"])

    assert response.undo_pending == ["Fundamentals"]
    assert manager.get_node("Fundamentals").status == STATUS_DONE


def test_putting_it_to_sleep_asks_too(monkeypatch, manager):
    """Done is hidden while Dormant is on, so going dormant un-marks it."""
    response = _save(monkeypatch, "Basics", status_done=[STATUS_DONE],
                     dormancy={"dormant": True, "event": NEW_EVENT_OPTION,
                               "event_name": "Later On"})

    assert response.undo_open is True
    assert manager.get_node("Basics").dormant
    assert _statuses(manager)["Advanced"] == STATUS_DONE


def test_cancel_puts_the_editor_switch_back(monkeypatch):
    close = _registered()["close_undo_done_modal"]
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-undo-done-cancel")
    snapshot = {"name": "Basics", "status_done": [], "desc": "new notes"}

    is_open, pending, switch, kept = close(1, None, ["Basics"], "Basics", snapshot)

    assert (is_open, pending) == (False, None)
    assert switch == [STATUS_DONE]
    assert kept == {**snapshot, "status_done": [STATUS_DONE]}


@pytest.mark.parametrize("trigger, editing", [
    ("btn-undo-done-cancel", "Something Else"),   # the editor moved on
    ("btn-undo-done-confirm", "Basics"),          # it really is reopened
])
def test_the_switch_is_left_alone_otherwise(monkeypatch, trigger, editing):
    close = _registered()["close_undo_done_modal"]
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)

    result = close(1, 1, ["Basics"], editing, {"status_done": []})

    assert result == (False, None, dash.no_update, dash.no_update)
