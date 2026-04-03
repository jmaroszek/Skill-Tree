"""
Tests for the Monte Carlo simulation engine (simulation.py).

Covers PERT-Beta sampling, single-node duration sampling, full task-chain
simulation with critical-path analysis, and statistics computation.
"""

import math
import numpy as np
import pytest
from models import Node
from simulation import pert_beta_sample, _sample_node, simulate_task_chain, _compute_stats


def _make_node(name="N", time_o=1.0, time_m=2.0, time_p=4.0, status="Open", **kw):
    defaults = dict(
        name=name, type="Learn", description="", value=5,
        time_o=time_o, time_m=time_m, time_p=time_p,
        interest=5, difficulty=5, status=status, context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


# ============================================================================
# pert_beta_sample
# ============================================================================

class TestPertBetaSample:
    def test_output_shape(self):
        samples = pert_beta_sample(1.0, 3.0, 5.0, size=500)
        assert samples.shape == (500,)

    def test_samples_within_bounds(self):
        samples = pert_beta_sample(2.0, 5.0, 10.0, size=5000)
        assert np.all(samples >= 2.0)
        assert np.all(samples <= 10.0)

    def test_mean_near_mode(self):
        # PERT distribution with symmetric spread — mean should be near mode
        samples = pert_beta_sample(1.0, 5.0, 9.0, size=50000)
        assert abs(np.mean(samples) - 5.0) < 0.5

    def test_degenerate_p_leq_o_returns_constant(self):
        samples = pert_beta_sample(5.0, 3.0, 2.0, size=100)
        assert np.all(samples == 3.0)

    def test_degenerate_p_leq_zero(self):
        samples = pert_beta_sample(0.0, 2.0, 0.0, size=100)
        assert np.all(samples == 2.0)

    def test_mode_clamped_to_o(self):
        # m <= o should be clamped up slightly
        samples = pert_beta_sample(5.0, 3.0, 10.0, size=1000)
        assert np.all(samples >= 5.0)
        assert np.all(samples <= 10.0)

    def test_mode_clamped_to_p(self):
        # m >= p should be clamped down slightly
        samples = pert_beta_sample(1.0, 12.0, 10.0, size=1000)
        assert np.all(samples >= 1.0)
        assert np.all(samples <= 10.0)


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
        samples = _sample_node(node, 5000)
        # Should sample around M with approximate spread
        assert abs(np.mean(samples) - 5.0) < 1.5

    def test_only_o_and_p_provided(self):
        node = _make_node(time_o=4.0, time_m=0, time_p=16.0)
        samples = _sample_node(node, 5000)
        geo_mean = math.sqrt(4.0 * 16.0)  # 8.0
        assert abs(np.mean(samples) - geo_mean) < 2.0

    def test_full_estimates(self):
        node = _make_node(time_o=2.0, time_m=5.0, time_p=10.0)
        samples = _sample_node(node, 5000)
        assert np.all(samples >= 2.0)
        assert np.all(samples <= 10.0)

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

    def test_no_edges_single_node_only(self):
        nodes = {
            "A": _make_node("A"),
            "B": _make_node("B"),
        }
        result = simulate_task_chain("A", nodes, [], n_simulations=500)
        assert result['chain_nodes'] == ["A"]
        assert result['chain_size'] == 1
