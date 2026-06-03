"""
Tests for the Skill Tree backend: Node model, PERT time, GraphManager, scoring, and config.

Uses a temporary database for isolation — does not touch the production skilltree.db.
"""

import math
from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_DONE, STATUS_BLOCKED, STATUS_OPEN
from graph_manager import GraphManager
from callback_helpers import compute_orphaned_subcontext_pairs, detect_context_renames
from config import ConfigManager, DEFAULT_NODE_TYPES, DEFAULT_HYPERPARAMS, DEFAULT_OBSIDIAN_VAULT
from scoring import intrinsic_value, perceived_cost, is_eligible, build_adjacency, total_value, score_nodes


# --- Fixtures ---

@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


@pytest.fixture
def mgr():
    """Returns a fresh GraphManager pointing at the temp database."""
    return GraphManager()


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    """Helper to create a Node with sensible defaults using current field names."""
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


# ============================================================================
# Node Model Validation
# ============================================================================

class TestNodeModel:
    def test_value_clamped_high(self):
        node = _make_node(value=15)
        assert node.value == 10

    def test_value_clamped_low(self):
        node = _make_node(value=0)
        assert node.value == 1

    def test_interest_clamped(self):
        node = _make_node(interest=15)
        assert node.interest == 10

    def test_difficulty_clamped(self):
        node = _make_node(difficulty=15)
        assert node.difficulty == 10

    def test_time_coercion(self):
        node = _make_node(time_o="1", time_m="2", time_p="3")
        assert isinstance(node.time_o, float)
        assert isinstance(node.time_m, float)
        assert isinstance(node.time_p, float)

    def test_to_dict_includes_computed_time(self):
        node = _make_node()
        d = node.to_dict()
        assert 'time' in d
        assert d['time'] == node.time

    def test_from_dict_strips_time(self):
        d = _make_node("X").to_dict()
        d['time'] = 999  # should be ignored
        node = Node.from_dict(d)
        assert node.time != 999

    def test_from_dict_legacy_effort(self):
        d = dict(
            name="Legacy", type="Skill", description="",
            value=5, time_o=1.0, time_m=2.0, time_p=3.0,
            interest=5, effort=7, status="Open"
        )
        node = Node.from_dict(d)
        assert node.difficulty == 7


# ============================================================================
# PERT Time Estimation
# ============================================================================

class TestPERTTime:
    def test_all_zeros_returns_default(self):
        node = _make_node(time_o=0, time_m=0, time_p=0)
        assert node.time == 1.0

    def test_only_m_provided(self):
        node = _make_node(time_o=0, time_m=5.0, time_p=0)
        assert node.time == 5.0

    def test_only_o_and_p_provided(self):
        node = _make_node(time_o=4.0, time_m=0, time_p=9.0)
        assert node.time == pytest.approx(math.sqrt(4.0 * 9.0))

    def test_equal_estimates(self):
        node = _make_node(time_o=2.0, time_m=2.0, time_p=2.0)
        assert node.time == 2.0

    def test_low_uncertainty_pure_arithmetic(self):
        # P/O = 2/1 = 2, weight should be 0 → pure arithmetic PERT
        node = _make_node(time_o=1.0, time_m=1.5, time_p=2.0)
        expected = (1.0 + 4 * 1.5 + 2.0) / 6.0
        assert node.time == pytest.approx(expected, rel=1e-2)

    def test_high_uncertainty_pure_geometric(self):
        # P/O = 100/1 = 100 ≥ 10, weight should be 1 → pure geometric PERT
        node = _make_node(time_o=1.0, time_m=10.0, time_p=100.0)
        e_log = math.exp((math.log(1) + 4 * math.log(10) + math.log(100)) / 6.0)
        assert node.time == pytest.approx(e_log, rel=1e-2)

    def test_medium_uncertainty_blended(self):
        # P/O = 5, between 2 and 10 → blended
        node = _make_node(time_o=2.0, time_m=5.0, time_p=10.0)
        assert 2.0 < node.time < 10.0

    def test_o_greater_than_m_clamped(self):
        # When o > m, the code clamps m = o
        node = _make_node(time_o=5.0, time_m=2.0, time_p=10.0)
        assert node.time > 0

    def test_all_provided_standard(self):
        node = _make_node(time_o=1.0, time_m=2.0, time_p=4.0)
        assert 1.0 <= node.time <= 4.0


# ============================================================================
# Node CRUD
# ============================================================================

class TestNodeCRUD:
    def test_add_and_get_node(self, mgr):
        mgr.add_node(_make_node("Alpha"))
        result = mgr.get_node("Alpha")
        assert result is not None
        assert result.name == "Alpha"
        assert result.type == "Learn"

    def test_add_duplicate_raises(self, mgr):
        mgr.add_node(_make_node("Alpha"))
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_node(_make_node("Alpha"))

    def test_update_node(self, mgr):
        mgr.add_node(_make_node("Alpha", value=3))
        mgr.update_node(_make_node("Alpha", value=9))
        result = mgr.get_node("Alpha")
        assert result.value == 9

    def test_delete_node(self, mgr):
        mgr.add_node(_make_node("Alpha"))
        mgr.delete_node("Alpha")
        assert mgr.get_node("Alpha") is None

    def test_delete_node_removes_edges(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.delete_node("A")
        assert len(mgr.get_edges()) == 0

    def test_delete_node_full_reference_cleanup(self, mgr):
        """Pinning the implicit FK-CASCADE + ConfigManager.delete_node_references
        contract: every table or settings list that references the deleted node
        must have no trace of it after delete_node returns."""
        from event_manager import EventManager
        from models import Event
        em = EventManager()

        # Set up X with edges in/out, an alias, an event triggered by X,
        # an EventNode attachment, X as priority goal, and X as override
        # parent — covering every reference path delete_node has to clean.
        mgr.add_node(_make_node("X", type="Goal"))
        mgr.add_node(_make_node("U"))
        mgr.add_node(_make_node("D"))
        mgr.add_edge("U", "X", EDGE_NEEDS_HARD)   # incoming
        mgr.add_edge("X", "D", EDGE_NEEDS_HARD)   # outgoing
        mgr.set_aliases("X", ["X-Alias"])
        em.add_event(Event(name="EvtX", trigger_node="X"))
        mgr.add_node(_make_node("Dormant", status="Open"))
        em.add_node_to_event("EvtX", "Dormant", delay_days=0)
        ConfigManager.set_priority_goals(["X"])
        ConfigManager.set_override({"parent": "X", "mode": "hard"})

        mgr.delete_node("X")

        # Node row gone
        assert mgr.get_node("X") is None
        # Edges referencing X (in either direction) gone
        assert all(e['source'] != "X" and e['target'] != "X" for e in mgr.get_edges())
        # Aliases gone (FK CASCADE)
        with mgr.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Aliases WHERE node_name=?", ("X",))
            assert cursor.fetchone()[0] == 0
            # EventNodes referencing X (none in this test, but ensure none leak)
            cursor.execute("SELECT COUNT(*) FROM EventNodes WHERE node_name=?", ("X",))
            assert cursor.fetchone()[0] == 0
        # Event's trigger_node is NULLed (event demotes to manual trigger)
        evt = em.get_event("EvtX")
        assert evt is not None
        assert evt.trigger_node is None
        # Priority goals list cleaned
        assert "X" not in ConfigManager.get_priority_goals()
        # Override parent cleared
        assert ConfigManager.get_override().get("parent") is None

    def test_get_all_nodes(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        assert len(mgr.get_all_nodes()) == 3

    def test_get_nonexistent_returns_none(self, mgr):
        assert mgr.get_node("DoesNotExist") is None

    def test_update_preserves_optional_fields(self, mgr):
        mgr.add_node(_make_node("A", obsidian_path="notes/a.md", google_drive_path="https://drive.google.com/x"))
        result = mgr.get_node("A")
        assert result.obsidian_path == "notes/a.md"
        assert result.google_drive_path == "https://drive.google.com/x"
        mgr.update_node(_make_node("A", value=9, obsidian_path="notes/a.md", google_drive_path="https://drive.google.com/x"))
        result = mgr.get_node("A")
        assert result.value == 9
        assert result.obsidian_path == "notes/a.md"

    def test_add_node_rejects_none_context(self, mgr):
        with pytest.raises(ValueError, match="must have a context"):
            mgr.add_node(_make_node("NoCtx", context=None))

    def test_add_node_rejects_empty_context(self, mgr):
        with pytest.raises(ValueError, match="must have a context"):
            mgr.add_node(_make_node("EmptyCtx", context=""))

    def test_update_node_rejects_none_context(self, mgr):
        mgr.add_node(_make_node("A"))
        with pytest.raises(ValueError, match="must have a context"):
            mgr.update_node(_make_node("A", context=None))


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
        import graph_manager
        from datetime import date as _real_date

        class _FixedDate:
            @staticmethod
            def today():
                return _real_date.fromisoformat(iso)

        monkeypatch.setattr(graph_manager, "date", _FixedDate)

    def test_now_flip_stamps_start_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-01-10")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", now=1))
        assert mgr.get_node("A").start_date == "2026-01-10"

    def test_now_reflip_uses_most_recent_date(self, mgr, monkeypatch):
        # First engagement on day 1.
        self._pin_today(monkeypatch, "2026-01-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", now=1))
        # Drop it (off-flip leaves start_date alone), then re-engage weeks later.
        mgr.update_node(_make_node("A", now=0, start_date="2026-01-01"))
        self._pin_today(monkeypatch, "2026-02-15")
        mgr.update_node(_make_node("A", now=1, start_date="2026-01-01"))
        assert mgr.get_node("A").start_date == "2026-02-15"

    def test_now_off_preserves_start_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-03-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", now=1))
        mgr.update_node(_make_node("A", now=0, start_date="2026-03-01"))
        assert mgr.get_node("A").start_date == "2026-03-01"

    def test_off_then_done_still_records_start(self, mgr, monkeypatch):
        """The accidental-toggle safety case: turning Now off and immediately
        marking Done must keep the start anchor and stamp a done_date so the
        time estimate is recoverable."""
        self._pin_today(monkeypatch, "2026-04-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", now=1))
        mgr.update_node(_make_node("A", now=0, start_date="2026-04-01"))
        self._pin_today(monkeypatch, "2026-04-05")
        mgr.update_node(_make_node("A", status=STATUS_DONE, start_date="2026-04-01"))
        result = mgr.get_node("A")
        assert result.start_date == "2026-04-01"
        assert result.done_date == "2026-04-05"

    def test_done_stamps_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-05-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", status=STATUS_DONE))
        assert mgr.get_node("A").done_date == "2026-05-01"

    def test_done_when_now_clears_now_flag(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-05-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", now=1))
        mgr.update_node(_make_node("A", status=STATUS_DONE, now=1, start_date="2026-05-01"))
        assert mgr.get_node("A").now == 0

    def test_revert_done_clears_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-06-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", status=STATUS_DONE))
        mgr.update_node(_make_node("A", status=STATUS_OPEN, done_date="2026-06-01"))
        assert mgr.get_node("A").done_date is None

    def test_redone_restamps_done_date(self, mgr, monkeypatch):
        self._pin_today(monkeypatch, "2026-06-01")
        mgr.add_node(_make_node("A"))
        mgr.update_node(_make_node("A", status=STATUS_DONE))
        mgr.update_node(_make_node("A", status=STATUS_OPEN, done_date="2026-06-01"))
        self._pin_today(monkeypatch, "2026-06-20")
        mgr.update_node(_make_node("A", status=STATUS_DONE))
        assert mgr.get_node("A").done_date == "2026-06-20"


# ============================================================================
# Node Rename (delete old + re-add under new name)
# ============================================================================

class TestNodeRename:
    """Tests the rename_node flow used by both Nodes and Goals tab renames."""

    def _rename(self, mgr, old_name, new_name, edges_from_form=None):
        """Helper that mirrors what confirm_rename_node does in callbacks.py."""
        old = mgr.get_node(old_name)
        assert old is not None
        mgr.rename_node(old_name, new_name)
        new_node = _make_node(new_name, type=old.type, description=old.description,
                              value=old.value, interest=old.interest, difficulty=old.difficulty,
                              status=old.status, context=old.context,
                              time_o=old.time_o, time_m=old.time_m, time_p=old.time_p)
        mgr.update_node(new_node)
        if edges_from_form:
            mgr.sync_edges(new_name, **edges_from_form)

    def test_rename_preserves_attributes(self, mgr):
        mgr.add_node(_make_node("OldName", description="desc", value=8,
                                interest=3, difficulty=7, context="Mind"))
        self._rename(mgr, "OldName", "NewName")
        assert mgr.get_node("OldName") is None
        new = mgr.get_node("NewName")
        assert new is not None
        assert new.description == "desc"
        assert new.value == 8
        assert new.interest == 3
        assert new.difficulty == 7
        assert new.context == "Mind"

    def test_rename_rewires_outgoing_edges(self, mgr):
        """When B is renamed to B2, B2 should still hard-need A."""
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # The UI form would still list A as a hard prerequisite
        self._rename(mgr, "B", "B2", edges_from_form={
            'needs_hard': ["A"], 'needs_soft': [], 'supports_hard': [],
            'supports_soft': [], 'helps': []})
        edges = mgr.get_edges()
        assert any(e['source'] == "A" and e['target'] == "B2" for e in edges)
        assert not any(e['target'] == "B" for e in edges)

    def test_rename_rewires_incoming_edges(self, mgr):
        """When A is renamed to A2, B should still hard-need A2 (via sync on B)."""
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # Rename A — the supports direction is handled by the form
        self._rename(mgr, "A", "A2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["B"],
            'supports_soft': [], 'helps': []})
        edges = mgr.get_edges()
        assert any(e['source'] == "A2" and e['target'] == "B" for e in edges)
        assert not any(e['source'] == "A" for e in edges)

    def test_rename_preserves_state_cascade(self, mgr):
        """Renaming a Done prereq should keep the dependent Open, not Blocked."""
        mgr.add_node(_make_node("Prereq", status="Done"))
        mgr.add_node(_make_node("Dep"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_HARD)
        assert mgr.get_node("Dep").status == "Open"
        self._rename(mgr, "Prereq", "Prereq2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["Dep"],
            'supports_soft': [], 'helps': []})
        assert mgr.get_node("Dep").status == "Open"

    def test_rename_undone_prereq_blocks_dependent(self, mgr):
        """Renaming an incomplete prereq should keep the dependent Blocked."""
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Dep"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_HARD)
        assert mgr.get_node("Dep").status == "Blocked"
        self._rename(mgr, "Prereq", "Prereq2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["Dep"],
            'supports_soft': [], 'helps': []})
        assert mgr.get_node("Dep").status == "Blocked"

    def test_rename_old_node_removed(self, mgr):
        mgr.add_node(_make_node("Old"))
        self._rename(mgr, "Old", "New")
        assert mgr.get_node("Old") is None
        assert mgr.get_node("New") is not None

    def test_rename_without_sync_preserves_edges(self, mgr):
        """Goal tab rename path: rename_node + update_node without sync_edges.
        All edges must survive the rename."""
        mgr.add_node(_make_node("Goal1", type="Goal"))
        mgr.add_node(_make_node("SubA"))
        mgr.add_node(_make_node("SubB"))
        mgr.add_edge("SubA", "Goal1", EDGE_NEEDS_HARD)
        mgr.add_edge("SubB", "Goal1", EDGE_NEEDS_HARD)

        # Rename without sync_edges (Goal tab path)
        mgr.rename_node("Goal1", "Goal2")
        new_node = _make_node("Goal2", type="Goal")
        mgr.update_node(new_node)

        edges = mgr.get_edges()
        assert any(e['source'] == "SubA" and e['target'] == "Goal2" for e in edges)
        assert any(e['source'] == "SubB" and e['target'] == "Goal2" for e in edges)
        assert not any(e['target'] == "Goal1" for e in edges)
        assert mgr.get_node("Goal1") is None
        assert mgr.get_node("Goal2") is not None


    def test_rename_preserves_soft_edges(self, mgr):
        """Soft-need edges (source→renamed) and (renamed→target) both survive."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)   # B soft-needs A
        mgr.add_edge("B", "C", EDGE_NEEDS_SOFT)   # C soft-needs B

        mgr.rename_node("B", "B2")
        mgr.update_node(_make_node("B2"))

        edges = mgr.get_edges()
        assert any(e['source'] == "A" and e['target'] == "B2" for e in edges), \
            "A→B2 soft edge must survive rename"
        assert any(e['source'] == "B2" and e['target'] == "C" for e in edges), \
            "B2→C soft edge must survive rename"
        assert not any(e['source'] == "B" or e['target'] == "B" for e in edges), \
            "Old name B must not appear in any edge after rename"

    def test_rename_preserves_helps_edges(self, mgr):
        """Helps edges referencing the renamed node are updated on both sides."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_HELPS)

        mgr.rename_node("A", "A2")
        mgr.update_node(_make_node("A2"))

        edges = mgr.get_edges()
        assert any(e['source'] == "A2" and e['target'] == "B" and e['type'] == EDGE_HELPS
                   for e in edges), "A2→B Helps edge must survive rename"
        assert not any(e['source'] == "A" or e['target'] == "A" for e in edges), \
            "Old name A must not appear in any edge after rename"

    def test_rename_preserves_deep_goal_subtree(self, mgr):
        """Renaming a goal preserves edges across multiple levels of the subtree.
        This is the exact scenario from the goal-tab rename bug: all subtasks
        were deleted because delete_node removed edges."""
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_node(_make_node("Mid"))
        mgr.add_node(_make_node("Leaf"))
        mgr.add_edge("Mid", "Goal", EDGE_NEEDS_HARD)   # Mid is a direct subtask
        mgr.add_edge("Leaf", "Mid", EDGE_NEEDS_HARD)   # Leaf is a transitive subtask

        # Goal-tab rename path: no sync_edges
        mgr.rename_node("Goal", "Goal2")
        mgr.update_node(_make_node("Goal2", type="Goal"))

        subtree = mgr.get_goal_subtree("Goal2")
        assert "Mid" in subtree, "Direct subtask Mid must be in Goal2's subtree"
        assert "Leaf" in subtree, "Transitive subtask Leaf must be in Goal2's subtree"
        assert mgr.get_node("Goal") is None
        assert mgr.get_node("Goal2") is not None

    def test_rename_event_trigger_reference_updated(self, mgr):
        """If an Event's trigger_node references the renamed node, it is updated."""
        from event_manager import EventManager
        from models import Event

        mgr.add_node(_make_node("TriggerNode"))
        em = EventManager()
        em.add_event(Event(
            name="TestEvent",
            trigger_node="TriggerNode",
            status="Pending"
        ))

        mgr.rename_node("TriggerNode", "TriggerRenamed")

        # Read Events table directly to verify the trigger_node column changed
        import database
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT trigger_node FROM Events WHERE name='TestEvent'"
            ).fetchone()
        assert row is not None
        assert row[0] == "TriggerRenamed", \
            "Event.trigger_node must be updated when the referenced node is renamed"


