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
    database._initialized = False
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


def assert_invariant(em: EventManager) -> None:
    """Every node with EventNodes rows is awake exactly when one row says so.

    Called from the activation tests as well as the ones below, because the
    rule is only worth having if every write path keeps it.
    """
    with em.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT n.name, n.dormant, "
            "  (SELECT COUNT(*) FROM EventNodes e "
            "    WHERE e.node_name = n.name AND e.activated = 1) "
            "FROM Nodes n "
            "WHERE n.name IN (SELECT node_name FROM EventNodes)"
        )
        for name, dormant, activated_rows in cursor.fetchall():
            expected = 0 if activated_rows else 1
            assert dormant == expected, (
                f"{name!r}: dormant={dormant} with {activated_rows} activated row(s)"
            )


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
        assert em.get_event_for_node("N1") == "E1-Renamed"

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

    def test_delete_dormant_node_deletes_the_node(self, em, mgr):
        em.add_event(Event(name="E1"))
        mgr.add_node(_make_node("N1", dormant=1))
        em.add_node_to_event("E1", "N1")
        em.delete_dormant_node("E1", "N1")
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

    def test_get_event_for_node(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.add_event(Event(name="E2"))
        mgr.add_node(_make_node("N1", dormant=1))
        mgr.add_node(_make_node("Plain"))
        em.add_node_to_event("E1", "N1")
        assert em.get_event_for_node("N1") == "E1"
        assert em.get_event_for_node("Plain") is None

    def test_create_dormant_node(self, em, mgr):
        em.add_event(Event(name="E1"))
        node = _make_node("N1")
        em.create_dormant_node(node, "E1", delay_days=7)
        result = mgr.get_node("N1")
        assert result.dormant == 1
        event_nodes = em.get_event_nodes("E1")
        assert len(event_nodes) == 1
        assert event_nodes[0]['delay_days'] == 7

    def test_handle_save_preserves_dormant(self, em, mgr):
        # Regression: editing a dormant node used to reset Nodes.dormant to 0
        # because handle_save's form-built Node defaulted dormant=0 and
        # update_node wrote that over the stored value. The node editor saves
        # dormant nodes through handle_save, so this is the main path now.
        from node_commands import handle_save

        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1", description="orig"), "E1")
        assert mgr.get_node("N1").dormant == 1

        handle_save(
            mgr, "N1", "Learn", "edited", 5, 1.0, 2.0, 4.0, 5, 5,
            status_done=[], context="Mind", subctx=None,
            obs_path="", drive_path="", website_path="",
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
        )

        after = mgr.get_node("N1")
        assert after.description == "edited"
        assert after.dormant == 1, "dormant flag must round-trip through edit/save"


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
        assert_invariant(em)

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
        assert_invariant(em)

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
        assert_invariant(em)

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


# --- Scheduled Trigger Tests ---

class TestScheduledTriggers:

    def test_event_trigger_date_stored(self, em):
        em.add_event(Event(name="Scheduled", trigger_date="2026-06-01"))
        event = em.get_event("Scheduled")
        assert event.trigger_date == "2026-06-01"

    def test_event_trigger_date_updated(self, em):
        em.add_event(Event(name="Ev"))
        event = em.get_event("Ev")
        assert event.trigger_date is None

        em.update_event("Ev", Event(name="Ev", trigger_date="2026-07-15"))
        event = em.get_event("Ev")
        assert event.trigger_date == "2026-07-15"

    def test_event_trigger_date_none_by_default(self, em):
        em.add_event(Event(name="NoDate"))
        event = em.get_event("NoDate")
        assert event.trigger_date is None

    def test_check_scheduled_triggers_fires_on_due_date(self, em, mgr):
        em.add_event(Event(name="Due", trigger_date="2026-03-25"))
        node = _make_node("DueNode")
        mgr.add_node(node)
        em.add_node_to_event("Due", "DueNode")

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            triggered = em.check_scheduled_triggers()

        assert "Due" in triggered
        event = em.get_event("Due")
        assert event.status == "Triggered"

    def test_check_scheduled_triggers_fires_past_date(self, em, mgr):
        em.add_event(Event(name="Past", trigger_date="2026-01-01"))
        node = _make_node("PastNode")
        mgr.add_node(node)
        em.add_node_to_event("Past", "PastNode")

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            triggered = em.check_scheduled_triggers()

        assert "Past" in triggered

    def test_check_scheduled_triggers_skips_future(self, em):
        em.add_event(Event(name="Future", trigger_date="2027-01-01"))

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            triggered = em.check_scheduled_triggers()

        assert triggered == []
        event = em.get_event("Future")
        assert event.status == "Pending"

    def test_check_scheduled_triggers_skips_already_triggered(self, em, mgr):
        em.add_event(Event(name="Done", trigger_date="2026-01-01"))
        node = _make_node("DoneNode")
        mgr.add_node(node)
        em.add_node_to_event("Done", "DoneNode")
        em.trigger_event("Done")

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            triggered = em.check_scheduled_triggers()

        assert triggered == []

    def test_check_scheduled_triggers_skips_no_date(self, em):
        em.add_event(Event(name="Manual"))

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 25)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            triggered = em.check_scheduled_triggers()

        assert triggered == []


