"""
Tests for the Monte Carlo simulation engine (simulation.py).

Covers quantile-matched duration sampling, single-node duration sampling, full
task-chain simulation, chain correlation, and statistics computation.
"""

import math
import numpy as np
import pytest
from models import Node
from models import expected_time_estimate
from simulation import (Z90, duration_sample, _sample_node, simulate_task_chain,
                        _compute_stats, fitted_duration_quantiles, bracket_diagnostics)


def _make_node(name="N", time_o=1.0, time_m=2.0, time_p=4.0, status="Open", **kw):
    defaults = dict(
        name=name, type="Learn", description="", value=5,
        time_o=time_o, time_m=time_m, time_p=time_p,
        interest=5, difficulty=5, status=status, context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


# ============================================================================
# duration_sample
# ============================================================================

class TestDurationSample:
    def test_output_shape(self):
        assert duration_sample(1.0, 3.0, 5.0, size=500).shape == (500,)

    def test_mean_matches_the_point_estimate(self):
        # The contract the whole module rests on: E[sample] == Node.time.
        rng = np.random.default_rng(0)
        samples = duration_sample(50.0, 116.0, 200.0, size=400_000, rng=rng)
        expected = expected_time_estimate(50.0, 116.0, 200.0)
        assert abs(np.mean(samples) / expected - 1) < 0.01

    def test_p10_to_p90_span_equals_the_stated_bracket(self):
        rng = np.random.default_rng(1)
        samples = duration_sample(20.0, 40.0, 80.0, size=400_000, rng=rng)
        lo, hi = np.percentile(samples, [10, 90])
        assert abs((hi / lo) / (80.0 / 20.0) - 1) < 0.02

    def test_upper_estimate_is_exceeded_about_a_tenth_of_the_time(self):
        # The point of reading `p` as P90 rather than as a hard ceiling.
        rng = np.random.default_rng(2)
        samples = duration_sample(20.0, 40.0, 80.0, size=200_000, rng=rng)
        assert 0.03 < np.mean(samples > 80.0) < 0.20

    def test_always_positive(self):
        rng = np.random.default_rng(3)
        assert np.all(duration_sample(1.0, 2.0, 40.0, size=20_000, rng=rng) > 0)

    def test_degenerate_bracket_returns_the_point_estimate(self):
        samples = duration_sample(3.0, 3.0, 3.0, size=100)
        assert np.all(samples == 3.0)

    def test_inverted_bracket_returns_constant(self):
        samples = duration_sample(5.0, 3.0, 2.0, size=100)
        assert np.all(samples == expected_time_estimate(5.0, 3.0, 2.0))

    def test_shared_draw_is_reused_when_fully_correlated(self):
        shared = np.random.default_rng(4).standard_normal(1000)
        a = duration_sample(10., 20., 40., 1000, correlation=1.0, shared=shared)
        b = duration_sample(10., 20., 40., 1000, correlation=1.0, shared=shared)
        assert np.allclose(a, b)

    def test_correlation_does_not_change_the_marginal(self):
        lo = duration_sample(10., 20., 40., 300_000, rng=np.random.default_rng(5),
                             correlation=0.0)
        hi = duration_sample(10., 20., 40., 300_000, rng=np.random.default_rng(6),
                             correlation=0.6,
                             shared=np.random.default_rng(7).standard_normal(300_000))
        assert abs(np.mean(lo) / np.mean(hi) - 1) < 0.02
        assert abs(np.std(lo) / np.std(hi) - 1) < 0.05


# ============================================================================
# _sample_node
# ============================================================================

class TestSampleNode:
    def test_all_zeros_returns_one(self):
        node = _make_node(time_o=0, time_m=0, time_p=0)
        samples = _sample_node(node, 100)
        assert np.all(samples == 1.0)

    def test_only_m_provided(self):
        node = _make_node(time_o=0, time_m=5.0, time_p=0)
        samples = _sample_node(node, 200_000, rng=np.random.default_rng(42))
        assert np.mean(samples) == pytest.approx(node.time, rel=0.01)
        assert np.std(samples) > 0

    def test_only_o_and_p_provided(self):
        node = _make_node(time_o=4.0, time_m=0, time_p=16.0)
        samples = _sample_node(node, 20000)
        assert np.mean(samples) == pytest.approx(
            expected_time_estimate(4.0, 0.0, 16.0), rel=0.05)

    def test_full_estimates(self):
        node = _make_node(time_o=2.0, time_m=5.0, time_p=10.0)
        samples = _sample_node(node, 5000)
        assert np.all(samples > 0)
        # Not bounded by [o, p] any more — those are the 10th and 90th
        # percentiles, so mass has to fall outside them.
        assert np.mean(samples) == pytest.approx(
            expected_time_estimate(2.0, 5.0, 10.0), rel=0.06)

    def test_equal_estimates_returns_constant(self):
        node = _make_node(time_o=3.0, time_m=3.0, time_p=3.0)
        samples = _sample_node(node, 100)
        assert np.all(samples == 3.0)

    def test_o_negative_clamped(self):
        node = _make_node(time_o=-1.0, time_m=2.0, time_p=5.0)
        samples = _sample_node(node, 500)
        assert np.all(samples > 0)

    def test_m_less_than_o_clamped(self):
        node = _make_node(time_o=5.0, time_m=2.0, time_p=10.0)
        samples = _sample_node(node, 500)
        assert np.all(samples > 0)


# ============================================================================
# _compute_stats
# ============================================================================

class TestComputeStats:
    def test_all_zeros(self):
        stats = _compute_stats(np.zeros(100))
        assert all(v == 0.0 for v in stats.values())

    def test_constant_samples(self):
        stats = _compute_stats(np.full(1000, 5.0))
        assert stats['mean'] == 5.0
        assert stats['std'] == 0.0
        assert stats['p50'] == 5.0
        assert stats['min'] == 5.0
        assert stats['max'] == 5.0

    def test_known_statistics(self):
        # Uniform discrete values
        samples = np.array([1.0, 2.0, 3.0, 4.0, 5.0] * 200)
        stats = _compute_stats(samples)
        assert stats['mean'] == 3.0
        assert stats['min'] == 1.0
        assert stats['max'] == 5.0
        assert stats['p50'] == 3.0

    def test_percentile_ordering(self):
        np.random.seed(42)
        samples = np.random.lognormal(2, 1, size=10000)
        stats = _compute_stats(samples)
        assert stats['p10'] <= stats['p25'] <= stats['p50'] <= stats['p75'] <= stats['p90']
        assert stats['min'] <= stats['p10']
        assert stats['p90'] <= stats['max']

    def test_all_keys_present(self):
        stats = _compute_stats(np.array([1.0, 2.0, 3.0]))
        expected_keys = {'mean', 'std', 'p10', 'p25', 'p50', 'p75', 'p90', 'min', 'max'}
        assert set(stats.keys()) == expected_keys


# ============================================================================
# simulate_task_chain
# ============================================================================

class TestSimulateTaskChain:
    def test_single_node(self):
        nodes = {"A": _make_node("A", time_o=2, time_m=4, time_p=8)}
        result = simulate_task_chain("A", nodes, [], n_simulations=1000)
        assert result['chain_size'] == 1
        assert result['chain_nodes'] == ["A"]
        assert len(result['samples']) == 1000
        assert result['stats']['mean'] > 0

    def test_linear_chain(self):
        # A → B → C (all hardcoded to 1h each → total ~3h)
        nodes = {
            "A": _make_node("A", time_o=1, time_m=1, time_p=1),
            "B": _make_node("B", time_o=1, time_m=1, time_p=1),
            "C": _make_node("C", time_o=1, time_m=1, time_p=1),
        }
        edges = [
            {"source": "A", "target": "B", "type": "Needs_Hard"},
            {"source": "B", "target": "C", "type": "Needs_Hard"},
        ]
        result = simulate_task_chain("C", nodes, edges, n_simulations=500)
        assert result['chain_size'] == 3
        assert result['stats']['mean'] == pytest.approx(3.0, abs=0.1)

    def test_parallel_prereqs_sums_serial(self):
        # A (1h) and B (5h) both required before C (1h)
        # Serial total = 1 + 5 + 1 = 7h (single person does one task at a time)
        nodes = {
            "A": _make_node("A", time_o=1, time_m=1, time_p=1),
            "B": _make_node("B", time_o=5, time_m=5, time_p=5),
            "C": _make_node("C", time_o=1, time_m=1, time_p=1),
        }
        edges = [
            {"source": "A", "target": "C", "type": "Needs_Hard"},
            {"source": "B", "target": "C", "type": "Needs_Hard"},
        ]
        result = simulate_task_chain("C", nodes, edges, n_simulations=500)
        assert result['stats']['mean'] == pytest.approx(7.0, abs=0.1)

    def test_done_nodes_excluded(self):
        # A is Done, B depends on A → only B should be in the chain
        nodes = {
            "A": _make_node("A", time_o=10, time_m=10, time_p=10, status="Done"),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
        }
        edges = [{"source": "A", "target": "B", "type": "Needs_Hard"}]
        result = simulate_task_chain("B", nodes, edges, n_simulations=500)
        assert result['chain_size'] == 1
        assert "A" not in result['chain_nodes']
        assert result['stats']['mean'] == pytest.approx(2.0, abs=0.1)

    def test_all_done_returns_zeroes(self):
        nodes = {
            "A": _make_node("A", status="Done"),
            "B": _make_node("B", status="Done"),
        }
        edges = [{"source": "A", "target": "B", "type": "Needs_Hard"}]
        result = simulate_task_chain("B", nodes, edges, n_simulations=500)
        assert result['chain_size'] == 0
        assert result['stats']['mean'] == 0.0

    def test_soft_deps_included_for_target(self):
        # A (soft dep) → B (target)
        nodes = {
            "A": _make_node("A", time_o=3, time_m=3, time_p=3),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
        }
        edges = [{"source": "A", "target": "B", "type": "Needs_Soft"}]
        result = simulate_task_chain("B", nodes, edges, include_soft=True, n_simulations=500)
        assert result['chain_size'] == 2  # Both included

    def test_soft_deps_excluded_when_disabled(self):
        nodes = {
            "A": _make_node("A", time_o=3, time_m=3, time_p=3),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
        }
        edges = [{"source": "A", "target": "B", "type": "Needs_Soft"}]
        result = simulate_task_chain("B", nodes, edges, include_soft=False, n_simulations=500)
        assert result['chain_size'] == 1

    def test_helps_included_when_enabled(self):
        nodes = {
            "A": _make_node("A", time_o=3, time_m=3, time_p=3),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
        }
        edges = [{"source": "A", "target": "B", "type": "Helps"}]
        result = simulate_task_chain("B", nodes, edges, include_helps=True, n_simulations=500)
        assert result['chain_size'] == 2

    def test_helps_excluded_by_default(self):
        nodes = {
            "A": _make_node("A", time_o=3, time_m=3, time_p=3),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
        }
        edges = [{"source": "A", "target": "B", "type": "Helps"}]
        result = simulate_task_chain("B", nodes, edges, include_helps=False, n_simulations=500)
        assert result['chain_size'] == 1

    def test_missing_node_in_dict_uses_default(self):
        # Edge references "Ghost" which isn't in nodes_dict
        nodes = {"A": _make_node("A", time_o=2, time_m=2, time_p=2)}
        edges = [{"source": "Ghost", "target": "A", "type": "Needs_Hard"}]
        result = simulate_task_chain("A", nodes, edges, n_simulations=500)
        # Should not crash — Ghost gets default 1h
        assert result['chain_size'] >= 1

    def test_diamond_dependency(self):
        # A → B, A → C, B → D, C → D
        # A=1h, B=2h, C=3h, D=1h
        # Serial total: 1 + 2 + 3 + 1 = 7h
        nodes = {
            "A": _make_node("A", time_o=1, time_m=1, time_p=1),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
            "C": _make_node("C", time_o=3, time_m=3, time_p=3),
            "D": _make_node("D", time_o=1, time_m=1, time_p=1),
        }
        edges = [
            {"source": "A", "target": "B", "type": "Needs_Hard"},
            {"source": "A", "target": "C", "type": "Needs_Hard"},
            {"source": "B", "target": "D", "type": "Needs_Hard"},
            {"source": "C", "target": "D", "type": "Needs_Hard"},
        ]
        result = simulate_task_chain("D", nodes, edges, n_simulations=500)
        assert result['chain_size'] == 4
        assert result['stats']['mean'] == pytest.approx(7.0, abs=0.1)

    def test_goal_node_zero_estimates_contributes_zero(self):
        # Goal node with all-zero estimates should not add spurious 1h default
        nodes = {
            "A": _make_node("A", time_o=2, time_m=2, time_p=2),
            "G": _make_node("G", time_o=0, time_m=0, time_p=0, type="Goal"),
        }
        edges = [{"source": "A", "target": "G", "type": "Needs_Hard"}]
        result = simulate_task_chain("G", nodes, edges, n_simulations=500)
        # Should be ~2h (just A), not 3h (A + 1h default for Goal)
        assert result['stats']['mean'] == pytest.approx(2.0, abs=0.1)

    def test_inherited_node_skipped_even_with_nonzero_omp(self):
        """An inherited-mode node is a container — its preserved o/m/p must
        not contribute time to the simulation. Guards against regressions
        from when models.__post_init__ stopped zeroing those fields."""
        nodes = {
            "A": _make_node("A", time_o=2, time_m=2, time_p=2),
            "Container": _make_node("Container", type="Goal", time_mode='inherited',
                                    time_o=99, time_m=99, time_p=99),
        }
        edges = [{"source": "A", "target": "Container", "type": "Needs_Hard"}]
        result = simulate_task_chain("Container", nodes, edges, n_simulations=500)
        # ~2h from A only; Container's 99h is invisible because it's inherited.
        assert result['stats']['mean'] == pytest.approx(2.0, abs=0.1)

    def test_no_edges_single_node_only(self):
        nodes = {
            "A": _make_node("A"),
            "B": _make_node("B"),
        }
        result = simulate_task_chain("A", nodes, [], n_simulations=500)
        assert result['chain_nodes'] == ["A"]
        assert result['chain_size'] == 1


# ============================================================================
# Regression tests: serial execution model
#
# These tests guard against regressing back to critical-path analysis.
# The original bug: parallel independent tasks returned max(durations)
# instead of sum(durations), drastically understating the single-person
# total work time.
# ============================================================================

class TestSerialExecutionRegression:
    """Ensures the simulation always computes the sum of all task durations,
    not the critical-path maximum, regardless of dependency structure."""

    def test_many_parallel_tasks_sum_not_max(self):
        """10 independent tasks at 1h each must yield ~10h, never ~1h.
        This was the primary symptom of the bug: P50 ≈ 1h instead of 10h."""
        nodes = {f"T{i}": _make_node(f"T{i}", time_o=1, time_m=1, time_p=1)
                 for i in range(10)}
        # All are prereqs of the target, none depend on each other
        target = _make_node("Goal", time_o=0, time_m=0, time_p=0, type="Goal")
        nodes["Goal"] = target
        edges = [{"source": f"T{i}", "target": "Goal", "type": "Needs_Hard"}
                 for i in range(10)]
        result = simulate_task_chain("Goal", nodes, edges, n_simulations=1000)
        # Serial total ≈ 10h; critical-path would be ≈ 1h
        assert result['stats']['mean'] == pytest.approx(10.0, abs=0.2), (
            "10 parallel 1h tasks for a single person should total ~10h, not ~1h"
        )

    def test_wide_tree_exceeds_longest_branch(self):
        """In a tree where one branch is longer than others, serial time must
        still exceed the longest branch (unlike critical-path which equals it)."""
        # Branch A: 5h. Branch B: 2h. Branch C: 1h. The Goal is a container
        # (forced time_mode='inherited' by the model), so it contributes 0h —
        # serial = 5 + 2 + 1 = 8h.
        nodes = {
            "A": _make_node("A", time_o=5, time_m=5, time_p=5),
            "B": _make_node("B", time_o=2, time_m=2, time_p=2),
            "C": _make_node("C", time_o=1, time_m=1, time_p=1),
            "Goal": _make_node("Goal", time_o=1, time_m=1, time_p=1, type="Goal"),
        }
        edges = [
            {"source": "A", "target": "Goal", "type": "Needs_Hard"},
            {"source": "B", "target": "Goal", "type": "Needs_Hard"},
            {"source": "C", "target": "Goal", "type": "Needs_Hard"},
        ]
        result = simulate_task_chain("Goal", nodes, edges, n_simulations=1000)
        # Serial = 5 + 2 + 1 = 8 (Goal contributes 0 as a container).
        # Critical-path would be max(5,2,1) = 5.
        assert result['stats']['mean'] == pytest.approx(8.0, abs=0.2), (
            "Serial time must be the sum of all branches, not just the longest"
        )
        assert result['stats']['mean'] > 5.0, (
            "Serial total must exceed the longest single task duration"
        )

    def test_serial_chain_unchanged_by_model(self):
        """For a perfectly sequential chain, serial and critical-path give the
        same answer. This test confirms the model change didn't break chains."""
        nodes = {
            "A": _make_node("A", time_o=3, time_m=3, time_p=3),
            "B": _make_node("B", time_o=4, time_m=4, time_p=4),
            "C": _make_node("C", time_o=2, time_m=2, time_p=2),
        }
        edges = [
            {"source": "A", "target": "B", "type": "Needs_Hard"},
            {"source": "B", "target": "C", "type": "Needs_Hard"},
        ]
        result = simulate_task_chain("C", nodes, edges, n_simulations=1000)
        assert result['stats']['mean'] == pytest.approx(9.0, abs=0.2)


# ============================================================================
# Chain coherence and correlation
#
# These pin the two properties the duration model is built around: the
# simulated total is centred on exactly the number the score uses, and chain
# uncertainty does not evaporate as the chain gets longer.
# ============================================================================

def _chain(n, **kw):
    nodes = {f"N{i}": _make_node(f"N{i}", **kw) for i in range(n)}
    edges = [{"source": f"N{i}", "target": f"N{i+1}", "type": "Needs_Hard"}
             for i in range(n - 1)]
    return nodes, edges


class TestChainCoherence:
    @pytest.mark.parametrize('rho', [0.0, 0.4, 1.0])
    def test_expected_only_chain_preserves_mean(self, rho):
        nodes, edges = _chain(5, time_o=0, time_m=100, time_p=0)
        result = simulate_task_chain('N4', nodes, edges, n_simulations=100_000,
                                     rng=np.random.default_rng(42), correlation=rho)
        assert result['stats']['mean'] == pytest.approx(500, rel=0.01)

    def test_chain_mean_equals_sum_of_node_times(self):
        nodes, edges = _chain(12, time_o=20.0, time_m=40.0, time_p=80.0)
        result = simulate_task_chain(f"N11", nodes, edges, n_simulations=120_000,
                                     rng=np.random.default_rng(0))
        assert result['stats']['mean'] == pytest.approx(
            sum(n.time for n in nodes.values()), rel=0.01)

    def test_correlation_leaves_the_chain_mean_alone(self):
        nodes, edges = _chain(12, time_o=20.0, time_m=40.0, time_p=80.0)
        expected = sum(n.time for n in nodes.values())
        for rho in (0.0, 0.4, 1.0):
            result = simulate_task_chain("N11", nodes, edges, n_simulations=120_000,
                                         rng=np.random.default_rng(1), correlation=rho)
            assert result['stats']['mean'] == pytest.approx(expected, rel=0.02), rho

    def test_correlation_widens_the_chain(self):
        nodes, edges = _chain(30, time_o=20.0, time_m=40.0, time_p=80.0)
        spreads = []
        for rho in (0.0, 0.3, 0.7):
            s = simulate_task_chain("N29", nodes, edges, n_simulations=60_000,
                                    rng=np.random.default_rng(2), correlation=rho)['stats']
            spreads.append(s['p90'] / s['p10'])
        assert spreads == sorted(spreads)
        # Independence collapses a 30-task chain to a near-point estimate; the
        # shared factor is what keeps a long project honestly uncertain.
        assert spreads[0] < 1.35 < spreads[2]

    def test_independent_chain_spread_shrinks_with_length_but_correlated_does_not(self):
        def spread(n, rho):
            nodes, edges = _chain(n, time_o=20.0, time_m=40.0, time_p=80.0)
            s = simulate_task_chain(f"N{n-1}", nodes, edges, n_simulations=60_000,
                                    rng=np.random.default_rng(3), correlation=rho)['stats']
            return s['p90'] / s['p10']
        assert spread(60, 0.0) < spread(6, 0.0) - 0.15
        assert spread(60, 0.5) == pytest.approx(spread(6, 0.5), rel=0.15)

    def test_rejects_out_of_range_correlation(self):
        nodes, edges = _chain(2, time_o=1.0, time_m=2.0, time_p=4.0)
        for bad in (-0.1, 1.1):
            with pytest.raises(ValueError):
                simulate_task_chain("N1", nodes, edges, n_simulations=100, correlation=bad)


def test_asymmetric_fit_is_reported_without_changing_the_distribution():
    n = _make_node(time_o=10, time_m=90, time_p=100)
    fitted = fitted_duration_quantiles(10, 90, 100)
    assert fitted == pytest.approx([14.5747, 46.0892, 145.747], rel=0.001)
    samples = _sample_node(n, 200_000, rng=np.random.default_rng(52))
    assert np.percentile(samples, [10, 50, 90]) == pytest.approx(fitted, rel=0.02)
    rows = bracket_diagnostics([n])
    assert rows[0]['supplied'] == [10, 90, 100]
    assert rows[0]['fitted'] == list(fitted)


def test_bracket_diagnostics_only_compare_supplied_remaining_task_values():
    nodes = [_make_node('symmetric', time_o=20, time_m=40, time_p=80),
             _make_node('point', time_o=0, time_m=100, time_p=0),
             _make_node('done', time_o=10, time_m=90, time_p=100, status='Done'),
             _make_node('container', time_o=10, time_m=90, time_p=100,
                        time_mode='inherited')]
    assert bracket_diagnostics(nodes) == []
    two_point = _make_node('two', time_o=1, time_m=0, time_p=100)
    assert bracket_diagnostics([two_point])[0]['supplied'] == [1, None, 100]
