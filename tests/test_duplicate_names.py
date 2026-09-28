"""A save may not claim another node's name.

Saving a new node, or renaming one, under a name another node already uses
used to update that other node in place. The form's fields, links, aliases
and (usually empty) relationships replaced the existing node's, silently.
"""

import dash
import pytest

import callbacks
from editor_forms import call
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD
from node_commands import conflicting_node_name


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    manager = GraphManager()
    manager.add_node(_node("Sleep", description="keep me"))
    manager.add_node(_node("Rest"))
    manager.add_edge("Rest", "Sleep", EDGE_NEEDS_HARD)
    manager.set_aliases("Sleep", ["Shuteye"])
    return manager


class TestConflictRule:
    def test_new_node_with_an_existing_name(self, manager):
        assert conflicting_node_name(manager, "Sleep", None) == "Sleep"

    def test_new_node_differing_only_in_case(self, manager):
        assert conflicting_node_name(manager, "sleep", "") == "Sleep"

    def test_rename_onto_another_node(self, manager):
        assert conflicting_node_name(manager, "Sleep", "Rest") == "Sleep"

    def test_keeping_the_name_never_conflicts(self, manager):
        # Even beside a case-variant duplicate an older database may hold.
        # add_node refuses one now, so write it the way older versions did.
        import database
        with database.transaction() as conn:
            conn.execute("INSERT INTO Nodes (name, type, description, value, time_o, "
                         "time_m, time_p, interest, difficulty, context, status) "
                         "SELECT 'sleep', type, description, value, time_o, time_m, "
                         "time_p, interest, difficulty, context, status FROM Nodes "
                         "WHERE name = 'Sleep'")
        assert conflicting_node_name(manager, "Sleep", "Sleep") is None

    def test_case_only_rename_of_the_node_itself(self, manager):
        assert conflicting_node_name(manager, "SLEEP", "Sleep") is None

    def test_a_fresh_name(self, manager):
        assert conflicting_node_name(manager, "Nap", None) is None
        assert conflicting_node_name(manager, "Nap", "Rest") is None

    def test_dormant_nodes_hold_their_names(self, manager):
        manager.add_node(_node("Hibernate", dormant=1))
        assert conflicting_node_name(manager, "Hibernate", None) == "Hibernate"


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


def _save(monkeypatch, trigger, **form):
    fn = _core_engine()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {trigger})
    values = dict(n_type="Learn", desc="replacement", context="Mind",
                  status_done=[], val=5, interest=5, diff=5,
                  time_o=1, time_m=2, time_p=4, time_unit="hours",
                  e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
                  link_values=[], link_ids=[], aliases=[],
                  ed_style={"transform": "translateX(0px)"})
    values.update(form)
    return callbacks.CoreResponse(*call(fn, **values))


@pytest.mark.parametrize("trigger", ["btn-save", "btn-save-close"])
def test_new_node_cannot_overwrite_an_existing_one(monkeypatch, manager, trigger):
    response = _save(monkeypatch, trigger, name="Sleep", original_name=None)

    assert response.message.startswith("Error:")
    assert "'Sleep' already exists" in response.message
    # The form stays open, even for Save & Close, so nothing typed is lost.
    assert response.editor_style["transform"] == "translateX(0px)"
    sleep = manager.get_node("Sleep")
    assert sleep.description == "keep me"
    assert manager.get_edges() == [
        {"source": "Rest", "target": "Sleep", "type": EDGE_NEEDS_HARD}]
    assert manager.get_aliases("Sleep") == ["Shuteye"]


def test_rename_cannot_take_another_nodes_name(monkeypatch, manager):
    response = _save(monkeypatch, "btn-save", name="sleep", original_name="Rest")

    assert "'Sleep' already exists" in response.message
    assert manager.get_node("Rest") is not None
    assert manager.get_node("Sleep").description == "keep me"