class TestDormantNodeSubcontext:

    def test_dormant_node_with_subcontext(self, em, mgr):
        em.add_event(Event(name="Ev"))
        node = _make_node("SubNode", context="Mind", subcontext="Rational")
        em.create_dormant_node(node, "Ev")

        saved = mgr.get_node("SubNode")
        assert saved.subcontext == "Rational"
        assert saved.dormant == 1


# ============================================================================
# The dormant-flag invariant
# ============================================================================

class TestDormantInvariant:
    """`Nodes.dormant` is one bit and lives apart from the node's event row,
    so nothing keeps them agreeing unless every writer says so."""

    def test_a_node_its_event_woke_cannot_join_another(self, mgr, em):
        mgr.add_node(_make_node("Woken"))
        em.add_event(Event(name="First"))
        em.add_event(Event(name="Second"))
        em.add_node_to_event("First", "Woken")
        em.trigger_event("First")

        with pytest.raises(ValueError, match="already woke from 'First'"):
            em.add_node_to_event("Second", "Woken")

        assert mgr.get_node("Woken").dormant == 0
        assert em.get_event_for_node("Woken") == "First"
        assert_invariant(em)

    def test_adding_a_plain_node_to_an_event_still_sleeps_it(self, mgr, em):
        mgr.add_node(_make_node("Fresh"))
        em.add_event(Event(name="E1"))
        em.add_node_to_event("E1", "Fresh")
        assert mgr.get_node("Fresh").dormant == 1
        assert_invariant(em)

    def test_delete_event_keeping_nodes_wakes_them(self, mgr, em):
        mgr.add_node(_make_node("Kept"))
        em.add_event(Event(name="Going"))
        em.add_node_to_event("Going", "Kept")

        result = em.delete_event("Going", delete_nodes=False)

        assert result == {"woken": ["Kept"], "deleted": []}
        assert mgr.get_node("Kept").dormant == 0
        assert em.get_event_for_node("Kept") is None
        assert_invariant(em)

    def test_reconcile_is_a_noop_on_a_clean_database(self, mgr, em):
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="E1"))
        em.add_node_to_event("E1", "N1")
        assert em.reconcile_dormant_flags() == 0

    def test_reconcile_is_a_noop_with_no_events_at_all(self, mgr, em):
        mgr.add_node(_make_node("Plain"))
        assert em.reconcile_dormant_flags() == 0
        assert mgr.get_node("Plain").dormant == 0

    def test_reconcile_wakes_a_node_whose_row_says_it_already_activated(self, mgr, em):
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="E1"))
        em.add_node_to_event("E1", "N1")
        em.trigger_event("E1")
        # Forge the drift the safety net exists for.
        with em.get_connection() as conn:
            conn.execute("UPDATE Nodes SET dormant=1 WHERE name='N1'")
            conn.commit()

        assert em.reconcile_dormant_flags() == 1

        assert mgr.get_node("N1").dormant == 0
        assert_invariant(em)

    def test_reconcile_never_sleeps_a_node(self, mgr, em):
        """The sleep half is a decision, so it stays out of the automatic path."""
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="E1"))
        em.add_node_to_event("E1", "N1")
        with em.get_connection() as conn:
            conn.execute("UPDATE Nodes SET dormant=0 WHERE name='N1'")
            conn.commit()

        assert em.reconcile_dormant_flags() == 0
        assert mgr.get_node("N1").dormant == 0


# ============================================================================
# A node belongs to one event
# ============================================================================

