"""The dates, events and ledger a node's lifecycle records."""
import pytest
from skilltree.store import database
from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from skilltree.store import schema
from support.graphs import make_node


# ============================================================================
# Lifecycle date auto-stamping (start_date / done_date in update_node)
# ============================================================================

class TestLifecycleDates:
    """start_date refreshes to the most recent off→on Now flip; turning Now
    off preserves it so a later Done still records elapsed time. done_date is
    stamped on each fresh →Done transition and cleared on revert."""

    @staticmethod
    def _pin_today(monkeypatch, iso):
        """Force graph_manager's date.today() to a fixed day so successive
        flips can land on distinct, assertable dates."""
        from skilltree.store.graph import manager as graph_manager
        from datetime import date as _real_date

        class _FixedDate:
            @staticmethod
            def today():
                return _real_date.fromisoformat(iso)

        monkeypatch.setattr(graph_manager, "date", _FixedDate)

    def test_now_flip_stamps_start_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-01-10")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", now=1))
        assert mgr.get_node("A").start_date == "2026-01-10"

    def test_now_reflip_uses_most_recent_date(self, mgr, monkeypatch):
        # First engagement on day 1.
        self._pin_today(monkeypatch, "2026-01-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", now=1))
        # Drop it (off-flip leaves start_date alone), then re-engage weeks later.
        mgr.update_node(make_node("A", now=0, start_date="2026-01-01"))
        self._pin_today(monkeypatch, "2026-02-15")
        mgr.update_node(make_node("A", now=1, start_date="2026-01-01"))
        assert mgr.get_node("A").start_date == "2026-02-15"

    def test_now_off_preserves_start_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-03-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", now=1))
        mgr.update_node(make_node("A", now=0, start_date="2026-03-01"))
        assert mgr.get_node("A").start_date == "2026-03-01"

    def test_off_then_done_still_records_start(self, mgr, monkeypatch):
        """The accidental-toggle safety case: turning Now off and immediately
        marking Done keeps both latest-state snapshots available to existing
        reports even though the append-only event log is authoritative."""
        self._pin_today(monkeypatch, "2026-04-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", now=1))
        mgr.update_node(make_node("A", now=0, start_date="2026-04-01"))
        self._pin_today(monkeypatch, "2026-04-05")
        mgr.update_node(make_node("A", status=STATUS_DONE, start_date="2026-04-01"))
        result = mgr.get_node("A")
        assert result.start_date == "2026-04-01"
        assert result.done_date == "2026-04-05"

    def test_done_stamps_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-05-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", status=STATUS_DONE))
        assert mgr.get_node("A").done_date == "2026-05-01"

    def test_done_when_now_clears_now_flag(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-05-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", now=1))
        mgr.update_node(make_node("A", status=STATUS_DONE, now=1, start_date="2026-05-01"))
        assert mgr.get_node("A").now == 0

    def test_revert_done_clears_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-06-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", status=STATUS_DONE))
        mgr.update_node(make_node("A", status=STATUS_OPEN, done_date="2026-06-01"))
        assert mgr.get_node("A").done_date is None

    def test_redone_restamps_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-06-01")
        mgr.add_node(make_node("A"))
        mgr.update_node(make_node("A", status=STATUS_DONE))
        mgr.update_node(make_node("A", status=STATUS_OPEN, done_date="2026-06-01"))
        self._pin_today(monkeypatch, "2026-06-20")
        mgr.update_node(make_node("A", status=STATUS_DONE))
        assert mgr.get_node("A").done_date == "2026-06-20"


class TestLifecycleEvents:
    @staticmethod
    def _pin_times(monkeypatch, *timestamps):
        from skilltree.store.graph import manager as graph_manager
        remaining = iter(timestamps)
        monkeypatch.setattr(graph_manager, "_utc_now_ts", lambda: next(remaining))

    def test_repeated_now_cycles_and_completion_are_lossless(self, mgr, monkeypatch):
        self._pin_times(monkeypatch, 50, 100, 200, 300, 400)
        mgr.add_node(make_node("A"))

        node = mgr.get_node("A")
        node.now = 1
        mgr.update_node(node)

        # Positive-to-positive is a card reorder, not a lifecycle boundary.
        node = mgr.get_node("A")
        node.now = 2
        mgr.update_node(node)

        node = mgr.get_node("A")
        node.now = 0
        mgr.update_node(node)

        node = mgr.get_node("A")
        node.now = 1
        mgr.update_node(node)

        node = mgr.get_node("A")
        node.status = STATUS_DONE
        mgr.update_node(node)

        events = mgr.get_node_lifecycle_events("A")
        assert [(e["event_type"], e["occurred_at"]) for e in events] == [
            ("now_started", 100),
            ("now_stopped", 200),
            ("now_started", 300),
            ("now_stopped", 400),
            ("completed", 400),
        ]
        assert {e["source"] for e in events} == {"live"}

    def test_completion_reopen_and_recompletion_are_all_retained(self, mgr, monkeypatch):
        self._pin_times(monkeypatch, 50, 100, 200, 300)
        mgr.add_node(make_node("A"))

        node = mgr.get_node("A")
        node.status = STATUS_DONE
        mgr.update_node(node)
        node = mgr.get_node("A")
        node.status = STATUS_OPEN
        mgr.update_node(node)
        node = mgr.get_node("A")
        node.status = STATUS_DONE
        mgr.update_node(node)

        assert [e["event_type"] for e in mgr.get_node_lifecycle_events("A")] == [
            "completed", "reopened", "completed",
        ]

    def test_rename_preserves_history_and_delete_cascades_it(self, mgr, monkeypatch):
        self._pin_times(monkeypatch, 50, 100, 150)
        mgr.add_node(make_node("Old"))
        node = mgr.get_node("Old")
        node.now = 1
        mgr.update_node(node)

        mgr.rename_node("Old", "New")
        assert mgr.get_node_lifecycle_events("Old") == []
        renamed = mgr.get_node_lifecycle_events("New")
        assert [(e["node_name"], e["event_type"]) for e in renamed] == [
            ("New", "now_started"),
        ]

        mgr.delete_node("New")
        assert mgr.get_node_lifecycle_events("New") == []

    def test_v6_migration_marks_coverage_and_current_now_as_partial(
            self, mgr, monkeypatch):
        mgr.add_node(make_node("Already Active"))
        with database.get_connection() as conn:
            conn.execute('UPDATE Nodes SET "now"=1 WHERE name=?', ("Already Active",))
            conn.execute("DROP TABLE NodeLifecycleEvents")
            conn.execute(
                "DELETE FROM Settings WHERE key='lifecycle_history_started_at'"
            )
            conn.execute("PRAGMA user_version = 6")
            conn.commit()

        monkeypatch.setattr(schema, "_utc_now_ts", lambda: 123456)
        schema.init_db(recheck=True)

        with database.get_connection() as conn:
            marker = conn.execute(
                "SELECT value FROM Settings "
                "WHERE key='lifecycle_history_started_at'"
            ).fetchone()[0]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert marker == "123456"
        assert version == schema.SCHEMA_VERSION
        assert mgr.get_node_lifecycle_events("Already Active") == [{
            "id": 1,
            "node_name": "Already Active",
            "event_type": "now_started",
            "occurred_at": 123456,
            "source": "migration_snapshot",
            "rank": None,
            "ranked_of": None,
        }]

    def test_entering_now_records_the_node_s_place_in_the_ranking(self, mgr):
        mgr.add_node(make_node("Top", value=10, interest=10))
        mgr.add_node(make_node("Second", value=2, interest=2))
        mgr.add_node(make_node("Goal", type="Goal", time_mode="inherited"))
        for name in ("Second", "Goal"):
            node = mgr.get_node(name)
            node.now = 1
            mgr.update_node(node)
        second, = mgr.get_node_lifecycle_events("Second")
        assert (second["rank"], second["ranked_of"]) == (2, 2)
        # A Goal is never ranked; the ranking it left still had one node.
        goal, = mgr.get_node_lifecycle_events("Goal")
        assert (goal["rank"], goal["ranked_of"]) == (None, 1)

    def test_only_now_starts_carry_a_rank(self, mgr):
        mgr.add_node(make_node("A"))
        node = mgr.get_node("A")
        node.now = 1
        mgr.update_node(node)
        node = mgr.get_node("A")
        node.status = STATUS_DONE
        mgr.update_node(node)
        events = {e["event_type"]: e for e in mgr.get_node_lifecycle_events("A")}
        assert events["now_started"]["rank"] == 1
        assert events["completed"]["rank"] is None
        assert events["now_stopped"]["rank"] is None


class TestNodeLedger:
    """Work entering and leaving the graph, kept after the node is gone."""

    def test_adding_records_the_estimate_it_arrived_with(self, mgr):
        mgr.add_node(make_node("A", context="Mind", time_o=3, time_m=3, time_p=3))
        row, = mgr.get_node_ledger()
        assert (row["node_name"], row["event_type"], row["node_type"],
                row["context"], row["status"]) == ("A", "created", "Learn", "Mind",
                                                   STATUS_OPEN)
        assert row["hours"] == pytest.approx(3)

    def test_deleting_keeps_the_history(self, mgr):
        mgr.add_node(make_node("A"))
        node = mgr.get_node("A")
        node.status = STATUS_DONE
        mgr.update_node(node)
        mgr.delete_node("A")
        assert [(r["event_type"], r["status"]) for r in mgr.get_node_ledger("A")] == [
            ("created", STATUS_OPEN), ("deleted", STATUS_DONE)]

    def test_rename_moves_only_the_live_node_s_rows(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.delete_node("A")
        mgr.add_node(make_node("A"))
        mgr.rename_node("A", "B")
        assert [r["event_type"] for r in mgr.get_node_ledger("A")] == [
            "created", "deleted"]
        assert [r["event_type"] for r in mgr.get_node_ledger("B")] == ["created"]

    def test_a_new_database_marks_when_coverage_began(self, mgr):
        with database.get_connection() as conn:
            marker = conn.execute(
                "SELECT value FROM Settings WHERE key='node_ledger_started_at'"
            ).fetchone()
        assert marker is not None and int(marker[0]) > 0
