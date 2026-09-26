"""A Done node that stops being Done drops its completion date and records a
reopen, whichever path un-marks it: the cascade or the startup repair."""
import database
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD, STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _set_status(mgr, name, status):
    node = mgr.get_node(name)
    node.status = status
    mgr.update_node(node)


def _event_types(mgr, name):
    return [event["event_type"] for event in mgr.get_node_lifecycle_events(name)]


def _completed_chain(mgr):
    """Prereq --Needs_Hard--> Dependent, both Done through the normal path."""
    mgr.add_node(_node("Prereq"))
    mgr.add_node(_node("Dependent"))
    mgr.add_edge("Prereq", "Dependent", EDGE_NEEDS_HARD)
    _set_status(mgr, "Prereq", STATUS_DONE)
    _set_status(mgr, "Dependent", STATUS_DONE)
    assert mgr.get_node("Dependent").done_date is not None


def test_cascade_reopen_clears_the_date_and_records_history():
    mgr = GraphManager()
    _completed_chain(mgr)

    _set_status(mgr, "Prereq", STATUS_OPEN)

    dependent = mgr.get_node("Dependent")
    assert dependent.status == STATUS_BLOCKED
    assert dependent.done_date is None
    assert _event_types(mgr, "Dependent") == ["completed", "reopened"]


def test_startup_repair_clears_the_date_and_records_history():
    mgr = GraphManager()
    _completed_chain(mgr)
    # Drift the cascade never saw: the prerequisite reopened outside it.
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Open', done_date=NULL WHERE name='Prereq'")
        conn.commit()

    assert mgr.recompute_all_statuses() == 1

    dependent = mgr.get_node("Dependent")
    assert dependent.status == STATUS_BLOCKED
    assert dependent.done_date is None
    assert _event_types(mgr, "Dependent") == ["completed", "reopened"]


def test_repair_that_only_unblocks_records_no_reopen():
    mgr = GraphManager()
    mgr.add_node(_node("Prereq"))
    mgr.add_node(_node("Dependent"))
    mgr.add_edge("Prereq", "Dependent", EDGE_NEEDS_HARD)
    assert mgr.get_node("Dependent").status == STATUS_BLOCKED
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Done' WHERE name='Prereq'")
        conn.commit()

    assert mgr.recompute_all_statuses() == 1

    assert mgr.get_node("Dependent").status == STATUS_OPEN
    assert _event_types(mgr, "Dependent") == []