class TestOneEventPerNode:
    def test_a_second_event_is_refused(self, mgr, em):
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="A"))
        em.add_event(Event(name="B"))
        em.add_node_to_event("A", "N1")

        with pytest.raises(ValueError, match="already in 'A'"):
            em.add_node_to_event("B", "N1")

        assert _names(em, "B") == []

    def test_the_database_enforces_it(self, mgr, em):
        import sqlite3
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="A"))
        em.add_event(Event(name="B"))
        em.add_node_to_event("A", "N1")

        with em.get_connection() as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO EventNodes (event_name, node_name) "
                         "VALUES ('B', 'N1')")

    def test_a_node_freed_by_its_event_being_deleted_can_join_another(self, mgr, em):
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="A"))
        em.add_event(Event(name="B"))
        em.add_node_to_event("A", "N1")
        em.delete_event("A", delete_nodes=False)

        em.add_node_to_event("B", "N1")

        assert em.get_event_for_node("N1") == "B"
        assert mgr.get_node("N1").dormant == 1

    def test_the_v8_migration_keeps_one_row_per_node(self, mgr, em):
        """An older database may hold a node in several events. It keeps the
        row that woke it, or else the one added first."""
        for name in ("Waiting", "Woken"):
            mgr.add_node(_make_node(name))
        for name in ("A", "B", "C"):
            em.add_event(Event(name=name))
        with database.get_connection() as conn:
            conn.execute("DROP INDEX idx_event_nodes_node")
            conn.executemany(
                "INSERT INTO EventNodes (event_name, node_name, activated) "
                "VALUES (?, ?, ?)",
                [("B", "Waiting", 0), ("A", "Waiting", 0),
                 ("A", "Woken", 0), ("C", "Woken", 1)])
            conn.execute("PRAGMA user_version = 7")
            conn.commit()

        database._initialized = False
        database.init_db()

        assert em.get_event_for_node("Waiting") == "B"
        assert em.get_event_for_node("Woken") == "C"
        with database.get_connection() as conn:
            unique = conn.execute(
                "SELECT \"unique\" FROM pragma_index_list('EventNodes') "
                "WHERE name='idx_event_nodes_node'").fetchone()
        assert unique == (1,)


# ============================================================================
# Firing is all-or-nothing
# ============================================================================

class TestTriggerTakesNoSelection:
    def test_trigger_event_refuses_a_node_selection(self, em, mgr):
        """Selective firing marked the event Triggered either way, so the
        nodes left out could never be released through it again."""
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1")
        em.create_dormant_node(_make_node("N2"), "E1")

        with pytest.raises(TypeError):
            em.trigger_event("E1", selected_nodes=["N1"])

    def test_every_node_participates(self, em, mgr):
        em.add_event(Event(name="E1"))
        for name in ("N1", "N2", "N3"):
            em.create_dormant_node(_make_node(name), "E1")

        result = em.trigger_event("E1")

        assert sorted(result['activated']) == ["N1", "N2", "N3"]
        assert all(mgr.get_node(n).dormant == 0 for n in ("N1", "N2", "N3"))

    def test_firing_an_empty_event_still_marks_it_triggered(self, em):
        em.add_event(Event(name="Empty"))

        result = em.trigger_event("Empty")

        assert result == {'activated': [], 'scheduled': [], 'already_awake': [],
                          'now_intent': [], 'now_deferred': []}
        assert em.get_event("Empty").status == "Triggered"


# ============================================================================
# Moving a dormant node between events
# ============================================================================

def _names(em, event_name):
    return sorted(r['node'].name for r in em.get_event_nodes(event_name))


