"""
Monte Carlo simulation engine for PERT-based time estimation.
Uses critical-path analysis across dependency chains.
"""

import numpy as np
from typing import Dict, List


def pert_beta_sample(o: float, m: float, p: float, size: int = 10000) -> np.ndarray:
    """Sample from a PERT-Beta distribution on [o, p] with mode m.

    The PERT distribution uses lambda=4 weighting:
        alpha = 1 + 4*(m-o)/(p-o)
        beta  = 1 + 4*(p-m)/(p-o)
    """
    if p <= o or p <= 0:
        return np.full(size, max(m, 0.1))

    # Clamp mode within bounds
    if m <= o:
        m = o + 0.001 * (p - o)
    if m >= p:
        m = p - 0.001 * (p - o)

    lam = 4.0
    alpha = 1 + lam * (m - o) / (p - o)
    beta_param = 1 + lam * (p - m) / (p - o)

    samples = np.random.beta(alpha, beta_param, size=size)
    return o + (p - o) * samples


def _sample_node(node, n: int) -> np.ndarray:
    """Sample duration for a single node from its PERT estimates."""
    o, m, p = node.time_o, node.time_m, node.time_p

    # All missing → default 1 hour
    if o == 0 and m == 0 and p == 0:
        return np.full(n, 1.0)

    # Only M provided → approximate spread around M
    if m > 0 and o == 0 and p == 0:
        return pert_beta_sample(m * 0.5, m, m * 2.0, n)

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

    return pert_beta_sample(o, m, p, n)


def simulate_task_chain(
    target_name: str,
    nodes_dict: Dict,
    edges: List[Dict],
    include_soft: bool = True,
    include_helps: bool = False,
    n_simulations: int = 10000,
) -> dict:
    """Critical-path Monte Carlo simulation for a node's dependency chain.

    BFS backwards from target through dependency edges, then simulates
    durations and computes the longest path (critical path) for each run.

    Returns dict with 'samples', 'stats', 'chain_nodes', 'chain_size'.
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
        if node and node.status != 'Done':
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
            # Goal nodes with no time estimates contribute zero time (they're containers)
            if node.type == 'Goal' and node.time_o == 0 and node.time_m == 0 and node.time_p == 0:
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
