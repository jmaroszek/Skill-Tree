"""
Tests for the Analyze tab compute functions.

Uses a temporary database for isolation — does not touch the production skilltree.db.
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from graph_manager import GraphManager
from config import ConfigManager
from analyze_callbacks import (
    _trunc, _build_adjacency, _compute_overview, _compute_bottlenecks,
    _compute_top_time_sinks, _compute_ratings, _compute_goal_comparison,
    _compute_risk, _compute_dependency_structure, _compute_context_coverage,
)


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
    return GraphManager()


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


def _setup_graph(mgr, nodes, edges=None):
    """Add nodes and edges to the graph manager."""
    for n in nodes:
        mgr.add_node(n)
    for src, tgt, etype in (edges or []):
        mgr.add_edge(src, tgt, etype)


# ============================================================================
# _trunc
# ============================================================================

class TestTrunc:
    def test_short_name_unchanged(self):
        assert _trunc("Short") == "Short"

    def test_exact_length_unchanged(self):
        name = "A" * 25
        assert _trunc(name) == name

    def test_long_name_truncated(self):
        name = "A" * 30
        result = _trunc(name)
        assert len(result) == 25
        assert result.endswith("…")

    def test_custom_max_len(self):
        result = _trunc("Hello World", max_len=8)
        assert len(result) == 8
        assert result.endswith("…")


# ============================================================================
# _compute_overview
# ============================================================================

class TestComputeOverview:
    def test_basic_counts(self, mgr):
        nodes = [
            _make_node("A", status="Open"),
            _make_node("B", status="Blocked"),
            _make_node("C", status="Done"),
            _make_node("G", type="Goal", status="Open"),
        ]
        edges = []
        result = _compute_overview(nodes, edges)

        assert result['active_count'] == 3  # A, B, G (not C)
        assert result['blocked_count'] == 1
        assert result['done_count'] == 1
        assert result['goal_count'] == 1
        assert result['total_count'] == 4

    def test_blocked_percentage(self):
        nodes = [
            _make_node("A", status="Open"),
            _make_node("B", status="Blocked"),
        ]
        result = _compute_overview(nodes, [])
        assert result['blocked_pct'] == 50

    def test_empty_graph(self):
        result = _compute_overview([], [])
        assert result['active_count'] == 0
        assert result['blocked_pct'] == 0
        assert result['milestone_count'] == 0


# ============================================================================
# _compute_bottlenecks
# ============================================================================

class TestComputeBottlenecks:
    def test_cascade_ordering(self, mgr):
        """Node A → B → C: A has cascade 2, B has cascade 1."""
        nodes = [
            _make_node("A", status="Open"),
            _make_node("B", status="Open"),
            _make_node("C", status="Open"),
        ]
        edges = [
            {'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD},
            {'source': 'B', 'target': 'C', 'type': EDGE_NEEDS_HARD},
        ]
        hard_fwd, _, _, _, _ = _build_adjacency(edges)
        limits = {'bottlenecks': 25}
        result = _compute_bottlenecks(nodes, hard_fwd, limits)

        assert result[0]['name'] == 'A'
        assert result[0]['cascade'] == 2
        assert result[1]['name'] == 'B'
        assert result[1]['cascade'] == 1

    def test_done_nodes_excluded(self):
        nodes = [
            _make_node("A", status="Done"),
            _make_node("B", status="Open"),
        ]
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD}]
        hard_fwd, _, _, _, _ = _build_adjacency(edges)
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25})
        # A is Done, so it shouldn't appear; B has no outgoing
        assert len(result) == 0

    def test_respects_limit(self):
        nodes = [_make_node(f"N{i}", status="Open") for i in range(10)]
        edges = [{'source': f'N{i}', 'target': f'N{i+1}', 'type': EDGE_NEEDS_HARD} for i in range(9)]
        hard_fwd, _, _, _, _ = _build_adjacency(edges)
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 3})
        assert len(result) == 3


# ============================================================================
# _compute_top_time_sinks
# ============================================================================

class TestComputeTopTimeSinks:
    def test_time_sinks_limit(self):
        nodes = [_make_node(f"N{i}", time_m=float(i)) for i in range(20)]
        top_nodes = _compute_top_time_sinks(nodes, {'time_sinks': 5})
        assert len(top_nodes) == 5

    def test_sorted_descending(self):
        nodes = [
            _make_node("Small", time_m=1),
            _make_node("Big", time_m=100),
        ]
        top_nodes = _compute_top_time_sinks(nodes, {'time_sinks': 10})
        assert top_nodes[0].name == "Big"

    def test_done_excluded(self):
        nodes = [
            _make_node("A", status="Done", time_m=100),
            _make_node("B", status="Open", time_m=10),
        ]
        top_nodes = _compute_top_time_sinks(nodes, {'time_sinks': 10})
        assert len(top_nodes) == 1
        assert top_nodes[0].name == "B"


# ============================================================================
# _compute_ratings
# ============================================================================

class TestComputeRatings:
    def test_averages(self):
        nodes = [
            _make_node("A", value=8, interest=6, difficulty=4, context="Mind"),
            _make_node("B", value=4, interest=2, difficulty=8, context="Mind"),
        ]
        result = _compute_ratings(nodes)
        mind = [r for r in result if r['context'] == 'Mind'][0]
        assert mind['avg_value'] == 6.0
        assert mind['avg_interest'] == 4.0
        assert mind['avg_difficulty'] == 6.0

    def test_no_context_bucket(self):
        nodes = [_make_node("A", context=None)]
        result = _compute_ratings(nodes)
        assert result[0]['context'] == 'No Context'

    def test_completion_rate(self):
        nodes = [
            _make_node("A", status="Done", context="Mind"),
            _make_node("B", status="Open", context="Mind"),
            _make_node("C", status="Open", context="Mind"),
        ]
        result = _compute_ratings(nodes)
        mind = [r for r in result if r['context'] == 'Mind'][0]
        assert mind['completion_pct'] == 33  # 1 of 3


# ============================================================================
# _compute_goal_comparison
# ============================================================================

class TestComputeGoalComparison:
    def test_basic_goal_stats(self, mgr):
        _setup_graph(mgr, [
            _make_node("Goal1", type="Goal"),
            _make_node("Task1", status="Done"),
            _make_node("Task2", status="Open"),
        ], [
            ("Task1", "Goal1", EDGE_NEEDS_HARD),
            ("Task2", "Goal1", EDGE_NEEDS_HARD),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)
        goal_rows, overlap_rows, total = _compute_goal_comparison(
            nodes, hard_rev, prereq_rev, {'goals': 25})
        assert total == 1
        assert goal_rows[0]['done'] == 1
        assert goal_rows[0]['total'] == 2
        assert goal_rows[0]['pct'] == 50

    def test_respects_goal_limit(self, mgr):
        goals = [_make_node(f"Goal{i}", type="Goal", value=i) for i in range(10)]
        _setup_graph(mgr, goals)
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)
        goal_rows, _, total = _compute_goal_comparison(
            nodes, hard_rev, prereq_rev, {'goals': 3})
        assert total == 10
        assert len(goal_rows) == 3

    def test_overlap_computed(self, mgr):
        _setup_graph(mgr, [
            _make_node("GoalA", type="Goal"),
            _make_node("GoalB", type="Goal"),
            _make_node("Shared", status="Open"),
        ], [
            ("Shared", "GoalA", EDGE_NEEDS_HARD),
            ("Shared", "GoalB", EDGE_NEEDS_HARD),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)
        _, overlap_rows, _ = _compute_goal_comparison(
            nodes, hard_rev, prereq_rev, {'goals': 25})
        assert len(overlap_rows) == 1
        assert overlap_rows[0]['shared'] == 1

    def test_overlap_includes_soft_prereqs(self, mgr):
        """Shared overlap should count nodes connected by Needs_Soft, not just Needs_Hard."""
        _setup_graph(mgr, [
            _make_node("GoalA", type="Goal"),
            _make_node("GoalB", type="Goal"),
            _make_node("HardShared", status="Open"),
            _make_node("SoftShared", status="Open"),
        ], [
            ("HardShared", "GoalA", EDGE_NEEDS_HARD),
            ("HardShared", "GoalB", EDGE_NEEDS_HARD),
            ("SoftShared", "GoalA", EDGE_NEEDS_SOFT),
            ("SoftShared", "GoalB", EDGE_NEEDS_SOFT),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)
        goal_rows, overlap_rows, _ = _compute_goal_comparison(
            nodes, hard_rev, prereq_rev, {'goals': 25})
        # Overlap counts both hard- and soft-shared prereqs
        assert overlap_rows[0]['shared'] == 2
        # But completion stats stay hard-only: each goal's total is just HardShared
        for row in goal_rows:
            assert row['total'] == 1

    def test_overlap_excludes_helps_edges(self, mgr):
        """Helps (synergy) edges should not contribute to shared overlap."""
        _setup_graph(mgr, [
            _make_node("GoalA", type="Goal"),
            _make_node("GoalB", type="Goal"),
            _make_node("HelpsBoth", status="Open"),
        ], [
            ("HelpsBoth", "GoalA", EDGE_HELPS),
            ("HelpsBoth", "GoalB", EDGE_HELPS),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, prereq_rev, _, _ = _build_adjacency(edges)
        _, overlap_rows, _ = _compute_goal_comparison(
            nodes, hard_rev, prereq_rev, {'goals': 25})
        assert overlap_rows == []


# ============================================================================
# _compute_risk
# ============================================================================

class TestComputeRisk:
    def test_spread_ordering(self):
        nodes = [
            _make_node("Small", time_o=1.0, time_p=2.0, status="Open"),
            _make_node("Big", time_o=1.0, time_p=10.0, status="Open"),
        ]
        result = _compute_risk(nodes, {'risk': 25})
        assert result[0]['name'] == 'Big'
        assert result[0]['spread'] == 9.0

    def test_done_excluded(self):
        nodes = [_make_node("Done", status="Done", time_o=1.0, time_p=100.0)]
        result = _compute_risk(nodes, {'risk': 25})
        assert len(result) == 0

    def test_zero_estimates_excluded(self):
        nodes = [_make_node("NoEst", time_o=0, time_p=0)]
        result = _compute_risk(nodes, {'risk': 25})
        assert len(result) == 0


# ============================================================================
# _compute_dependency_structure
# ============================================================================

class TestComputeDependencyStructure:
    def test_longest_chain(self):
        """A → B → C should produce a chain of length 2 (3 nodes)."""
        nodes = [
            _make_node("A", status="Open"),
            _make_node("B", status="Open"),
            _make_node("C", status="Open"),
        ]
        edges = [
            {'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD},
            {'source': 'B', 'target': 'C', 'type': EDGE_NEEDS_HARD},
        ]
        hard_fwd, hard_rev, _, all_fwd, all_rev = _build_adjacency(edges)
        limits = {'deepest': 10, 'connected': 10}
        result = _compute_dependency_structure(
            nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        assert result['longest_length'] == 2
        assert len(result['longest_chain']) == 3

    def test_deepest_node(self):
        """C depends on B depends on A: C has 2 hard prereqs."""
        nodes = [
            _make_node("A", status="Open"),
            _make_node("B", status="Open"),
            _make_node("C", status="Open"),
        ]
        edges = [
            {'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD},
            {'source': 'B', 'target': 'C', 'type': EDGE_NEEDS_HARD},
        ]
        hard_fwd, hard_rev, _, all_fwd, all_rev = _build_adjacency(edges)
        limits = {'deepest': 10, 'connected': 10}
        result = _compute_dependency_structure(
            nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        deepest = result['deepest']
        assert deepest[0]['name'] == 'C'
        assert deepest[0]['prereq_count'] == 2

    def test_most_connected(self):
        """B is the most connected node (in from A, out to C and D)."""
        nodes = [
            _make_node("A"), _make_node("B"), _make_node("C"), _make_node("D"),
        ]
        edges = [
            {'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD},
            {'source': 'B', 'target': 'C', 'type': EDGE_NEEDS_HARD},
            {'source': 'B', 'target': 'D', 'type': EDGE_NEEDS_SOFT},
        ]
        hard_fwd, hard_rev, _, all_fwd, all_rev = _build_adjacency(edges)
        limits = {'deepest': 10, 'connected': 10}
        result = _compute_dependency_structure(
            nodes, hard_fwd, hard_rev, all_fwd, all_rev, edges, limits)
        connected = result['most_connected']
        assert connected[0]['name'] == 'B'
        assert connected[0]['degree'] == 3

    def test_empty_graph(self):
        result = _compute_dependency_structure(
            [], {}, {}, {}, {}, [], {'deepest': 10, 'connected': 10})
        assert result['longest_chain'] == []
        assert result['longest_length'] == 0


# ============================================================================
# _compute_context_coverage
# ============================================================================

class TestComputeContextCoverage:
    def test_zero_count_contexts(self, mgr):
        """Contexts configured in settings with no nodes should appear with count=0."""
        ConfigManager.set_contexts(["Mind", "Body", "Social"])
        nodes = [_make_node("A", context="Mind")]
        ctx_data, _ = _compute_context_coverage(nodes)
        body = [d for d in ctx_data if d['context'] == 'Body']
        assert len(body) == 1
        assert body[0]['count'] == 0
        assert body[0]['time'] == 0.0

    def test_subcontext_format(self, mgr):
        """Subcontext labels should use '>' separator."""
        ConfigManager.set_contexts(["Mind"])
        ConfigManager.set_subcontexts({"Mind": ["Logic", "Memory"]})
        nodes = [_make_node("A", context="Mind", subcontext="Logic")]
        _, subctx_data = _compute_context_coverage(nodes)
        labels = [d['label'] for d in subctx_data]
        assert "Mind > Logic" in labels
        assert "Mind > Memory" in labels

    def test_sorted_by_time(self, mgr):
        ConfigManager.set_contexts(["Mind", "Body"])
        nodes = [
            _make_node("A", context="Mind", time_m=100),
            _make_node("B", context="Body", time_m=1),
        ]
        ctx_data, _ = _compute_context_coverage(nodes)
        # Body has less time, should come first (sorted ascending)
        assert ctx_data[0]['context'] == 'Body'

    def test_no_context_bucket(self, mgr):
        ConfigManager.set_contexts(["Mind"])
        nodes = [_make_node("A", context=None)]
        ctx_data, _ = _compute_context_coverage(nodes)
        no_ctx = [d for d in ctx_data if d['context'] == 'No Context']
        assert len(no_ctx) == 1

    def test_weight_included_from_settings(self, mgr):
        """Each ctx_data row includes its context's weight (default 1.0)."""
        ConfigManager.set_contexts(["Mind", "Body"])
        ConfigManager.set_context_weights({"Mind": 2.5})
        nodes = [
            _make_node("A", context="Mind"),
            _make_node("B", context="Body"),
        ]
        ctx_data, _ = _compute_context_coverage(nodes)
        by_ctx = {d['context']: d for d in ctx_data}
        assert by_ctx['Mind']['weight'] == 2.5
        assert by_ctx['Body']['weight'] == 1.0

    def test_no_context_bucket_gets_default_weight(self, mgr):
        ConfigManager.set_contexts(["Mind"])
        nodes = [_make_node("A", context=None)]
        ctx_data, _ = _compute_context_coverage(nodes)
        no_ctx = next(d for d in ctx_data if d['context'] == 'No Context')
        assert no_ctx['weight'] == 1.0


