"""
Monte Carlo simulation engine for duration forecasting.

Samples per-node durations from a lognormal matched to the node's quantile
bracket (see `models.expected_time_estimate` for what the three inputs mean) and
sums them across the dependency chain — this assumes one person working on one
task at a time, not parallel execution.

Two properties tie this module to the headline number the rest of the app shows:

* Each node's marginal is mean-matched, so ``E[chain total]`` is exactly the sum
  of the nodes' `Node.time` values. The histogram and the score cannot drift.
* Tasks are coupled by a shared factor (`correlation`) rather than sampled
  independently. Independence makes a chain's relative spread shrink like
  1/sqrt(N), which quoted a 116-task project to +/-3% — an artefact of the
  assumption, not a forecast. The shared factor leaves every marginal (and
  therefore every mean) untouched and only changes how the chain adds up.
"""

import math
from collections import deque

import numpy as np
from typing import Dict, List
from models import STATUS_DONE, expected_time_estimate

# Phi^-1(0.90). The bracket [o, p] is read as a P10/P90 pair, so it spans
# 2 * Z90 standard deviations of log-duration.
Z90 = 1.2815515655446004

_CHUNK = 2048


def _standard_normal(size: int, rng, correlation: float, shared) -> np.ndarray:
    """A standard normal draw carrying `correlation` of its variance in common
    with every other task in the chain.

    ``Z = sqrt(rho)*Z_shared + sqrt(1-rho)*Z_own`` is itself standard normal for
    any rho in [0, 1], which is why raising rho widens the chain without
    touching any single task's own distribution.
    """
    random = rng if rng is not None else np.random
    if shared is None or correlation <= 0.0:
        return random.standard_normal(size)
    if correlation >= 1.0:
        return shared
    return math.sqrt(correlation) * shared + math.sqrt(1.0 - correlation) * random.standard_normal(size)


def duration_sample(o: float, m: float, p: float, size: int = 10000, rng=None,
                    *, correlation: float = 0.0, shared=None, mean=None) -> np.ndarray:
    """Sample a task's duration — the sampler counterpart of
    `models.expected_time_estimate`.

    Lognormal, with two parameters read straight off the bracket:

    * ``sigma = log(p/o) / (2*Z90)``, so the sampled 10th-to-90th percentile
      span is exactly the ``p/o`` ratio the user typed.
    * the location set so the sample MEAN equals `expected_time_estimate`
      exactly.

    Unbounded above. The supplied percentiles are approximate: matching the
    mean and width can move their locations, especially for asymmetric inputs.
    An explicit mean retains a node's point estimate when imputing a spread.

    The three inputs over-determine any two-parameter family (a lognormal can
    only honour all three when ``m == sqrt(o*p)``), so something has to give.
    The width and the mean are kept because those are what the chain forecast
    and the score are built on; the median absorbs the mismatch.
    """
    mean = expected_time_estimate(o, m, p) if mean is None else mean
    if not (o > 0 and p > o):
        # No spread to sample (or a degenerate bracket) — the point estimate is
        # the whole distribution.
        return np.full(size, mean)

    sigma = math.log(p / o) / (2.0 * Z90)
    z = _standard_normal(size, rng, correlation, shared)
    return mean * np.exp(sigma * z - 0.5 * sigma * sigma)


def _sample_node(node, n: int, rng=None, *, correlation: float = 0.0, shared=None) -> np.ndarray:
    """Sample duration for a single node from its time estimates."""
    o, m, p = node.time_o, node.time_m, node.time_p

    # All missing → default 1 hour
    if o == 0 and m == 0 and p == 0:
        return np.full(n, 1.0)

    # Only M provided → assume a bracket half to double it, matching the
    # spread the graph's typical three-point estimate carries.
    if m > 0 and o == 0 and p == 0:
        o, p = m * 0.5, m * 2.0

    # Only O and P provided → the two bounds imply this median
    if m == 0 and o > 0 and p > 0:
        m = math.sqrt(o * p)

    return duration_sample(o, m, p, n, rng=rng, correlation=correlation,
                           shared=shared, mean=node.time)


class SimulationCancelled(Exception):
    """A newer selection made this calculation unnecessary."""


