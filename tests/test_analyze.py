"""
Tests for the Analyze tab compute functions.

Uses a temporary database for isolation — does not touch the production skilltree.db.
"""

from datetime import date
from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from graph_manager import GraphManager
from config import ConfigManager
from analyze_callbacks import (
    _trunc, _build_adjacency, _compute_overview, _compute_bottlenecks,
    _compute_goal_progress,
    _compute_throughput, _compute_reflection_drift,
    _compute_rating_distribution,
)


def _throughput_node_names(rows):
    """Flatten the throughput result into the set of node names it charts."""
    return {nm for r in rows
            for seg in (r.get('segments') or [])
            for (nm, _hrs) in seg.get('nodes', [])}


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


def _walk(component):
    """Every Dash component in a rendered tree, the root first."""
    yield component
    kids = getattr(component, 'children', None)
    for kid in (kids if isinstance(kids, (list, tuple)) else [kids]):
        if hasattr(kid, 'to_plotly_json'):
            yield from _walk(kid)


def _figure(card):
    """The Plotly figure in a rendered Analyze card."""
    from dash import dcc
    return next(c for c in _walk(card) if isinstance(c, dcc.Graph)).figure


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
    @staticmethod
    def _edges(*pairs):
        return [{'source': s, 'target': t, 'type': EDGE_NEEDS_HARD} for s, t in pairs]

    def test_ranks_by_hours_of_work_gated(self):
        """A → B → C: A gates B and C, B gates only C."""
        nodes = [_make_node(n, status="Open") for n in "ABC"]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "B"), ("B", "C")))
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25})

        assert [r['names'] for r in result] == [['A'], ['B']]
        assert result[0]['count'] == 2
        assert result[0]['hours'] == pytest.approx(nodes[1].time + nodes[2].time)
        assert result[0]['own_hours'] == pytest.approx(nodes[0].time)

    def test_blocked_nodes_are_left_out(self):
        """B's gated work already sits inside A's row."""
        nodes = [_make_node("A", status="Open"), _make_node("B", status="Blocked"),
                 _make_node("C", status="Blocked")]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "B"), ("B", "C")))
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25})
        assert [r['names'] for r in result] == [['A']]

    def test_goals_and_milestones_are_walked_through_not_counted(self):
        nodes = [_make_node("A", status="Open"),
                 _make_node("M", type="Milestone", status="Blocked"),
                 _make_node("G", type="Goal", status="Blocked"),
                 _make_node("B", status="Blocked")]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "M"), ("M", "G"), ("G", "B")))
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25})
        assert [(r['names'], r['count']) for r in result] == [(['A'], 1)]

    def test_nodes_gating_the_same_work_share_a_row(self):
        nodes = [_make_node("B", status="Open"), _make_node("A", status="Open"),
                 _make_node("C", status="Blocked")]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "C"), ("B", "C")))
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25})
        assert [r['names'] for r in result] == [['A', 'B']]
        # Both stand in the way of C, so the row costs both.
        assert result[0]['own_hours'] == pytest.approx(nodes[0].time + nodes[1].time)

    def test_chart_draws_own_time_before_what_is_unlocked(self):
        from analyze_callbacks import _render_bottleneck_chart
        nodes = [_make_node("A", status="Open", time_o=5, time_m=5, time_p=5),
                 _make_node("B", status="Blocked", time_o=40, time_m=40, time_p=40)]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "B")))
        parts = list(_walk(_render_bottleneck_chart(
            _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25}))))
        track = next(p for p in parts if getattr(p, 'className', None) == "gp-track")
        assert [s.className for s in track.children] == ["bn-own", "bn-unlocks"]
        # The widest row fills the track; the stub is its share of that.
        widths = [float(s.style['width'].split('(')[1].split('%')[0]) for s in track.children]
        assert widths == [pytest.approx(100 * 5 / 45, abs=0.01),
                          pytest.approx(100 * 40 / 45, abs=0.01)]
        fmt = ConfigManager.format_time_friendly
        tip = next(p for p in parts if getattr(p, 'className', None) == "gp-bar")
        assert f"Takes {fmt(5)}" in getattr(tip, 'data-tip')
        value = next(p for p in parts if getattr(p, 'className', None) == "gp-pct")
        assert value.children == fmt(40)

    def test_done_nodes_excluded(self):
        nodes = [
            _make_node("A", status="Done"),
            _make_node("B", status="Open"),
        ]
        hard_fwd, *_ = _build_adjacency(self._edges(("A", "B")))
        # A is Done, so it shouldn't appear; B has no outgoing
        assert _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 25}) == []

    def test_respects_limit(self):
        nodes = [_make_node(f"N{i}", status="Open") for i in range(10)]
        hard_fwd, *_ = _build_adjacency(
            self._edges(*[(f"N{i}", f"N{i+1}") for i in range(9)]))
        result = _compute_bottlenecks(nodes, hard_fwd, {'bottlenecks': 3})
        assert len(result) == 3


