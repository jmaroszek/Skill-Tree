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
    # Determine which edge types to traverse
    edge_types = {'Needs_Hard'}
    if include_soft:
        edge_types.add('Needs_Soft')
    if include_helps:
        edge_types.add('Helps')

    # Build prereq map: target → [sources]
    prereq_map: Dict[str, List[str]] = {}
    for e in edges:
        if e['type'] in edge_types:
            prereq_map.setdefault(e['target'], []).append(e['source'])
            # Helps edges are bidirectional — also traverse reverse
            if e['type'] == 'Helps':
                prereq_map.setdefault(e['source'], []).append(e['target'])

    # BFS to find all reachable nodes
    visited = set()
    queue = [target_name]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for prereq in prereq_map.get(current, []):
            if prereq not in visited:
                queue.append(prereq)

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
            task_samples[name] = _sample_node(node, n_simulations)
        else:
            task_samples[name] = np.full(n_simulations, 1.0)

    # Build forward adjacency within incomplete subgraph
    # Edge direction: prereq → dependent (prereq must finish before dependent starts)
    forward = {name: [] for name in incomplete}
    in_degree = {name: 0 for name in incomplete}

    for e in edges:
        src, tgt = e['source'], e['target']
        if e['type'] in edge_types and src in incomplete and tgt in incomplete:
            forward[src].append(tgt)
            in_degree[tgt] += 1

    # Topological sort (Kahn's algorithm)
    topo_order = []
    queue = [n for n in incomplete if in_degree[n] == 0]
    while queue:
        n = queue.pop(0)
        topo_order.append(n)
        for dep in forward[n]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    # Handle any nodes not reached by topo sort (cycles from Helps edges)
    remaining = incomplete - set(topo_order)
    topo_order.extend(remaining)

    # Compute earliest finish times via DP
    name_to_idx = {name: i for i, name in enumerate(topo_order)}
    finish = np.zeros((len(topo_order), n_simulations))

    for name in topo_order:
        idx = name_to_idx[name]
        prereqs_of_name = [
            e['source'] for e in edges
            if e['target'] == name and e['source'] in incomplete
            and e['type'] in edge_types
        ]
        if prereqs_of_name:
            prereq_finishes = [finish[name_to_idx[p]] for p in prereqs_of_name if p in name_to_idx]
            if prereq_finishes:
                max_prereq_finish = np.max(prereq_finishes, axis=0)
                finish[idx] = max_prereq_finish + task_samples[name]
            else:
                finish[idx] = task_samples[name]
        else:
            finish[idx] = task_samples[name]

    # Total time = finish time of target node (or max if target is done)
    if target_name in name_to_idx:
        samples = finish[name_to_idx[target_name]]
    else:
        samples = np.max(finish, axis=0)

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
