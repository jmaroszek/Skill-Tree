"""
Tests for the silent-state-drift cleanup landed in v3.0.

Covers two issues that share a root cause — node references stored outside
FK-protected tables were not cleaned up on delete:

  C1. Events.trigger_node referencing a deleted node (now NULLed +
      announcement queued).
  C2. priority_goals containing a deleted Goal name (now pruned).

Plus a regression for the unaffected rename path.
"""

import sqlite3
from typing import Any
import pytest

import database
from models import Node, Event, EDGE_NEEDS_HARD
from graph_manager import GraphManager
from event_manager import EventManager
from config import ConfigManager
from callback_helpers import handle_group_delete


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
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


# ============================================================================
# C1 — Events.trigger_node cleanup
# ============================================================================

class TestC1TriggerNodeCleanup:
    def test_trigger_node_cleared_on_delete(self, mgr, em):
        mgr.add_node(_make_node("X"))
        em.add_event(Event(name="E", trigger_nodes=["X"]))

        mgr.delete_node("X")

        # Direct DB peek — the FK cascade should have taken the trigger row
        # with the node, leaving the event itself intact.
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM Events WHERE name=?", ("E",)
            ).fetchone()
            assert row[0] == 1, "Event row should still exist"
            row = conn.execute(
                "SELECT COUNT(*) FROM EventTriggerNodes WHERE event_name=?", ("E",)
            ).fetchone()
        assert row[0] == 0, "trigger row should be cascaded away"
        assert em.get_event("E").trigger_nodes == []

    def test_dormant_node_stays_dormant_after_trigger_deletion(self, mgr, em):
        mgr.add_node(_make_node("X"))
        em.add_event(Event(name="E", trigger_nodes=["X"]))
        em.create_dormant_node(_make_node("D"), event_name="E")

        mgr.delete_node("X")

        # The event was Pending and is still Pending; D is still dormant.
        ev = em.get_event("E")
        assert ev is not None
        assert ev.status == "Pending"

        d = mgr.get_node("D")
        assert d is not None and d.dormant == 1

    def test_notification_queued_on_trigger_deletion(self, mgr, em):
        mgr.add_node(_make_node("X"))
        em.add_event(Event(name="E1", trigger_nodes=["X"]))
        em.add_event(Event(name="E2", trigger_nodes=["X"]))

        mgr.delete_node("X")

        notes = ConfigManager.get_pending_event_notifications()
        td = [n for n in notes if n.get("kind") == "trigger_node_deleted"]
        assert len(td) == 1
        assert td[0]["deleted_node"] == "X"
        assert sorted(td[0]["events"]) == ["E1", "E2"]

    def test_no_notification_when_no_events_affected(self, mgr):
        mgr.add_node(_make_node("X"))
        mgr.delete_node("X")
        notes = ConfigManager.get_pending_event_notifications()
        assert not any(n.get("kind") == "trigger_node_deleted" for n in notes)

    def test_already_triggered_event_unaffected(self, mgr, em):
        # Only Pending events are surfaced — Triggered ones already fired.
        mgr.add_node(_make_node("X"))
        em.add_event(Event(name="E", trigger_nodes=["X"], status="Triggered"))

        mgr.delete_node("X")

        notes = ConfigManager.get_pending_event_notifications()
        assert not any(n.get("kind") == "trigger_node_deleted" for n in notes)


# ============================================================================
# C2 — priority_goals cleanup
# ============================================================================

class TestC2PriorityGoalsCleanup:
    def test_deleted_goal_pruned_from_list(self, mgr):
        mgr.add_node(_make_node("G1", type="Goal"))
        mgr.add_node(_make_node("G2", type="Goal"))
        mgr.add_node(_make_node("G3", type="Goal"))
        ConfigManager.set_priority_goals(["G1", "G2", "G3"])

        mgr.delete_node("G1")

        assert ConfigManager.get_priority_goals() == ["G2", "G3"]

    def test_remaining_goals_shift_up_in_rank(self, mgr):
        # After G1 is deleted, G2 should now be the rank-1 goal — verify by
        # checking the boost it receives in score_nodes.
        from scoring import score_nodes

        mgr.add_node(_make_node("G1", type="Goal"))
        mgr.add_node(_make_node("G2", type="Goal"))
        # An ordinary task gated by G2 so the goal-boost has somewhere to land.
        mgr.add_node(_make_node("Task"))
        mgr.add_edge("Task", "G2", EDGE_NEEDS_HARD)
        ConfigManager.set_priority_goals(["G1", "G2"])

        # Score before delete: Task is in G2's subtree, gets rank-2 multiplier.
        before = score_nodes(
            mgr.get_all_nodes(), mgr.get_all_nodes(), mgr.get_edges(),
            ConfigManager.get_hyperparams(),
            priority_goals=ConfigManager.get_priority_goals(),
        )
        before_score = next(n for n in before if n.name == "Task").priority_score

        mgr.delete_node("G1")

        after = score_nodes(
            mgr.get_all_nodes(), mgr.get_all_nodes(), mgr.get_edges(),
            ConfigManager.get_hyperparams(),
            priority_goals=ConfigManager.get_priority_goals(),
        )
        after_score = next(n for n in after if n.name == "Task").priority_score

        # G2 promoted from rank 2 to rank 1 → bigger multiplier → higher score.
        assert after_score > before_score

    def test_delete_non_priority_node_leaves_list_alone(self, mgr):
        mgr.add_node(_make_node("G1", type="Goal"))
        mgr.add_node(_make_node("Other"))
        ConfigManager.set_priority_goals(["G1"])

        mgr.delete_node("Other")

        assert ConfigManager.get_priority_goals() == ["G1"]


# ============================================================================
# Regression: rename path is unaffected by the new delete cleanup
# ============================================================================

class TestRenameStillWorks:
    def test_rename_propagates_event_trigger_node(self, mgr, em):
        mgr.add_node(_make_node("Old"))
        em.add_event(Event(name="E", trigger_nodes=["Old"]))

        mgr.rename_node("Old", "New")

        ev = em.get_event("E")
        assert ev.trigger_nodes == ["New"]

    def test_rename_propagates_priority_goal(self, mgr):
        # Renaming a Goal in priority_goals must update the list, otherwise
        # the goal silently loses its rank and the slot wastes its boost.
        mgr.add_node(_make_node("OldGoal", type="Goal"))
        mgr.add_node(_make_node("OtherGoal", type="Goal"))
        ConfigManager.set_priority_goals(["OldGoal", "OtherGoal"])

        mgr.rename_node("OldGoal", "NewGoal")

        assert ConfigManager.get_priority_goals() == ["NewGoal", "OtherGoal"]
