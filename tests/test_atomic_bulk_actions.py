"""Bulk actions from the node menu are all or nothing.

Each node used to be updated or deleted in its own transaction, so a failure
part-way through a multi-node Done toggle or group delete left some of the
selection changed and the rest not.
"""
import inspect

import dash
import pytest

import callbacks
from graph_manager import GraphManager
from models import Node, STATUS_OPEN
from node_commands import handle_group_delete


def _node(name):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status=STATUS_OPEN, context="Mind")


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("A", "B", "C"):
        manager.add_node(_node(name))
    return manager


def _fail_on(monkeypatch, method, failing_name):
    original = getattr(GraphManager, method)

    def flaky(self, arg, *args, **kwargs):
        name = arg if isinstance(arg, str) else arg.name
        if name == failing_name:
            raise RuntimeError("disk full")
        return original(self, arg, *args, **kwargs)
    monkeypatch.setattr(GraphManager, method, flaky)


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


def test_multi_node_done_toggle_rolls_back_as_one(monkeypatch, manager):
    core_engine = _core_engine()
    trigger = "toggle-done-trigger-input"
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    _fail_on(monkeypatch, "update_node", "C")
    kwargs = dict.fromkeys(inspect.signature(core_engine).parameters)
    kwargs["toggle_done_trigger_data"] = '["A", "B", "C"]|1|1'

    response = callbacks.CoreResponse(*core_engine(**kwargs))

    assert response.message.startswith("Error")
    assert [manager.get_node(n).status for n in "ABC"] == [STATUS_OPEN] * 3


def test_group_delete_rolls_back_as_one(monkeypatch, manager):
    _fail_on(monkeypatch, "delete_node", "C")

    with pytest.raises(RuntimeError):
        handle_group_delete(manager, '["A", "B", "C"]|1')

    assert all(manager.get_node(n) is not None for n in "ABC")
