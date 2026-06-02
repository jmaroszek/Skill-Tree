"""
Monte Carlo simulation engine for PERT-based time estimation.

Samples per-node durations from the same Blended PERT distribution the point
estimate uses (`models.blend_time_estimate`) and sums them serially across the
dependency chain — this assumes one person working on one task at a time, not
parallel execution.
"""

import math

import numpy as np
from scipy.special import betaincinv
from typing import Dict, List
from models import STATUS_DONE, pert_blend_weight

_LAMBDA = 4.0  # Conventional PERT weighting; keeps alpha, beta >= 1 (unimodal).


def _pert_alpha_beta(lo: float, mode: float, hi: float):
    """PERT-Beta shape parameters for a unimodal Beta on [lo, hi] with the
    given mode, using the conventional lambda=4 weighting."""
    span = hi - lo
    alpha = 1.0 + _LAMBDA * (mode - lo) / span
    beta = 1.0 + _LAMBDA * (hi - mode) / span
    return alpha, beta


def _clamp_mode(o: float, m: float, p: float) -> float:
    """Nudge the mode strictly inside (o, p) so both shape parameters stay
    above 1 and the density is unimodal and interior."""
    if m <= o:
        return o + 0.001 * (p - o)
    if m >= p:
        return p - 0.001 * (p - o)
    return m


def pert_beta_sample(o: float, m: float, p: float, size: int = 10000) -> np.ndarray:
    """Sample from a linear PERT-Beta distribution on [o, p] with mode m.

    This is the low-uncertainty primitive: a Beta on [o, p] with
        alpha = 1 + 4*(m-o)/(p-o),  beta = 1 + 4*(p-m)/(p-o).
    `blended_pert_sample` uses it for the w=0 regime; wider brackets blend it
    with a Log-Beta. Its mean is exactly (o+4m+p)/6 and its mode is exactly m.
    """
    if p <= o or p <= 0:
        return np.full(size, max(m, 0.1))

    m = _clamp_mode(o, m, p)
    alpha, beta_param = _pert_alpha_beta(o, m, p)

    samples = np.random.beta(alpha, beta_param, size=size)
    return o + (p - o) * samples


def blended_pert_sample(o: float, m: float, p: float, size: int = 10000) -> np.ndarray:
    """Sample from the Blended PERT distribution — the sampler counterpart of
    `models.blend_time_estimate`.

    Comonotonically blends a linear Beta-PERT on [o, p] with a Log-Beta
    (a Beta-PERT in log space, i.e. log(T) ~ Beta-PERT on [log o, log p]),
    weighting the two by w(p/o) — the same uncertainty-ratio weight the point
    estimate uses. A single shared uniform draw drives both components via the
    Beta quantile function, so the distribution slides smoothly from the plain
    Beta (w=0, tight brackets) to the Log-Beta (w=1, wide brackets) without
    averaging away its spread. Both components keep their mode at m and stay
    within [o, p], so the blend does too.
    """
    # Non-positive lower bound makes the log map undefined, and a collapsed or
    # inverted range has no spread to blend — defer to the linear primitive,
    # which handles both. (Callers resolve o to >= 0.1 before reaching here.)
    if o <= 0 or p <= o:
        return pert_beta_sample(o, m, p, size)

    w = pert_blend_weight(p / o)
    if w == 0.0:
        return pert_beta_sample(o, m, p, size)

    m = _clamp_mode(o, m, p)

    # Shared quantiles couple the two components (comonotonic blend): the same
    # percentile of the linear and the log view of this one task are combined,
    # rather than two independent draws (which would shrink the spread).
    u = np.random.uniform(size=size)

    a_lin, b_lin = _pert_alpha_beta(o, m, p)
    linear = o + (p - o) * betaincinv(a_lin, b_lin, u)

    lo, mode_log, hi = math.log(o), math.log(m), math.log(p)
    a_log, b_log = _pert_alpha_beta(lo, mode_log, hi)
    log_beta = np.exp(lo + (hi - lo) * betaincinv(a_log, b_log, u))

    return (1.0 - w) * linear + w * log_beta


def _sample_node(node, n: int) -> np.ndarray:
    """Sample duration for a single node from its PERT estimates."""
    o, m, p = node.time_o, node.time_m, node.time_p

    # All missing → default 1 hour
    if o == 0 and m == 0 and p == 0:
        return np.full(n, 1.0)

    # Only M provided → approximate spread around M
    if m > 0 and o == 0 and p == 0:
        return blended_pert_sample(m * 0.5, m, m * 2.0, n)

    # Only O and P provided → mode at geometric mean
    if m == 0 and o > 0 and p > 0:
        m = np.sqrt(o * p)

    # Validate
    if o <= 0:
        o = 0.1
    if m < o:
        m = o
    if p < m:
        p = m
    if p == o:
        return np.full(n, m)

    return blended_pert_sample(o, m, p, n)


def simulate_task_chain(
    target_name: str,
    nodes_dict: Dict,
    edges: List[Dict],
    include_soft: bool = True,
    include_helps: bool = False,
    n_simulations: int = 10000,
) -> dict:
    """Monte Carlo simulation of total time for a target node's dependency chain.

    Walks backward from `target_name` via hard (and optionally soft /
    synergistic) prereq edges, collects every incomplete node along
    the way, samples each node's duration from its PERT-Beta
    distribution, and returns a distribution of the serial sum.

    Returns dict with keys 'samples', 'stats', 'chain_nodes', 'chain_size'.
    """
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
    queue = [(target_name, True)]
    sim_edges = set() # (prereq, dependent)
    
    while queue:
        current, is_root = queue.pop(0)
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

    # Sample durations for each incomplete node
    task_samples = {}
    for name in incomplete:
        node = nodes_dict.get(name)
        if node:
            # Inherited-time nodes contribute zero own time — their
            # constituents are already in the chain and sample independently.
            # This covers Goals and Milestones (forced to inherited time by the
            # model) as well as any other container with inherited time.
            if node.time_mode == 'inherited':
                task_samples[name] = np.zeros(n_simulations)
            else:
                task_samples[name] = _sample_node(node, n_simulations)
        else:
            task_samples[name] = np.full(n_simulations, 1.0)

    # Serial execution: total time is the sum of all task durations.
    # A single person works on one task at a time, so all tasks are sequential
    # regardless of dependency structure.
    samples = np.zeros(n_simulations)
    for name in incomplete:
        samples += task_samples[name]

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
    return {
        'mean': round(float(np.mean(samples)), 1),
        'std': round(float(np.std(samples)), 1),
        'p10': round(float(np.percentile(samples, 10)), 1),
        'p25': round(float(np.percentile(samples, 25)), 1),
        'p50': round(float(np.percentile(samples, 50)), 1),
        'p75': round(float(np.percentile(samples, 75)), 1),
        'p90': round(float(np.percentile(samples, 90)), 1),
        'min': round(float(np.min(samples)), 1),
        'max': round(float(np.max(samples)), 1),
    }
