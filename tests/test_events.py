"""
Tests for the Events system: EventManager, dormant node filtering, activation, and staged delays.

Uses a temporary database for isolation.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch
import pytest
import database
from models import Node, Event, EDGE_NEEDS_HARD, EDGE_HELPS
from graph_manager import GraphManager
from event_manager import EventManager


# --- Fixtures ---

@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database.init_db()
    yield tmp_db_path


@pytest.fixture
def mgr():
    return GraphManager()


@pytest.fixture
def em():
    return EventManager()


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


# ============================================================================
# Event CRUD
# ============================================================================

class TestEventCRUD:
    def test_add_and_get_event(self, em):
        event = Event(name="Job Offer", description="Got the job")
        em.add_event(event)
        result = em.get_event("Job Offer")
        assert result.name == "Job Offer"
        assert result.description == "Got the job"
        assert result.status == "Pending"

    def test_add_duplicate_raises(self, em):
        em.add_event(Event(name="E1"))
        with pytest.raises(ValueError):
            em.add_event(Event(name="E1"))

    def test_get_all_events(self, em):
        em.add_event(Event(name="E1"))
        em.add_event(Event(name="E2"))
        events = em.get_all_events()
        assert len(events) == 2

    def test_update_event(self, em):
        em.add_event(Event(name="E1", description="old"))
        em.update_event("E1", Event(name="E1", description="new"))
        result = em.get_event("E1")
        assert result.description == "new"

    def test_update_event_rename(self, em, mgr):
        em.add_event(Event(name="E1"))
        node = _make_node("N1", dormant=1)
        mgr.add_node(node)
        em.add_node_to_event("E1", "N1")
        em.update_event("E1", Event(name="E1-Renamed"))
        assert em.get_event("E1") is None
        assert em.get_event("E1-Renamed") is not None
        # EventNodes should follow
        events = em.get_events_for_node("N1")
        assert "E1-Renamed" in events

    def test_delete_event_deletes_dormant_nodes(self, em, mgr):
        em.add_event(Event(name="E1"))
        node = _make_node("N1", dormant=1)
        mgr.add_node(node)
        em.add_node_to_event("E1", "N1")
        em.delete_event("E1", delete_nodes=True)
        assert mgr.get_node("N1") is None

    def test_delete_event_activates_nodes(self, em, mgr):
        em.add_event(Event(name="E1"))
        node = _make_node("N1", dormant=1)
        mgr.add_node(node)
        em.add_node_to_event("E1", "N1")
        em.delete_event("E1", delete_nodes=False)
        result = mgr.get_node("N1")
        assert result is not None
        assert result.dormant == 0

    def test_get_nonexistent_event_returns_none(self, em):
        assert em.get_event("Nonexistent") is None


# ============================================================================
# Dormant Node Filtering
# ============================================================================

class TestDormantFiltering:
    def test_get_all_nodes_excludes_dormant(self, mgr):
        mgr.add_node(_make_node("Active"))
        mgr.add_node(_make_node("Dormant", dormant=1))
        nodes = mgr.get_all_nodes()
        names = [n.name for n in nodes]
        assert "Active" in names
        assert "Dormant" not in names

    def test_get_all_nodes_include_dormant(self, mgr):
        mgr.add_node(_make_node("Active"))
        mgr.add_node(_make_node("Dormant", dormant=1))
        nodes = mgr.get_all_nodes(include_dormant=True)
        names = [n.name for n in nodes]
        assert "Active" in names
        assert "Dormant" in names

    def test_dormant_nodes_excluded_from_scoring(self, mgr):
        mgr.add_node(_make_node("Active", value=8))
        mgr.add_node(_make_node("Dormant", value=8, dormant=1))
        active_nodes = mgr.get_all_nodes()
        scored = mgr.calculate_priority_scores(active_nodes)
        names = [n.name for n in scored]
        assert "Active" in names
        assert "Dormant" not in names

    def test_edges_to_dormant_nodes_invisible(self, mgr):
        mgr.add_node(_make_node("Active"))
        mgr.add_node(_make_node("Dormant", dormant=1))
        mgr.add_edge("Active", "Dormant", EDGE_HELPS)
        # get_all_nodes() excludes Dormant, so edge won't appear in element generation
        nodes = mgr.get_all_nodes()
        valid_names = {n.name for n in nodes}
        edges = mgr.get_edges()
        visible_edges = [e for e in edges if e['source'] in valid_names and e['target'] in valid_names]
        assert len(visible_edges) == 0


# ============================================================================
# Event-Node Association
# ============================================================================

class TestEventNodeAssociation:
    def test_add_node_to_event(self, em, mgr):
        em.add_event(Event(name="E1"))
        mgr.add_node(_make_node("N1"))
        em.add_node_to_event("E1", "N1", delay_days=0)
        # Node should now be dormant
        node = mgr.get_node("N1")
        assert node.dormant == 1
        # Should appear in event nodes
        event_nodes = em.get_event_nodes("E1")
        assert len(event_nodes) == 1
        assert event_nodes[0]['node'].name == "N1"
        assert event_nodes[0]['delay_days'] == 0

    def test_remove_node_from_event(self, em, mgr):
        em.add_event(Event(name="E1"))
        mgr.add_node(_make_node("N1", dormant=1))
        em.add_node_to_event("E1", "N1")
        em.remove_node_from_event("E1", "N1")
        assert mgr.get_node("N1") is None
        assert len(em.get_event_nodes("E1")) == 0

    def test_set_node_delay(self, em, mgr):
        em.add_event(Event(name="E1"))
        mgr.add_node(_make_node("N1", dormant=1))
        em.add_node_to_event("E1", "N1", delay_days=0)
        em.set_node_delay("E1", "N1", 14)
        event_nodes = em.get_event_nodes("E1")
        assert event_nodes[0]['delay_days'] == 14

    def test_get_event_node_count(self, em, mgr):
        em.add_event(Event(name="E1"))
        mgr.add_node(_make_node("N1", dormant=1))
        mgr.add_node(_make_node("N2", dormant=1))
        em.add_node_to_event("E1", "N1")
        em.add_node_to_event("E1", "N2")
        counts = em.get_event_node_count("E1")
        assert counts['total'] == 2
        assert counts['activated'] == 0

    def test_get_events_for_node(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.add_event(Event(name="E2"))
        mgr.add_node(_make_node("N1", dormant=1))
        em.add_node_to_event("E1", "N1")
        events = em.get_events_for_node("N1")
        assert events == ["E1"]

    def test_create_dormant_node(self, em, mgr):
        em.add_event(Event(name="E1"))
        node = _make_node("N1")
        em.create_dormant_node(node, "E1", delay_days=7)
        result = mgr.get_node("N1")
        assert result.dormant == 1
        event_nodes = em.get_event_nodes("E1")
        assert len(event_nodes) == 1
        assert event_nodes[0]['delay_days'] == 7


# ============================================================================
# Event Activation
# ============================================================================

class TestEventActivation:
    def test_trigger_event_immediate(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1", delay_days=0)
        em.create_dormant_node(_make_node("N2"), "E1", delay_days=0)

        result = em.trigger_event("E1")
        assert set(result['activated']) == {"N1", "N2"}
        assert result['scheduled'] == []

        # Event should be Triggered
        event = em.get_event("E1")
        assert event.status == "Triggered"

        # Nodes should be active
        assert mgr.get_node("N1").dormant == 0
        assert mgr.get_node("N2").dormant == 0

        # Should appear in get_all_nodes
        names = [n.name for n in mgr.get_all_nodes()]
        assert "N1" in names
        assert "N2" in names

    def test_trigger_event_with_delays(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("Immediate"), "E1", delay_days=0)
        em.create_dormant_node(_make_node("OneWeek"), "E1", delay_days=7)
        em.create_dormant_node(_make_node("ThreeMonths"), "E1", delay_days=90)

        result = em.trigger_event("E1")
        assert result['activated'] == ["Immediate"]
        assert set(result['scheduled']) == {"OneWeek", "ThreeMonths"}

        # Immediate should be active
        assert mgr.get_node("Immediate").dormant == 0
        # Delayed should still be dormant
        assert mgr.get_node("OneWeek").dormant == 1
        assert mgr.get_node("ThreeMonths").dormant == 1

    def test_check_pending_activations(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1", delay_days=7)

        # Trigger the event (schedules N1 for 7 days from now)
        em.trigger_event("E1")
        assert mgr.get_node("N1").dormant == 1

        # Check today — nothing should activate
        activated = em.check_pending_activations()
        assert activated == []

        # Mock date to 7 days in the future
        future_date = date.today() + timedelta(days=7)
        with patch('event_manager.date') as mock_date:
            mock_date.today.return_value = future_date
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            activated = em.check_pending_activations()

        assert activated == ["N1"]
        assert mgr.get_node("N1").dormant == 0

    def test_activation_cascades_state(self, em, mgr):
        """When a dormant prerequisite activates, dependent nodes should update status."""
        # Create active node that depends on a dormant prerequisite
        mgr.add_node(_make_node("ActiveNode", status="Open"))
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("Prereq", status="Done"), "E1", delay_days=0)

        # Add hard prerequisite edge: Prereq -> ActiveNode
        mgr.add_edge("Prereq", "ActiveNode", EDGE_NEEDS_HARD)

        # Trigger event — Prereq activates as Done, so ActiveNode stays Open
        em.trigger_event("E1")
        node = mgr.get_node("ActiveNode")
        assert node.status == "Open"

    def test_relationships_between_dormant_nodes(self, em, mgr):
        """Dormant nodes can have edges to each other; visible only after activation."""
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("A"), "E1", delay_days=0)
        em.create_dormant_node(_make_node("B"), "E1", delay_days=0)
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)

        # Before trigger: neither visible
        active_names = {n.name for n in mgr.get_all_nodes()}
        assert "A" not in active_names
        assert "B" not in active_names

        # After trigger: both visible with their edge
        em.trigger_event("E1")
        active_names = {n.name for n in mgr.get_all_nodes()}
        assert "A" in active_names
        assert "B" in active_names
        edges = mgr.get_edges()
        matching = [e for e in edges if e['source'] == "A" and e['target'] == "B"]
        assert len(matching) == 1

    def test_relationships_dormant_to_active(self, em, mgr):
        """Dormant nodes can have edges to active nodes; edge visible only after activation."""
        mgr.add_node(_make_node("ActiveNode"))
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("DormantNode"), "E1", delay_days=0)
        mgr.add_edge("ActiveNode", "DormantNode", EDGE_HELPS)

        # Before trigger: edge exists but DormantNode is filtered out
        active_names = {n.name for n in mgr.get_all_nodes()}
        assert "DormantNode" not in active_names

        # After trigger: both visible
        em.trigger_event("E1")
        active_names = {n.name for n in mgr.get_all_nodes()}
        assert "DormantNode" in active_names

    def test_event_node_count_after_trigger(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1", delay_days=0)
        em.create_dormant_node(_make_node("N2"), "E1", delay_days=30)

        em.trigger_event("E1")
        counts = em.get_event_node_count("E1")
        assert counts['total'] == 2
        assert counts['activated'] == 1


# ============================================================================
# Node Dormant Field
# ============================================================================

class TestNodeDormantField:
    def test_node_dormant_default(self):
        node = _make_node("N1")
        assert node.dormant == 0

    def test_node_dormant_explicit(self):
        node = _make_node("N1", dormant=1)
        assert node.dormant == 1

    def test_node_dormant_coerced(self):
        node = _make_node("N1", dormant="1")
        assert node.dormant == 1

    def test_node_dormant_none_defaults(self):
        node = _make_node("N1", dormant=None)
        assert node.dormant == 0

    def test_dormant_in_to_dict(self):
        node = _make_node("N1", dormant=1)
        d = node.to_dict()
        assert d['dormant'] == 1