# ============================================================================
# _compute_goal_progress
# ============================================================================

class TestComputeGoalProgress:
    @staticmethod
    def _rows(mgr, limit=25, today=None):
        nodes = mgr.get_all_nodes()
        edges = mgr.get_edges()
        _, hard_rev, _, _, _ = _build_adjacency(edges)
        return _compute_goal_progress(nodes, edges, hard_rev, {'goals': limit},
                                      today=today)

    def test_progress_weighs_each_node_by_its_estimate(self, mgr):
        """One small Done node of four: half the nodes, a fifth of the work."""
        _setup_graph(mgr, [
            _make_node("Goal1", type="Goal", time_mode='inherited'),
            _make_node("Small", status="Done", time_o=10, time_m=10, time_p=10),
            _make_node("Big", status="Open", time_o=40, time_m=40, time_p=40),
        ], [
            ("Small", "Goal1", EDGE_NEEDS_HARD),
            ("Big", "Goal1", EDGE_NEEDS_HARD),
        ])
        rows, total = self._rows(mgr)
        assert total == 1
        row = rows[0]
        assert (row['done'], row['total']) == (1, 2)
        assert row['share'] == pytest.approx(0.2)
        assert row['pct'] == 20
        assert (row['done_time'], row['total_time']) == (pytest.approx(10), pytest.approx(50))

    def test_respects_goal_limit(self, mgr):
        goals = [_make_node(f"Goal{i}", type="Goal", value=i) for i in range(10)]
        _setup_graph(mgr, goals)
        rows, total = self._rows(mgr, limit=3)
        assert total == 10
        assert len(rows) == 3

    def test_soft_prerequisites_are_not_progress(self, mgr):
        _setup_graph(mgr, [
            _make_node("Goal1", type="Goal", time_mode='inherited'),
            _make_node("Hard", status="Open"),
            _make_node("Soft", status="Done"),
        ], [
            ("Hard", "Goal1", EDGE_NEEDS_HARD),
            ("Soft", "Goal1", EDGE_NEEDS_SOFT),
        ])
        row = self._rows(mgr)[0][0]
        assert (row['done'], row['total'], row['pct']) == (0, 1, 0)

    def test_recent_work_is_the_last_six_months(self, mgr):
        _setup_graph(mgr, [
            _make_node("Goal1", type="Goal", time_mode='inherited'),
            _make_node("Old", status="Done", done_date="2025-01-10", time_o=10, time_m=10, time_p=10),
            _make_node("New", status="Done", done_date="2026-05-01", time_o=30, time_m=30, time_p=30),
            _make_node("Left", status="Open", time_o=60, time_m=60, time_p=60),
        ], [(name, "Goal1", EDGE_NEEDS_HARD) for name in ("Old", "New", "Left")])
        row = self._rows(mgr, today=date(2026, 6, 1))[0][0]
        assert row['recent_time'] == pytest.approx(30)
        assert row['recent_count'] == 1
        assert row['share'] == pytest.approx(0.4)

    def test_rows_put_the_priority_badge_after_the_name(self, mgr):
        from dash import html
        from analyze_callbacks import _render_goal_progress
        _setup_graph(mgr, [
            _make_node("Goal1", type="Goal", time_mode='inherited'),
            _make_node("Done1", status="Done", done_date="2026-05-01", time_o=1, time_m=1, time_p=1),
            _make_node("Open1", status="Open", time_o=299, time_m=299, time_p=299),
        ], [("Done1", "Goal1", EDGE_NEEDS_HARD), ("Open1", "Goal1", EDGE_NEEDS_HARD)])
        ConfigManager.set_priority_goals(["Goal1"])
        rows, _ = self._rows(mgr, today=date(2026, 6, 1))
        parts = list(_walk(_render_goal_progress(rows)))
        name = next(p for p in parts if getattr(p, 'className', None) == 'gp-name')
        assert [getattr(c, 'className', None) for c in name.children] == [
            'gp-name-text', 'badge gp-rank']
        pct = next(p for p in parts if getattr(p, 'className', None) == 'gp-pct')
        assert pct.children == "0.3%"   # started, so not 0%
        bar = next(p for p in parts if getattr(p, 'className', None) == 'gp-bar')
        fmt = ConfigManager.format_time_friendly
        assert getattr(bar, 'data-tip').splitlines() == [
            "Goal1", f"{fmt(1)} of {fmt(300)} done",
            f"{fmt(1)} of it in the last 6 months, across 1 node"]

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
        from goal_ranking import _rank_goals
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
        """Milestones hold no work. Here M is constructed with manual time +
        high ratings + 100h, but the model forces every Milestone to a pure
        container (both modes inherited), so its value AND its 100h drop out
        of the Goal's score entirely. Work behind it still earns G's credit
        at one hop's discount, as if M weren't there."""
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

        from goal_ranking import _rank_goals
        ranked = _rank_goals(
            [n for n in nodes if n.type == 'Goal'],
            nodes, edges,
            ConfigManager.get_priority_goals(), hp,
            with_components=True,
        )
        comps = {g.name: c for g, c in ranked}
        work = next(n for n in nodes if n.name == "Work")

        g = hp.get('value_exponent', 1.0)
        expected_tv = (
            hp['w_v'] * 10 ** g + hp['w_i'] * 10 ** g
            + hp['d_H'] * (hp['w_v'] * 1 ** g + hp['w_i'] * 1 ** g)
        )
        assert comps["G"]["tv"] == pytest.approx(expected_tv)
        assert comps["G"]["n_tasks"] == 1
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

        from goal_ranking import _rank_goals, explain_goal
        ranked = dict(
            (g.name, c) for g, c in _rank_goals(
                [n for n in nodes if n.type == 'Goal'],
                nodes, edges, pgoals, hp, with_components=True)
        )
        bd, normalized = explain_goal("G", nodes, edges, hp, pgoals)
        assert bd['is_goal'] is True
        assert bd['eligible'] is True
        assert bd['score'] == round(ranked["G"]["score"], 2)
        # Only the Hard prerequisite is work toward G. Its worth splits into
        # its own ratings and the credit it earns for G.
        comp = bd['composition']
        assert [r['name'] for r in bd['contributors']] == ["P1"]
        assert comp['iv'] > 0 and comp['goal_credit'] > 0
        assert comp['iv'] + comp['goal_credit'] + comp['other_goal_credit'] == \
            pytest.approx(comp['total_value'])
        # Sole ranked goal -> normalized to the top (100).
        assert normalized == 100

    def test_explain_goal_rejects_non_goal(self, mgr):
        """explain_goal returns None for a non-Goal node."""
        _setup_graph(mgr, [_make_node("L", type="Learn")])
        nodes = mgr.get_all_nodes()
        from goal_ranking import explain_goal
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
        from goal_ranking import _rank_goals
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
        names = ["Solo"] + [f"Crowd{i}" for i in range(4)]
        _setup_graph(mgr, [
            _make_node("Solo", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="Self", subcontext="Creativity"),
        ] + [
            _make_node(f"Crowd{i}", type="Goal", time_mode='inherited',
                       value=5, interest=5,
                       context="STEM", subcontext="Math")
            for i in range(4)
        ] + [_make_node(f"Task{name}") for name in names],
            [(f"Task{name}", name, EDGE_NEEDS_HARD) for name in names])
        comps = self._rank_with(mgr)
        # Raw scores are identical (same ratings, same work). Density is the
        # tiebreaker.
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
        from goal_ranking import explain_goal
        bd, _ = explain_goal("G1", nodes, edges, hp,
                             ConfigManager.get_priority_goals())
        ca = bd['context_adjustment']
        assert ca['n_bucket'] == 2
        assert ca['alpha'] == pytest.approx(hp['alpha_goal'])
        assert ca['density_mult'] == pytest.approx(2 ** -hp['alpha_goal'])


