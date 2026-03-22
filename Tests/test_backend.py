"""
Tests for the Skill Tree backend (GraphManager, Node model, database).

Uses a temporary database for isolation — does not touch the production skilltree.db.
"""

import os
import tempfile
import pytest
import database
from models import Node
from graph_manager import GraphManager


@pytest.fixture(autouse=True)
def temp_database(monkeypatch):
    """Creates a temporary database for each test, ensuring full isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db_path = os.path.join(tmpdir, "test_skilltree.db")
        monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
        database.init_db()
        yield tmp_db_path


@pytest.fixture
def mgr():
    """Returns a fresh GraphManager pointing at the temp database."""
    return GraphManager()


def _make_node(name="TestNode", **overrides):
    """Helper to create a Node with sensible defaults."""
    defaults = dict(
        name=name, type="Topic", description="A test node",
        value=5, time=1.0, interest=5, effort=2, status="Open",
        context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


# --- Node CRUD ---

class TestNodeCRUD:
    def test_add_and_get_node(self, mgr):
        node = _make_node("Alpha")
        mgr.add_node(node)
        result = mgr.get_node("Alpha")
        assert result is not None
        assert result.name == "Alpha"
        assert result.type == "Topic"

    def test_add_duplicate_raises(self, mgr):
        mgr.add_node(_make_node("Alpha"))
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_node(_make_node("Alpha"))

    def test_update_node(self, mgr):
        mgr.add_node(_make_node("Alpha", value=3))
        updated = _make_node("Alpha", value=9)
        mgr.update_node(updated)
        result = mgr.get_node("Alpha")
        assert result.value == 9

    def test_delete_node(self, mgr):
        mgr.add_node(_make_node("Alpha"))
        mgr.delete_node("Alpha")
        assert mgr.get_node("Alpha") is None

    def test_delete_node_removes_edges(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", "Needs")
        mgr.delete_node("A")
        edges = mgr.get_edges()
        assert len(edges) == 0

    def test_get_all_nodes(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        assert len(mgr.get_all_nodes()) == 3


# --- Edge Operations ---

class TestEdgeOperations:
    def test_add_and_get_edge(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", "Needs")
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"

    def test_duplicate_edge_ignored(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", "Needs")
        mgr.add_edge("A", "B", "Needs")  # Should not raise
        assert len(mgr.get_edges()) == 1

    def test_remove_edge(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", "Needs")
        mgr.remove_edge("A", "B", "Needs")
        assert len(mgr.get_edges()) == 0


# --- Cycle Detection ---

class TestCycleDetection:
    def test_self_loop_rejected(self, mgr):
        mgr.add_node(_make_node("A"))
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("A", "A", "Needs")

    def test_simple_cycle_rejected(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", "Needs")
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("B", "A", "Needs")

    def test_transitive_cycle_rejected(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", "Needs")
        mgr.add_edge("B", "C", "Needs")
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("C", "A", "Needs")


# --- State Management ---

class TestStateManagement:
    def test_node_blocked_when_prereq_not_done(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", "Needs")
        result = mgr.get_node("Target")
        assert result.status == "Blocked"

    def test_node_unblocked_when_prereq_done(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", "Needs")
        # Complete the prereq
        mgr.update_node(_make_node("Prereq", status="Done"))
        result = mgr.get_node("Target")
        assert result.status == "Open"


# --- Sync Edges ---

class TestSyncEdges:
    def test_sync_edges_replaces_all(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.add_node(_make_node("D"))

        # Initial edges
        mgr.add_edge("A", "C", "Needs")
        mgr.add_edge("C", "D", "Helps")

        # Sync: change C's needs from A to B, remove helps
        mgr.sync_edges("C", needs=["B"], supports=[], helps=[], resources=[])

        edges = mgr.get_edges()
        needs_edges = [e for e in edges if e['type'] == 'Needs']
        helps_edges = [e for e in edges if e['type'] == 'Helps']

        assert len(needs_edges) == 1
        assert needs_edges[0]['source'] == "B"
        assert len(helps_edges) == 0


# --- Priority Scoring ---

class TestPriorityScoring:
    def test_done_nodes_get_negative_score(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score == -1.0

    def test_blocked_nodes_get_negative_score(self, mgr):
        mgr.add_node(_make_node("A", status="Blocked"))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score == -1.0

    def test_open_node_gets_positive_score(self, mgr):
        mgr.add_node(_make_node("A", status="Open", value=8, interest=7))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score > 0


# --- Filtering ---

class TestFiltering:
    def test_filter_by_context(self, mgr):
        nodes = [_make_node("A", context="Mind"), _make_node("B", context="Body")]
        result = mgr.filter_nodes(nodes, {"context": "Mind"})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_hide_done(self, mgr):
        nodes = [_make_node("A", status="Done"), _make_node("B", status="Open")]
        result = mgr.filter_nodes(nodes, {"hide_done": True})
        assert len(result) == 1
        assert result[0].name == "B"


# --- Community Detection ---

class TestCommunityDetection:
    def test_disconnected_components(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", "Needs")
        # C is disconnected
        communities = mgr.detect_communities(method="components")
        assert len(communities) == 2

    def test_empty_graph(self, mgr):
        communities = mgr.detect_communities()
        assert len(communities) == 0


# --- Node Model Validation ---

class TestNodeModel:
    def test_value_clamped(self):
        node = _make_node("X", value=15)
        assert node.value == 10

    def test_effort_clamped(self):
        node = _make_node("X", effort=5)
        assert node.effort == 3

    def test_time_coerced_to_float(self):
        node = _make_node("X", time="2")
        assert node.time == 2.0
        assert isinstance(node.time, float)

    def test_minimum_time(self):
        node = _make_node("X", time=0)
        assert node.time >= 0.1
