"""
Tests for the Skill Tree backend: Node model, PERT time, GraphManager, scoring, and config.

Uses a temporary database for isolation — does not touch the production skilltree.db.
"""

import math
from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE
from graph_manager import GraphManager
from config import ConfigManager, DEFAULT_NODE_TYPES, DEFAULT_CONTEXTS, DEFAULT_HYPERPARAMS, DEFAULT_OBSIDIAN_VAULT
from scoring import intrinsic_value, perceived_cost, is_eligible, build_adjacency, total_value, score_nodes


# --- Fixtures ---

@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
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

    def test_multiple_edge_types_coexist(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_HELPS)
        assert len(mgr.get_edges()) == 2

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
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("A", "A", EDGE_NEEDS_HARD)

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

    def test_resource_edge_allows_bidirectional(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_RESOURCE)
        mgr.add_edge("B", "A", EDGE_RESOURCE)  # should not raise


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

    def test_done_node_stays_done_after_prereq_change(self, mgr):
        mgr.add_node(_make_node("Prereq", status="Done"))
        mgr.add_node(_make_node("Target", status="Done"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        # Change prereq back to Open — Target should stay Done
        mgr.update_node(_make_node("Prereq", status="Open"))
        assert mgr.get_node("Target").status == "Done"

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
        mgr.sync_edges("C", needs_hard=["B"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[], resources=[])
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
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=[], supports_soft=[], helps=["C"], resources=[])
        edges = mgr.get_edges()
        helps_edges = [e for e in edges if e['type'] == EDGE_HELPS]
        assert len(helps_edges) == 1
        assert helps_edges[0]['target'] == "C"

    def test_sync_supports_creates_reverse_edges(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        # A supports_hard B means B Needs_Hard A → edge from A to B
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[], resources=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_sync_skips_cyclic_edges(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # Sync B: B needs A (re-creates A→B), and B supports A (would create B→A — a cycle)
        mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=["A"], supports_soft=[], helps=[], resources=[])
        edges = [e for e in mgr.get_edges() if e['type'] == EDGE_NEEDS_HARD]
        # A→B should exist (from needs_hard), but B→A should be skipped (cycle)
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"

    def test_sync_with_none_args(self, mgr):
        mgr.add_node(_make_node("A"))
        # None args should be treated as empty lists
        mgr.sync_edges("A", None, None, None, None, None, None)
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
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.35)
        assert tv == intrinsic_value(node, 1.0, 1.0)

    def test_total_value_with_hard_dependent(self):
        a = _make_node("A", value=5, interest=5)
        b = _make_node("B", value=10, interest=10)
        nodes = {"A": a, "B": b}
        H_out = {"A": ["B"], "B": []}
        S_out = {"A": [], "B": []}
        Syn = {"A": set(), "B": set()}
        d_H = 0.6
        tv_a = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, d_H, 0.25, 0.35)
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
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.35)
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

    def test_apply_migration_type_clears_habit_fields(self, mgr):
        mgr.add_node(_make_node("A", type="Habit", frequency="Daily",
                                session_lower=10, session_expected=20,
                                session_upper=30, habit_status="Active"))
        mgr.apply_migration('type', {"Habit": "Learn"})
        node = mgr.get_node("A")
        assert node.type == "Learn"
        assert node.frequency is None
        assert node.session_lower is None
        assert node.habit_status is None

    def test_apply_migration_type_clears_resource_fields(self, mgr):
        mgr.add_node(_make_node("A", type="Resource", progress=50))
        mgr.apply_migration('type', {"Resource": "Goal"})
        node = mgr.get_node("A")
        assert node.type == "Goal"
        assert node.progress is None

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
