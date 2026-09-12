"""
Tests for the Events-system improvements:
- PENDING_EVENT_NOTIFICATIONS (app-load announcement queue)
- Silent auto-trigger by node completion
- Notification hooks in check_scheduled_triggers / check_pending_activations
- now_on_trigger: an event moving the node it wakes onto the Now list
"""

from datetime import date, timedelta
from typing import Any
import pytest
import database
from models import Node, Event, EDGE_NEEDS_HARD
from graph_manager import GraphManager
from event_manager import EventManager
from config import ConfigManager


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


def _node(name: str, **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


# ---------------------------------------------------------------------------
# PENDING_EVENT_NOTIFICATIONS — CRUD
# ---------------------------------------------------------------------------

class TestPendingNotifications:
    def test_crud_roundtrip(self):
        assert ConfigManager.get_pending_event_notifications() == []
        ConfigManager.add_pending_event_notification({
            "kind": "date_triggered", "event": "E1", "when": "2026-04-17",
        })
        entries = ConfigManager.get_pending_event_notifications()
        assert len(entries) == 1
        assert entries[0]["event"] == "E1"

        ConfigManager.add_pending_event_notification({
            "kind": "node_triggered", "event": "E2", "when": "2026-04-17",
        })
        assert len(ConfigManager.get_pending_event_notifications()) == 2

        ConfigManager.clear_pending_event_notifications()
        assert ConfigManager.get_pending_event_notifications() == []


# ---------------------------------------------------------------------------
# Auto-trigger notification hooks
# ---------------------------------------------------------------------------

class TestNotificationHooks:
    def test_check_scheduled_triggers_writes_notification(self, em, mgr):
        mgr.add_node(_node("D1"))
        em.add_event(Event(
            name="DateEvent",
            description="",
            trigger_date=(date.today() - timedelta(days=1)).isoformat(),
        ))
        em.add_node_to_event("DateEvent", "D1", delay_days=0)

        ConfigManager.clear_pending_event_notifications()
        triggered = em.check_scheduled_triggers()
        assert "DateEvent" in triggered
        entries = ConfigManager.get_pending_event_notifications()
        date_entries = [e for e in entries if e["kind"] == "date_triggered"]
        assert len(date_entries) == 1
        assert date_entries[0]["event"] == "DateEvent"
        assert "D1" in date_entries[0]["activated"]

    def test_check_pending_activations_writes_notification(self, em, mgr):
        mgr.add_node(_node("Delayed"))
        em.add_event(Event(name="DelayEvent", description=""))
        em.add_node_to_event("DelayEvent", "Delayed", delay_days=1)
        # Manually set activation_date in the past to simulate a due delayed node
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with em.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE EventNodes SET activation_date=? WHERE event_name=? AND node_name=?",
                (yesterday, "DelayEvent", "Delayed"),
            )
            conn.commit()

        ConfigManager.clear_pending_event_notifications()
        activated = em.check_pending_activations()
        assert "Delayed" in activated
        entries = ConfigManager.get_pending_event_notifications()
        delayed_entries = [e for e in entries if e["kind"] == "delayed_activated"]
        assert len(delayed_entries) == 1
        assert delayed_entries[0]["event"] == "DelayEvent"
        assert "Delayed" in delayed_entries[0]["nodes"]


# ---------------------------------------------------------------------------
# Silent node-completion auto-trigger
# ---------------------------------------------------------------------------

class TestNodeCompletionAutoTrigger:
    def test_auto_trigger_by_node_completion_silently_activates_dormant_nodes(self, em, mgr):
        mgr.add_node(_node("Key", status="Done"))
        mgr.add_node(_node("Reward"))
        em.add_event(Event(name="OnKey", description="", trigger_nodes=["Key"]))
        em.add_node_to_event("OnKey", "Reward", delay_days=0)

        ConfigManager.clear_pending_event_notifications()
        triggered = em.auto_trigger_by_node_completion("Key")
        assert "OnKey" in triggered

        reward = mgr.get_node("Reward")
        assert reward.dormant == 0

        entries = ConfigManager.get_pending_event_notifications()
        node_entries = [e for e in entries if e["kind"] == "node_triggered"]
        assert len(node_entries) == 1
        assert node_entries[0]["event"] == "OnKey"
        assert node_entries[0]["trigger_node"] == "Key"
        assert "Reward" in node_entries[0]["activated"]

    def test_auto_trigger_does_nothing_when_no_matching_event(self, em, mgr):
        mgr.add_node(_node("Lonely"))
        ConfigManager.clear_pending_event_notifications()
        triggered = em.auto_trigger_by_node_completion("Lonely")
        assert triggered == []
        assert ConfigManager.get_pending_event_notifications() == []


# ---------------------------------------------------------------------------
# now_on_trigger: the event intent that replaced the priority override
# ---------------------------------------------------------------------------

class TestNowOnTrigger:
    def test_intent_round_trips_on_the_event_node(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Wakes"), "E", now_on_trigger=True)
        em.create_dormant_node(_node("Sleeps"), "E")

        rows = {r['node'].name: r['now_on_trigger'] for r in em.get_event_nodes("E")}
        assert rows == {"Wakes": True, "Sleeps": False}

    def test_triggering_moves_flagged_nodes_onto_now(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Pinned"), "E", now_on_trigger=True)
        em.create_dormant_node(_node("Plain"), "E")

        result = em.trigger_event("E")
        assert result['now_intent'] == ["Pinned"]

        pinned, skipped = em._apply_now_intent(result['now_intent'])
        assert (pinned, skipped) == (["Pinned"], [])
        assert [n.name for n in mgr.get_now_nodes()] == ["Pinned"]

    def test_the_now_cap_wins_and_the_skip_is_reported(self, em, mgr):
        """An event must not be able to blow past the limit set by hand."""
        ConfigManager.set_now_node_cap(1)
        mgr.add_node(_node("Already", now=1))
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Wants In"), "E", now_on_trigger=True)

        result = em.trigger_event("E")
        pinned, skipped = em._apply_now_intent(result['now_intent'])

        assert (pinned, skipped) == ([], ["Wants In"])
        assert [n.name for n in mgr.get_now_nodes()] == ["Already"]
        # Skipped means un-pinned, not un-woken.
        assert mgr.get_node("Wants In").dormant == 0

    def test_an_auto_trigger_pins_without_asking(self, em, mgr):
        """No conflict prompt survives — Now is a plain list."""
        mgr.add_node(_node("Gate"))
        em.add_event(Event(name="E", trigger_nodes=["Gate"]))
        em.create_dormant_node(_node("Waiting"), "E", now_on_trigger=True)

        mgr.update_node(_node("Gate", status="Done"))

        assert [n.name for n in mgr.get_now_nodes()] == ["Waiting"]
        kinds = [e["kind"] for e in ConfigManager.get_pending_event_notifications()]
        assert kinds == ["node_triggered"]
        entry = ConfigManager.get_pending_event_notifications()[0]
        assert entry["now_pinned"] == ["Waiting"]
        assert entry["now_skipped"] == []

