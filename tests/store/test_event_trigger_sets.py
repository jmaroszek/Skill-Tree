"""
Tests for multi-node event triggers with AND/OR semantics.

An Event's node-completion trigger holds a *set* of nodes plus a mode:
  - 'any' (OR)  — fires as soon as one listed node is Done
  - 'all' (AND) — fires only once every listed node is Done

Also covers the v5 schema migration that lifts the old single
`Events.trigger_node` column into the EventTriggerNodes table.
"""

from typing import Any
import pytest

from skilltree.store import database
from skilltree.domain.models import Node, Event, TRIGGER_MODE_ALL, TRIGGER_MODE_ANY
from skilltree.store.graph.manager import GraphManager
from skilltree.store import settings
from skilltree.store import schema


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    schema.init_db(recheck=True)
    yield tmp_db_path


@pytest.fixture
def em(services):
    return services.events


def _node(name: str, **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


def _complete(mgr: GraphManager, name: str) -> None:
    """Marks a node Done through the real update path, which is what fires events."""
    node = mgr.get_node(name)
    node.status = "Done"
    mgr.update_node(node)


def _setup(mgr, em, mode, triggers=("A", "B")):
    for t in triggers:
        mgr.add_node(_node(t))
    mgr.add_node(_node("Reward"))
    em.add_event(Event(name="E", trigger_nodes=list(triggers), trigger_mode=mode))
    em.add_node_to_event("E", "Reward", delay_days=0)
    settings.PENDING_EVENT_NOTIFICATIONS.set([])


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestTriggerSetPersistence:
    def test_round_trips_multiple_trigger_nodes(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B", "C"))
        ev = em.get_event("E")
        assert sorted(ev.trigger_nodes) == ["A", "B", "C"]
        assert ev.trigger_mode == TRIGGER_MODE_ALL

    def test_defaults_to_any_mode(self, mgr, em):
        mgr.add_node(_node("A"))
        em.add_event(Event(name="E", trigger_nodes=["A"]))
        assert em.get_event("E").trigger_mode == TRIGGER_MODE_ANY

    def test_update_replaces_the_whole_set(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ANY, triggers=("A", "B"))
        mgr.add_node(_node("C"))
        em.update_event("E", Event(name="E", trigger_nodes=["C"],
                                   trigger_mode=TRIGGER_MODE_ALL))
        ev = em.get_event("E")
        assert ev.trigger_nodes == ["C"]
        assert ev.trigger_mode == TRIGGER_MODE_ALL

    def test_duplicates_are_collapsed(self, mgr, em):
        mgr.add_node(_node("A"))
        em.add_event(Event(name="E", trigger_nodes=["A", "A"]))
        assert em.get_event("E").trigger_nodes == ["A"]

    def test_rename_carries_the_event_name_across(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL)
        em.update_event("E", Event(name="E2", trigger_nodes=["A", "B"],
                                   trigger_mode=TRIGGER_MODE_ALL))
        assert em.get_event("E") is None
        assert sorted(em.get_event("E2").trigger_nodes) == ["A", "B"]

    def test_malformed_mode_falls_back_to_any(self, mgr, em):
        """A junk mode must not strand an event behind an unsatisfiable AND."""
        mgr.add_node(_node("A"))
        em.add_event(Event(name="E", trigger_nodes=["A"], trigger_mode="nonsense"))
        assert em.get_event("E").trigger_mode == TRIGGER_MODE_ANY


# ---------------------------------------------------------------------------
# OR semantics
# ---------------------------------------------------------------------------

class TestOrTriggers:
    def test_fires_on_first_completion(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ANY)
        _complete(mgr, "A")
        assert em.get_event("E").status == "Triggered"
        assert mgr.get_node("Reward").dormant == 0

    def test_either_node_suffices(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ANY)
        _complete(mgr, "B")
        assert em.get_event("E").status == "Triggered"

    def test_single_node_set_matches_legacy_behavior(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ANY, triggers=("A",))
        _complete(mgr, "A")
        assert em.get_event("E").status == "Triggered"
        assert mgr.get_node("Reward").dormant == 0


# ---------------------------------------------------------------------------
# AND semantics
# ---------------------------------------------------------------------------

class TestAndTriggers:
    def test_does_not_fire_on_partial_completion(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL)
        _complete(mgr, "A")
        assert em.get_event("E").status == "Pending"
        assert mgr.get_node("Reward").dormant == 1

    def test_fires_once_every_node_is_done(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL)
        _complete(mgr, "A")
        _complete(mgr, "B")
        assert em.get_event("E").status == "Triggered"
        assert mgr.get_node("Reward").dormant == 0

    def test_completion_order_does_not_matter(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B", "C"))
        for name in ("C", "A", "B"):
            _complete(mgr, name)
        assert em.get_event("E").status == "Triggered"

    def test_three_way_and_waits_for_the_last(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B", "C"))
        _complete(mgr, "A")
        _complete(mgr, "B")
        assert em.get_event("E").status == "Pending", "two of three is not enough"
        _complete(mgr, "C")
        assert em.get_event("E").status == "Triggered"

    def test_notification_names_the_final_node(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL)
        _complete(mgr, "A")
        _complete(mgr, "B")
        entries = [e for e in settings.PENDING_EVENT_NOTIFICATIONS.get()
                   if e["kind"] == "node_triggered"]
        assert len(entries) == 1
        assert entries[0]["trigger_node"] == "B"
        assert entries[0]["trigger_mode"] == TRIGGER_MODE_ALL
        assert sorted(entries[0]["trigger_nodes"]) == ["A", "B"]


# ---------------------------------------------------------------------------
# Latching — un-completing must not put nodes back to sleep
# ---------------------------------------------------------------------------

class TestFiringIsLatched:
    def test_uncompleting_does_not_reverse_an_and_trigger(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL)
        _complete(mgr, "A")
        _complete(mgr, "B")
        assert em.get_event("E").status == "Triggered"

        node = mgr.get_node("A")
        node.status = "Open"
        mgr.update_node(node)

        assert em.get_event("E").status == "Triggered"
        assert mgr.get_node("Reward").dormant == 0

    def test_recompleting_does_not_double_fire(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ANY)
        _complete(mgr, "A")
        node = mgr.get_node("A")
        node.status = "Open"
        mgr.update_node(node)
        _complete(mgr, "A")
        entries = [e for e in settings.PENDING_EVENT_NOTIFICATIONS.get()
                   if e["kind"] == "node_triggered"]
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Deleting a trigger node narrows the set
# ---------------------------------------------------------------------------

class TestDeleteNarrowsTriggerSet:
    def test_delete_removes_only_that_node(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B", "C"))
        mgr.delete_node("B")
        assert sorted(em.get_event("E").trigger_nodes) == ["A", "C"]

    def test_narrowed_and_still_fires_on_the_remainder(self, mgr, em):
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B"))
        mgr.delete_node("B")
        _complete(mgr, "A")
        assert em.get_event("E").status == "Triggered"

    def test_notification_separates_narrowed_from_demoted(self, mgr, em):
        mgr.add_node(_node("A"))
        mgr.add_node(_node("B"))
        em.add_event(Event(name="Narrowed", trigger_nodes=["A", "B"],
                           trigger_mode=TRIGGER_MODE_ALL))
        em.add_event(Event(name="Demoted", trigger_nodes=["B"]))
        settings.PENDING_EVENT_NOTIFICATIONS.set([])

        mgr.delete_node("B")

        entries = [e for e in settings.PENDING_EVENT_NOTIFICATIONS.get()
                   if e["kind"] == "trigger_node_deleted"]
        assert len(entries) == 1
        assert entries[0]["narrowed"] == ["Narrowed"]
        assert entries[0]["demoted"] == ["Demoted"]

    def test_emptied_set_never_fires_vacuously(self, mgr, em):
        """An event whose last trigger is deleted must not wake on the next completion."""
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A",))
        mgr.add_node(_node("Unrelated"))
        mgr.delete_node("A")
        assert em.get_event("E").trigger_nodes == []
        _complete(mgr, "Unrelated")
        assert em.get_event("E").status == "Pending"
        assert mgr.get_node("Reward").dormant == 1

    def test_deleting_a_done_node_from_an_and_set_does_not_fire(self, mgr, em):
        """Narrowing must not be a back door to satisfying an AND condition."""
        _setup(mgr, em, TRIGGER_MODE_ALL, triggers=("A", "B"))
        _complete(mgr, "A")
        assert em.get_event("E").status == "Pending"
        mgr.delete_node("A")
        # B is still outstanding, so the event stays asleep.
        assert em.get_event("E").status == "Pending"
        assert mgr.get_node("Reward").dormant == 1