# ============================================================================
# _compute_rating_distribution
# ============================================================================

class TestComputeRatingDistribution:
    def test_counts_and_mean(self, mgr):
        nodes = [_make_node("A", context="Mind", value=3),
                 _make_node("B", context="Mind", value=3),
                 _make_node("C", context="Mind", value=9)]
        dist = _compute_rating_distribution(nodes)
        v = dist['all']['value']
        assert v['counts'] == [0, 0, 2, 0, 0, 0, 0, 0, 1, 0]
        assert v['mean'] == pytest.approx(5.0)
        assert dist['all']['count'] == 3

    def test_skips_done_milestones_and_inherited(self, mgr):
        nodes = [_make_node("A", context="Mind"),
                 _make_node("B", context="Mind", status="Done"),
                 _make_node("C", context="Mind", type="Milestone"),
                 _make_node("D", context="Mind", value_mode="inherited")]
        assert _compute_rating_distribution(nodes)['all']['count'] == 1

    def test_effort_reads_difficulty(self, mgr):
        dist = _compute_rating_distribution([_make_node("A", difficulty=8)])
        assert dist['all']['effort']['counts'][7] == 1

    def test_order_by_time_with_no_subcontext_and_no_context_last(self, mgr):
        nodes = [
            _make_node("A", context="Mind", subcontext=None, time_m=500),
            _make_node("B", context="Mind", subcontext="Logic", time_m=1),
            _make_node("C", context="Mind", subcontext="Memory", time_m=50),
            _make_node("D", context="Body", subcontext="Strength", time_m=900),
            _make_node("E", context=None, time_m=5000),
        ]
        groups = _compute_rating_distribution(nodes)['groups']
        assert [g['row']['context'] for g in groups] == ['Body', 'Mind', 'No Context']
        mind = groups[1]
        assert mind['row']['subcontext'] is None
        assert mind['row']['count'] == 3
        assert [s['subcontext'] for s in mind['subs']] == [
            'Memory', 'Logic', 'No subcontext']

    def test_work_left_counts_every_open_node(self, mgr):
        """Time matches Work Time by Context: Milestones and inherited nodes
        add their time though they carry no ratings; Done nodes don't."""
        nodes = [
            _make_node("A", context="Mind", subcontext="Logic"),
            _make_node("B", context="Mind", subcontext="Logic",
                       value_mode="inherited"),
            _make_node("C", context="Mind", subcontext="Logic", status="Done"),
            _make_node("D", context="Body"),
        ]
        dist = _compute_rating_distribution(nodes)
        per = nodes[0].time
        mind = next(g for g in dist['groups'] if g['row']['context'] == 'Mind')
        assert mind['row']['count'] == 1
        assert mind['row']['time'] == pytest.approx(2 * per)
        assert mind['row']['share'] == pytest.approx(2 / 3)
        assert dist['all']['time'] == pytest.approx(3 * per)

    def test_work_left_splits_by_type_with_a_median(self, mgr):
        nodes = [
            _make_node("L", context="Mind", time_o=30, time_m=30, time_p=30),
            _make_node("R", context="Mind", type="Resource", time_o=10, time_m=10, time_p=10),
            _make_node("A", context="Mind", type="Action", time_o=20, time_m=20, time_p=20),
            _make_node("C", context="Mind", time_mode="inherited"),
        ]
        row = _compute_rating_distribution(nodes)['groups'][0]['row']
        assert row['time_by_type'] == {
            'Learn': pytest.approx(30), 'Resource': pytest.approx(10),
            'Action': pytest.approx(20)}
        # The container counts in the row but holds no time of its own.
        assert row['count'] == 4
        assert row['median_time'] == pytest.approx(20)

    def test_lone_no_subcontext_gets_no_child_rows(self, mgr):
        dist = _compute_rating_distribution(
            [_make_node("A", context="Mind", subcontext=None)])
        assert dist['groups'][0]['subs'] == []


