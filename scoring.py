"""
Priority scoring algorithm based on Return on Investment (ROI).

Each node's priority is: P = eligibility * (TotalValue / PerceivedCost)
- TotalValue: intrinsic value + cascaded value from dependent nodes
- PerceivedCost: sub-linear combination of difficulty and time
- Eligibility: 1 if all hard prerequisites are Done, 0 otherwise

See README.md for full mathematical specification and hyperparameter profiles.
"""

from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from typing import List, Dict, Tuple


def build_adjacency(edges: List[Dict], node_names: set) -> Tuple[dict, dict, dict, dict]:
    """Builds H_out, S_out, Syn, and Hard_in adjacency structures from edges."""
    H_out = {n: [] for n in node_names}
    S_out = {n: [] for n in node_names}
    Syn = {n: set() for n in node_names}
    Hard_in = {n: [] for n in node_names}

    for e in edges:
        src, trg, etype = e['source'], e['target'], e['type']
        if src not in node_names or trg not in node_names:
            continue

        if etype == EDGE_NEEDS_HARD:
            H_out[src].append(trg)
            Hard_in[trg].append(src)
        elif etype == EDGE_NEEDS_SOFT:
            S_out[src].append(trg)
        elif etype == EDGE_HELPS:
            Syn[src].add(trg)
            Syn[trg].add(src)

    return H_out, S_out, Syn, Hard_in


def intrinsic_value(node: Node, w_v: float, w_i: float) -> float:
    """Weighted sum of a node's Value and Interest."""
    return (w_v * node.value) + (w_i * node.interest)


def perceived_cost(node: Node, w_e: float, w_t: float, beta: float) -> float:
    """Sub-linear cost combining Difficulty and PERT time."""
    return 1.0 + (w_e * node.difficulty) + (w_t * (node.time ** beta))


def is_eligible(node_name: str, hard_in: dict, all_nodes: dict) -> bool:
    """True if all hard prerequisites are Done."""
    for req in hard_in.get(node_name, []):
        req_node = all_nodes.get(req)
        if not req_node or req_node.status != "Done":
            return False
    return True


def total_value(
    node_name: str, visited: set, all_nodes: dict,
    H_out: dict, S_out: dict, Syn: dict,
    w_v: float, w_i: float, d_H: float, d_S: float, d_Syn: float
) -> float:
    """Recursively computes Total Value (IV + cascaded Network Value)."""
    if node_name in visited:
        return 0.0
    node = all_nodes.get(node_name)
    if not node:
        return 0.0

    iv = intrinsic_value(node, w_v, w_i)
    new_visited = visited | {node_name}

    nv = 0.0
    for x in H_out.get(node_name, []):
        if x not in visited:
            nv += d_H * total_value(x, new_visited, all_nodes, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn)
    for y in S_out.get(node_name, []):
        if y not in visited:
            nv += d_S * total_value(y, new_visited, all_nodes, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn)
    for z in Syn.get(node_name, set()):
        if z not in visited:
            nv += d_Syn * total_value(z, new_visited, all_nodes, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn)

    return iv + nv


def score_nodes(
    active_nodes: List[Node], all_nodes: List[Node],
    edges: List[Dict], hyperparams: dict
) -> List[Node]:
    """Scores active nodes by priority (TV / Cost) and returns them sorted descending."""
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.25)
    d_Syn = hyperparams.get('d_Syn', 0.35)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)

    all_nodes_dict = {n.name: n for n in all_nodes}
    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))

    scored_nodes = []
    for node in active_nodes:
        if node.status in ("Done", "Blocked"):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        if not is_eligible(node.name, Hard_in, all_nodes_dict):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        cost = perceived_cost(node, w_e, w_t, beta)
        tv = total_value(node.name, set(), all_nodes_dict, H_out, S_out, Syn, w_v, w_i, d_H, d_S, d_Syn)
        node.priority_score = round(tv / cost, 2)
        scored_nodes.append(node)

    return sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1.0), reverse=True)
