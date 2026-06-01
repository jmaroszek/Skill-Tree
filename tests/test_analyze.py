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
    _compute_ratings, _compute_goal_comparison, _compute_context_coverage,
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
            nodes, edges, hard_rev, prereq_rev, {'goals': 25})
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
            nodes, edges, hard_rev, prereq_rev, {'goals': 3})
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
            nodes, edges, hard_rev, prereq_rev, {'goals': 25})
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
            nodes, edges, hard_rev, prereq_rev, {'goals': 25})
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
            nodes, edges, hard_rev, prereq_rev, {'goals': 25})
        assert overlap_rows == []

    def test_ranks_by_prereq_subtree_value(self, mgr):
        """With cost held equal, a goal with a higher-value Hard-prereq
        subtree outranks one with high own-rating but low-value prereqs.

        _rank_goals scores ROI = subtree value / subtree-time cost. To
        isolate the *value* axis, both goals get four Hard prereqs with
        identical (default) time, so their costs match exactly and the
        ranking turns purely on prereq-subtree value.
        """
        # GoalSparse: high own rating, but four low-value prereqs.
        # GoalRich:   modest own rating, but four high-value prereqs whose
        #             intrinsic value cascades up the inverted graph.
        _setup_graph(mgr, [
            _make_node("GoalSparse", type="Goal",
                       time_mode='inherited', value=10, interest=10),
            _make_node("GoalRich", type="Goal",
                       time_mode='inherited', value=3, interest=3),
            _make_node("SP1", value=1, interest=1),
            _make_node("SP2", value=1, interest=1),
            _make_node("SP3", value=1, interest=1),
            _make_node("SP4", value=1, interest=1),
            _make_node("RC1", value=10, interest=10),
            _make_node("RC2", value=10, interest=10),
            _make_node("RC3", value=10, interest=10),
            _make_node("RC4", value=10, interest=10),
        ], [
            ("SP1", "GoalSparse", EDGE_NEEDS_HARD),
            ("SP2", "GoalSparse", EDGE_NEEDS_HARD),
            ("SP3", "GoalSparse", EDGE_NEEDS_HARD),
            ("SP4", "GoalSparse", EDGE_NEEDS_HARD),
            ("RC1", "GoalRich", EDGE_NEEDS_HARD),
            ("RC2", "GoalRich", EDGE_NEEDS_HARD),
            ("RC3", "GoalRich", EDGE_NEEDS_HARD),
            ("RC4", "GoalRich", EDGE_NEEDS_HARD),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        from analyze_callbacks import _rank_goals
        hp = ConfigManager.get_hyperparams()
        ranked = _rank_goals(
            [n for n in nodes if n.type == 'Goal'],
            nodes, edges,
            ConfigManager.get_priority_goals(), hp,
            with_components=True,
        )
        comps = {g.name: c for g, c in ranked}
        # Costs match (four equal-time prereqs each), so ROI is value-driven.
        assert comps["GoalRich"]["cost"] == pytest.approx(comps["GoalSparse"]["cost"])
        assert comps["GoalRich"]["score"] > comps["GoalSparse"]["score"]

    def test_rank_goals_treats_milestones_as_transparent_checkpoints(self, mgr):
        """Milestones pass through upstream work without adding own ROI. Here M
        is constructed with manual time + high ratings + 100h, but the model
        forces every Milestone to a pure container (both modes inherited), so
        its value AND its 100h drop out of the Goal's ROI entirely — no
        in-memory transform in the ranker required."""
        _setup_graph(mgr, [
            _make_node("G", type="Goal", time_mode='inherited',
                       value=1, interest=1),
            _make_node("M", type="Milestone", time_mode='manual',
                       value=10, interest=10,
                       time_o=100.0, time_m=100.0, time_p=100.0),
            _make_node("Work", value=10, interest=10),
        ], [
            ("Work", "M", EDGE_NEEDS_HARD),
            ("M", "G", EDGE_NEEDS_HARD),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        hp = ConfigManager.get_hyperparams()

        from analyze_callbacks import _rank_goals
        ranked = _rank_goals(
            [n for n in nodes if n.type == 'Goal'],
            nodes, edges,
            ConfigManager.get_priority_goals(), hp,
            with_components=True,
        )
        comps = {g.name: c for g, c in ranked}
        work = next(n for n in nodes if n.name == "Work")

        expected_tv = (
            hp['w_v'] * 1 + hp['w_i'] * 1
            + (hp['d_H'] ** 2) * (hp['w_v'] * 10 + hp['w_i'] * 10)
        )
        assert comps["G"]["tv"] == pytest.approx(expected_tv)
        assert comps["G"]["remaining_time"] == pytest.approx(work.time)

    def test_explain_goal_matches_rank_goals(self, mgr):
        """analyze_callbacks.explain_goal reports the same headline score
        _rank_goals ranks by, and flags the breakdown as a goal."""
        _setup_graph(mgr, [
            _make_node("G", type="Goal", time_mode='inherited',
                       value=4, interest=4),
            _make_node("P1", value=8, interest=8),
            _make_node("P2", value=6, interest=6),
        ], [
            ("P1", "G", EDGE_NEEDS_HARD),
            ("P2", "G", EDGE_NEEDS_SOFT),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        hp = ConfigManager.get_hyperparams()
        pgoals = ConfigManager.get_priority_goals()

        from analyze_callbacks import _rank_goals, explain_goal
        ranked = dict(
            (g.name, c) for g, c in _rank_goals(
                [n for n in nodes if n.type == 'Goal'],
                nodes, edges, pgoals, hp, with_components=True)
        )
        bd, normalized = explain_goal("G", nodes, edges, hp, pgoals)
        assert bd['is_goal'] is True
        assert bd['eligible'] is True
        assert bd['score'] == round(ranked["G"]["score"], 2)
        # Prereq subtree value flows into the cascade rows; G alone (no
        # prereqs) would have a zero cascade.
        cascade = (bd['composition']['hard_cascade']
                   + bd['composition']['soft_cascade'])
        assert cascade > 0
        # Sole ranked goal -> normalized to the top (100).
        assert normalized == 100

    def test_explain_goal_rejects_non_goal(self, mgr):
        """explain_goal returns None for a non-Goal node."""
        _setup_graph(mgr, [_make_node("L", type="Learn")])
        nodes = mgr.get_all_nodes()
        from analyze_callbacks import explain_goal
        assert explain_goal("L", nodes, mgr.get_edges(),
                            ConfigManager.get_hyperparams(),
                            ConfigManager.get_priority_goals()) is None


# ============================================================================
# _rank_goals — Goal-level density normalization (alpha_goal)
# ============================================================================

class TestGoalDensityNormalization:
    """Goal scores are damped by a delta_g = 1 / max(1, |B_goals|)^alpha_goal
    correction, mirroring the leaf-node alpha density correction. Buckets are
    keyed by (context, subcontext) and count open Goals only.
    """

    def _rank_with(self, mgr, hp_overrides=None):
        """Helper: get _rank_goals component dicts keyed by Goal name, with
        an optional hp_overrides dict patched onto the default hyperparams.
        """
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        hp = ConfigManager.get_hyperparams()
        if hp_overrides:
            hp = {**hp, **hp_overrides}
        from analyze_callbacks import _rank_goals
        return {
            g.name: c for g, c in _rank_goals(
                [n for n in nodes if n.type == 'Goal'],
                nodes, edges,
                ConfigManager.get_priority_goals(), hp,
                with_components=True,
            )
        }

    def test_solo_goal_in_bucket_unaffected(self, mgr):
        """A Goal alone in its (ctx, subctx) bucket gets density_mult = 1.0."""
        _setup_graph(mgr, [
            _make_node("G", type="Goal", time_mode='inherited',
                       value=5, interest=5, context="STEM", subcontext="Math"),
        ])
        comps = self._rank_with(mgr)
        assert comps["G"]["bucket_count"] == 1
        assert comps["G"]["density_mult"] == pytest.approx(1.0)

    def test_sibling_goals_in_same_bucket_damped(self, mgr):
        """Multiple open Goals sharing (ctx, subctx) get damped together."""
        _setup_graph(mgr, [
            _make_node(f"G{i}", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math")
            for i in range(4)
        ])
        comps = self._rank_with(mgr)
        for i in range(4):
            assert comps[f"G{i}"]["bucket_count"] == 4
            # 4 ** -0.20 ≈ 0.7579
            assert comps[f"G{i}"]["density_mult"] == pytest.approx(4 ** -0.20)

    def test_alpha_goal_zero_disables(self, mgr):
        """alpha_goal=0 returns density_mult=1.0 regardless of bucket size."""
        _setup_graph(mgr, [
            _make_node(f"G{i}", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math")
            for i in range(5)
        ])
        comps = self._rank_with(mgr, hp_overrides={'alpha_goal': 0.0})
        for i in range(5):
            assert comps[f"G{i}"]["density_mult"] == pytest.approx(1.0)

    def test_done_goals_excluded_from_bucket_count(self, mgr):
        """A Done Goal doesn't crowd its bucketmates."""
        _setup_graph(mgr, [
            _make_node("Open1", type="Goal", time_mode='inherited',
                       value=5, interest=5, status="Open",
                       context="STEM", subcontext="Math"),
            _make_node("Open2", type="Goal", time_mode='inherited',
                       value=5, interest=5, status="Open",
                       context="STEM", subcontext="Math"),
            _make_node("DoneOne", type="Goal", time_mode='inherited',
                       value=5, interest=5, status="Done",
                       context="STEM", subcontext="Math"),
        ])
        comps = self._rank_with(mgr)
        # Bucket sees Open1 + Open2 only; Done is excluded.
        assert comps["Open1"]["bucket_count"] == 2
        assert comps["Open2"]["bucket_count"] == 2

    def test_different_subcontexts_dont_share_bucket(self, mgr):
        """Same context but different subcontext = different buckets."""
        _setup_graph(mgr, [
            _make_node("GMath", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math"),
            _make_node("GPhys", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Physics"),
        ])
        comps = self._rank_with(mgr)
        assert comps["GMath"]["bucket_count"] == 1
        assert comps["GPhys"]["bucket_count"] == 1
        assert comps["GMath"]["density_mult"] == pytest.approx(1.0)
        assert comps["GPhys"]["density_mult"] == pytest.approx(1.0)

    def test_none_subcontext_is_its_own_bucket(self, mgr):
        """Goals with explicit subcontext=None form a single bucket, distinct
        from Goals in named subcontexts within the same context."""
        _setup_graph(mgr, [
            _make_node("GBroad1", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext=None),
            _make_node("GBroad2", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext=None),
            _make_node("GMath", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math"),
        ])
        comps = self._rank_with(mgr)
        assert comps["GBroad1"]["bucket_count"] == 2
        assert comps["GBroad2"]["bucket_count"] == 2
        assert comps["GMath"]["bucket_count"] == 1

    def test_scored_nodes_dont_inflate_goal_bucket(self, mgr):
        """Leaf-node siblings in the same (ctx, subctx) don't count toward the
        Goal density bucket — only Goals do."""
        _setup_graph(mgr, [
            _make_node("G", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math"),
        ] + [
            _make_node(f"L{i}", type="Learn", value=5, interest=5,
                       context="STEM", subcontext="Math")
            for i in range(10)
        ])
        comps = self._rank_with(mgr)
        # 10 leaf Learns share the bucket but the Goal sees count = 1.
        assert comps["G"]["bucket_count"] == 1
        assert comps["G"]["density_mult"] == pytest.approx(1.0)

    def test_density_changes_final_ranking(self, mgr):
        """Two Goals with equal intrinsic worth — one alone in its bucket, one
        with three siblings — should rank the lone Goal higher."""
        _setup_graph(mgr, [
            _make_node("Solo", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="Self", subcontext="Creativity"),
        ] + [
            _make_node(f"Crowd{i}", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math")
            for i in range(4)
        ])
        comps = self._rank_with(mgr)
        # Raw ROI is identical (same value/interest, same inherited cost
        # structure). Density is the tiebreaker.
        assert comps["Solo"]["raw"] == pytest.approx(comps["Crowd0"]["raw"])
        assert comps["Solo"]["score"] > comps["Crowd0"]["score"]

    def test_explain_goal_reports_density(self, mgr):
        """explain_goal's context_adjustment now reflects the live Goal
        bucket count and alpha_goal, not the old hardcoded neutral values."""
        _setup_graph(mgr, [
            _make_node("G1", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math"),
            _make_node("G2", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math"),
        ])
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        hp = ConfigManager.get_hyperparams()
        from analyze_callbacks import explain_goal
        bd, _ = explain_goal("G1", nodes, edges, hp,
                             ConfigManager.get_priority_goals())
        ca = bd['context_adjustment']
        assert ca['n_bucket'] == 2
        assert ca['alpha'] == pytest.approx(hp['alpha_goal'])
        assert ca['density_mult'] == pytest.approx(2 ** -hp['alpha_goal'])


# ============================================================================
# _compute_context_coverage
# ============================================================================

class TestComputeContextCoverage:
    def test_zero_count_contexts(self, mgr):
        """Contexts configured in settings with no nodes should appear with count=0."""
        ConfigManager.set_contexts(["Mind", "Body", "Social"])
        nodes = [_make_node("A", context="Mind")]
        ctx_data = _compute_context_coverage(nodes)
        body = [d for d in ctx_data if d['context'] == 'Body']
        assert len(body) == 1
        assert body[0]['count'] == 0
        assert body[0]['time'] == 0.0
        assert body[0]['segments'] == []

    def test_segments_partition_context_time(self, mgr):
        """A context's segment times sum to its total; nodes with no
        subcontext fall into a "(No subcontext)" segment."""
        ConfigManager.set_contexts(["Mind"])
        nodes = [
            _make_node("A", context="Mind", subcontext="Logic"),
            _make_node("B", context="Mind", subcontext="Logic"),
            _make_node("C", context="Mind", subcontext=None),
        ]
        ctx_data = _compute_context_coverage(nodes)
        mind = next(d for d in ctx_data if d['context'] == 'Mind')
        seg_names = {s['name'] for s in mind['segments']}
        assert seg_names == {"Logic", "(No subcontext)"}
        assert sum(s['time'] for s in mind['segments']) == pytest.approx(mind['time'])
        assert sum(s['count'] for s in mind['segments']) == mind['count']
        logic = next(s for s in mind['segments'] if s['name'] == 'Logic')
        assert logic['count'] == 2

    def test_sorted_by_time(self, mgr):
        ConfigManager.set_contexts(["Mind", "Body"])
        nodes = [
            _make_node("A", context="Mind", time_m=100),
            _make_node("B", context="Body", time_m=1),
        ]
        ctx_data = _compute_context_coverage(nodes)
        # Body has less time, should come first (sorted ascending)
        assert ctx_data[0]['context'] == 'Body'

    def test_no_context_bucket(self, mgr):
        ConfigManager.set_contexts(["Mind"])
        nodes = [_make_node("A", context=None)]
        ctx_data = _compute_context_coverage(nodes)
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
        ctx_data = _compute_context_coverage(nodes)
        by_ctx = {d['context']: d for d in ctx_data}
        assert by_ctx['Mind']['weight'] == 2.5
        assert by_ctx['Body']['weight'] == 1.0

    def test_no_context_bucket_gets_default_weight(self, mgr):
        ConfigManager.set_contexts(["Mind"])
        nodes = [_make_node("A", context=None)]
        ctx_data = _compute_context_coverage(nodes)
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