# ============================================================================
# _build_adjacency
# ============================================================================

class TestBuildAdjacency:
    def test_hard_edges(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD}]
        hard_fwd, hard_rev, prereq_rev, all_fwd, all_rev = _build_adjacency(edges)
        assert 'B' in hard_fwd['A']
        assert 'A' in hard_rev['B']
        # Hard edges feed into prereq_rev as well
        assert 'A' in prereq_rev['B']

    def test_all_edge_types(self):
        edges = [
            {'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD},
            {'source': 'C', 'target': 'D', 'type': EDGE_NEEDS_SOFT},
            {'source': 'E', 'target': 'F', 'type': EDGE_HELPS},
        ]
        hard_fwd, hard_rev, prereq_rev, all_fwd, all_rev = _build_adjacency(edges)
        assert 'B' in hard_fwd['A']
        assert 'D' in all_fwd['C']
        assert 'F' in all_fwd['E']
        # Soft and Helps should NOT be in hard adjacency
        assert 'D' not in hard_fwd.get('C', [])

    def test_prereq_rev_includes_hard_and_soft(self):
        """prereq_rev must include both Needs_Hard and Needs_Soft, but not Helps."""
        edges = [
            {'source': 'H', 'target': 'X', 'type': EDGE_NEEDS_HARD},
            {'source': 'S', 'target': 'X', 'type': EDGE_NEEDS_SOFT},
            {'source': 'P', 'target': 'X', 'type': EDGE_HELPS},
        ]
        _, _, prereq_rev, _, _ = _build_adjacency(edges)
        assert 'H' in prereq_rev['X']
        assert 'S' in prereq_rev['X']
        assert 'P' not in prereq_rev['X']

    def test_empty_edges(self):
        hard_fwd, hard_rev, prereq_rev, all_fwd, all_rev = _build_adjacency([])
        assert len(hard_fwd) == 0
        assert len(prereq_rev) == 0