class TestRenderRatingDistribution:
    def test_contexts_fold_and_cells_carry_definitions(self, mgr):
        from dash import html
        from analyze_callbacks import _render_rating_distribution
        nodes = [_make_node("A", context="Mind", subcontext="Logic", value=4),
                 _make_node("B", context="Mind", subcontext="Memory", value=6)]
        card = _render_rating_distribution(_compute_rating_distribution(nodes))

        def walk(c):
            yield c
            kids = getattr(c, 'children', None)
            for k in (kids if isinstance(kids, list) else [kids]):
                if hasattr(k, 'to_plotly_json'):
                    yield from walk(k)
        parts = list(walk(card))
        details = [p for p in parts if isinstance(p, html.Details)]
        assert len(details) == 1 and not getattr(details[0], 'open', None)
        tips = [getattr(p, 'data-tip') for p in parts
                if 'rd-cell' in (getattr(p, 'className', '') or '')]
        # All nodes, Mind, Logic, Memory: four rows of 3 x 10 cells.
        assert len(tips) == 4 * 30
        definition = ConfigManager.get_ratings_definitions()[3]['value']
        assert f"Mind > Logic\n1 of 1 node has Value 4\n{definition}" in tips
        assert "All nodes\n0 of 2 nodes have Value 1\n" in tips[0]

    @staticmethod
    def _parts(nodes):
        from analyze_callbacks import _render_rating_distribution
        card = _render_rating_distribution(_compute_rating_distribution(nodes))

        def walk(c):
            yield c
            kids = getattr(c, 'children', None)
            for k in (kids if isinstance(kids, list) else [kids]):
                if hasattr(k, 'to_plotly_json'):
                    yield from walk(k)
        return list(walk(card))

    @staticmethod
    def _gaps(parts):
        return sorted(p.className for p in parts
                      if (getattr(p, 'className', None) or '').startswith('rd-gap'))

    def test_guide_marks_all_nodes_mean_outside_the_top_row(self, mgr):
        parts = self._parts([_make_node("A", context="Mind", value=2),
                             _make_node("B", context="Body", value=8)])
        guides = [p for p in parts if getattr(p, 'className', None) == 'rd-guide']
        # Mind and Body rows, three ratings each; none in All nodes.
        assert len(guides) == 6
        means = [getattr(p, 'data-tip') for p in parts
                 if getattr(p, 'className', None) == 'rd-mean']
        assert means[0] == "All nodes\nMean Value: 5.0"
        assert "Mind\nMean Value: 2.0\n3.0 below all nodes (5.0)" in means
        # Interest and Effort match the graph, so only Value draws a gap:
        # Mind below, Body above.
        assert self._gaps(parts) == ['rd-gap above', 'rd-gap below']
        assert "Body\nMean Interest: 5.0\nSame as all nodes (5.0)" in means

    def test_gap_bars_skip_tiny_gaps(self, mgr):
        # Mind 5.0 and Body 5.25 around an overall 5.2: both under the cutoff.
        nodes = [_make_node("A", context="Mind", value=5),
                 _make_node("B", context="Body", value=5),
                 _make_node("C", context="Body", value=5),
                 _make_node("D", context="Body", value=6),
                 _make_node("E", context="Body", value=5)]
        assert self._gaps(self._parts(nodes)) == []

    def test_work_left_tooltip_gives_share_mix_and_median(self, mgr):
        parts = self._parts([
            _make_node("L", context="Mind", time_o=30, time_m=30, time_p=30),
            _make_node("A", context="Mind", type="Action", time_o=10, time_m=10, time_p=10),
            _make_node("B", context="Body", time_o=40, time_m=40, time_p=40),
        ])
        tips = [getattr(p, 'data-tip') for p in parts
                if getattr(p, 'className', None) == 'rd-work']
        assert tips[0] == "All nodes\nLearn 88% · Action 12%\nMedian node time: 1.5w"
        assert "Mind\n50% of all remaining work\nLearn 75% · Action 25%\nMedian node time: 1w" in tips
        segs = [p for p in parts if getattr(p, 'className', None) == 'rd-work-seg']
        assert len(segs) == 3   # Mind's two, Body's one

    def test_empty_graph_message(self, mgr):
        from analyze_callbacks import _render_rating_distribution
        card = _render_rating_distribution(_compute_rating_distribution([]))
        assert "No open rated nodes." in str(card)


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


