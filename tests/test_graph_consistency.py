"""Derived state must agree with a fresh read after every mutation path."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

import pytest

import database
from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event, EDGE_NEEDS_HARD as HARD, EDGE_NEEDS_SOFT as SOFT
from test_atomic_saves import graph, node, save, sync


def scores(manager):
    ConfigManager.set_show_scoring_perf(False)
    return {n.name: n.priority_score for n in
            manager.calculate_priority_scores(manager.get_all_nodes())}


def test_relationship_only_save_invalidates_warm_memo():
    m = graph("A", "B")
    before = scores(m)
    save(m, "A", e_supp_s=["B"])
    assert scores(m) == scores(GraphManager())
    assert scores(m)["A"] > before["A"]
    save(m, "A")  # Removing the last edge must invalidate too.
    assert scores(m) == before


def test_removing_outgoing_prerequisite_unblocks_former_dependent():
    m = graph("A", "B")
    m.add_edge("A", "B", HARD)
    assert m.get_node("B").status == "Blocked"
    save(m, "A")
    assert m.get_node("B").status == "Open"


@pytest.mark.parametrize("operation", ["trigger", "detach", "delayed", "delete_keep"])
def test_event_wake_invalidates_all_managers(operation):
    m = graph("A", "B")
    m.add_edge("A", "B", SOFT)
    events = EventManager()
    events.add_event(Event(name="Wake"))
    events.add_node_to_event("Wake", "B", delay_days=1 if operation == "delayed" else 0)
    scores(m)
    before = m._scoring_version
    if operation == "trigger":
        events.trigger_event("Wake")
    elif operation == "detach":
        events.detach_node_from_all_events("B")
    elif operation == "delete_keep":
        events.delete_event("Wake", delete_nodes=False)
    else:
        events.trigger_event("Wake")
        with database.get_connection() as conn:
            conn.execute("UPDATE EventNodes SET activation_date='2000-01-01'")
        events.check_pending_activations()
    assert not m.get_node("B").dormant
    assert m._scoring_version > before
    assert scores(m) == scores(GraphManager())


@pytest.mark.parametrize("remove_only", [False, True])
def test_event_delete_cleans_references_and_unblocks_dependents(remove_only):
    m = graph("A", "B")
    m.add_edge("A", "B", HARD)
    ConfigManager.set_priority_goals(["A"])
    events = EventManager()
    events.add_event(Event(name="Delete"))
    events.add_node_to_event("Delete", "A")
    if remove_only:
        events.remove_node_from_event("Delete", "A")
    else:
        events.delete_event("Delete")
    assert m.get_node("B").status == "Open"
    assert ConfigManager.get_priority_goals() == []


@pytest.mark.parametrize("bulk", [True, False])
def test_type_migration_invalidates_scores(bulk):
    m = graph("A", "B")
    m.add_edge("A", "B", SOFT)
    scores(m)
    before = m._scoring_version
    if bulk:
        m.apply_migration("type", {"Learn": "Milestone"})
    else:
        m.apply_node_migration("B", "type", "Milestone")
    assert m._scoring_version > before
    assert scores(m) == scores(GraphManager())


def test_pending_changes_never_poison_committed_caches():
    m = graph("A", "B")
    baseline = scores(m)
    m.get_goal_subtree("B")
    with pytest.raises(ValueError):
        with database.transaction():
            m.add_edge("A", "B", SOFT)
            assert m.get_goal_subtree("B") == {"A"}
            assert scores(m)["A"] > baseline["A"]
            raise ValueError("cancel save")
    assert m.get_goal_subtree("B") == set()
    assert scores(m) == baseline


def test_cache_read_and_publication_cannot_straddle_a_write(monkeypatch):
    m = graph("A", "B")
    read_started, release_read = ThreadEvent(), ThreadEvent()
    original = m.get_connection
    def paused_connection():
        read_started.set()
        assert release_read.wait(timeout=5)
        return original()
    monkeypatch.setattr(m, "get_connection", paused_connection)
    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(m.get_goal_subtree, "B")
        assert read_started.wait(timeout=5)
        write = pool.submit(GraphManager().add_edge, "A", "B", SOFT)
        release_read.set()
        assert read.result(timeout=5) == set()
        write.result(timeout=5)
    assert m.get_goal_subtree("B") == {"A"}


def test_cascade_revisits_a_shared_dependent_after_later_parent_changes():
    m = graph("A", "B", "C")
    m.add_edge("A", "B", HARD)
    m.add_edge("B", "C", HARD)
    # Simulate an old saved state with several Done dependents needing repair.
    with database.transaction() as conn:
        conn.execute("UPDATE Nodes SET status='Done' WHERE name IN ('B','C')")
        m._cascade_update_states(["C", "B"], conn.cursor())
    assert m.get_node("C").status == "Blocked"
