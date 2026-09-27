"""Editor follow-ups act on a committed save, never on the Save click.

populate_editor (the unsaved-changes dialog moving on to the next node) and
sync_original_name_after_save (adopting the saved name) both fired on the
click itself, in parallel with core_engine's save. A refused save therefore
still swapped the form out and lost its edits. And because the sync polled for
the form's name, a new node refused for taking an existing node's name made
the editor adopt that node, so the next Save overwrote it.

core_engine now reports a committed save in editor-save-result-store.
"""
import inspect

import dash
import pytest

import callbacks
from graph_manager import GraphManager
from models import Node


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
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


def _save(monkeypatch, trigger, **form):
    core_engine = _registered()["core_engine"]
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    kwargs = dict.fromkeys(inspect.signature(core_engine).parameters)
    kwargs.update(n_type="Learn", desc="", context="Mind", status_done=[],
                  val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit="hours", link_values=[], link_ids=[], alias_values=[],
                  ed_style={"transform": "translateX(0px)"})
    kwargs.update(form)
    return callbacks.CoreResponse(*core_engine(**kwargs))


@pytest.fixture
def manager():
    manager = GraphManager()
    manager.add_node(_node("Sleep", description="keep me"))
    return manager


def test_a_committed_save_is_reported(monkeypatch, manager):
    response = _save(monkeypatch, "btn-unsaved-save", name="Nap", original_name=None)

    assert response.save_result["name"] == "Nap"
    assert response.save_result["via"] == "btn-unsaved-save"
    assert manager.get_node("Nap") is not None


def test_a_refused_save_is_not_reported(monkeypatch, manager):
    response = _save(monkeypatch, "btn-unsaved-save", name="Sleep", original_name=None)

    assert response.message.startswith("Error:")
    assert response.save_result is dash.no_update


def test_the_unsaved_dialog_moves_on_only_after_its_save(monkeypatch, manager):
    manager.add_node(_node("Next"))
    populate = _registered()["populate_editor"]
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "editor-save-result-store")
    params = list(inspect.signature(populate).parameters)

    def call(save_result):
        kwargs = dict.fromkeys(params)
        kwargs.update(save_result=save_result, pending_nav="Next")
        return populate(**kwargs)

    # An ordinary Save is not the dialog's: nothing moves.
    unchanged = call({"name": "Nap", "via": "btn-save", "ts": 1})
    assert all(value is dash.no_update for value in unchanged)

    # The dialog's own save committed: go to the node the user clicked.
    moved = call({"name": "Nap", "via": "btn-unsaved-save", "ts": 2})
    assert moved[0] == "Next"


def test_the_editor_adopts_only_a_name_that_was_saved(manager):
    sync = _registered()["sync_original_name_after_save"]
    params = list(inspect.signature(sync).parameters)

    def call(save_result):
        kwargs = dict.fromkeys(params)
        kwargs.update(save_result=save_result, cur_name="Sleep")
        return sync(**kwargs)

    # No committed save (the refused duplicate): the editor stays a new node,
    # even though a node called "Sleep" exists.
    assert call(None) == (dash.no_update,) * 4
    # The unsaved dialog's save moves on to another node instead.
    assert call({"name": "Sleep", "via": "btn-unsaved-save", "ts": 1}) == (dash.no_update,) * 4

    original, name, _aliases, snapshot = call({"name": "Sleep", "via": "btn-save", "ts": 2})
    assert original == "Sleep" and name == "Sleep" and snapshot