# ============================================================================
# Status gating: un-done nodes must drop out of completion-based analytics
# ============================================================================

class TestThroughputStatusGate:
    """done_date/actual-time data lingers when a node is reverted from Done
    (older reverts predate the auto-clear), so throughput must gate on the
    node's *current* status, not merely the presence of a done_date."""

    def test_done_node_charted(self):
        nodes = [_make_node("DoneA", status="Done", done_date="2026-01-15")]
        assert "DoneA" in _throughput_node_names(_compute_throughput(nodes))

    def test_undone_node_with_lingering_done_date_excluded(self):
        nodes = [
            _make_node("DoneA", status="Done", done_date="2026-01-15"),
            _make_node("RevertedB", status="Open", done_date="2026-01-20"),
        ]
        names = _throughput_node_names(_compute_throughput(nodes))
        assert "DoneA" in names
        assert "RevertedB" not in names

    def test_blocked_node_with_done_date_excluded(self):
        nodes = [_make_node("X", status="Blocked", done_date="2026-02-01")]
        assert _compute_throughput(nodes) == []


class TestThroughputCapacity:
    """Each bucket carries the hours a week from the time settings, spread
    over its days, and the chart runs to today so quiet months show."""

    @staticmethod
    def _per_day():
        return ConfigManager.get_time_settings()['hours_per_week'] / 7

    def test_runs_to_today_with_the_current_month_prorated(self):
        nodes = [_make_node("A", status="Done", done_date="2026-01-15")]
        rows = _compute_throughput(nodes, granularity='month',
                                   today=date(2026, 3, 10))
        assert [r['label'] for r in rows] == ['Jan 2026', 'Feb 2026', 'Mar 2026']
        assert [r['capacity'] for r in rows] == [
            pytest.approx(31 * self._per_day()), pytest.approx(28 * self._per_day()),
            pytest.approx(10 * self._per_day())]
        assert rows[1]['segments'] == []

    def test_dates_trim_the_buckets_they_fall_in(self):
        nodes = [_make_node("A", status="Done", done_date="2026-02-15")]
        rows = _compute_throughput(nodes, granularity='quarter',
                                   start_date="2026-02-01", end_date="2026-02-20",
                                   today=date(2026, 9, 1))
        assert [r['label'] for r in rows] == ['2026 Q1']
        assert rows[0]['capacity'] == pytest.approx(20 * self._per_day())

    def test_segments_by_type_stack_in_type_order(self):
        nodes = [_make_node("A", type="Action", status="Done", done_date="2026-01-15"),
                 _make_node("L", status="Done", done_date="2026-01-20"),
                 _make_node("R", type="Resource", status="Done", done_date="2026-01-21")]
        rows = _compute_throughput(nodes, granularity='month', by='type',
                                   today=date(2026, 1, 31))
        assert [s['key'] for s in rows[0]['segments']] == ['Learn', 'Resource', 'Action']

    def test_chart_draws_a_capacity_step_across_each_slot(self):
        from analyze_callbacks import _render_throughput_chart
        nodes = [_make_node("A", status="Done", done_date="2026-01-15")]
        rows = _compute_throughput(nodes, granularity='month', today=date(2026, 2, 14))
        fig = _figure(_render_throughput_chart(rows, granularity='month'))
        line = next(t for t in fig.data if t.type == 'scatter')
        assert list(line.x) == [-0.5, 0.5, 0.5, 1.5]
        assert list(line.y) == [pytest.approx(31 * self._per_day())] * 2 + [
            pytest.approx(14 * self._per_day())] * 2
        assert not fig.layout.showlegend   # contexts name themselves on hover
        fig = _figure(_render_throughput_chart(
            _compute_throughput(nodes, granularity='month', by='type',
                                today=date(2026, 2, 14)),
            granularity='month', by='type'))
        assert fig.layout.showlegend


