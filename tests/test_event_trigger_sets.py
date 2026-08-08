"""
Tests for multi-node event triggers with AND/OR semantics.

An Event's node-completion trigger holds a *set* of nodes plus a mode:
  - 'any' (OR)  — fires as soon as one listed node is Done
  - 'all' (AND) — fires only once every listed node is Done

Also covers the v5 schema migration that lifts the old single
`Events.trigger_node` column into the EventTriggerNodes table.
"""

import sqlite3
from typing import Any
import pytest

import database
from models import Node, Event, TRIGGER_MODE_ALL, TRIGGER_MODE_ANY
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
    ConfigManager.clear_pending_event_notifications()


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
        entries = [e for e in ConfigManager.get_pending_event_notifications()
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
        entries = [e for e in ConfigManager.get_pending_event_notifications()
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
        ConfigManager.clear_pending_event_notifications()

        mgr.delete_node("B")

        entries = [e for e in ConfigManager.get_pending_event_notifications()
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


# ---------------------------------------------------------------------------
# v5 migration
# ---------------------------------------------------------------------------

class TestV5Migration:
    def _build_v4_db(self, path):
        """Creates a v4-shaped DB with the old single trigger_node column."""
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute('''CREATE TABLE Nodes (
            name TEXT PRIMARY KEY, type TEXT NOT NULL, description TEXT NOT NULL,
            value INTEGER NOT NULL, time_o REAL NOT NULL, time_m REAL NOT NULL,
            time_p REAL NOT NULL, interest INTEGER NOT NULL, difficulty INTEGER NOT NULL,
            context TEXT, subcontext TEXT, status TEXT NOT NULL, dormant INTEGER NOT NULL DEFAULT 0,
            time_mode TEXT NOT NULL DEFAULT 'manual', value_mode TEXT NOT NULL DEFAULT 'manual',
            habit_duration REAL NOT NULL DEFAULT 0, habit_duration_unit TEXT NOT NULL DEFAULT 'weeks',
            habit_intensity_o REAL NOT NULL DEFAULT 0, habit_intensity_m REAL NOT NULL DEFAULT 0,
            habit_intensity_p REAL NOT NULL DEFAULT 0,
            habit_intensity_unit TEXT NOT NULL DEFAULT 'min_per_day',
            habit_days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
            calibration_dismissed INTEGER NOT NULL DEFAULT 0, "now" INTEGER NOT NULL DEFAULT 0,
            obsidian_path TEXT, google_drive_path TEXT, website TEXT,
            actual_time_lower REAL, actual_time_upper REAL, actual_time_point REAL,
            actual_time_unit TEXT, start_date TEXT, done_date TEXT,
            reflect_value INTEGER, reflect_interest INTEGER, reflect_difficulty INTEGER)''')
        cur.execute('''CREATE TABLE Events (
            name TEXT PRIMARY KEY, description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending', trigger_date TEXT, trigger_node TEXT)''')
        cur.execute("INSERT INTO Nodes (name, type, description, value, time_o, time_m, "
                    "time_p, interest, difficulty, context, status) "
                    "VALUES ('Key','Learn','',5,1,2,4,5,5,'Mind','Open')")
        cur.execute("INSERT INTO Events (name, status, trigger_node) VALUES ('Legacy','Pending','Key')")
        # An event pointing at a node that no longer exists — must not break the
        # migration, and must not violate the new foreign key.
        cur.execute("INSERT INTO Events (name, status, trigger_node) VALUES ('Dangling','Pending','Ghost')")
        cur.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

    def test_legacy_trigger_node_is_lifted_into_the_new_table(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "legacy.db")
        self._build_v4_db(db_path)

        monkeypatch.setattr(database, "get_db_path", lambda: db_path)
        database._initialized = False
        database.init_db()

        em = EventManager()
        assert em.get_event("Legacy").trigger_nodes == ["Key"]
        assert em.get_event("Legacy").trigger_mode == TRIGGER_MODE_ANY
        # Dangling reference dropped rather than migrated.
        assert em.get_event("Dangling").trigger_nodes == []

        with database.get_connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == database.SCHEMA_VERSION

    def test_migration_is_idempotent(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "legacy2.db")
        self._build_v4_db(db_path)
        monkeypatch.setattr(database, "get_db_path", lambda: db_path)

        for _ in range(3):
            database._initialized = False
            database.init_db()

        assert EventManager().get_event("Legacy").trigger_nodes == ["Key"]

    def test_migrated_event_still_fires(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "legacy3.db")
        self._build_v4_db(db_path)
        monkeypatch.setattr(database, "get_db_path", lambda: db_path)
        database._initialized = False
        database.init_db()

        mgr, em = GraphManager(), EventManager()
        mgr.add_node(_node("Reward"))
        em.add_node_to_event("Legacy", "Reward", delay_days=0)

        _complete(mgr, "Key")

        assert em.get_event("Legacy").status == "Triggered"
        assert mgr.get_node("Reward").dormant == 0
