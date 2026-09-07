"""Compound saves must either persist the entire proposed graph or nothing."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import networkx as nx
import pytest

import database
from config import ConfigManager
from graph_manager import GraphManager
from event_manager import EventManager
from models import Node, Event, EDGE_NEEDS_HARD as HARD
from callback_helpers import handle_save


def node(name, **kwargs):
    return Node(**dict(dict(name=name, type="Learn", description="original",
                           value=5, interest=5, difficulty=5, time_o=1,
                           time_m=2, time_p=4, context="Mind", status="Open"), **kwargs))


def graph(*names):
    manager = GraphManager()
    for name in names:
        manager.add_node(node(name))
    return manager


def sync(manager, name, needs=(), supports=()):
    manager.sync_edges(name, list(needs), [], list(supports), [], [])


def save(manager, name, **kwargs):
    args = dict(name=name, n_type="Learn", desc="edited", val=5, time_o=1,
                time_m=2, time_p=4, interest=5, diff=5, status_done=[],
                context="Mind", subctx=None, obs_path=None, drive_path=None,
                website_path=None, e_needs_h=[], e_needs_s=[], e_supp_h=[],
                e_supp_s=[], e_helps=[])
    args.update(kwargs)
    return handle_save(manager, **args)


def test_valid_edge_reversal_uses_proposed_graph():
    m = graph("A", "B")
    m.add_edge("A", "B", HARD)
    sync(m, "B", supports=["A"])
    assert m.get_edges() == [dict(source="B", target="A", type=HARD)]


def test_jointly_cyclic_edges_roll_back():
    m = graph("A", "B", "C")
    m.add_edge("B", "C", HARD)
    before = m.get_edges()
    with pytest.raises(ValueError, match="cycle"):
        sync(m, "A", needs=["C"], supports=["B"])
    assert m.get_edges() == before


def test_rejected_editor_save_preserves_fields_versions_and_edges():
    m = graph("A", "B")
    before = (m._graph_version, m._scoring_version)
    with pytest.raises(ValueError):
        save(m, "A", e_needs_h=["B"], e_supp_h=["B"])
    assert m.get_node("A").description == "original"
    assert (m._graph_version, m._scoring_version) == before
    assert m.get_edges() == []


def test_rename_alias_and_settings_failure_rolls_back_everything():
    m = graph("A", "B")
    m.set_aliases("A", ["Original alias"])
    m.set_aliases("B", ["Taken"])
    ConfigManager.set_priority_goals(["A"])
    with pytest.raises(ValueError, match="already belongs"):
        with database.transaction():
            m.rename_node("A", "Renamed")
            save(m, "Renamed")
            m.set_aliases("Renamed", ["Taken"])
    assert m.get_node("Renamed") is None
    assert m.get_node("A").description == "original"
    assert ConfigManager.get_priority_goals() == ["A"]
    assert m.get_aliases("A") == ["Original Alias"]


def test_missing_endpoint_is_not_silently_ignored():
    m = graph("A")
    with pytest.raises(ValueError, match="missing node"):
        m.add_edge("A", "Missing", HARD)


def test_invalid_done_save_does_not_activate_event_or_queue_suggestions():
    m = graph("A", "B")
    m.add_node(node("Reward", dormant=True))
    events = EventManager()
    events.add_event(Event(name="On done", trigger_nodes=["A"]))
    events.add_node_to_event("On done", "Reward")
    m.pop_auto_done_candidates()
    with pytest.raises(ValueError):
        save(m, "A", status_done=["Done"], e_needs_h=["B"], e_supp_h=["B"])
    assert m.get_node("A").status == "Open"
    assert m.get_node("Reward").dormant
    assert events.get_event("On done").status == "Pending"
    assert m.pop_auto_done_candidates() == []


def test_caught_nested_failure_cannot_commit_partial_event_save():
    m = graph("A")
    with database.transaction():
        EventManager().add_event(Event(name="New event"))
        try:
            m.add_edge("A", "Missing", HARD)
        except ValueError:
            pass  # A Dash callback may return a validation message here.
    assert EventManager().get_event("New event") is None


def test_simultaneous_opposite_edges_cannot_create_a_cycle():
    graph("A", "B")
    ready = Barrier(2)
    def add(source, target):
        m = GraphManager()
        ready.wait(timeout=5)
        try:
            m.add_edge(source, target, HARD)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(add, "A", "B"), pool.submit(add, "B", "A")]
        assert sum(f.result(timeout=10) for f in futures) == 1
    edges = GraphManager().get_edges()
    assert nx.is_directed_acyclic_graph(nx.DiGraph((e["source"], e["target"]) for e in edges))


def test_foreign_keys_remain_enforced_at_commit():
    graph("A")
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as conn:
            conn.execute("INSERT INTO Edges VALUES ('A', 'Missing', 'Needs_Hard')")
    assert GraphManager().get_edges() == []
