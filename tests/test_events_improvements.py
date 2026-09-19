"""
Tests for the Events-system improvements:
- PENDING_EVENT_NOTIFICATIONS (app-load announcement queue)
- Silent auto-trigger by node completion
- Notification hooks in check_scheduled_triggers / check_pending_activations
- now_on_trigger: an event moving the node it wakes onto the Now list
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch
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


# ---------------------------------------------------------------------------
# A delayed node's Add-to-Now intent, which used to be dropped on the floor
# ---------------------------------------------------------------------------

def _sweep_on(em, day):
    """Run the delayed-activation sweep as if today were `day`."""
    with patch("event_manager.date") as mock_date:
        mock_date.today.return_value = day
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        return em.check_pending_activations()


class TestDelayedNowIntent:
    """Triggering put a delayed node into now_intent while it was still
    dormant, and _apply_now_intent skips dormant nodes -- so the pin was
    silently dropped and never retried. The intent now waits for the wake."""

    def test_a_delayed_flagged_node_is_not_pinned_at_trigger_time(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Later"), "E", delay_days=7, now_on_trigger=True)

        result = em.trigger_event("E")

        assert result["now_intent"] == [], "still dormant, nothing to pin yet"
        assert result["now_deferred"] == ["Later"]
        assert mgr.get_now_nodes() == []

    def test_it_is_pinned_when_it_actually_wakes(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Later"), "E", delay_days=7, now_on_trigger=True)
        em.trigger_event_manually("E")
        ConfigManager.clear_pending_event_notifications()

        assert _sweep_on(em, date.today() + timedelta(days=7)) == ["Later"]

        assert [n.name for n in mgr.get_now_nodes()] == ["Later"]
        entry = ConfigManager.get_pending_event_notifications()[0]
        assert entry["kind"] == "delayed_activated"
        assert entry["now_pinned"] == ["Later"]
        assert entry["now_skipped"] == []

    def test_an_unflagged_delayed_node_is_left_off_now(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Later"), "E", delay_days=7)
        em.trigger_event("E")

        _sweep_on(em, date.today() + timedelta(days=7))

        assert mgr.get_now_nodes() == []

    def test_the_now_cap_still_wins_at_a_delayed_wake(self, em, mgr):
        ConfigManager.set_now_node_cap(1)
        mgr.add_node(_node("Already", now=1))
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Later"), "E", delay_days=7, now_on_trigger=True)
        em.trigger_event("E")

        _sweep_on(em, date.today() + timedelta(days=7))

        assert [n.name for n in mgr.get_now_nodes()] == ["Already"]
        entry = ConfigManager.get_pending_event_notifications()[-1]
        assert entry["now_skipped"] == ["Later"]
        # Skipped means un-pinned, not un-woken.
        assert mgr.get_node("Later").dormant == 0

    def test_a_node_flagged_in_two_events_is_only_pinned_once(self, em, mgr):
        mgr.add_node(_node("Shared"))
        em.add_event(Event(name="A"))
        em.add_event(Event(name="B"))
        em.add_node_to_event("A", "Shared", delay_days=7, now_on_trigger=True)
        em.add_node_to_event("B", "Shared", delay_days=7, now_on_trigger=True)
        em.trigger_event("A")
        em.trigger_event("B")

        _sweep_on(em, date.today() + timedelta(days=7))

        assert [n.name for n in mgr.get_now_nodes()] == ["Shared"]


# ---------------------------------------------------------------------------
# The manual path, which used to leave no durable record
# ---------------------------------------------------------------------------

class TestManualTriggerAnnouncement:
    def test_a_manual_trigger_queues_an_announcement(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Wakes"), "E")
        em.create_dormant_node(_node("Later"), "E", delay_days=30)

        em.trigger_event_manually("E")

        entry = ConfigManager.get_pending_event_notifications()[-1]
        assert entry["kind"] == "manual_triggered"
        assert entry["event"] == "E"
        assert entry["activated"] == ["Wakes"]
        assert entry["scheduled"] == ["Later"]

    def test_pin_all_now_pins_every_node_the_firing_woke(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Flagged"), "E", now_on_trigger=True)
        em.create_dormant_node(_node("Plain"), "E")

        result = em.trigger_event_manually("E", pin_all_now=True)

        assert result["now_pinned"] == ["Flagged", "Plain"]
        assert sorted(n.name for n in mgr.get_now_nodes()) == ["Flagged", "Plain"]

    def test_without_the_switch_only_flagged_nodes_are_pinned(self, em, mgr):
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Flagged"), "E", now_on_trigger=True)
        em.create_dormant_node(_node("Plain"), "E")

        result = em.trigger_event_manually("E")

        assert result["now_pinned"] == ["Flagged"]

    def test_pin_all_now_does_not_reach_scheduled_nodes(self, em, mgr):
        """They are still dormant. Their turn comes at the delayed wake."""
        em.add_event(Event(name="E"))
        em.create_dormant_node(_node("Later"), "E", delay_days=30)

        result = em.trigger_event_manually("E", pin_all_now=True)

        assert result["now_pinned"] == []
        assert mgr.get_now_nodes() == []