class TestReflectionDriftStatusGate:
    """reflect_* columns persist across un-Done, so the drift chart must
    only count currently-Done reflected nodes."""

    def test_undone_reflected_node_not_counted(self):
        nodes = [
            _make_node(n, status="Done", context="Mind", value=5, reflect_value=v)
            for n, v in (("A", 8), ("B", 7), ("C", 6), ("D", 7))
        ] + [
            # Reverted to Open but still carrying a reflection — must be ignored.
            _make_node("E", status="Open", context="Mind", value=5, reflect_value=2),
        ]
        rows = _compute_reflection_drift(nodes)
        mind = next(r for r in rows if r["context"] == "Mind")
        assert mind["count"] == 4                      # E excluded from the total
        assert mind["d_value"] == 2.0                  # mean over A-D ((3+2+1+2)/4)

    def test_context_drops_below_min_after_revert(self):
        names = ("A", "B", "C", "D")
        # Four Done reflected nodes => context qualifies (MIN_N == 4).
        done = [_make_node(n, status="Done", context="Body", value=5,
                           reflect_value=6) for n in names]
        assert any(r["context"] == "Body" for r in _compute_reflection_drift(done))
        # Revert one: only three reflected Done nodes remain => context drops out.
        reverted = done[:3] + [_make_node("D", status="Open", context="Body",
                                          value=5, reflect_value=6)]
        assert all(r["context"] != "Body" for r in _compute_reflection_drift(reverted))