def simulate_task_chain(
    target_name: str,
    nodes_dict: Dict,
    edges: List[Dict],
    include_soft: bool = True,
    include_helps: bool = False,
    n_simulations: int = 10000,
    *, rng=None, should_cancel=None, correlation: float = 0.0,
) -> dict:
    """Monte Carlo simulation of total time for a target node's dependency chain.

    Walks backward from `target_name` via hard (and optionally soft /
    synergistic) prereq edges, collects every incomplete node along
    the way, samples each node's duration, and returns a distribution of the
    serial sum.

    `correlation` is the fraction of each task's log-variance shared with every
    other task in the chain — "am I systematically an optimistic estimator", as
    against "did this one task surprise me". It widens the total without moving
    it: the mean of the returned samples equals the sum of the chain's
    `Node.time` values at every value of `correlation`. Callers in the app pass
    `ConfigManager.get_estimate_correlation()`; the 0.0 default keeps this
    function a pure, explicit primitive for tests.

    Returns dict with keys 'samples', 'stats', 'chain_nodes', 'chain_size'.
    """
    if not 0.0 <= correlation <= 1.0:
        raise ValueError("Estimate correlation must be between 0 and 1.")
    if isinstance(n_simulations, bool) or not isinstance(n_simulations, (int, np.integer)) or not 1 <= n_simulations <= 1_000_000:
        raise ValueError("Simulation trials must be between 1 and 1,000,000.")
    def check_cancelled():
        if should_cancel is not None and should_cancel():
            raise SimulationCancelled()
    check_cancelled()

    prereq_hard: Dict[str, List[str]] = {}
    prereq_soft: Dict[str, List[str]] = {}
    synergies: Dict[str, List[str]] = {}
    
    for e in edges:
        src, tgt, etype = e['source'], e['target'], e['type']
        if etype == 'Needs_Hard':
            prereq_hard.setdefault(tgt, []).append(src)
        elif etype == 'Needs_Soft':
            prereq_soft.setdefault(tgt, []).append(src)
        elif etype == 'Helps':
            synergies.setdefault(tgt, []).append(src)
            synergies.setdefault(src, []).append(tgt)
            
    # BFS to find all reachable nodes and their relationships for this simulation
    visited = set()
    queue = deque([(target_name, True)])
    sim_edges = set() # (prereq, dependent)
    
    while queue:
        check_cancelled()
        current, is_root = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        
        # Hard dependencies: current depends on p
        for p in prereq_hard.get(current, []):
            sim_edges.add((p, current))
            if p not in visited:
                queue.append((p, False))
                
        # Soft dependencies (only for target)
        if is_root and include_soft:
            for p in prereq_soft.get(current, []):
                sim_edges.add((p, current))
                if p not in visited:
                    queue.append((p, False))
                    
        # Synergies (only for target)
        if is_root and include_helps:
            for p in synergies.get(current, []):
                sim_edges.add((p, current))
                if p not in visited:
                    queue.append((p, False))

    # Filter to incomplete nodes only
    incomplete = set()
    for name in visited:
        node = nodes_dict.get(name)
        if node and node.status != STATUS_DONE:
            incomplete.add(name)

    if not incomplete:
        return {
            'samples': np.zeros(n_simulations),
            'stats': _compute_stats(np.zeros(n_simulations)),
            'chain_nodes': [],
            'chain_size': 0,
        }

    # One accumulator and a small temporary chunk replace one full sample array
    # per task. The shared factor has to be drawn once up front and reused for
    # the same trial index across every task — that reuse IS the correlation —
    # so it is the one full-length array besides the accumulator.
    samples = np.zeros(n_simulations)
    shared = None
    if correlation > 0.0:
        shared = (rng if rng is not None else np.random).standard_normal(n_simulations)
    for name in sorted(incomplete):
        check_cancelled()
        node = nodes_dict[name]
        if node.time_mode == 'inherited':
            continue
        for offset in range(0, n_simulations, _CHUNK):
            check_cancelled()
            stop = min(offset + _CHUNK, n_simulations)
            samples[offset:stop] += _sample_node(
                node, stop - offset, rng=rng, correlation=correlation,
                shared=None if shared is None else shared[offset:stop])
    check_cancelled()

    chain_nodes = sorted(incomplete)

    return {
        'samples': samples,
        'stats': _compute_stats(samples),
        'chain_nodes': chain_nodes,
        'chain_size': len(chain_nodes),
    }


def _compute_stats(samples: np.ndarray) -> dict:
    """Compute summary statistics from simulation samples."""
    if np.all(samples == 0):
        return {k: 0.0 for k in ['mean', 'std', 'p10', 'p25', 'p50', 'p75', 'p90', 'min', 'max']}
    percentiles = np.percentile(samples, [10, 25, 50, 75, 90])
    return {
        'mean': round(float(np.mean(samples)), 1),
        'std': round(float(np.std(samples)), 1),
        'p10': round(float(percentiles[0]), 1),
        'p25': round(float(percentiles[1]), 1),
        'p50': round(float(percentiles[2]), 1),
        'p75': round(float(percentiles[3]), 1),
        'p90': round(float(percentiles[4]), 1),
        'min': round(float(np.min(samples)), 1),
        'max': round(float(np.max(samples)), 1),
    }