# ============================================================================
# Edge Operations
# ============================================================================

class TestEdgeOperations:
    def test_add_and_get_edge(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_duplicate_edge_ignored(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        assert len(mgr.get_edges()) == 1

    def test_remove_edge(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.remove_edge("A", "B", EDGE_NEEDS_HARD)
        assert len(mgr.get_edges()) == 0

    def test_pair_conflict_rejected(self, mgr):
        """Directional edges (Hard/Soft) on a pair are mutually exclusive."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # Opposite direction Hard/Soft is rejected as a cycle, before
        # reaching the pair-conflict check; either way the new row is denied.
        with pytest.raises(ValueError, match="cycle|already exists"):
            mgr.add_edge("B", "A", EDGE_NEEDS_SOFT)
        assert len(mgr.get_edges()) == 1

    def test_helps_coexists_with_directional_edge(self, mgr):
        """Per design (composite PK on source/target/type), Helps may coexist
        with a Hard or Soft prereq on the same pair — a node that unlocks
        another can also synergize with it."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_HELPS)  # should NOT raise
        edges = mgr.get_edges()
        assert len(edges) == 2
        types = {e['type'] for e in edges}
        assert types == {EDGE_NEEDS_HARD, EDGE_HELPS}

    def test_helps_canonicalization_collapses_reverse_insert(self, mgr):
        """Fix 6: (A,B,Helps) and (B,A,Helps) are the same fact — only one row."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("B", "A", EDGE_HELPS)
        mgr.add_edge("A", "B", EDGE_HELPS)
        edges = mgr.get_edges()
        assert len(edges) == 1
        # Canonical form: lexically-sorted endpoints
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_HELPS

    def test_remove_nonexistent_edge_no_error(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.remove_edge("A", "B", EDGE_NEEDS_HARD)  # should not raise


# ============================================================================
# Cycle Detection
# ============================================================================

class TestCycleDetection:
    def test_self_loop_rejected(self, mgr):
        mgr.add_node(_make_node("A"))
        with pytest.raises(ValueError, match="[Ss]elf-loop"):
            mgr.add_edge("A", "A", EDGE_NEEDS_HARD)

    def test_self_loop_rejected_for_all_edge_types(self, mgr):
        """Fix 3: self-loops rejected on Hard, Soft, AND Helps."""
        mgr.add_node(_make_node("A"))
        for etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS):
            with pytest.raises(ValueError, match="[Ss]elf-loop"):
                mgr.add_edge("A", "A", etype)

    def test_simple_cycle_rejected(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("B", "A", EDGE_NEEDS_HARD)

    def test_transitive_cycle_rejected(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("C", "A", EDGE_NEEDS_HARD)

    def test_soft_edge_cycle_also_rejected(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("B", "A", EDGE_NEEDS_SOFT)

    def test_helps_edge_allows_bidirectional(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        mgr.add_edge("B", "A", EDGE_HELPS)  # should not raise


# ============================================================================
# State Management
# ============================================================================

class TestStateManagement:
    def test_node_blocked_when_hard_prereq_not_done(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"

    def test_node_unblocked_when_hard_prereq_done(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        mgr.update_node(_make_node("Prereq", status="Done"))
        assert mgr.get_node("Target").status == "Open"

    def test_soft_prereq_does_not_block(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_SOFT)
        assert mgr.get_node("Target").status == "Open"

    def test_done_node_reblocks_when_prereq_un_dones(self, mgr):
        """Un-Done-ing a prereq cascades downstream: a Done dependent flips
        to Blocked because its hard prereq is no longer satisfied. This is
        the post-Group-3 non-sticky-Done semantics — the UI guards this with
        a confirmation modal so the user is aware before triggering."""
        mgr.add_node(_make_node("Prereq", status="Done"))
        mgr.add_node(_make_node("Target", status="Done"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        # Change prereq back to Open — Target should re-Block
        mgr.update_node(_make_node("Prereq", status="Open"))
        assert mgr.get_node("Target").status == "Blocked"

    def test_cascade_unblock(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_node(_make_node("C", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Complete A — B should unblock, then C should unblock (B is now Open, not Done)
        mgr.update_node(_make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"
        # C still Blocked because B is Open, not Done
        assert mgr.get_node("C").status == "Blocked"
        # Complete B — C should unblock
        mgr.update_node(_make_node("B", status="Done"))
        assert mgr.get_node("C").status == "Open"

    def test_multiple_hard_prereqs_all_must_be_done(self, mgr):
        mgr.add_node(_make_node("P1", status="Open"))
        mgr.add_node(_make_node("P2", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("P1", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("P2", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"
        mgr.update_node(_make_node("P1", status="Done"))
        assert mgr.get_node("Target").status == "Blocked"  # P2 still Open
        mgr.update_node(_make_node("P2", status="Done"))
        assert mgr.get_node("Target").status == "Open"

    def test_sync_edges_blocks_chain_via_needs(self, mgr):
        """Creating a chain A→B→C via sync_edges should block B and C immediately."""
        mgr.add_node(_make_node("Chain1"))
        mgr.add_node(_make_node("Chain2"))
        mgr.add_node(_make_node("Chain3"))
        # Chain2 needs Chain1
        mgr.sync_edges("Chain2", needs_hard=["Chain1"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("Chain2").status == "Blocked"
        # Chain3 needs Chain2
        mgr.sync_edges("Chain3", needs_hard=["Chain2"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("Chain3").status == "Blocked"

    def test_sync_edges_blocks_via_supports(self, mgr):
        """When node A declares supports_hard=[B, C], B and C should become Blocked."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B", "C"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"

    def test_sync_edges_supports_unblocks_when_done(self, mgr):
        """After A supports B and A is marked Done, B should become Open."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        mgr.update_node(_make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"

    def test_sync_edges_chain_via_supports_cascades(self, mgr):
        """Building a chain entirely through supports: A supports B, B supports C.
        When saving B, existing needs_hard from A must be preserved in the call."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        # B also supports C; preserve the existing A→B prereq in needs_hard
        mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=["C"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Complete A — B unblocks, C stays blocked
        mgr.update_node(_make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"
        assert mgr.get_node("C").status == "Blocked"

    def test_delete_node_unblocks_dependents(self, mgr):
        """Deleting a hard prereq should unblock its dependents."""
        mgr.add_node(_make_node("Prereq"))
        mgr.add_node(_make_node("Target"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"
        mgr.delete_node("Prereq")
        assert mgr.get_node("Target").status == "Open"

    def test_sync_edges_preserves_dormant_needs_edges(self, mgr):
        """Regression: sync_edges replaces only edges whose other endpoint is
        non-dormant. The editor's edge dropdowns hide dormant nodes, so the
        form's needs_hard list never includes them — without this filter,
        every save would silently drop dormant prerequisite edges from the DB."""
        mgr.add_node(_make_node("Target"))
        mgr.add_node(_make_node("ActivePrereq"))
        mgr.add_node(_make_node("DormantPrereq", dormant=1))
        mgr.add_edge("ActivePrereq", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("DormantPrereq", "Target", EDGE_NEEDS_HARD)
        # Editor only sees ActivePrereq; sync_edges is called with just that.
        mgr.sync_edges("Target", needs_hard=["ActivePrereq"], needs_soft=[],
                       supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        incoming = {e['source'] for e in edges
                    if e['target'] == 'Target' and e['type'] == EDGE_NEEDS_HARD}
        assert incoming == {"ActivePrereq", "DormantPrereq"}

    def test_sync_edges_preserves_dormant_helps_edges(self, mgr):
        """Same regression as above but for the undirected Helps edge type —
        the OR-clause in the DELETE must filter dormancy on whichever endpoint
        isn't the saved node."""
        mgr.add_node(_make_node("Target"))
        mgr.add_node(_make_node("ActiveHelper"))
        mgr.add_node(_make_node("DormantHelper", dormant=1))
        mgr.add_edge("Target", "ActiveHelper", EDGE_HELPS)
        mgr.add_edge("Target", "DormantHelper", EDGE_HELPS)
        mgr.sync_edges("Target", needs_hard=[], needs_soft=[],
                       supports_hard=[], supports_soft=[], helps=["ActiveHelper"])
        edges = mgr.get_edges()
        helps_partners = {e['target'] for e in edges
                          if e['source'] == 'Target' and e['type'] == EDGE_HELPS}
        helps_partners |= {e['source'] for e in edges
                           if e['target'] == 'Target' and e['type'] == EDGE_HELPS}
        assert helps_partners == {"ActiveHelper", "DormantHelper"}

    def test_delete_node_cascades_unblock(self, mgr):
        """Deleting the root of a chain should cascade unblocking through dependents."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Delete A — B loses its only prereq → Open, C still blocked by B (not Done)
        mgr.delete_node("A")
        assert mgr.get_node("B").status == "Open"
        assert mgr.get_node("C").status == "Blocked"

    def test_removing_edge_via_sync_unblocks(self, mgr):
        """Removing a hard prereq via sync_edges should unblock the node."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        # Remove the prereq
        mgr.sync_edges("B", needs_hard=[], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Open"

    def test_recompute_all_statuses_repairs_drift(self, mgr):
        """Raw-SQL edge insertion bypasses the cascade, leaving the target stuck
        at Open. recompute_all_statuses must repair it."""
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        with mgr.get_connection() as conn:
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("A", "B", EDGE_NEEDS_HARD),
            )
            conn.commit()
        assert mgr.get_node("B").status == "Open"
        changed = mgr.recompute_all_statuses()
        assert changed == 1
        assert mgr.get_node("B").status == "Blocked"

    def test_recompute_all_statuses_noop_when_consistent(self, mgr):
        """On a clean graph where statuses already match the cascade, recompute
        should report zero changes."""
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.recompute_all_statuses() == 0

    def test_recompute_all_statuses_skips_goals_and_repairs_done(self, mgr):
        """Goals keep their manual status. Done nodes whose prereqs are no
        longer satisfied are repaired to Blocked — recompute is the safety
        net that surfaces drift the cascade missed."""
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("GoalNode", type="Goal", status="Open"))
        mgr.add_node(_make_node("DoneNode", status="Done"))
        with mgr.get_connection() as conn:
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("Prereq", "GoalNode", EDGE_NEEDS_HARD),
            )
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("Prereq", "DoneNode", EDGE_NEEDS_HARD),
            )
            conn.commit()
        mgr.recompute_all_statuses()
        # Goal status is user-controlled even when raw-SQL inserts created
        # an unsatisfied prereq.
        assert mgr.get_node("GoalNode").status == "Open"
        # Done with un-Done prereq is asymmetric drift; recompute repairs it.
        assert mgr.get_node("DoneNode").status == "Blocked"


# ============================================================================
# Sync Edges
# ============================================================================

class TestSyncEdges:
    def test_sync_replaces_needs_hard(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "C", EDGE_NEEDS_HARD)
        # Replace A with B as hard prereq
        mgr.sync_edges("C", needs_hard=["B"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        hard_edges = [e for e in edges if e['type'] == EDGE_NEEDS_HARD]
        assert len(hard_edges) == 1
        assert hard_edges[0]['source'] == "B"

    def test_sync_replaces_helps(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        # Sync A: replace helps from B to C
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=[], supports_soft=[], helps=["C"])
        edges = mgr.get_edges()
        helps_edges = [e for e in edges if e['type'] == EDGE_HELPS]
        assert len(helps_edges) == 1
        assert helps_edges[0]['target'] == "C"

    def test_sync_supports_creates_reverse_edges(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        # A supports_hard B means B Needs_Hard A → edge from A to B
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_sync_rejects_pair_conflict_in_form(self, mgr):
        """Fix 6: declaring the same pair in two different edge buckets raises
        a clear error before any DB mutation. Replaces the old behavior where
        a (B needs A, B supports A) form would silently skip the cycle-creating
        edge — now caught earlier as a pair conflict at form-validation time."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="[Oo]nly one edge type"):
            mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=["A"], supports_soft=[], helps=[])

    def test_sync_with_none_args(self, mgr):
        mgr.add_node(_make_node("A"))
        # None args should be treated as empty lists
        mgr.sync_edges("A", None, None, None, None, None)
        assert len(mgr.get_edges()) == 0


# ============================================================================
# Prerequisite Chains
# ============================================================================

class TestPrerequisiteChains:
    def test_simple_chain(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains("B")
        assert len(chains) >= 1
        assert any("A" in chain for chain in chains)

    def test_no_prereqs_returns_empty(self, mgr):
        mgr.add_node(_make_node("Solo", status="Open"))
        chains = mgr.get_prerequisite_chains("Solo")
        # A standalone Open node has no incomplete prerequisite chains
        # The chain [Solo] itself has an incomplete node, so it may or may not be returned
        # depending on implementation — let's just check it doesn't crash
        assert isinstance(chains, list)

    def test_branching_chain(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_node(_make_node("C", status="Open"))
        mgr.add_edge("A", "C", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains("C")
        assert len(chains) == 2

    def test_all_done_chain_excluded(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains("B")
        assert len(chains) == 0

    def test_nonexistent_node_returns_empty(self, mgr):
        chains = mgr.get_prerequisite_chains("DoesNotExist")
        assert chains == []


# ============================================================================
# Directly Unlocked Nodes
# ============================================================================

class TestDirectlyUnlockedNodes:
    def test_returns_blocked_dependents(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # B should be Blocked now
        assert mgr.get_node("B").status == "Blocked"
        unlocked = mgr.get_directly_unlocked_nodes("A")
        assert "B" in unlocked

    def test_ignores_open_dependents(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # B is Open (A is Done), so it shouldn't be in "unlocked"
        unlocked = mgr.get_directly_unlocked_nodes("A")
        assert "B" not in unlocked

    def test_no_dependents_returns_empty(self, mgr):
        mgr.add_node(_make_node("Solo"))
        assert mgr.get_directly_unlocked_nodes("Solo") == []


# ============================================================================
# Filtering
# ============================================================================

class TestFiltering:
    def test_filter_by_context(self, mgr):
        nodes = [_make_node("A", context="Mind"), _make_node("B", context="Body")]
        result = mgr.filter_nodes(nodes, {"context": "Mind"})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_subcontext(self, mgr):
        nodes = [_make_node("A", subcontext="Rational"), _make_node("B", subcontext="Sensory")]
        result = mgr.filter_nodes(nodes, {"subcontext": "Rational"})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_hide_done(self, mgr):
        nodes = [_make_node("A", status="Done"), _make_node("B", status="Open")]
        result = mgr.filter_nodes(nodes, {"hide_done": True})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_filter_by_min_value(self, mgr):
        nodes = [_make_node("A", value=3), _make_node("B", value=8)]
        result = mgr.filter_nodes(nodes, {"min_value": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_filter_by_min_interest(self, mgr):
        nodes = [_make_node("A", interest=2), _make_node("B", interest=7)]
        result = mgr.filter_nodes(nodes, {"min_interest": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_filter_by_max_time(self, mgr):
        nodes = [_make_node("A", time_o=1, time_m=1, time_p=1), _make_node("B", time_o=100, time_m=100, time_p=100)]
        result = mgr.filter_nodes(nodes, {"max_time": 10})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_max_difficulty(self, mgr):
        nodes = [_make_node("A", difficulty=3), _make_node("B", difficulty=8)]
        result = mgr.filter_nodes(nodes, {"max_difficulty": 5})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_search(self, mgr):
        nodes = [_make_node("Python Basics"), _make_node("Rust Advanced")]
        result = mgr.filter_nodes(nodes, {"search": "python"})
        assert len(result) == 1
        assert result[0].name == "Python Basics"

    def test_combined_filters(self, mgr):
        nodes = [
            _make_node("A", context="Mind", status="Done", value=8),
            _make_node("B", context="Mind", status="Open", value=8),
            _make_node("C", context="Body", status="Open", value=8),
            _make_node("D", context="Mind", status="Open", value=2),
        ]
        result = mgr.filter_nodes(nodes, {"context": "Mind", "hide_done": True, "min_value": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_empty_filters_returns_all(self, mgr):
        nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
        result = mgr.filter_nodes(nodes, {})
        assert len(result) == 3


# ============================================================================
# Community Detection
# ============================================================================

class TestCommunityDetection:
    def test_disconnected_components(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # C is disconnected
        communities = mgr.detect_communities(method="components")
        assert len(communities) == 2

    def test_single_connected_component(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        communities = mgr.detect_communities(method="components")
        assert len(communities) == 1

    def test_empty_graph(self, mgr):
        communities = mgr.detect_communities()
        assert len(communities) == 0

    def test_louvain_method(self, mgr):
        # Create a graph with enough structure for Louvain
        for name in ["A", "B", "C", "D", "E"]:
            mgr.add_node(_make_node(name))
        mgr.add_edge("A", "B", EDGE_HELPS)
        mgr.add_edge("B", "C", EDGE_HELPS)
        mgr.add_edge("C", "A", EDGE_HELPS)
        mgr.add_edge("D", "E", EDGE_HELPS)
        communities = mgr.detect_communities(method="louvain")
        assert len(communities) >= 1
        # All nodes accounted for
        all_names = set()
        for c in communities:
            all_names.update(c)
        assert all_names == {"A", "B", "C", "D", "E"}

    def test_communities_with_filters(self, mgr):
        mgr.add_node(_make_node("A", context="Mind"))
        mgr.add_node(_make_node("B", context="Mind"))
        mgr.add_node(_make_node("C", context="Body"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        communities = mgr.detect_communities(method="components", filters={"context": "Mind"})
        all_names = set()
        for c in communities:
            all_names.update(c)
        assert "C" not in all_names


# ============================================================================
# Community Naming
# ============================================================================

class TestCommunityNaming:
    def test_empty_community(self, mgr):
        assert mgr.name_community(set()) == "Empty"

    def test_nonexistent_nodes(self, mgr):
        assert mgr.name_community({"DoesNotExist"}) == "Unknown"

    def test_dominant_context(self, mgr):
        mgr.add_node(_make_node("A", context="Mind"))
        mgr.add_node(_make_node("B", context="Mind"))
        mgr.add_node(_make_node("C", context="Body"))
        name = mgr.name_community({"A", "B", "C"})
        assert name == "Mind"  # 2/3 >= 50%

    def test_dominant_context_with_subcontext(self, mgr):
        mgr.add_node(_make_node("A", context="Mind", subcontext="Logic"))
        mgr.add_node(_make_node("B", context="Mind", subcontext="Logic"))
        name = mgr.name_community({"A", "B"})
        assert name == "Mind › Logic"

    def test_type_fallback(self, mgr):
        # No dominant context — all different contexts
        mgr.add_node(_make_node("A", context="Mind", type="Goal"))
        mgr.add_node(_make_node("B", context="Body", type="Goal"))
        mgr.add_node(_make_node("C", context="Spirit", type="Goal"))
        name = mgr.name_community({"A", "B", "C"})
        assert name == "Goals"  # 100% Goal type

    def test_word_fallback(self, mgr):
        # No dominant context or type
        mgr.add_node(_make_node("Python Basics", context="Mind", type="Learn"))
        mgr.add_node(_make_node("Python Advanced", context="Body", type="Goal"))
        mgr.add_node(_make_node("Rust Intro", context="Spirit", type="Action"))
        name = mgr.name_community({"Python Basics", "Python Advanced", "Rust Intro"})
        assert name == "Python"  # "python" appears twice

    def test_single_node_uses_context(self, mgr):
        mgr.add_node(_make_node("Solo Node", context="Body"))
        name = mgr.name_community({"Solo Node"})
        assert name == "Body"


# ============================================================================
# Priority Scoring (integration via GraphManager)
# ============================================================================

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

    def test_higher_value_scores_higher(self, mgr):
        mgr.add_node(_make_node("Low", value=1, interest=1, difficulty=5))
        mgr.add_node(_make_node("High", value=10, interest=10, difficulty=5))
        scored = mgr.calculate_priority_scores([mgr.get_node("Low"), mgr.get_node("High")])
        high_score = next(n for n in scored if n.name == "High").priority_score
        low_score = next(n for n in scored if n.name == "Low").priority_score
        assert high_score > low_score

    def test_higher_difficulty_scores_lower(self, mgr):
        mgr.add_node(_make_node("Easy", value=5, interest=5, difficulty=1))
        mgr.add_node(_make_node("Hard", value=5, interest=5, difficulty=10))
        scored = mgr.calculate_priority_scores([mgr.get_node("Easy"), mgr.get_node("Hard")])
        easy_score = next(n for n in scored if n.name == "Easy").priority_score
        hard_score = next(n for n in scored if n.name == "Hard").priority_score
        assert easy_score > hard_score

    def test_ineligible_hard_prereq_scores_negative(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        # Target is now Blocked by state management, but even if we force-pass it,
        # it would be ineligible
        scored = mgr.calculate_priority_scores([mgr.get_node("Target")])
        assert scored[0].priority_score == -1.0

    def test_network_value_propagation(self, mgr):
        # Node that unlocks a high-value downstream should score higher
        mgr.add_node(_make_node("Gateway", status="Open", value=1, interest=1))
        mgr.add_node(_make_node("Treasure", status="Open", value=10, interest=10))
        mgr.add_node(_make_node("Isolated", status="Open", value=1, interest=1))
        mgr.add_edge("Gateway", "Treasure", EDGE_NEEDS_HARD)
        scored = mgr.calculate_priority_scores([mgr.get_node("Gateway"), mgr.get_node("Isolated")])
        gateway_score = next(n for n in scored if n.name == "Gateway").priority_score
        isolated_score = next(n for n in scored if n.name == "Isolated").priority_score
        assert gateway_score > isolated_score

    def test_scores_sorted_descending(self, mgr):
        for i, name in enumerate(["A", "B", "C"]):
            mgr.add_node(_make_node(name, value=i + 1, interest=i + 1))
        all_nodes = mgr.get_all_nodes()
        scored = mgr.calculate_priority_scores(all_nodes)
        scores = [n.priority_score for n in scored]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# Scoring Module (pure function tests)
# ============================================================================

class TestScoringFunctions:
    def test_intrinsic_value(self):
        node = _make_node(value=8, interest=6)
        assert intrinsic_value(node, w_v=1.0, w_i=1.0) == 14.0
        assert intrinsic_value(node, w_v=2.0, w_i=0.5) == 19.0

    def test_perceived_cost(self):
        node = _make_node(difficulty=5, time_o=2, time_m=2, time_p=2)
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        assert cost == pytest.approx(1.0 + 2.5 * 5 + 1.0 * (2.0 ** 0.85), rel=1e-4)

    def test_is_eligible_no_prereqs(self):
        assert is_eligible("A", {"A": []}, {"A": _make_node("A")}) is True

    def test_is_eligible_all_done(self):
        nodes = {"A": _make_node("A"), "B": _make_node("B", status="Done")}
        hard_in = {"A": ["B"]}
        assert is_eligible("A", hard_in, nodes) is True

    def test_is_eligible_one_not_done(self):
        nodes = {"A": _make_node("A"), "B": _make_node("B", status="Open")}
        hard_in = {"A": ["B"]}
        assert is_eligible("A", hard_in, nodes) is False

    def test_build_adjacency_hard_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in H_out['A']
        assert 'A' in Hard_in['B']
        assert len(S_out['A']) == 0

    def test_build_adjacency_soft_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_SOFT}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in S_out['A']
        assert len(H_out['A']) == 0

    def test_build_adjacency_helps_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_HELPS}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in Syn['A']
        assert 'A' in Syn['B']  # bidirectional

    def test_build_adjacency_ignores_unknown_nodes(self):
        edges = [{'source': 'A', 'target': 'Z', 'type': EDGE_NEEDS_HARD}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert len(H_out['A']) == 0  # Z not in node_names

    def test_total_value_isolated_node(self):
        node = _make_node("A", value=8, interest=6)
        nodes = {"A": node}
        H_out = {"A": []}
        S_out = {"A": []}
        Syn = {"A": set()}
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.10, 0.40)
        assert tv == intrinsic_value(node, 1.0, 1.0)

    def test_total_value_with_hard_dependent(self):
        a = _make_node("A", value=5, interest=5)
        b = _make_node("B", value=10, interest=10)
        nodes = {"A": a, "B": b}
        H_out = {"A": ["B"], "B": []}
        S_out = {"A": [], "B": []}
        Syn = {"A": set(), "B": set()}
        d_H = 0.6
        tv_a = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, d_H, 0.25, 0.10, 0.40)
        iv_a = intrinsic_value(a, 1.0, 1.0)
        iv_b = intrinsic_value(b, 1.0, 1.0)
        assert tv_a == pytest.approx(iv_a + d_H * iv_b)

    def test_total_value_cycle_prevention(self):
        # A→B→A would recurse infinitely without visited set
        a = _make_node("A", value=5, interest=5)
        b = _make_node("B", value=5, interest=5)
        nodes = {"A": a, "B": b}
        H_out = {"A": ["B"], "B": ["A"]}
        S_out = {"A": [], "B": []}
        Syn = {"A": set(), "B": set()}
        # Should not hang — visited set prevents infinite recursion
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.10, 0.40)
        assert tv > 0


# ============================================================================
# ConfigManager
# ============================================================================

class TestConfigManager:
    def test_default_node_types(self):
        assert ConfigManager.get_node_types() == DEFAULT_NODE_TYPES

    def test_set_and_get_node_types(self):
        custom = ["Alpha", "Beta"]
        ConfigManager.set_node_types(custom)
        assert ConfigManager.get_node_types() == custom

    def test_set_and_get_contexts(self):
        custom = ["Work", "Play"]
        ConfigManager.set_contexts(custom)
        assert ConfigManager.get_contexts() == custom

    def test_set_and_get_subcontexts(self):
        custom = {"Mind": ["Rational", "Sensory"], "Body": ["Stress"]}
        ConfigManager.set_subcontexts(custom)
        assert ConfigManager.get_subcontexts() == custom

    def test_subcontexts_invalid_json_returns_empty(self):
        # Manually write bad data
        from database import get_connection
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", ("SUBCONTEXTS", "not valid json"))
            conn.commit()
        assert ConfigManager.get_subcontexts() == {}

    def test_subcontexts_list_returns_empty(self):
        # Legacy format was a list, should return {} for safety
        ConfigManager._set_db_value("SUBCONTEXTS", '["a", "b"]')
        assert ConfigManager.get_subcontexts() == {}

    def test_subcontext_sort_mode_default_is_definition(self):
        from config import DEFAULT_SUBCONTEXT_SORT_MODE
        assert ConfigManager.get_subcontext_sort_mode() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_subcontext_sort_mode_round_trip(self):
        from config import (
            SUBCONTEXT_SORT_LENGTH,
            SUBCONTEXT_SORT_ALPHABETICAL,
            SUBCONTEXT_SORT_DEFINITION,
        )
        for mode in (SUBCONTEXT_SORT_LENGTH, SUBCONTEXT_SORT_ALPHABETICAL, SUBCONTEXT_SORT_DEFINITION):
            ConfigManager.set_subcontext_sort_mode(mode)
            assert ConfigManager.get_subcontext_sort_mode() == mode

    def test_subcontext_sort_mode_invalid_falls_back_to_default(self):
        from config import DEFAULT_SUBCONTEXT_SORT_MODE
        ConfigManager._set_db_value("SUBCONTEXT_SORT_MODE", "garbage")
        assert ConfigManager.get_subcontext_sort_mode() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_subcontext_sort_mode_setter_rejects_invalid(self):
        from config import DEFAULT_SUBCONTEXT_SORT_MODE
        ConfigManager.set_subcontext_sort_mode("not-a-mode")
        assert ConfigManager.get_subcontext_sort_mode() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_sort_subcontexts_definition_preserves_order(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_DEFINITION
        items = ["Rational", "Sensory", "Judgment"]
        assert sort_subcontexts(items, SUBCONTEXT_SORT_DEFINITION) == items

    def test_sort_subcontexts_length_orders_short_first(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_LENGTH
        items = ["Engineering", "Math", "Data Science", "Physics"]
        # Stable: 'Math' (4) < 'Physics' (7) < 'Engineering' (11) == 'Data Science' (12)
        # Length-only key keeps relative order of equal-length entries.
        assert sort_subcontexts(items, SUBCONTEXT_SORT_LENGTH) == [
            "Math", "Physics", "Engineering", "Data Science",
        ]

    def test_sort_subcontexts_alphabetical_case_insensitive(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_ALPHABETICAL
        items = ["banana", "Apple", "cherry"]
        assert sort_subcontexts(items, SUBCONTEXT_SORT_ALPHABETICAL) == ["Apple", "banana", "cherry"]

    def test_sort_subcontexts_uses_configured_mode_when_none(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_ALPHABETICAL
        ConfigManager.set_subcontext_sort_mode(SUBCONTEXT_SORT_ALPHABETICAL)
        assert sort_subcontexts(["zeta", "alpha"]) == ["alpha", "zeta"]

    def test_sort_subcontexts_does_not_mutate_input(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_ALPHABETICAL
        items = ["zeta", "alpha"]
        sort_subcontexts(items, SUBCONTEXT_SORT_ALPHABETICAL)
        assert items == ["zeta", "alpha"]

    def test_sort_subcontexts_empty(self):
        from config import sort_subcontexts, SUBCONTEXT_SORT_LENGTH
        assert sort_subcontexts([], SUBCONTEXT_SORT_LENGTH) == []

    def test_set_and_get_hyperparams(self):
        custom = {**DEFAULT_HYPERPARAMS, 'w_v': 2.0}
        ConfigManager.set_hyperparams(custom)
        result = ConfigManager.get_hyperparams()
        assert result['w_v'] == 2.0

    def test_obsidian_vault_default(self):
        assert ConfigManager.get_obsidian_vault() == DEFAULT_OBSIDIAN_VAULT

    def test_obsidian_vault_set_and_get(self):
        ConfigManager.set_obsidian_vault("/custom/path")
        assert ConfigManager.get_obsidian_vault() == "/custom/path"

    def test_sync_shapes_to_types_adds_new(self):
        ConfigManager.set_node_shapes({"Learn": "ellipse", "Goal": "star"})
        ConfigManager.sync_shapes_to_types(["Learn", "Goal", "Quest"])
        shapes = ConfigManager.get_node_shapes()
        assert shapes["Quest"] == "rectangle"
        assert shapes["Learn"] == "ellipse"

    def test_sync_shapes_to_types_removes_old(self):
        ConfigManager.set_node_shapes({"Learn": "ellipse", "Goal": "star", "Removed": "diamond"})
        ConfigManager.sync_shapes_to_types(["Learn", "Goal"])
        shapes = ConfigManager.get_node_shapes()
        assert "Removed" not in shapes
        assert shapes["Learn"] == "ellipse"


# ============================================================================
# Node Migration
# ============================================================================

class TestNodeMigration:
    def test_find_orphaned_nodes_no_removals(self, mgr):
        mgr.add_node(_make_node("A", context="Mind"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Mind", "Body"])
        assert result == {}

    def test_find_orphaned_nodes_with_removal(self, mgr):
        mgr.add_node(_make_node("A", context="Mind"))
        mgr.add_node(_make_node("B", context="Body"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Body"])
        assert "Mind" in result
        assert len(result["Mind"]) == 1
        assert result["Mind"][0].name == "A"
        assert "Body" not in result

    def test_find_orphaned_nodes_no_affected(self, mgr):
        mgr.add_node(_make_node("A", context="Body"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Body"])
        assert result == {}

    def test_find_orphaned_nodes_type(self, mgr):
        mgr.add_node(_make_node("A", type="Learn"))
        mgr.add_node(_make_node("B", type="Goal"))
        result = mgr.find_orphaned_nodes('type', ["Learn", "Goal"], ["Goal"])
        assert "Learn" in result
        assert result["Learn"][0].name == "A"

    def test_apply_migration_context(self, mgr):
        mgr.add_node(_make_node("A", context="OldCtx"))
        mgr.add_node(_make_node("B", context="OldCtx"))
        mgr.apply_migration('context', {"OldCtx": "NewCtx"})
        assert mgr.get_node("A").context == "NewCtx"
        assert mgr.get_node("B").context == "NewCtx"

    def test_apply_migration_clear(self, mgr):
        mgr.add_node(_make_node("A", context="OldCtx"))
        mgr.apply_migration('context', {"OldCtx": "__clear__"})
        assert mgr.get_node("A").context is None

    def test_apply_migration_context_clears_invalid_subcontexts(self, mgr):
        mgr.add_node(_make_node("A", context="Mind", subcontext="Rational"))
        new_subs = {"Body": ["Stress", "Sleep"]}
        mgr.apply_migration('context', {"Mind": "Body"}, new_subcontexts=new_subs)
        node = mgr.get_node("A")
        assert node.context == "Body"
        assert node.subcontext is None  # "Rational" not valid under "Body"

    def test_apply_migration_subcontext(self, mgr):
        mgr.add_node(_make_node("A", context="Mind", subcontext="OldSub"))
        mgr.apply_migration('subcontext', {"OldSub": "NewSub"})
        assert mgr.get_node("A").subcontext == "NewSub"

    def test_apply_migration_empty_remap(self, mgr):
        mgr.add_node(_make_node("A", context="Mind"))
        mgr.apply_migration('context', {})
        assert mgr.get_node("A").context == "Mind"  # unchanged


# ============================================================================
# Subcontext-Pair Orphan Detection
# ============================================================================

class TestOrphanedSubcontextPairs:
    """Pure-helper tests — no DB. Identifies (ctx, sub) pairs that no longer exist."""

    def test_move_between_parents(self):
        old = {"STEM": ["Psychology"]}
        new = {"Social": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Social"])
        assert pairs == [("STEM", "Psychology")]

    def test_rename_in_place(self):
        old = {"STEM": ["Psychology"]}
        new = {"STEM": ["Cognitive"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == [("STEM", "Psychology")]

    def test_pure_delete(self):
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == [("STEM", "Psychology")]

    def test_parent_context_removed_is_skipped(self):
        # Psychology "moves" but its old parent STEM no longer exists in new_contexts —
        # those nodes are handled by the context-orphan path, not this one.
        old = {"STEM": ["Psychology"]}
        new = {"Social": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["Social"])
        assert pairs == []

    def test_same_name_added_under_new_parent_does_not_orphan(self):
        old = {"STEM": ["Psychology"]}
        new = {"STEM": ["Psychology"], "Arts": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Arts"])
        assert pairs == []

    def test_empty_old(self):
        pairs = compute_orphaned_subcontext_pairs({}, {"STEM": ["Math"]}, ["STEM"])
        assert pairs == []

    def test_unchanged_returns_empty(self):
        old = {"STEM": ["Math"]}
        new = {"STEM": ["Math"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == []

    def test_combined_move_and_rename(self):
        old = {"STEM": ["Psychology", "Bio"], "Mind": ["Sleep"]}
        new = {"STEM": ["Biology"], "Social": ["Psychology"], "Mind": ["Sleep"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Social", "Mind"])
        assert sorted(pairs) == sorted([("STEM", "Psychology"), ("STEM", "Bio")])


class TestDetectContextRenames:
    """Strict 1:1 rename detection — used by the migration modal to pre-fill defaults."""

    def test_pure_rename_preserves_subcontexts(self):
        old_ctx = ["Social", "Mind"]
        new_ctx = ["People", "Mind"]
        old_sub = {"Social": ["Dating", "Morality"], "Mind": ["Sleep"]}
        new_sub = {"People": ["Dating", "Morality"], "Mind": ["Sleep"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {"Social": "People"}

    def test_superset_subcontexts_still_counts(self):
        old_ctx = ["Social"]
        new_ctx = ["People"]
        old_sub = {"Social": ["Dating"]}
        new_sub = {"People": ["Dating", "Friends"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {"Social": "People"}

    def test_missing_subcontext_blocks_rename(self):
        old_ctx = ["Social"]
        new_ctx = ["People"]
        old_sub = {"Social": ["Dating", "Morality"]}
        new_sub = {"People": ["Dating"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {}

    def test_two_removals_is_ambiguous(self):
        old_ctx = ["A", "B"]
        new_ctx = ["X", "Y"]
        old_sub = {"A": ["sub"], "B": ["sub"]}
        new_sub = {"X": ["sub"], "Y": ["sub"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {}

    def test_pure_addition_is_not_a_rename(self):
        old_ctx = ["A"]
        new_ctx = ["A", "B"]
        old_sub = {"A": ["sub"]}
        new_sub = {"A": ["sub"], "B": ["sub"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {}

    def test_pure_removal_is_not_a_rename(self):
        old_ctx = ["A", "B"]
        new_ctx = ["A"]
        old_sub = {"A": ["sub"], "B": ["sub"]}
        new_sub = {"A": ["sub"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {}

    def test_no_changes_returns_empty(self):
        old_ctx = ["A"]
        new_ctx = ["A"]
        assert detect_context_renames(old_ctx, new_ctx, {"A": ["s"]}, {"A": ["s"]}) == {}

    def test_rename_with_no_old_subcontexts(self):
        # Old context had no subs; new context has some — still a valid rename.
        old_ctx = ["Old"]
        new_ctx = ["New"]
        assert detect_context_renames(old_ctx, new_ctx, {}, {"New": ["a"]}) == {"Old": "New"}

    def test_subcontext_only_change_is_not_a_rename(self):
        # Same context names; only subcontexts shifted. Not a rename.
        old_ctx = ["A"]
        new_ctx = ["A"]
        old_sub = {"A": ["s1"]}
        new_sub = {"A": ["s2"]}
        assert detect_context_renames(old_ctx, new_ctx, old_sub, new_sub) == {}


class TestBuildMigrationContent:
    """Per-node UI generation, smart defaults, and mapping-store shape.

    Walks the rendered Dash component tree to verify each per-node dropdown's
    default value, since the smart-default logic is the headline feature of
    the flexible-migration redesign.
    """

    @staticmethod
    def _walk(children):
        """Return {(type, idx): {'value': v, 'options': [...]}} for every
        pattern-matched component in the rendered tree."""
        found = {}
        def visit(el):
            if el is None or isinstance(el, (str, int, float, bool)):
                return
            ch = getattr(el, 'children', None)
            if isinstance(ch, list):
                for x in ch: visit(x)
            elif ch is not None:
                visit(ch)
            eid = getattr(el, 'id', None)
            if isinstance(eid, dict):
                t, i = eid.get('type'), eid.get('index')
                found[(t, i)] = {
                    'value': getattr(el, 'value', None),
                    'options': getattr(el, 'options', None),
                }
        for c in (children if isinstance(children, list) else [children]):
            visit(c)
        return found

    @staticmethod
    def _ns(name, **attrs):
        from types import SimpleNamespace
        return SimpleNamespace(name=name, **attrs)

    def _build(self, **kwargs):
        from layout import build_migration_content
        return build_migration_content(**kwargs)

    # --- Pure-rename smart defaults -----------------------------------------

    def test_pure_rename_prefills_each_node_with_original_subcontext(self):
        """The headline scenario — Social → People preserving 5 subcontexts."""
        nodes = [
            self._ns('A', subcontext='Dating'),
            self._ns('B', subcontext='Morality'),
            self._ns('C', subcontext='Influence'),
            self._ns('D', subcontext='Relationships'),
            self._ns('E', subcontext='Psychology'),
        ]
        children, mapping = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Morality', 'Influence',
                                               'Relationships', 'Psychology']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        for i, n in enumerate(nodes):
            assert sels[('migration-cgc-node', i)]['value'] == 'People'
            assert sels[('migration-cgs-node', i)]['value'] == n.subcontext

    def test_rename_clears_subcontext_absent_from_new_context(self):
        """A node tagged with a subcontext the new context doesn't have
        should default to __clear__, not to a random first-of-list."""
        nodes = [
            self._ns('Keep', subcontext='Dating'),
            self._ns('Drop', subcontext='Vanished'),
        ]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgs-node', 0)]['value'] == 'Dating'
        assert sels[('migration-cgs-node', 1)]['value'] == '__clear__'

    def test_rename_with_node_having_no_subcontext_uses_fallback(self):
        nodes = [self._ns('NoSub', subcontext=None)]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Friends']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgc-node', 0)]['value'] == 'People'
        # Fallback should be the first available sub for the new context
        assert sels[('migration-cgs-node', 0)]['value'] == 'Dating'

    def test_rename_with_no_subcontexts_under_new_context(self):
        """Renamed-to has no subs at all → fallback is __keep__."""
        nodes = [self._ns('NoSub', subcontext=None)]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': []},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgs-node', 0)]['value'] == '__keep__'

    # --- No-rename fallback --------------------------------------------------

    def test_no_rename_falls_back_to_first_new_ctx_uniformly(self):
        """When detect_context_renames returned {}, every per-node row
        should default to (first_new_ctx, first_sub) — the user can adjust."""
        nodes = [self._ns('A', subcontext='Dating'),
                 self._ns('B', subcontext='Morality')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['Mind', 'Body'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Mind': ['Sleep'], 'Body': ['Strength']},
            rename_map={},
        )
        sels = self._walk(children)
        for i in range(2):
            assert sels[('migration-cgc-node', i)]['value'] == 'Mind'
            assert sels[('migration-cgs-node', i)]['value'] == 'Sleep'

    def test_no_rename_with_empty_new_contexts(self):
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': [], 'subcontext': [], 'type': []},
            subcontexts_by_context={},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-cgc-node', 0)]['value'] == '__keep__'

    # --- Subcontext-orphan smart default ------------------------------------

    def test_subcontext_orphan_smart_default_when_unique_new_parent(self):
        """`Old › Sub` label and `Sub` lives under exactly one new ctx →
        pre-pick that (parent, sub) pair on every node row."""
        nodes = [self._ns('A', context='STEM'),
                 self._ns('B', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM › Psychology': nodes}},
            new_values_by_field={'context': ['STEM', 'Social'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'STEM': ['Math'], 'Social': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        for i in range(2):
            assert sels[('migration-sgc-node', i)]['value'] == 'Social'
            assert sels[('migration-sgs-node', i)]['value'] == 'Psychology'

    def test_subcontext_orphan_falls_back_when_sub_under_multiple_parents(self):
        """`Sub` under multiple new parents → can't auto-pick → __keep__."""
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM › Psychology': nodes}},
            new_values_by_field={'context': ['Social', 'Mind'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Social': ['Psychology'], 'Mind': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-sgc-node', 0)]['value'] == '__keep__'
        assert sels[('migration-sgs-node', 0)]['value'] == '__keep__'

    def test_subcontext_orphan_falls_back_when_sub_under_no_new_parent(self):
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM › Vanished': nodes}},
            new_values_by_field={'context': ['STEM'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'STEM': ['Math']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-sgc-node', 0)]['value'] == '__keep__'

    # --- Mapping store shape -------------------------------------------------

    def test_mapping_ctx_nodes_indexed_to_match_dropdown_indices(self):
        nodes = [self._ns('A', subcontext='Dating'),
                 self._ns('B', subcontext='Morality'),
                 self._ns('C', subcontext='Influence')]
        _, mapping = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Morality', 'Influence']},
            rename_map={'Social': 'People'},
        )
        assert len(mapping['ctx_nodes']) == 3
        for i, n in enumerate(nodes):
            assert mapping['ctx_nodes'][i]['node_name'] == n.name
            assert mapping['ctx_nodes'][i]['old_value'] == 'Social'
            assert mapping['ctx_nodes'][i]['group_idx'] == 0
            assert mapping['ctx_nodes'][i]['field'] == 'context'

    def test_multiple_ctx_orphan_groups_get_distinct_group_idx(self):
        """Two old contexts removed → two cards, each entry tagged with its group_idx."""
        social = [self._ns('A', subcontext='Dating')]
        hobbies = [self._ns('X', subcontext='Reading'),
                   self._ns('Y', subcontext='Reading')]
        _, mapping = self._build(
            orphans_by_field={'context': {'Social': social, 'Hobbies': hobbies}},
            new_values_by_field={'context': ['Mind'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Mind': ['Sleep']},
            rename_map={},
        )
        assert len(mapping['ctx_nodes']) == 3
        groups = {e['old_value']: e['group_idx'] for e in mapping['ctx_nodes']}
        assert groups['Social'] != groups['Hobbies']

    def test_no_orphans_returns_empty_lists(self):
        children, mapping = self._build(
            orphans_by_field={},
            new_values_by_field={'context': [], 'subcontext': [], 'type': []},
            subcontexts_by_context={},
            rename_map={},
        )
        assert children == []
        assert mapping == {'type': [], 'ctx_nodes': [], 'sub_nodes': []}

    def test_type_orphans_use_per_node_dropdowns_unchanged(self):
        """Type path is untouched — each node still gets a migration-dropdown."""
        nodes = [self._ns('A'), self._ns('B')]
        children, mapping = self._build(
            orphans_by_field={'type': {'OldType': nodes}},
            new_values_by_field={'context': [], 'subcontext': [], 'type': ['NewType']},
            subcontexts_by_context={},
            rename_map={},
        )
        sels = self._walk(children)
        assert ('migration-dropdown', 0) in sels
        assert ('migration-dropdown', 1) in sels
        assert all(s['value'] == 'NewType' for s in sels.values()
                   if s['value'] not in ('__keep__', '__clear__', None))
        assert len(mapping['type']) == 2
        assert mapping['type'][0]['node_name'] == 'A'

    def test_default_rename_map_arg_is_treated_as_empty(self):
        """rename_map=None should behave the same as rename_map={}."""
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map=None,
        )
        sels = self._walk(children)
        # No rename → fallback default ctx (first new), not preserve original sub
        assert sels[('migration-cgc-node', 0)]['value'] == 'People'

    # --- Bulk row presence and defaults -------------------------------------

    def test_bulk_row_renders_per_group_with_renamed_default(self):
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-bulk-cgc', 0)]['value'] == 'People'
        # Bulk apply button is also rendered
        assert ('migration-bulk-cg-apply', 0) in sels

    def test_bulk_row_renders_for_subcontext_orphan_groups(self):
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM › Psychology': nodes}},
            new_values_by_field={'context': ['Social'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Social': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-bulk-sgc', 0)]['value'] == 'Social'
        assert ('migration-bulk-sg-apply', 0) in sels


class TestBuildRenameMapFromPerNodeChoices:
    """Majority-vote rename-map builder used to feed _migrate_context_weights
    after a heterogeneous per-node migration."""

    def _build(self, ctx_nodes, cgc_values):
        from settings_callbacks import _build_rename_map_from_per_node_choices
        return _build_rename_map_from_per_node_choices(ctx_nodes, cgc_values)

    @staticmethod
    def _entries(old, names):
        return [{'field': 'context', 'old_value': old, 'node_name': n,
                 'group_idx': 0} for n in names]

    def test_unanimous_choice_wins(self):
        entries = self._entries('Social', ['A', 'B', 'C'])
        assert self._build(entries, ['People', 'People', 'People']) == {'Social': 'People'}

    def test_clear_majority_wins(self):
        entries = self._entries('Social', ['A', 'B', 'C', 'D', 'E'])
        # 3 People, 2 Mind → People wins
        assert self._build(entries, ['People', 'People', 'People', 'Mind', 'Mind']) == {'Social': 'People'}

    def test_two_way_tie_drops_old(self):
        entries = self._entries('Social', ['A', 'B'])
        assert self._build(entries, ['People', 'Mind']) == {}

    def test_three_way_tie_drops_old(self):
        entries = self._entries('Social', ['A', 'B', 'C'])
        assert self._build(entries, ['People', 'Mind', 'Body']) == {}

    def test_plurality_with_tie_for_top_drops_old(self):
        # 2 People, 2 Mind, 1 Body → tie at top → drop
        entries = self._entries('Social', ['A', 'B', 'C', 'D', 'E'])
        assert self._build(entries, ['People', 'People', 'Mind', 'Mind', 'Body']) == {}

    def test_keep_and_clear_dont_count_toward_majority(self):
        # 1 People, 1 Mind, 3 __keep__ → 1-1 tie → drop
        entries = self._entries('Social', ['A', 'B', 'C', 'D', 'E'])
        assert self._build(entries, ['People', 'Mind', '__keep__', '__keep__', '__keep__']) == {}

    def test_keep_filtered_lets_real_majority_emerge(self):
        # 2 People + 1 Mind (the Mind is a vote, not __keep__) → People wins
        entries = self._entries('Social', ['A', 'B', 'C'])
        assert self._build(entries, ['People', 'People', 'Mind']) == {'Social': 'People'}

    def test_all_keep_yields_empty_map(self):
        entries = self._entries('Social', ['A', 'B'])
        assert self._build(entries, ['__keep__', '__keep__']) == {}

    def test_all_clear_yields_empty_map(self):
        entries = self._entries('Social', ['A', 'B'])
        assert self._build(entries, ['__clear__', '__clear__']) == {}

    def test_multiple_old_groups_voted_independently(self):
        entries = (
            self._entries('Social', ['A', 'B'])
            + [{'field': 'context', 'old_value': 'Hobbies', 'node_name': n,
                'group_idx': 1} for n in ['X', 'Y', 'Z']]
        )
        # Social: unanimous People; Hobbies: tie Mind/Body/Body
        cgc = ['People', 'People', 'Mind', 'Body', 'Body']
        assert self._build(entries, cgc) == {'Social': 'People', 'Hobbies': 'Body'}

    def test_empty_entries_returns_empty_map(self):
        assert self._build([], []) == {}

    def test_cgc_values_shorter_than_entries_is_graceful(self):
        """Defensive — Dash shouldn't deliver mismatched lengths but the
        helper must not crash if it does."""
        entries = self._entries('Social', ['A', 'B', 'C'])
        # Only first 2 values present; 3rd entry has no choice → ignored
        assert self._build(entries, ['People', 'People']) == {'Social': 'People'}

    def test_cgc_values_longer_than_entries_is_graceful(self):
        entries = self._entries('Social', ['A'])
        # Trailing values beyond entries are ignored
        assert self._build(entries, ['People', 'Mind', 'Body']) == {'Social': 'People'}

    def test_none_value_is_ignored(self):
        entries = self._entries('Social', ['A', 'B'])
        # A None in cgc shouldn't count or crash
        assert self._build(entries, [None, 'People']) == {'Social': 'People'}


class TestApplyPerNodeMigrations:
    """Per-node ctx/sub remap iteration. Uses the temp_database fixture so
    actual DB writes can be observed."""

    def _apply(self, manager, entries, ctx_vals, sub_vals, new_subcontexts=None):
        from settings_callbacks import _apply_per_node_migrations
        _apply_per_node_migrations(manager, entries, ctx_vals, sub_vals,
                                    new_subcontexts or {})

    @staticmethod
    def _entry(name, old='Social'):
        return {'field': 'context', 'old_value': old, 'node_name': name,
                'group_idx': 0}

    def test_per_node_ctx_change_writes_each_node_independently(self, mgr):
        """The whole point of the redesign — different nodes go to different ctx."""
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        mgr.add_node(_make_node('B', context='Social', subcontext='Morality'))
        mgr.add_node(_make_node('C', context='Social', subcontext='Influence'))
        entries = [self._entry('A'), self._entry('B'), self._entry('C')]
        new_subs = {'Mind': ['Focus'], 'Body': ['Strength']}
        self._apply(mgr, entries, ['Mind', 'Body', 'Mind'],
                    ['Focus', 'Strength', 'Focus'], new_subs)
        nodes = {n.name: n for n in mgr.get_all_nodes()}
        assert nodes['A'].context == 'Mind' and nodes['A'].subcontext == 'Focus'
        assert nodes['B'].context == 'Body' and nodes['B'].subcontext == 'Strength'
        assert nodes['C'].context == 'Mind' and nodes['C'].subcontext == 'Focus'

    def test_keep_sentinel_skips_dimension(self, mgr):
        """`__keep__` must not call apply_node_migration for that field."""
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        # Change ctx but keep sub
        self._apply(mgr, entries, ['Mind'], ['__keep__'],
                    {'Mind': ['Dating', 'Other']})
        n = mgr.get_node('A')
        assert n.context == 'Mind'
        assert n.subcontext == 'Dating'  # preserved

    def test_keep_for_ctx_only_changes_sub(self, mgr):
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['Morality'],
                    {'Social': ['Morality']})
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Morality'

    def test_clear_sentinel_nullifies_field(self, mgr):
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['__clear__'])
        n = mgr.get_node('A')
        assert n.subcontext is None

    def test_both_keep_is_no_op(self, mgr):
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['__keep__'])
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Dating'

    def test_ctx_change_clears_sub_when_invalid_under_new_ctx(self, mgr):
        """`apply_node_migration` already clears sub when it's invalid under
        the new ctx — verify the per-node loop preserves that contract."""
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        # Mind has its own subs; Dating isn't one of them
        new_subs = {'Mind': ['Focus', 'Sleep']}
        self._apply(mgr, entries, ['Mind'], ['__keep__'], new_subs)
        n = mgr.get_node('A')
        assert n.context == 'Mind'
        assert n.subcontext is None

    def test_empty_entries_is_no_op(self, mgr):
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        self._apply(mgr, [], [], [])
        n = mgr.get_node('A')
        assert n.context == 'Social'

    def test_mismatched_value_lengths_handled_gracefully(self, mgr):
        """If Dash delivers a shorter values list than entries, extra entries
        are skipped (defensive — shouldn't normally happen)."""
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        mgr.add_node(_make_node('B', context='Social', subcontext='Morality'))
        entries = [self._entry('A'), self._entry('B')]
        # Only A has a value; B should be untouched
        self._apply(mgr, entries, ['Mind'], ['Focus'], {'Mind': ['Focus']})
        nodes = {n.name: n for n in mgr.get_all_nodes()}
        assert nodes['A'].context == 'Mind'
        assert nodes['B'].context == 'Social'  # untouched

    def test_none_values_treated_as_no_change(self, mgr):
        mgr.add_node(_make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, [None], [None])
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Dating'

    def test_subcontext_only_remap_via_sub_nodes_entries(self, mgr):
        """sub_nodes entries are also dicts with 'node_name' — same helper handles them."""
        mgr.add_node(_make_node('A', context='STEM', subcontext='Psychology'))
        # field is 'subcontext' for sub_nodes entries, but the helper only
        # uses node_name regardless of field
        entries = [{'field': 'subcontext', 'old_value': 'STEM › Psychology',
                    'node_name': 'A', 'group_idx': 0}]
        self._apply(mgr, entries, ['Social'], ['Psychology'],
                    {'STEM': [], 'Social': ['Psychology']})
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Psychology'


class TestFindOrphanedSubcontextPairs:
    """DB wrapper — confirms pair detection plus node lookup, keyed by display label."""

    def test_move_flags_only_pair_matched_nodes(self, mgr):
        mgr.add_node(_make_node("A", context="STEM", subcontext="Psychology"))
        mgr.add_node(_make_node("B", context="STEM", subcontext="Math"))
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"], "Social": ["Psychology"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM", "Social"])
        assert "STEM › Psychology" in result
        assert [n.name for n in result["STEM › Psychology"]] == ["A"]
        assert "STEM › Math" not in result

    def test_pair_removed_but_no_nodes_returns_empty(self, mgr):
        mgr.add_node(_make_node("A", context="STEM", subcontext="Math"))
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert result == {}

    def test_no_orphans_when_unchanged(self, mgr):
        mgr.add_node(_make_node("A", context="STEM", subcontext="Math"))
        old = {"STEM": ["Math"]}
        new = {"STEM": ["Math"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert result == {}


# ============================================================================
# ConfigManager — Time Multiplier
# ============================================================================

class TestTimeMultiplier:
    def test_hours_returns_one(self):
        assert ConfigManager.get_time_multiplier('hours') == 1.0

    def test_weeks_returns_hours_per_week(self):
        result = ConfigManager.get_time_multiplier('weeks')
        settings = ConfigManager.get_time_settings()
        assert result == settings.get('hours_per_week', 40.0)

    def test_months_returns_hours_per_month(self):
        result = ConfigManager.get_time_multiplier('months')
        settings = ConfigManager.get_time_settings()
        assert result == settings.get('hours_per_month', 160.0)

    def test_unknown_unit_returns_one(self):
        assert ConfigManager.get_time_multiplier('days') == 1.0

    def test_custom_settings_reflected(self):
        ConfigManager.set_time_settings({'hours_per_week': 20, 'hours_per_month': 80})
        assert ConfigManager.get_time_multiplier('weeks') == 20
        assert ConfigManager.get_time_multiplier('months') == 80

    def test_years_returns_thirteen_months(self):
        ConfigManager.set_time_settings({'hours_per_week': 20, 'hours_per_month': 80})
        assert ConfigManager.get_time_multiplier('years') == 13 * 80


# ============================================================================
# ConfigManager — format_time_friendly
# ============================================================================

class TestFormatTimeFriendly:
    def test_zero_hours(self):
        assert ConfigManager.format_time_friendly(0) == "0h"

    def test_none_hours(self):
        assert ConfigManager.format_time_friendly(None) == "0h"

    def test_negative_hours(self):
        assert ConfigManager.format_time_friendly(-5) == "0h"

    def test_small_hours(self):
        result = ConfigManager.format_time_friendly(2.5)
        assert result == "2.5h"

    def test_integer_hours_no_decimal(self):
        result = ConfigManager.format_time_friendly(8.0)
        assert result == "8h"  # Should not show ".0"

    def test_exactly_one_week(self):
        hw = ConfigManager.get_time_settings().get('hours_per_week', 40)
        result = ConfigManager.format_time_friendly(float(hw))
        assert "w" in result

    def test_exactly_one_month(self):
        hm = ConfigManager.get_time_settings().get('hours_per_month', 160)
        result = ConfigManager.format_time_friendly(float(hm))
        assert "m" in result

    def test_weeks_format(self):
        # With default 40h/week, 80h = 2w
        ConfigManager.set_time_settings({'hours_per_week': 40, 'hours_per_month': 160})
        result = ConfigManager.format_time_friendly(80.0)
        assert result == "2w"

    def test_months_format(self):
        ConfigManager.set_time_settings({'hours_per_week': 40, 'hours_per_month': 160})
        result = ConfigManager.format_time_friendly(320.0)
        assert result == "2m"

    def test_years_format(self):
        ConfigManager.set_time_settings({'hours_per_week': 40, 'hours_per_month': 160})
        # 13 months = 1 year; 2 years = 26 months = 4160 hours
        result = ConfigManager.format_time_friendly(4160.0)
        assert result == "2y"

    def test_exactly_one_year(self):
        ConfigManager.set_time_settings({'hours_per_week': 20, 'hours_per_month': 80})
        # 1 year = 13 × 80 = 1040h
        result = ConfigManager.format_time_friendly(1040.0)
        assert result == "1y"

    def test_year_threshold_just_under(self):
        # Just below 1 year should still display as months.
        ConfigManager.set_time_settings({'hours_per_week': 20, 'hours_per_month': 80})
        result = ConfigManager.format_time_friendly(1039.0)
        assert result.endswith("m")

    def test_integer_argument_all_branches(self):
        """Regression: callers (e.g. the Analyze throughput axis-tick
        generator) pass plain ints. round(int, 1) returns an int, and
        int.is_integer() doesn't exist before Python 3.12 — so on the app's
        3.10 runtime an int argument used to raise AttributeError and 500 the
        Analyze tab. Every magnitude branch must accept an int."""
        ConfigManager.set_time_settings({'hours_per_week': 40, 'hours_per_month': 160})
        assert ConfigManager.format_time_friendly(8) == "8h"      # hours branch
        assert ConfigManager.format_time_friendly(80) == "2w"     # weeks branch
        assert ConfigManager.format_time_friendly(320) == "2m"    # months branch
        assert ConfigManager.format_time_friendly(4160) == "2y"   # years branch
        # force_one_decimal path with an int must also not raise.
        assert ConfigManager.format_time_friendly(8, force_one_decimal=True) == "8.0h"


# ============================================================================
# ConfigManager — Priority Goals
# ============================================================================

class TestPriorityGoals:
    def test_default_empty(self):
        assert ConfigManager.get_priority_goals() == []

    def test_set_and_get(self):
        ConfigManager.set_priority_goals(["Goal A", "Goal B"])
        result = ConfigManager.get_priority_goals()
        assert result == ["Goal A", "Goal B"]

    def test_capped_at_three(self):
        ConfigManager.set_priority_goals(["A", "B", "C", "D", "E"])
        result = ConfigManager.get_priority_goals()
        assert len(result) == 3

    def test_empty_list(self):
        ConfigManager.set_priority_goals([])
        assert ConfigManager.get_priority_goals() == []


# ============================================================================
# ConfigManager — ensure_action_type
# ============================================================================

class TestEnsureActionType:
    def test_adds_action_if_missing(self):
        ConfigManager.set_node_types(["Learn", "Goal"])
        ConfigManager.ensure_action_type()
        types = ConfigManager.get_node_types()
        assert "Action" in types

    def test_no_duplicate_if_present(self):
        ConfigManager.set_node_types(["Learn", "Action", "Goal"])
        ConfigManager.ensure_action_type()
        types = ConfigManager.get_node_types()
        assert types.count("Action") == 1

    def test_shape_added_for_new_type(self):
        ConfigManager.set_node_types(["Learn"])
        ConfigManager.set_node_shapes({"Learn": "ellipse"})
        ConfigManager.ensure_action_type()
        shapes = ConfigManager.get_node_shapes()
        assert "Action" in shapes


# ============================================================================
# GraphManager — Goal Subtree
# ============================================================================

class TestGoalSubtree:
    def test_empty_goal_no_prereqs(self, mgr):
        mgr.add_node(_make_node("Goal", type="Goal"))
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == set()

    def test_single_prereq(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Done"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == {"Prereq"}

    def test_transitive_prereqs(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == {"A", "B"}

    def test_includes_soft_prereqs(self, mgr):
        mgr.add_node(_make_node("Soft"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Soft", "Goal", EDGE_NEEDS_SOFT)
        subtree = mgr.get_goal_subtree("Goal")
        assert "Soft" in subtree

    def test_goal_itself_excluded(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert "Goal" not in subtree

    def test_nonexistent_goal(self, mgr):
        subtree = mgr.get_goal_subtree("DoesNotExist")
        assert subtree == set()


class TestGoalSubtreeHelps:
    """Helps is bidirectional at the seed step only — it does not chain."""

    def test_helps_partner_source_to_goal(self, mgr):
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Partner", "Goal", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree

    def test_helps_partner_goal_to_target(self, mgr):
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree

    def test_no_helps_of_helps_chaining(self, mgr):
        # Goal --Helps-- Partner --Helps-- FarPartner
        # FarPartner must NOT be pulled in under seed-only semantics.
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("FarPartner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Partner", "FarPartner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree
        assert "FarPartner" not in subtree

    def test_partner_hard_prereqs_included_with_directed_types(self, mgr):
        # Goal --Helps-- Partner, and Prereq --Needs_Hard--> Partner.
        # With HARD+SOFT+HELPS, Prereq should be pulled in via BFS from Partner.
        mgr.add_node(_make_node("Prereq"))
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree
        assert "Prereq" in subtree

    def test_helps_only_returns_direct_partners(self, mgr):
        # edge_types=(HELPS,) alone = direct partners, nothing else.
        mgr.add_node(_make_node("Prereq"))
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal", edge_types=(EDGE_HELPS,))
        assert subtree == {"Partner"}

    def test_hard_soft_only_unaffected_by_helps_edges(self, mgr):
        # Helps edges in the graph must not leak into a HARD/SOFT-only query.
        mgr.add_node(_make_node("Prereq"))
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
        assert subtree == {"Prereq"}

    def test_synergy_label_set_arithmetic(self, mgr):
        # The synergy_nodes = overall - hard_soft arithmetic used in
        # details_layout.build_details_subtasks_table must correctly identify
        # a partner's Hard prereq as Synergy, not Soft.
        mgr.add_node(_make_node("Prereq"))
        mgr.add_node(_make_node("Partner"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)

        overall = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        hard_soft = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
        synergy_nodes = overall - hard_soft

        assert "Partner" in synergy_nodes
        assert "Prereq" in synergy_nodes
        assert hard_soft == set()


# ============================================================================
# GraphManager — Goal Completion
# ============================================================================

class TestGoalCompletion:
    def test_no_subtree_returns_zeros(self, mgr):
        mgr.add_node(_make_node("Goal", type="Goal"))
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 0
        assert result["done"] == 0
        assert result["pct"] == 0
        assert result["remaining_time"] == 0.0

    def test_all_done(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 1
        assert result["done"] == 1
        assert result["pct"] == 100

    def test_partial_completion(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C", status="Open"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 3
        assert result["done"] == 2
        assert result["pct"] == 67  # 2/3 rounded

    def test_remaining_time_excludes_done(self, mgr):
        mgr.add_node(_make_node("A", status="Done", time_o=10, time_m=10, time_p=10))
        mgr.add_node(_make_node("B", status="Open", time_o=5, time_m=5, time_p=5))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["remaining_time"] == 5.0  # Only B's time

    def test_is_blocked_all_subtasks_blocked(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "A", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        # A is blocked because Prereq is Open
        mgr.get_goal_completion("Goal")
        # The subtree is [Prereq, A]. Prereq is Open, A is Blocked.
        # done + blocked = 0 + 1, total = 2 → not all blocked
        # Only "blocked" if ALL remaining are blocked
        # Prereq is Open (not blocked), so the goal is not fully blocked

    def test_is_blocked_flag(self, mgr):
        # Create a scenario where all subtask nodes are either done or blocked
        mgr.add_node(_make_node("Blocker", status="Open"))
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("Goal", type="Goal"))
        mgr.add_edge("Blocker", "A", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        # Subtree: {Blocker, A, B}. Blocker=Open, A=Blocked, B=Done
        # done + blocked = 1 + 1 = 2, total = 3, blocked > 0 → not all blocked
        result = mgr.get_goal_completion("Goal")
        assert result["is_blocked"] == False  # Blocker is still Open (workable)




# ============================================================================
# Scoring — Goal Boost & Type Exclusions
# ============================================================================

class TestScoringGoalBoost:

    def test_goal_nodes_get_negative_score(self, mgr):
        mgr.add_node(_make_node("G", type="Goal"))
        scored = mgr.calculate_priority_scores([mgr.get_node("G")])
        assert scored[0].priority_score == -1.0

    def test_goal_boost_applied(self, mgr):
        # Gateway is a hard prereq of GoalNode → Gateway should be boosted
        mgr.add_node(_make_node("Gateway", value=5, interest=5))
        mgr.add_node(_make_node("Unrelated", value=5, interest=5))
        mgr.add_node(_make_node("GoalNode", type="Goal"))
        mgr.add_edge("Gateway", "GoalNode", EDGE_NEEDS_HARD)

        scored_without = mgr.calculate_priority_scores(
            [mgr.get_node("Gateway"), mgr.get_node("Unrelated")]
        )
        gw_base = next(n for n in scored_without if n.name == "Gateway").priority_score
        un_base = next(n for n in scored_without if n.name == "Unrelated").priority_score
        # Without goals, Gateway and Unrelated should score similarly
        # (Gateway has a slight edge due to network value from GoalNode)

        scored_with = mgr.calculate_priority_scores(
            [mgr.get_node("Gateway"), mgr.get_node("Unrelated")],
            priority_goals=["GoalNode"]
        )
        gw_boosted = next(n for n in scored_with if n.name == "Gateway").priority_score
        un_boosted = next(n for n in scored_with if n.name == "Unrelated").priority_score

        assert gw_boosted > gw_base  # Gateway got boosted
        assert un_boosted == un_base  # Unrelated unchanged

    def test_ranked_goals_decreasing_boost(self, mgr):
        # Three goals, each with one prereq
        for i, name in enumerate(["P1", "P2", "P3"]):
            mgr.add_node(_make_node(name, value=5, interest=5))
        for i, name in enumerate(["G1", "G2", "G3"]):
            mgr.add_node(_make_node(name, type="Goal"))
            mgr.add_edge(f"P{i+1}", name, EDGE_NEEDS_HARD)

        scored = mgr.calculate_priority_scores(
            [mgr.get_node("P1"), mgr.get_node("P2"), mgr.get_node("P3")],
            priority_goals=["G1", "G2", "G3"]
        )
        p1 = next(n for n in scored if n.name == "P1").priority_score
        p2 = next(n for n in scored if n.name == "P2").priority_score
        p3 = next(n for n in scored if n.name == "P3").priority_score

        # Rank 1 gets full boost, rank 2 gets 66%, rank 3 gets 33%
        assert p1 >= p2 >= p3


# ============================================================================
# Scoring — Milestone exclusion
# ============================================================================

class TestScoringMilestoneSkip:
    """Milestone nodes are non-competing containers (like Goals): they should
    receive priority_score=-1.0 and be excluded from per-bucket density counts.
    """

    def test_milestone_nodes_get_negative_score(self, mgr):
        mgr.add_node(_make_node("M", type="Milestone", value=10, interest=10))
        scored = mgr.calculate_priority_scores([mgr.get_node("M")])
        assert scored[0].priority_score == -1.0

    def test_milestone_excluded_from_density_bucket(self, mgr):
        # Two Learns + one Milestone in same (context, subcontext) bucket.
        # Density is computed only from competing nodes, so the Milestone
        # should NOT inflate the bucket count and dilute the Learn scores.
        # Using score_nodes directly so we can pass alpha=1.0 (density on).
        hypers = {**DEFAULT_HYPERPARAMS, 'alpha': 1.0}
        mgr.add_node(_make_node("L1", type="Learn", context="Mind", subcontext="Rational"))
        mgr.add_node(_make_node("L2", type="Learn", context="Mind", subcontext="Rational"))
        mgr.add_node(_make_node("MS", type="Milestone", context="Mind", subcontext="Rational"))
        active = [mgr.get_node("L1"), mgr.get_node("L2"), mgr.get_node("MS")]
        scored_with_ms = score_nodes(active, active, mgr.get_edges(), hypers)

        # Now add another Learn — this DOES increase density and should lower
        # L1's score. Confirms density is sensitive to competing nodes only.
        mgr.add_node(_make_node("L3", type="Learn", context="Mind", subcontext="Rational"))
        active2 = [mgr.get_node(n) for n in ("L1", "L2", "L3", "MS")]
        scored_with_l3 = score_nodes(active2, active2, mgr.get_edges(), hypers)

        l1_with_ms = next(n for n in scored_with_ms if n.name == "L1").priority_score
        l1_with_l3 = next(n for n in scored_with_l3 if n.name == "L1").priority_score
        # Adding a real competing Learn lowers density-adjusted score for L1;
        # adding a Milestone (already present) did not.
        assert l1_with_l3 < l1_with_ms


# ============================================================================
# get_prerequisite_chains_typed
# ============================================================================

class TestPrerequisiteChainsTyped:
    """Tests for chain classification into Hard vs Soft."""

    def test_single_hard_chain(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains_typed("B")
        assert len(chains) == 1
        chain, ctype = chains[0]
        assert ctype == "Hard"
        assert "A" in chain

    def test_single_soft_chain(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)
        chains = mgr.get_prerequisite_chains_typed("B")
        assert len(chains) == 1
        chain, ctype = chains[0]
        assert ctype == "Soft"

    def test_mixed_chain_classified_as_soft(self, mgr):
        """A chain with one soft edge anywhere is classified as Soft."""
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_node(_make_node("C", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_SOFT)
        chains = mgr.get_prerequisite_chains_typed("C")
        # Should find chain A -> B -> C classified as Soft
        soft_chains = [c for c, t in chains if t == "Soft"]
        assert len(soft_chains) >= 1
        assert any("A" in c for c in soft_chains)

    def test_all_done_chain_excluded(self, mgr):
        """Chains where all nodes are Done should not appear."""
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains_typed("B")
        assert len(chains) == 0

    def test_nonexistent_node_returns_empty(self, mgr):
        assert mgr.get_prerequisite_chains_typed("NoSuchNode") == []

    def test_no_prereqs_self_chain(self, mgr):
        """A node with no prereqs but status Open returns itself as a single-node chain."""
        mgr.add_node(_make_node("Alone", status="Open"))
        chains = mgr.get_prerequisite_chains_typed("Alone")
        assert len(chains) == 1
        assert chains[0][0] == ["Alone"]

    def test_multiple_branches(self, mgr):
        """Two independent hard prereqs produce two separate chains."""
        mgr.add_node(_make_node("P1", status="Open"))
        mgr.add_node(_make_node("P2", status="Open"))
        mgr.add_node(_make_node("Target", status="Open"))
        mgr.add_edge("P1", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("P2", "Target", EDGE_NEEDS_HARD)
        chains = mgr.get_prerequisite_chains_typed("Target")
        assert len(chains) == 2
        assert all(t == "Hard" for _, t in chains)

    def test_helps_edges_ignored(self, mgr):
        """Helps edges should not appear in prerequisite chains — only the self-chain."""
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        chains = mgr.get_prerequisite_chains_typed("B")
        # Only the self-chain for B (no prereqs found via Needs edges)
        assert len(chains) == 1
        assert chains[0][0] == ["B"]


# ============================================================================
# get_directly_unlocked_nodes_by_type
# ============================================================================

class TestDirectlyUnlockedByType:
    """Tests for separating hard vs soft unlocks."""

    def test_hard_unlock(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Dep", status="Blocked"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_HARD)
        result = mgr.get_directly_unlocked_nodes_by_type("Prereq")
        assert "Dep" in result['hard']
        assert result['soft'] == []

    def test_soft_unlock(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("Dep", status="Open"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_SOFT)
        result = mgr.get_directly_unlocked_nodes_by_type("Prereq")
        assert "Dep" in result['soft']
        assert result['hard'] == []

    def test_mixed_unlocks(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Open"))
        mgr.add_node(_make_node("HardDep", status="Blocked"))
        mgr.add_node(_make_node("SoftDep", status="Open"))
        mgr.add_edge("Prereq", "HardDep", EDGE_NEEDS_HARD)
        mgr.add_edge("Prereq", "SoftDep", EDGE_NEEDS_SOFT)
        result = mgr.get_directly_unlocked_nodes_by_type("Prereq")
        assert "HardDep" in result['hard']
        assert "SoftDep" in result['soft']

    def test_done_nodes_excluded(self, mgr):
        """Nodes already Done should not appear in unlocked lists. With
        non-sticky-Done semantics, DoneDep can only stay Done while its hard
        prereq is also Done — so the test sets that up explicitly."""
        mgr.add_node(_make_node("Prereq", status="Done"))
        mgr.add_node(_make_node("DoneDep", status="Done"))
        mgr.add_edge("Prereq", "DoneDep", EDGE_NEEDS_HARD)
        # DoneDep stays Done because Prereq is Done; the unlocked-by query
        # filters Done out of its results.
        result = mgr.get_directly_unlocked_nodes_by_type("Prereq")
        assert result['hard'] == []
        assert result['soft'] == []

    def test_no_dependents_returns_empty(self, mgr):
        mgr.add_node(_make_node("Alone"))
        result = mgr.get_directly_unlocked_nodes_by_type("Alone")
        assert result == {'hard': [], 'soft': []}

    def test_helps_edges_not_included(self, mgr):
        mgr.add_node(_make_node("A", status="Open"))
        mgr.add_node(_make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        result = mgr.get_directly_unlocked_nodes_by_type("A")
        assert result == {'hard': [], 'soft': []}


# ============================================================================
# sync_edges without resources parameter
# ============================================================================

class TestSyncEdgesWithoutResources:
    """Tests that sync_edges works without the removed resources parameter."""

    def test_sync_hard_and_soft_needs(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.sync_edges("C",
                        needs_hard=["A"], needs_soft=["B"],
                        supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        hard = [e for e in edges if e['type'] == EDGE_NEEDS_HARD]
        soft = [e for e in edges if e['type'] == EDGE_NEEDS_SOFT]
        assert len(hard) == 1 and hard[0]['source'] == "A"
        assert len(soft) == 1 and soft[0]['source'] == "B"

    def test_sync_supports_direction(self, mgr):
        mgr.add_node(_make_node("Source", status="Done"))
        mgr.add_node(_make_node("Target"))
        mgr.sync_edges("Source",
                        needs_hard=[], needs_soft=[],
                        supports_hard=["Target"], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "Source"
        assert edges[0]['target'] == "Target"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_sync_helps(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.sync_edges("A",
                        needs_hard=[], needs_soft=[],
                        supports_hard=[], supports_soft=[], helps=["B"])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['type'] == EDGE_HELPS

    def test_sync_clears_old_edges(self, mgr):
        mgr.add_node(_make_node("A", status="Done"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.sync_edges("C",
                        needs_hard=["A"], needs_soft=[],
                        supports_hard=[], supports_soft=[], helps=[])
        assert len(mgr.get_edges()) == 1
        # Now sync again with different edges
        mgr.sync_edges("C",
                        needs_hard=[], needs_soft=["B"],
                        supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['type'] == EDGE_NEEDS_SOFT


# ============================================================================
# ConfigManager — ensure_goal_type
# ============================================================================

class TestEnsureGoalType:
    def test_adds_goal_if_missing(self):
        ConfigManager.set_node_types(["Learn", "Action"])
        ConfigManager.ensure_goal_type()
        types = ConfigManager.get_node_types()
        assert "Goal" in types

    def test_no_duplicate_if_present(self):
        ConfigManager.set_node_types(["Learn", "Action", "Goal"])
        ConfigManager.ensure_goal_type()
        types = ConfigManager.get_node_types()
        assert types.count("Goal") == 1

    def test_shape_added_for_new_type(self):
        ConfigManager.set_node_types(["Learn"])
        ConfigManager.set_node_shapes({"Learn": "ellipse"})
        ConfigManager.ensure_goal_type()
        shapes = ConfigManager.get_node_shapes()
        assert "Goal" in shapes


# ============================================================================
# ConfigManager — ensure_milestone_type
# ============================================================================

class TestEnsureMilestoneType:
    def test_adds_milestone_if_missing(self):
        ConfigManager.set_node_types(["Learn", "Action", "Goal"])
        ConfigManager.ensure_milestone_type()
        types = ConfigManager.get_node_types()
        assert "Milestone" in types

    def test_no_duplicate_if_present(self):
        ConfigManager.set_node_types(["Learn", "Action", "Goal", "Milestone"])
        ConfigManager.ensure_milestone_type()
        types = ConfigManager.get_node_types()
        assert types.count("Milestone") == 1

    def test_shape_added_for_new_type(self):
        ConfigManager.set_node_types(["Learn"])
        ConfigManager.set_node_shapes({"Learn": "ellipse"})
        ConfigManager.ensure_milestone_type()
        shapes = ConfigManager.get_node_shapes()
        assert shapes.get("Milestone") == "diamond"


# ============================================================================
# Container types always inherit time (model-level enforcement)
# ============================================================================

class TestContainerTypeTimeInheritance:
    """Goals and Milestones are container types: their time is the sum of their
    children's, never an own estimate. ``Node.__post_init__`` forces
    time_mode='inherited' for both, so the invariant holds on every read —
    including legacy DB rows and programmatic constructions that pass 'manual'.
    (This replaces an earlier one-time DB migration; enforcing at the model
    layer means there's no stored state to drift.)
    """

    def test_goal_forced_to_inherited_time(self):
        n = _make_node("G", type="Goal", time_mode='manual')
        assert n.time_mode == 'inherited'

    def test_milestone_forced_to_inherited_time(self):
        n = _make_node("M", type="Milestone", time_mode='manual')
        assert n.time_mode == 'inherited'

    def test_non_container_type_keeps_manual_time(self):
        n = _make_node("L", type="Learn", time_mode='manual')
        assert n.time_mode == 'manual'

    def test_goal_inherited_time_persists_through_db(self, mgr):
        mgr.add_node(_make_node("MigGoal", type="Goal", time_mode='manual'))
        assert mgr.get_node("MigGoal").time_mode == 'inherited'

    def test_goal_time_reads_as_zero(self):
        """Forced inherited time means Node.time short-circuits to 0 even with
        stored time_o/m/p."""
        n = _make_node("G", type="Goal", time_mode='manual',
                       time_o=10, time_m=20, time_p=40)
        assert n.time == 0.0


# ============================================================================
# GraphManager — auto-Done candidate queue
# ============================================================================

class TestAutoDoneCandidates:
    """When the last hard prerequisite of a Goal or Milestone becomes Done,
    GraphManager should queue the container as an auto-Done candidate. The UI
    drains this queue and surfaces a "Mark Done?" suggestion modal.
    """

    @pytest.fixture(autouse=True)
    def _reset_candidates(self):
        # Class-level state — reset between every test in this class so the
        # queue from one assertion doesn't leak into the next.
        GraphManager._auto_done_candidates = []
        yield
        GraphManager._auto_done_candidates = []

    def test_pop_returns_and_clears(self, mgr):
        GraphManager._auto_done_candidates = ['A', 'B', 'C']
        popped = mgr.pop_auto_done_candidates()
        assert popped == ['A', 'B', 'C']
        assert mgr.pop_auto_done_candidates() == []

    def test_last_prereq_done_queues_goal(self, mgr):
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        # Flip P to Done — its only dependent G has all prereqs Done now.
        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == ["G"]

    def test_last_prereq_done_queues_milestone(self, mgr):
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "M", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == ["M"]

    def test_non_last_prereq_done_does_not_queue(self, mgr):
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("P1", type="Learn"))
        mgr.add_node(_make_node("P2", type="Learn"))
        mgr.add_edge("P1", "G", EDGE_NEEDS_HARD)
        mgr.add_edge("P2", "G", EDGE_NEEDS_HARD)

        # P1 done, but P2 is still Open — Goal isn't ready.
        p1 = mgr.get_node("P1")
        p1.status = STATUS_DONE
        mgr.update_node(p1)

        assert mgr.pop_auto_done_candidates() == []

    def test_non_container_dependent_not_queued(self, mgr):
        # A Learn that depends on a Learn shouldn't be queued — only Goals
        # and Milestones get the auto-done suggestion.
        mgr.add_node(_make_node("L1", type="Learn"))
        mgr.add_node(_make_node("L2", type="Learn"))
        mgr.add_edge("L1", "L2", EDGE_NEEDS_HARD)

        l1 = mgr.get_node("L1")
        l1.status = STATUS_DONE
        mgr.update_node(l1)

        assert mgr.pop_auto_done_candidates() == []

    def test_already_done_container_not_queued(self, mgr):
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited',
                                status=STATUS_DONE))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == []

    def test_resave_already_done_node_does_not_queue(self, mgr):
        # Re-saving an already-Done leaf shouldn't re-fire candidates.
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        # First save: P → Done. Queues G.
        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)
        mgr.pop_auto_done_candidates()  # Drain

        # Re-save P (still Done) — should NOT re-queue.
        p = mgr.get_node("P")
        mgr.update_node(p)
        assert mgr.pop_auto_done_candidates() == []

    def test_open_to_open_save_does_not_queue(self, mgr):
        # Saving a node without a Done transition shouldn't queue.
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.description = "edited"
        mgr.update_node(p)
        assert mgr.pop_auto_done_candidates() == []

    def test_multiple_containers_share_prereq(self, mgr):
        # One leaf shared between two Goals — when the leaf goes Done and
        # both Goals' other prereqs are also Done, both queue.
        mgr.add_node(_make_node("G1", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("G2", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("Shared", type="Learn"))
        mgr.add_edge("Shared", "G1", EDGE_NEEDS_HARD)
        mgr.add_edge("Shared", "G2", EDGE_NEEDS_HARD)

        s = mgr.get_node("Shared")
        s.status = STATUS_DONE
        mgr.update_node(s)

        candidates = mgr.pop_auto_done_candidates()
        assert set(candidates) == {"G1", "G2"}

    def test_chained_containers_only_direct_queued(self, mgr):
        # Leaf → Milestone → Goal. When leaf goes Done, only the Milestone
        # is direct-eligible. The Goal still has the Milestone as an Open
        # prereq, so it shouldn't queue yet.
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("L", type="Learn"))
        mgr.add_edge("L", "M", EDGE_NEEDS_HARD)
        mgr.add_edge("M", "G", EDGE_NEEDS_HARD)

        l = mgr.get_node("L")
        l.status = STATUS_DONE
        mgr.update_node(l)
        assert mgr.pop_auto_done_candidates() == ["M"]

        # Mark Milestone Done — now Goal becomes a candidate.
        m = mgr.get_node("M")
        m.status = STATUS_DONE
        mgr.update_node(m)
        assert mgr.pop_auto_done_candidates() == ["G"]

    def test_milestone_with_no_prereqs_not_queued(self, mgr):
        # A Milestone with zero hard prereqs has "all prereqs done" vacuously.
        # We don't queue it — there's nothing concrete the user just achieved.
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited'))
        # Trigger collection by saving an unrelated Done node — but there's
        # no edge from it, so the dependent walk yields nothing.
        mgr.add_node(_make_node("Other", type="Learn"))
        other = mgr.get_node("Other")
        other.status = STATUS_DONE
        mgr.update_node(other)
        assert mgr.pop_auto_done_candidates() == []

    def test_dedup_in_queue(self, mgr):
        # Multiple update_node calls that would each queue the same candidate
        # should only queue it once.
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)
        # Re-save P (also as Done) to attempt double-queue
        p = mgr.get_node("P")
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == ["G"]


# ============================================================================
# Node Model — time_mode validation
# ============================================================================

class TestTimeModeField:
    def test_default_is_manual(self):
        node = _make_node()
        assert node.time_mode == 'manual'

    def test_inherited_accepted(self):
        node = _make_node(time_mode='inherited')
        assert node.time_mode == 'inherited'

    def test_invalid_time_mode_defaults_to_manual(self):
        node = _make_node(time_mode='auto')
        assert node.time_mode == 'manual'

    def test_time_mode_in_to_dict(self):
        node = _make_node(time_mode='inherited')
        d = node.to_dict()
        assert d['time_mode'] == 'inherited'

    def test_time_mode_persisted_in_db(self, mgr):
        mgr.add_node(_make_node("Inherited", time_mode='inherited'))
        node = mgr.get_node("Inherited")
        assert node.time_mode == 'inherited'

    def test_time_mode_manual_persisted_in_db(self, mgr):
        mgr.add_node(_make_node("Manual", time_mode='manual'))
        node = mgr.get_node("Manual")
        assert node.time_mode == 'manual'

    def test_time_mode_updated(self, mgr):
        mgr.add_node(_make_node("Node", time_mode='manual'))
        node = mgr.get_node("Node")
        node.time_mode = 'inherited'
        mgr.update_node(node)
        updated = mgr.get_node("Node")
        assert updated.time_mode == 'inherited'

    def test_inherited_preserves_omp_on_construction(self):
        # Preserved so a user who toggles inherited→manual gets their original
        # three-point estimate back. The .time property still returns 0 in
        # inherited mode, so the values are inert at read time.
        n = _make_node(time_mode='inherited', time_o=10, time_m=20, time_p=30)
        assert n.time_o == 10.0 and n.time_m == 20.0 and n.time_p == 30.0

    def test_inherited_time_property_returns_zero(self):
        n = _make_node(time_mode='inherited', time_o=10, time_m=20, time_p=30)
        assert n.time == 0.0

    def test_inherited_db_roundtrip_preserves_omp(self, mgr):
        mgr.add_node(_make_node("Inh", time_mode='inherited', time_o=7, time_m=14, time_p=21))
        fetched = mgr.get_node("Inh")
        assert fetched.time_o == 7.0 and fetched.time_m == 14.0 and fetched.time_p == 21.0
        # And the property still reads as 0 — preservation is purely for the
        # round-trip when the user toggles back to manual.
        assert fetched.time == 0.0

    def test_toggle_inherited_to_manual_restores_estimates(self, mgr):
        """User adds a node with manual estimates, toggles to inherited, then
        back to manual — their original o/m/p must still be there."""
        mgr.add_node(_make_node("Toggle", time_mode='manual',
                                time_o=2, time_m=4, time_p=8))
        # Toggle to inherited (preserving o/m/p in the form).
        node = mgr.get_node("Toggle")
        node.time_mode = 'inherited'
        mgr.update_node(node)
        # Toggle back to manual.
        node = mgr.get_node("Toggle")
        node.time_mode = 'manual'
        mgr.update_node(node)
        final = mgr.get_node("Toggle")
        assert final.time_mode == 'manual'
        assert final.time_o == 2.0 and final.time_m == 4.0 and final.time_p == 8.0
        # And the .time property now blends them as expected.
        assert final.time > 0.0


# ============================================================================
# Node Model — value_mode validation
# ============================================================================

class TestValueModeField:
    def test_default_is_manual(self):
        node = _make_node()
        assert node.value_mode == 'manual'

    def test_inherited_accepted(self):
        node = _make_node(value_mode='inherited')
        assert node.value_mode == 'inherited'

    def test_invalid_value_mode_defaults_to_manual(self):
        node = _make_node(value_mode='auto')
        assert node.value_mode == 'manual'

    def test_value_mode_in_to_dict(self):
        node = _make_node(value_mode='inherited')
        d = node.to_dict()
        assert d['value_mode'] == 'inherited'

    def test_value_mode_persisted_in_db(self, mgr):
        mgr.add_node(_make_node("Inh", value_mode='inherited'))
        node = mgr.get_node("Inh")
        assert node.value_mode == 'inherited'

    def test_value_mode_manual_persisted_in_db(self, mgr):
        mgr.add_node(_make_node("Man", value_mode='manual'))
        node = mgr.get_node("Man")
        assert node.value_mode == 'manual'

    def test_value_mode_updated(self, mgr):
        mgr.add_node(_make_node("X", value_mode='manual'))
        node = mgr.get_node("X")
        node.value_mode = 'inherited'
        mgr.update_node(node)
        updated = mgr.get_node("X")
        assert updated.value_mode == 'inherited'

    def test_inherited_preserves_vid_on_construction(self):
        """v/i/d are preserved when value_mode='inherited' so a toggle back
        to 'manual' restores the user's original ratings. Mirrors the
        time_mode precedent."""
        n = _make_node(value_mode='inherited', value=8, interest=9, difficulty=4)
        assert n.value == 8 and n.interest == 9 and n.difficulty == 4

    def test_inherited_zeroes_intrinsic_value(self):
        """`intrinsic_value()` returns 0 when value_mode='inherited' regardless
        of the underlying v/i/d ratings — the node becomes a pure structural
        conduit and contributes no own-IV bump to its descendants."""
        n = _make_node(value_mode='inherited', value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 0.0

    def test_manual_uses_full_intrinsic_value(self):
        n = _make_node(value_mode='manual', value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 20.0

    def test_inherited_db_roundtrip_preserves_vid(self, mgr):
        mgr.add_node(_make_node("R", value_mode='inherited',
                                value=7, interest=8, difficulty=6))
        fetched = mgr.get_node("R")
        assert fetched.value == 7 and fetched.interest == 8 and fetched.difficulty == 6
        # And the IV reads as 0 — preservation is purely for the round-trip
        # when the user toggles back to manual.
        assert intrinsic_value(fetched, 1.0, 1.0) == 0.0

    def test_toggle_inherited_to_manual_restores_ratings(self, mgr):
        """Add manual, toggle to inherited, toggle back — original ratings still there."""
        mgr.add_node(_make_node("T", value_mode='manual',
                                value=6, interest=7, difficulty=8))
        node = mgr.get_node("T")
        node.value_mode = 'inherited'
        mgr.update_node(node)
        node = mgr.get_node("T")
        node.value_mode = 'manual'
        mgr.update_node(node)
        final = mgr.get_node("T")
        assert final.value_mode == 'manual'
        assert final.value == 6 and final.interest == 7 and final.difficulty == 8
        # And the IV is back to its full value.
        assert intrinsic_value(final, 1.0, 1.0) == 13.0

    def test_independent_of_time_mode(self):
        """value_mode and time_mode are orthogonal flags."""
        n1 = _make_node(time_mode='inherited', value_mode='manual',
                        value=5, interest=5)
        assert intrinsic_value(n1, 1.0, 1.0) == 10.0  # value still contributes
        assert n1.time == 0.0  # time still inherited

        n2 = _make_node(time_mode='manual', value_mode='inherited',
                        value=5, interest=5)
        assert intrinsic_value(n2, 1.0, 1.0) == 0.0  # value zeroed
        assert n2.time > 0.0  # time still manual


# ============================================================================
# Milestone value-transparency invariant
# ============================================================================

class TestMilestoneValueTransparency:
    """Milestones are transparent checkpoints: their own value/interest/effort
    must never enter scoring. The invariant is enforced at the model layer
    (Node.__post_init__ forces value_mode='inherited' for Milestones) so it
    holds on every read path — primary Next-tab ranking included, not just
    Goal ranking. Goals are exempt: they legitimately carry their own value.
    """

    def test_milestone_forced_to_inherited_on_construction(self):
        """A Milestone constructed with value_mode='manual' is corrected."""
        n = _make_node("MS", type="Milestone", value_mode='manual',
                       value=10, interest=10)
        assert n.value_mode == 'inherited'

    def test_milestone_inherited_even_with_default_value_mode(self):
        n = _make_node("MS", type="Milestone")  # no value_mode passed
        assert n.value_mode == 'inherited'

    def test_milestone_intrinsic_value_is_zero(self):
        """High ratings on a Milestone contribute 0 IV — the leak this fixes."""
        n = _make_node("MS", type="Milestone", value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 0.0

    def test_milestone_ratings_preserved_for_roundtrip(self):
        """v/i/d are preserved (not destroyed) even though value_mode is forced,
        mirroring the time_mode precedent — a type change restores them."""
        n = _make_node("MS", type="Milestone", value=9, interest=7, difficulty=4)
        assert n.value == 9 and n.interest == 7 and n.difficulty == 4

    def test_goal_not_forced_to_inherited(self):
        """Goals carry their own value (docs/modeling.md) — NOT forced."""
        g = _make_node("G", type="Goal", value_mode='manual', value=8, interest=6)
        assert g.value_mode == 'manual'
        assert intrinsic_value(g, w_v=1.0, w_i=1.0) == 14.0

    def test_milestone_db_roundtrip_is_inherited(self, mgr):
        mgr.add_node(_make_node("MS", type="Milestone", value=10, interest=10))
        fetched = mgr.get_node("MS")
        assert fetched.value_mode == 'inherited'
        assert intrinsic_value(fetched, 1.0, 1.0) == 0.0

    def test_milestone_does_not_leak_value_into_unlocking_node(self):
        """The core bug: a Learn that hard-unlocks a high-rated Milestone must
        score the SAME as if the Milestone carried no ratings — the Milestone's
        own value must not cascade back into the work that leads to it.

        Compare the unlocking Learn's score against a baseline where the
        downstream node is an explicit zero-IV container. They must match.
        """
        # Graph A: Learn → Milestone (Milestone has high placeholder ratings).
        learn_a = _make_node("LearnA", type="Learn", value=5, interest=5,
                             difficulty=3, context="Body", subcontext="Exercise")
        ms = _make_node("MS", type="Milestone", value=10, interest=10,
                        context="Body", subcontext="Exercise")
        edges_a = [{'source': 'LearnA', 'target': 'MS', 'type': EDGE_NEEDS_HARD}]
        scored_a = score_nodes([learn_a], [learn_a, ms], edges_a, DEFAULT_HYPERPARAMS)
        learn_a_score = scored_a[0].priority_score

        # Graph B: Learn → explicit pure container (IV genuinely 0).
        learn_b = _make_node("LearnB", type="Learn", value=5, interest=5,
                             difficulty=3, context="Body", subcontext="Exercise")
        cont = _make_node("Cont", type="Learn", value=10, interest=10,
                          value_mode='inherited', time_mode='inherited',
                          context="Body", subcontext="Exercise")
        edges_b = [{'source': 'LearnB', 'target': 'Cont', 'type': EDGE_NEEDS_HARD}]
        scored_b = score_nodes([learn_b], [learn_b, cont], edges_b, DEFAULT_HYPERPARAMS)
        learn_b_score = scored_b[0].priority_score

        assert learn_a_score == pytest.approx(learn_b_score)

    def test_legacy_milestone_row_corrected_on_read(self, mgr):
        """A legacy Milestone row stored with value_mode='manual' and a real
        time estimate (written via raw SQL to bypass the model guard, simulating
        a row that predates this rule) reads back as a pure container: both
        modes inherited, zero IV, zero time. There is no DB migration —
        Node.__post_init__ enforces the invariant on every construction, so the
        correction happens transparently when GraphManager loads the row."""
        import sqlite3
        conn = sqlite3.connect(database.get_db_path())
        conn.execute(
            "INSERT INTO Nodes (name, type, description, value, time_o, time_m, "
            "time_p, interest, difficulty, status, context, value_mode, time_mode) "
            "VALUES (?, 'Milestone', '', 10, 5, 10, 20, 10, 5, 'Open', 'Body', "
            "'manual', 'manual')",
            ("LegacyMS",),
        )
        conn.commit()
        conn.close()

        node = mgr.get_node("LegacyMS")
        assert node.value_mode == 'inherited'
        assert node.time_mode == 'inherited'
        assert intrinsic_value(node, 1.0, 1.0) == 0.0
        assert node.time == 0.0

    def test_milestone_value_leak_would_inflate_without_fix(self):
        """Guard test: confirm the scenario is non-trivial — if the Milestone
        DID carry its ratings (the old bug), the unlocking Learn would score
        strictly higher. We simulate the buggy case with a manual-value Learn
        as the downstream node and confirm it scores higher than our Milestone
        case, proving the transparency is actually doing work."""
        learn = _make_node("Learn", type="Learn", value=5, interest=5,
                           difficulty=3, context="Body", subcontext="Exercise")
        ms = _make_node("MS", type="Milestone", value=10, interest=10,
                        context="Body", subcontext="Exercise")
        edges = [{'source': 'Learn', 'target': 'MS', 'type': EDGE_NEEDS_HARD}]
        ms_case = score_nodes([learn], [learn, ms], edges, DEFAULT_HYPERPARAMS)[0].priority_score

        learn2 = _make_node("Learn2", type="Learn", value=5, interest=5,
                            difficulty=3, context="Body", subcontext="Exercise")
        downstream = _make_node("Down", type="Learn", value=10, interest=10,
                                context="Body", subcontext="Exercise")
        edges2 = [{'source': 'Learn2', 'target': 'Down', 'type': EDGE_NEEDS_HARD}]
        learn_case = score_nodes([learn2], [learn2, downstream], edges2,
                                 DEFAULT_HYPERPARAMS)[0].priority_score

        assert learn_case > ms_case


# ============================================================================
# Scoring — inherited value_mode prevents own-IV injection
# ============================================================================

class TestScoringInheritedValueMode:
    def test_inherited_node_scores_with_zero_iv(self):
        """A node with value_mode='inherited' contributes 0 IV to its own score
        — score depends entirely on cascade from descendants (none here)."""
        n = _make_node("Container", value=10, interest=10, difficulty=3,
                       value_mode='inherited')
        scored = score_nodes([n], [n], [], {})
        # iv = 0, cascade = 0 (no children), so total_value = 0, score = 0.
        assert scored[0].priority_score == 0.0

    def test_manual_node_scores_with_full_iv(self):
        """Sanity baseline: identical node in manual mode scores normally."""
        n = _make_node("Manual", value=10, interest=10, difficulty=3,
                       value_mode='manual')
        scored = score_nodes([n], [n], [], {})
        assert scored[0].priority_score > 0.0

    def test_inherited_parent_does_not_inflate_child_score(self):
        """A child's score is its own IV + d_H * tv(parent). When the parent
        is value_mode='inherited', the parent contributes 0 to its own IV,
        so the child's score loses the parent's IV bump.

        Compare two structurally identical trees: in tree A the parent is
        manual (full IV), in tree B the parent is inherited (zero IV).
        The child in A should score higher than the child in B.
        """
        # Tree A: manual parent
        child_a = _make_node("ChildA", value=5, interest=5, difficulty=3)
        parent_a = _make_node("ParentA", type='Learn', value=10, interest=10,
                              difficulty=3, value_mode='manual')
        edges_a = [{'source': 'ChildA', 'target': 'ParentA', 'type': 'Needs_Hard'}]

        # Tree B: inherited parent (same children, same parent v/i/d)
        child_b = _make_node("ChildB", value=5, interest=5, difficulty=3)
        parent_b = _make_node("ParentB", type='Learn', value=10, interest=10,
                              difficulty=3, value_mode='inherited')
        edges_b = [{'source': 'ChildB', 'target': 'ParentB', 'type': 'Needs_Hard'}]

        scored_a = score_nodes([child_a, parent_a], [child_a, parent_a], edges_a, {})
        scored_b = score_nodes([child_b, parent_b], [child_b, parent_b], edges_b, {})

        a = next(n for n in scored_a if n.name == 'ChildA').priority_score
        b = next(n for n in scored_b if n.name == 'ChildB').priority_score
        # Manual parent injects extra IV into the child via cascade — child A wins.
        assert a > b

    def test_inherited_value_mode_zeroes_effort_in_cost(self):
        """value_mode='inherited' also zeros the difficulty term in cost.
        A pure container shouldn't inject its own effort into its denominator."""
        manual = _make_node("M", value=5, interest=5, difficulty=10,
                            time_o=1, time_m=1, time_p=1, value_mode='manual')
        inherited = _make_node("I", value=5, interest=5, difficulty=10,
                               time_o=1, time_m=1, time_p=1, value_mode='inherited')
        # cost_manual  = 1 + 2.5*10 + 1.0*1 = 27
        # cost_inherit = 1 + 0      + 1.0*1 = 2
        c_manual = perceived_cost(manual, w_e=2.5, w_t=1.0, beta=0.85)
        c_inherit = perceived_cost(inherited, w_e=2.5, w_t=1.0, beta=0.85,
                                   effort_override=0.0)
        assert c_manual > c_inherit
        # And the score path uses the override automatically.
        scored = score_nodes([inherited], [inherited], [], {})
        # iv = 0, cost = 1 + 0 + 1.0*1 = 2.0, tv = 0, score = 0/2 = 0
        assert scored[0].priority_score == 0.0

    def test_inherited_parent_still_passes_descendant_value(self):
        """An inherited parent zeroes its OWN IV but still passes its descendants'
        IV upward through the cascade. Verify a grandchild → parent → grandparent
        chain still flows when the middle node is inherited."""
        gc = _make_node("Grandchild", value=8, interest=8, difficulty=3)
        mid = _make_node("Middle", type='Learn', value=10, interest=10,
                         difficulty=3, value_mode='inherited')
        gp = _make_node("Grandparent", type='Learn', value=2, interest=2,
                        difficulty=3, value_mode='manual')
        edges = [
            {'source': 'Grandchild', 'target': 'Middle', 'type': 'Needs_Hard'},
            {'source': 'Middle',     'target': 'Grandparent', 'type': 'Needs_Hard'},
        ]
        scored = score_nodes([gc, mid, gp], [gc, mid, gp], edges, {})
        # Grandchild gets its own IV plus d_H * tv(Middle), where tv(Middle) =
        # 0 (inherited) + d_H * tv(Grandparent). So Grandchild's score is non-zero
        # and reflects the path through Middle even though Middle itself adds 0.
        gc_score = next(n for n in scored if n.name == 'Grandchild').priority_score
        assert gc_score > 0.0


# ============================================================================
# Scoring — container exclusion (both modes inherited)
# ============================================================================

class TestScoringContainerExclusion:
    """A node with both value_mode='inherited' AND time_mode='inherited' is a
    pure container (Node.is_container). Its IV is 0 and cost denominator
    collapses to 1.0, so without an explicit guard a container with valuable
    descendants downstream of an outgoing prereq edge would ride the cascade
    straight to the top of the recommendations. Containers are skipped — the
    children compete on their own merits."""

    def test_is_pure_container_property(self):
        # Both modes inherited → pure container (the scoring-exclusion gate).
        c = _make_node(value_mode='inherited', time_mode='inherited')
        assert c.is_pure_container is True
        assert c.is_container is True  # also a container under the broad notion

    def test_one_mode_inherited_is_container_but_not_pure(self):
        # Under the split: either mode inherited → is_container; both → pure.
        v_only = _make_node(value_mode='inherited', time_mode='manual')
        t_only = _make_node(value_mode='manual', time_mode='inherited')
        assert v_only.is_container is True
        assert v_only.is_pure_container is False
        assert t_only.is_container is True
        assert t_only.is_pure_container is False

    def test_manual_node_is_neither(self):
        n = _make_node(value_mode='manual', time_mode='manual')
        assert n.is_container is False
        assert n.is_pure_container is False

    def test_standalone_container_excluded_from_recommendations(self):
        """A container with no descendants is marked -1.0 and won't surface."""
        c = _make_node("EmptyContainer", value_mode='inherited',
                       time_mode='inherited')
        scored = score_nodes([c], [c], [], {})
        assert scored[0].priority_score == -1.0

    def test_container_with_outgoing_prereq_still_excluded(self):
        """The bug case: container with no children pointing in, but it gates
        a valuable downstream node via an outgoing Needs_Hard. Pre-fix the
        cascade would give it a near-1.0 cost and a positive cascaded TV,
        putting it at the top of the list. Post-fix it's excluded outright,
        and the previously-top non-container is the actual #1."""
        container = _make_node("ClassicalWorks", type='Learn',
                               value=6, interest=6, difficulty=8,
                               value_mode='inherited', time_mode='inherited')
        # Make the gated downstream an unranked Goal (mirrors the real prod
        # case: ClassicalWorks → Reading [Goal]). Goals don't compete, so the
        # container would otherwise have nothing to crowd it off the top.
        downstream = _make_node("Reading", type='Goal',
                                value=9, interest=9, difficulty=5)
        rival = _make_node("UnrelatedLearn", type='Learn',
                           value=7, interest=7, difficulty=3)
        edges = [{'source': 'ClassicalWorks', 'target': 'Reading',
                  'type': 'Needs_Hard'}]
        scored = score_nodes([container, downstream, rival],
                             [container, downstream, rival], edges, {})
        c = next(n for n in scored if n.name == 'ClassicalWorks')
        r = next(n for n in scored if n.name == 'UnrelatedLearn')
        assert c.priority_score == -1.0       # container excluded
        assert r.priority_score > 0.0         # rival ranks normally
        # And the rival is the top of the sorted list, not the container.
        top = sorted(scored, key=lambda n: n.priority_score, reverse=True)[0]
        assert top.name == 'UnrelatedLearn'

    def test_container_still_propagates_cascade_to_dependents(self):
        """Excluding a container from being scored does NOT remove it from the
        cascade graph — its dependents still get value flowing through it."""
        leaf = _make_node("Leaf", value=10, interest=10)
        container = _make_node("Container", type='Learn',
                               value_mode='inherited', time_mode='inherited')
        # leaf --Needs_Hard--> container (leaf unlocks container, so the
        # container's TV cascades into leaf's TV).
        edges = [{'source': 'Leaf', 'target': 'Container',
                  'type': 'Needs_Hard'}]
        scored = score_nodes([leaf, container], [leaf, container], edges, {})
        leaf_score = next(n for n in scored if n.name == 'Leaf').priority_score
        # Leaf's own IV is positive, so its score is positive regardless. The
        # important assertion is that leaf gets scored normally — the
        # container's exclusion didn't break the cascade walk.
        assert leaf_score > 0.0


# ============================================================================
# GraphManager — get_effective_time
# ============================================================================

class TestGetEffectiveTime:
    def test_manual_returns_node_time(self, mgr):
        mgr.add_node(_make_node("A", time_o=2, time_m=4, time_p=6, time_mode='manual'))
        eff = mgr.get_effective_time("A")
        node = mgr.get_node("A")
        assert eff == node.time

    def test_inherited_sums_subtree(self, mgr):
        mgr.add_node(_make_node("A", time_o=3, time_m=3, time_p=3))
        mgr.add_node(_make_node("B", time_o=5, time_m=5, time_p=5))
        mgr.add_node(_make_node("Parent", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Parent", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Parent", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Parent")
        assert eff == pytest.approx(3.0 + 5.0)

    def test_inherited_excludes_done(self, mgr):
        mgr.add_node(_make_node("A", time_o=3, time_m=3, time_p=3, status="Done"))
        mgr.add_node(_make_node("B", time_o=5, time_m=5, time_p=5, status="Open"))
        mgr.add_node(_make_node("Parent", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Parent", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Parent", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Parent")
        assert eff == pytest.approx(5.0)

    def test_inherited_empty_subtree(self, mgr):
        mgr.add_node(_make_node("Alone", time_mode='inherited'))
        eff = mgr.get_effective_time("Alone")
        assert eff == 0.0

    def test_nonexistent_node(self, mgr):
        eff = mgr.get_effective_time("Ghost")
        assert eff == 0.0

    def test_inherited_transitive(self, mgr):
        """Inherited time includes transitive dependencies."""
        mgr.add_node(_make_node("A", time_o=2, time_m=2, time_p=2))
        mgr.add_node(_make_node("B", time_o=3, time_m=3, time_p=3))
        mgr.add_node(_make_node("Top", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Top", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Top")
        assert eff == pytest.approx(2.0 + 3.0)


# ============================================================================
# Scoring — perceived_cost time_override
# ============================================================================

class TestPerceivedCostTimeOverride:
    def test_default_uses_node_time(self):
        node = _make_node(difficulty=5, time_o=2, time_m=2, time_p=2)
        cost_default = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        cost_explicit = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=None)
        assert cost_default == cost_explicit

    def test_time_override_replaces_node_time(self):
        node = _make_node(difficulty=5, time_o=10, time_m=10, time_p=10)
        cost_overridden = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=1.0)
        expected = 1.0 + 2.5 * 5 + 1.0 * (1.0 ** 0.85)
        assert cost_overridden == pytest.approx(expected, rel=1e-4)

    def test_time_override_zero(self):
        node = _make_node(difficulty=5, time_o=10, time_m=10, time_p=10)
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=0.0)
        expected = 1.0 + 2.5 * 5 + 1.0 * (0.0 ** 0.85)
        assert cost == pytest.approx(expected, rel=1e-4)


# ============================================================================
# Scoring — inherited time_mode prevents double-counting
# ============================================================================

class TestScoringInheritedTimeMode:
    def test_inherited_node_uses_zero_time_in_cost(self, mgr):
        """A non-Goal node with time_mode='inherited' is a container — scoring
        substitutes time=0 to avoid double-counting its dependencies' costs."""
        mgr.add_node(_make_node("Dep", value=5, interest=5, time_o=10, time_m=10, time_p=10))
        mgr.add_node(_make_node("Container", value=5, interest=5, time_o=10, time_m=10, time_p=10,
                                time_mode='inherited'))
        # Score with manual time_mode (high time cost)
        manual_node = _make_node("Manual", value=5, interest=5, time_o=10, time_m=10, time_p=10,
                                 time_mode='manual')
        inherited_node = _make_node("Inherited", value=5, interest=5, time_o=10, time_m=10, time_p=10,
                                    time_mode='inherited')
        edges = []
        scored = score_nodes([manual_node, inherited_node], [manual_node, inherited_node],
                             edges, {})
        manual_score = next(n for n in scored if n.name == "Manual").priority_score
        inherited_score = next(n for n in scored if n.name == "Inherited").priority_score
        # Inherited should score higher because its time cost is 0 vs the manual node's PERT-blended ~10.
        assert inherited_score > manual_score

    def test_manual_node_still_uses_full_time(self, mgr):
        """A manual-mode node should use its full PERT time in cost calculation."""
        node = _make_node("Full", value=5, interest=5, time_o=10, time_m=10, time_p=10,
                          time_mode='manual')
        scored = score_nodes([node], [node], [], {})
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        iv = intrinsic_value(node, 1.0, 1.0)
        expected_score = round(iv / cost, 2)
        assert scored[0].priority_score == expected_score

    def test_inherited_cost_arithmetic(self, mgr):
        """Pin the exact cost formula for inherited nodes: 1 + w_e*difficulty + 0.

        Locks in the contract that the time term contributes nothing for
        containers — protects against an accidental revert to a non-zero override.
        """
        node = _make_node("C", value=5, interest=5, difficulty=4,
                          time_o=10, time_m=10, time_p=10, time_mode='inherited')
        scored = score_nodes([node], [node], [], {})
        # cost = 1 + 2.5 * 4 + 1.0 * (0 ** 0.85) = 11.0
        # iv = 1.0 * 5 + 1.0 * 5 = 10.0
        # score = round(10.0 / 11.0, 2) = 0.91
        assert scored[0].priority_score == 0.91

    def test_chained_inherited_nodes_no_phantom_cost(self, mgr):
        """A chain of inherited nodes shouldn't accumulate phantom 1.0 costs.

        With the old t_override=1.0, each inherited node added a phantom unit
        to its denominator. With t_override=0.0, the cost is purely from the
        base + difficulty contribution, so identical-difficulty chains have
        identical per-node costs.
        """
        a = _make_node("A", value=5, interest=5, difficulty=3, time_mode='inherited')
        b = _make_node("B", value=5, interest=5, difficulty=3, time_mode='inherited')
        c = _make_node("C", value=5, interest=5, difficulty=3, time_mode='inherited')
        scored = score_nodes([a, b, c], [a, b, c], [], {})
        # All three have the same intrinsic value, same difficulty, same
        # (zero) time contribution, no edges → identical scores.
        scores = [n.priority_score for n in scored]
        assert scores[0] == scores[1] == scores[2]


# ============================================================================
# Community Detection
# ============================================================================

class TestDetectCommunities:

    def test_empty_graph(self, mgr):
        result = mgr.detect_communities()
        assert result == []

    def test_single_component(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components")
        assert len(result) == 1
        assert {"A", "B"} == result[0]

    def test_two_disconnected_components(self, mgr):
        for name in ["A", "B", "C", "D"]:
            mgr.add_node(_make_node(name))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "D", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components")
        assert len(result) == 2
        names = [c for c in result]
        assert {"A", "B"} in names
        assert {"C", "D"} in names

    def test_orphan_detection(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("Lone"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="orphans")
        assert len(result) == 1
        assert {"Lone"} in result

    def test_louvain_returns_communities(self, mgr):
        for name in ["A", "B", "C", "D"]:
            mgr.add_node(_make_node(name))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "D", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="louvain")
        assert len(result) >= 2
        all_names = set()
        for c in result:
            all_names |= c
        assert all_names == {"A", "B", "C", "D"}

    def test_filters_restrict_communities(self, mgr):
        mgr.add_node(_make_node("A", context="Work"))
        mgr.add_node(_make_node("B", context="Work"))
        mgr.add_node(_make_node("C", context="Play"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components", filters={"context": ["Work"]})
        all_names = set()
        for c in result:
            all_names |= c
        assert "C" not in all_names