class TestMoveNodeToEvent:
    """Firing now takes every node an event holds, so "not this one yet" is
    said by moving the node somewhere that has not fired."""

    def test_the_node_changes_event(self, em, mgr):
        em.add_event(Event(name="From"))
        em.add_event(Event(name="To"))
        em.create_dormant_node(_make_node("N1"), "From")

        em.move_node_to_event("From", "N1", "To")

        assert _names(em, "From") == []
        assert _names(em, "To") == ["N1"]
        assert mgr.get_node("N1").dormant == 1
        assert_invariant(em)

    def test_the_delay_and_now_flag_travel_with_it(self, em, mgr):
        em.add_event(Event(name="From"))
        em.add_event(Event(name="To"))
        em.create_dormant_node(_make_node("N1"), "From", delay_days=14,
                               now_on_trigger=True)

        em.move_node_to_event("From", "N1", "To")

        row = em.get_event_nodes("To")[0]
        assert row['delay_days'] == 14
        assert row['now_on_trigger'] is True

    def test_an_explicit_delay_overrides_the_one_carried_over(self, em, mgr):
        em.add_event(Event(name="From"))
        em.add_event(Event(name="To"))
        em.create_dormant_node(_make_node("N1"), "From", delay_days=14)

        em.move_node_to_event("From", "N1", "To", delay_days=30,
                              now_on_trigger=True)

        row = em.get_event_nodes("To")[0]
        assert row['delay_days'] == 30
        assert row['now_on_trigger'] is True

    def test_a_scheduled_node_can_be_moved_and_its_date_resets(self, em, mgr):
        """The escape hatch for a delay committed too early. After firing the
        wake date is fixed, and moving is what lets it be set again."""
        em.add_event(Event(name="Fired"))
        em.add_event(Event(name="Later"))
        em.create_dormant_node(_make_node("N1"), "Fired", delay_days=90)
        em.trigger_event("Fired")
        assert em.get_event_nodes("Fired")[0]['activation_date'] is not None

        em.move_node_to_event("Fired", "N1", "Later")

        row = em.get_event_nodes("Later")[0]
        assert row['activation_date'] is None
        assert row['activated'] == 0
        assert row['delay_days'] == 90
        assert mgr.get_node("N1").dormant == 1

    def test_moving_the_row_that_kept_a_node_awake_puts_it_back_to_sleep(
            self, em, mgr):
        """Only reachable for an unfired row, so this is the scheduled case:
        the destination has not fired, so the node is dormant again."""
        mgr.add_node(_make_node("Shared"))
        em.add_event(Event(name="A"))
        em.add_event(Event(name="Spare"))
        em.add_node_to_event("A", "Shared", delay_days=30)
        em.trigger_event("A")

        em.move_node_to_event("A", "Shared", "Spare")

        assert mgr.get_node("Shared").dormant == 1
        assert_invariant(em)