class TestAnalyzeRefreshGate:
    """Arrivals and the hover prewarm must skip a render that is still
    current, redo one the graph outran, and ignore the stores' mount."""

    ARGS = (25, 75, 'quarter', '', '', 'context', None)
    PROPS = {'analyze-active-store': 'data', 'analyze-prewarm-store': 'data',
             'save-output': 'children'}

    @pytest.fixture
    def refresh(self, monkeypatch):
        import types
        import dash
        import analyze_callbacks

        monkeypatch.setattr(analyze_callbacks, '_last_render', None)
        app = dash.Dash(__name__)
        app.config.suppress_callback_exceptions = True
        analyze_callbacks.register_analyze_callbacks(app)
        spec = app.callback_map[next(k for k in app.callback_map
                                     if 'analyze-overview-content' in k)]
        fn = spec['callback']
        while hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__

        def call(trigger, active_tab, rendered, value=1):
            monkeypatch.setattr(analyze_callbacks, 'ctx', types.SimpleNamespace(
                triggered_id=trigger,
                triggered_prop_ids={f'{trigger}.{self.PROPS[trigger]}': trigger}))
            return fn(value, value, *self.ARGS, active_tab, rendered)
        return call

    def test_store_mounts_are_not_arrivals(self, refresh):
        """A dcc.Store whose data starts as None reports a change when it
        mounts. Analyze no longer renders at startup, so that must not."""
        from dash import no_update
        GraphManager().add_node(_make_node("A"))
        for store in ('analyze-active-store', 'analyze-prewarm-store'):
            assert refresh(store, 'tab-next', None, value=None) == (no_update,) * 10

    def test_click_after_hover_reuses_the_prewarm_render(self, refresh, monkeypatch):
        import analyze_callbacks
        GraphManager().add_node(_make_node("A"))
        calls = []
        real = analyze_callbacks._render_analyze_sections
        monkeypatch.setattr(analyze_callbacks, '_render_analyze_sections',
                            lambda *a: calls.append(a) or real(*a))
        refresh('analyze-prewarm-store', 'tab-next', None)
        # Dash drops the prewarm's response once the click re-requests, so
        # the click arrives with no signature and must not compute again.
        refresh('analyze-active-store', 'tab-analyze', None)
        assert len(calls) == 1

    def test_save_on_the_tab_always_rerenders(self, refresh, monkeypatch):
        """A reflection edit changes the charts without moving the signature."""
        import analyze_callbacks
        GraphManager().add_node(_make_node("A"))
        signature = refresh('analyze-prewarm-store', 'tab-next', None)[-1]
        calls = []
        real = analyze_callbacks._render_analyze_sections
        monkeypatch.setattr(analyze_callbacks, '_render_analyze_sections',
                            lambda *a: calls.append(a) or real(*a))
        refresh('save-output', 'tab-analyze', signature)
        assert len(calls) == 1

    def test_prewarm_renders_while_hidden_and_uncovers(self, refresh):
        GraphManager().add_node(_make_node("A"))
        out = refresh('analyze-prewarm-store', 'tab-next', None)
        assert out[-3:-1] == (False, True)
        assert out[-1]

    def test_arrival_skips_a_current_render(self, refresh):
        from dash import no_update
        GraphManager().add_node(_make_node("A"))
        signature = refresh('analyze-prewarm-store', 'tab-next', None)[-1]
        assert refresh('analyze-active-store', 'tab-analyze',
                       signature) == (no_update,) * 10

    def test_arrival_rerenders_after_a_graph_change(self, refresh):
        from dash import no_update
        GraphManager().add_node(_make_node("A"))
        signature = refresh('analyze-prewarm-store', 'tab-next', None)[-1]
        GraphManager().add_node(_make_node("B"))
        out = refresh('analyze-active-store', 'tab-analyze', signature)
        assert out[0] is not no_update
        assert out[-1] != signature

    def test_settings_changes_off_tab_do_nothing(self, refresh):
        from dash import no_update
        assert refresh('save-output', 'tab-next', None) == (no_update,) * 10

    def test_failed_render_uncovers_and_retries(self, refresh, monkeypatch):
        import analyze_callbacks
        def boom(*_args):
            raise RuntimeError("boom")
        monkeypatch.setattr(analyze_callbacks, '_render_analyze_sections', boom)
        out = refresh('analyze-active-store', 'tab-analyze', None)
        assert out[-3:-1] == (False, True)
        assert out[-1] is None