class TestMoveRefusals:
    def test_moving_to_the_same_event_is_refused(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1")

        with pytest.raises(ValueError, match="already in"):
            em.move_node_to_event("E1", "N1", "E1")

    def test_a_node_not_in_the_source_event_is_refused(self, em, mgr):
        em.add_event(Event(name="From"))
        em.add_event(Event(name="To"))

        with pytest.raises(ValueError, match="not found in event"):
            em.move_node_to_event("From", "Ghost", "To")

    def test_a_missing_destination_is_refused(self, em, mgr):
        em.add_event(Event(name="From"))
        em.create_dormant_node(_make_node("N1"), "From")

        with pytest.raises(ValueError, match="does not exist"):
            em.move_node_to_event("From", "N1", "Nowhere")

    def test_a_triggered_destination_is_refused(self, em, mgr):
        """It would never fire again, so the node would be stranded."""
        em.add_event(Event(name="From"))
        em.add_event(Event(name="Fired"))
        em.create_dormant_node(_make_node("N1"), "From")
        em.trigger_event("Fired")

        with pytest.raises(ValueError, match="already been triggered"):
            em.move_node_to_event("From", "N1", "Fired")

        assert _names(em, "From") == ["N1"], "the refusal changed nothing"

    def test_an_awake_node_is_refused(self, em, mgr):
        """Re-sleeping a live node is un-triggering by another name."""
        em.add_event(Event(name="Fired"))
        em.add_event(Event(name="To"))
        em.create_dormant_node(_make_node("N1"), "Fired")
        em.trigger_event("Fired")

        with pytest.raises(ValueError, match="already awake"):
            em.move_node_to_event("Fired", "N1", "To")

        assert mgr.get_node("N1").dormant == 0


# ============================================================================
# A fired event stops accepting nodes
# ============================================================================

class TestAddingToATriggeredEvent:
    """It will not fire again, so a node added to one would sit dormant with
    nothing left to wake it -- the stranding selective triggering used to cause."""

    def test_add_node_to_event_refuses(self, mgr, em):
        mgr.add_node(_make_node("Latecomer"))
        em.add_event(Event(name="Fired"))
        em.trigger_event("Fired")

        with pytest.raises(ValueError, match="already been triggered"):
            em.add_node_to_event("Fired", "Latecomer")

        assert em.get_event_nodes("Fired") == []
        assert mgr.get_node("Latecomer").dormant == 0

    def test_create_dormant_node_refuses_and_leaves_no_orphan(self, em, mgr):
        """The node is written before the association, so the refusal has to
        take the whole transaction with it."""
        em.add_event(Event(name="Fired"))
        em.trigger_event("Fired")

        with pytest.raises(ValueError, match="already been triggered"):
            em.create_dormant_node(_make_node("Latecomer"), "Fired")

        assert mgr.get_node("Latecomer") is None

    def test_a_pending_event_still_accepts_nodes(self, mgr, em):
        mgr.add_node(_make_node("N1"))
        em.add_event(Event(name="Waiting"))

        em.add_node_to_event("Waiting", "N1")

        assert [r['node'].name for r in em.get_event_nodes("Waiting")] == ["N1"]


# ============================================================================
# Counts, which the sidebar's "is it finished?" question is built on
# ============================================================================

class TestEventNodeCounts:
    def test_counts_every_event_in_one_pass(self, mgr, em):
        em.add_event(Event(name="A"))
        em.add_event(Event(name="B"))
        em.create_dormant_node(_make_node("N1"), "A")
        em.create_dormant_node(_make_node("N2"), "A", delay_days=30)
        em.create_dormant_node(_make_node("N3"), "B")
        em.trigger_event("A")

        counts = em.get_event_node_counts()

        assert counts["A"] == {'total': 2, 'activated': 1}
        assert counts["B"] == {'total': 1, 'activated': 0}

    def test_an_event_with_no_nodes_still_appears(self, em):
        """It has no rows to group, so it would otherwise be missing entirely
        and every caller would need its own default."""
        em.add_event(Event(name="Empty"))

        assert em.get_event_node_counts()["Empty"] == {'total': 0, 'activated': 0}

    def test_it_agrees_with_the_single_event_count(self, mgr, em):
        em.add_event(Event(name="A"))
        em.create_dormant_node(_make_node("N1"), "A")
        em.create_dormant_node(_make_node("N2"), "A")
        em.trigger_event("A")

        assert em.get_event_node_counts()["A"] == em.get_event_node_count("A")

    def test_a_fired_event_with_a_scheduled_node_is_not_finished(self, mgr, em):
        """This is the whole sidebar predicate: activated < total means work
        is still outstanding, so the event stays in the active list."""
        em.add_event(Event(name="A"))
        em.create_dormant_node(_make_node("Now"), "A")
        em.create_dormant_node(_make_node("Later"), "A", delay_days=90)
        em.trigger_event("A")

        counts = em.get_event_node_counts()["A"]
        assert counts['activated'] < counts['total']

    def test_a_fired_event_whose_nodes_all_woke_is_finished(self, mgr, em):
        em.add_event(Event(name="A"))
        em.create_dormant_node(_make_node("N1"), "A")
        em.trigger_event("A")

        counts = em.get_event_node_counts()["A"]
        assert counts['activated'] == counts['total']


# ============================================================================
# Editing a committed wake date
# ============================================================================

class TestSetNodeWakeDate:
    """After an event fires, the delay has nothing left to measure from --
    `Events` records no firing time -- so the date itself becomes the field."""

    def test_it_moves_a_scheduled_nodes_wake_date(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("Later"), "E1", delay_days=90)
        em.trigger_event("E1")

        em.set_node_wake_date("E1", "Later", "2027-03-01")

        assert em.get_event_nodes("E1")[0]['activation_date'] == "2027-03-01"

    def test_the_node_wakes_on_the_new_date(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("Later"), "E1", delay_days=365)
        em.trigger_event("E1")
        em.set_node_wake_date("E1", "Later", (date.today() + timedelta(days=1)).isoformat())

        with patch("event_manager.date") as mock_date:
            mock_date.today.return_value = date.today() + timedelta(days=1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            assert em.check_pending_activations() == ["Later"]

        assert mgr.get_node("Later").dormant == 0
        assert_invariant(em)

    def test_it_leaves_an_already_woken_row_alone(self, em, mgr):
        """Its date is a record of when it woke, not a plan."""
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("N1"), "E1")
        em.trigger_event("E1")
        woke_on = em.get_event_nodes("E1")[0]['activation_date']

        em.set_node_wake_date("E1", "N1", "2099-01-01")

        assert em.get_event_nodes("E1")[0]['activation_date'] == woke_on

    def test_clearing_it_puts_the_node_back_to_waiting_on_nothing(self, em, mgr):
        em.add_event(Event(name="E1"))
        em.create_dormant_node(_make_node("Later"), "E1", delay_days=90)
        em.trigger_event("E1")

        em.set_node_wake_date("E1", "Later", None)

        assert em.get_event_nodes("E1")[0]['activation_date'] is None
