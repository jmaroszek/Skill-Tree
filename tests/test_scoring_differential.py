"""Exhaustive differential tests for the scoring algorithm.

The Phase E memoization on total_value is safe only if it is a pure
optimization — byte-for-byte identical outputs vs the pre-change
(unmemoized) implementation across every graph shape the app might
actually encounter.

Strategy:

1. `_baseline_score_nodes` — an inline copy of score_nodes that calls
   total_value with memo=None, replicating main's behavior exactly.
2. Randomized graph generator seeded for reproducibility. Sizes are
   intentionally kept modest (n ≤ 25) because total_value's cycle-avoidance
   is per-path, so dense cyclic graphs are inherently exponential in the
   naive algorithm — the test's job is correctness verification, not stress.
3. Pathological shapes: self-loops, small fully-connected cycles,
   bidirectional pairs, goal-rooted subtrees, long chains, all-Done graphs.
4. Real-world DB tests: load the user's sandbox and production DBs and
   verify byte-equal scores under default + custom hyperparameter profiles.
5. Mutation invariance: scoring after any mutator call must match
   a baseline run on the same post-mutation state.
"""

import copy
import random
import shutil
from pathlib import Path
from typing import List, Dict, Optional

import pytest

import database
from config import ConfigManager
from graph_manager import GraphManager
from models import (
    Node,
    EDGE_NEEDS_HARD,
    EDGE_NEEDS_SOFT,
    EDGE_HELPS,
)
from scoring import (
    total_value,
    score_nodes,
    build_adjacency,
    perceived_cost,
    is_eligible,
    _get_goal_subtree_from_adjacency,
)


# ---------------------------------------------------------------------------
# Baseline: a copy of score_nodes that never passes memo (== main's behavior).
# ---------------------------------------------------------------------------

def _baseline_score_nodes(
    active_nodes: List[Node], all_nodes: List[Node],
    edges: List[Dict], hyperparams: dict,
    priority_goals: Optional[List[str]] = None,
) -> List[Node]:
    w_v = hyperparams.get('w_v', 1.0)
    w_i = hyperparams.get('w_i', 1.0)
    d_H = hyperparams.get('d_H', 0.6)
    d_S = hyperparams.get('d_S', 0.25)
    d_Syn_pair = hyperparams.get('d_Syn_pair', 0.10)
    d_Syn_mul = hyperparams.get('d_Syn_mul', 0.40)
    w_e = hyperparams.get('w_e', 2.5)
    w_t = hyperparams.get('w_t', 1.0)
    beta = hyperparams.get('beta', 0.85)
    goal_boost = hyperparams.get('goal_boost', 1.5)
    alpha = hyperparams.get('alpha', 0.0)
    context_weights = hyperparams.get('context_weights', {}) or {}

    all_nodes_dict = {n.name: n for n in all_nodes}
    H_out, S_out, Syn, Hard_in = build_adjacency(edges, set(all_nodes_dict.keys()))

    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]
    node_to_boost = {}
    if priority_goals:
        for rank_idx, g in enumerate(priority_goals[:3]):
            multiplier = rank_multipliers[rank_idx]
            subtree = _get_goal_subtree_from_adjacency(g, Hard_in)
            for n in subtree:
                if n not in node_to_boost or multiplier > node_to_boost[n]:
                    node_to_boost[n] = multiplier

    n_active_map = {}
    for n in active_nodes:
        if n.type in ('Goal', 'Milestone') or n.status in ('Done', 'Blocked'):
            continue
        key = (n.context, n.subcontext)
        n_active_map[key] = n_active_map.get(key, 0) + 1

    scored_nodes = []
    for node in active_nodes:
        if node.type in ('Goal', 'Milestone'):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue
        if node.status in ("Done", "Blocked"):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue
        if not is_eligible(node.name, Hard_in, all_nodes_dict):
            node.priority_score = -1.0
            scored_nodes.append(node)
            continue

        t_override = 0.0 if node.time_mode == 'inherited' else None
        e_override = 0.0 if node.value_mode == 'inherited' else None
        cost = perceived_cost(node, w_e, w_t, beta,
                              time_override=t_override, effort_override=e_override)
        # CRITICAL: memo=None — replicates pre-Phase-E behavior.
        tv = total_value(node.name, set(), all_nodes_dict, H_out, S_out, Syn,
                         w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo=None)
        score = round(tv / cost, 2)
        if node.name in node_to_boost:
            score = round(score * node_to_boost[node.name], 2)
        weight = context_weights.get(node.context, 1.0) if node.context else 1.0
        n_bucket = max(1, n_active_map.get((node.context, node.subcontext), 1))
        density_mult = (1.0 / (n_bucket ** alpha)) if alpha > 0 else 1.0
        if weight != 1.0 or density_mult != 1.0:
            score = round(score * weight * density_mult, 2)
        node.priority_score = score
        scored_nodes.append(node)

    return sorted(scored_nodes, key=lambda n: getattr(n, 'priority_score', -1.0), reverse=True)


# ---------------------------------------------------------------------------
# Random graph generator (bounded to avoid O(V!) blowup in total_value)
# ---------------------------------------------------------------------------

_TYPES = ["Learn", "Action", "Goal", "Resource"]
_STATUSES = ["Open", "Done", "Blocked"]
_CONTEXTS = ["Mind", "Body", "Work", "Social"]


def _rand_node(rng: random.Random, name: str, node_type: Optional[str] = None) -> Node:
    return Node(
        name=name,
        type=node_type or rng.choice(_TYPES),
        description="",
        value=rng.randint(1, 10),
        time_o=rng.uniform(0.5, 5),
        time_m=rng.uniform(1, 10),
        time_p=rng.uniform(5, 20),
        interest=rng.randint(1, 10),
        difficulty=rng.randint(1, 10),
        status=rng.choice(_STATUSES),
        context=rng.choice(_CONTEXTS),
    )


def _random_graph(seed: int, n_nodes: int = 15, edge_density: float = 0.08,
                  cycle_injection: bool = True):
    """Generate (nodes_list, edges_list)."""
    rng = random.Random(seed)
    nodes = [_rand_node(rng, f"N{i}") for i in range(n_nodes)]
    names = [n.name for n in nodes]

    edges = []
    added = set()

    # Forward DAG edges for Needs_Hard / Needs_Soft (no cycle issue).
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if rng.random() < edge_density:
                etype = rng.choice([EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS])
                key = (names[i], names[j], etype)
                if key not in added:
                    edges.append({"source": names[i], "target": names[j], "type": etype})
                    added.add(key)

    # Small Helps cycles (Helps allows cycles).
    if cycle_injection and n_nodes >= 3:
        for _ in range(max(1, n_nodes // 8)):
            k = rng.randint(3, min(4, n_nodes))
            cycle_nodes = rng.sample(names, k)
            for idx in range(k):
                src, trg = cycle_nodes[idx], cycle_nodes[(idx + 1) % k]
                key = (src, trg, EDGE_HELPS)
                if key not in added:
                    edges.append({"source": src, "target": trg, "type": EDGE_HELPS})
                    added.add(key)

    # A bidirectional Helps pair or two.
    if n_nodes >= 2:
        for _ in range(max(1, n_nodes // 10)):
            a, b = rng.sample(names, 2)
            for (s, t) in [(a, b), (b, a)]:
                key = (s, t, EDGE_HELPS)
                if key not in added:
                    edges.append({"source": s, "target": t, "type": EDGE_HELPS})
                    added.add(key)

    return nodes, edges


def _scores_equal(a: List[Node], b: List[Node]) -> bool:
    amap = {n.name: getattr(n, 'priority_score', None) for n in a}
    bmap = {n.name: getattr(n, 'priority_score', None) for n in b}
    return amap == bmap


HYPERS = {'w_v': 1.0, 'w_i': 1.0, 'd_H': 0.6, 'd_S': 0.25,
          'd_Syn_pair': 0.10, 'd_Syn_mul': 0.40}


# ---------------------------------------------------------------------------
# total_value: memo=None vs memo={} direct equivalence
# ---------------------------------------------------------------------------

def _tv_both(node_name, nodes, edges):
    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))
    args = (all_nodes_dict, H_out, S_out, Syn,
            HYPERS['w_v'], HYPERS['w_i'], HYPERS['d_H'], HYPERS['d_S'],
            HYPERS['d_Syn_pair'], HYPERS['d_Syn_mul'])
    no_memo = total_value(node_name, set(), *args, memo=None)
    fresh_memo = {}
    with_memo = total_value(node_name, set(), *args, memo=fresh_memo)
    return no_memo, with_memo


@pytest.mark.parametrize("seed", list(range(30)))
def test_total_value_memo_matches_nomemo_on_random_graphs(seed):
    nodes, edges = _random_graph(seed, n_nodes=15, edge_density=0.08)
    for n in nodes:
        no_memo, with_memo = _tv_both(n.name, nodes, edges)
        assert no_memo == with_memo, f"seed={seed} node={n.name}"


def test_total_value_memo_on_3_cycle():
    """3-cycle A->B->C->A via Helps."""
    nodes = [Node(name=x, type="Learn", description="", value=5,
                  time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                  status="Open", context="Mind") for x in ("A", "B", "C")]
    edges = [
        {"source": "A", "target": "B", "type": EDGE_HELPS},
        {"source": "B", "target": "C", "type": EDGE_HELPS},
        {"source": "C", "target": "A", "type": EDGE_HELPS},
    ]
    for n in nodes:
        assert _tv_both(n.name, nodes, edges)[0] == _tv_both(n.name, nodes, edges)[1]


def test_total_value_memo_on_bidirectional_pair():
    nodes = [Node(name=x, type="Learn", description="", value=5,
                  time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                  status="Open", context="Mind") for x in ("X", "Y")]
    edges = [
        {"source": "X", "target": "Y", "type": EDGE_HELPS},
        {"source": "Y", "target": "X", "type": EDGE_HELPS},
    ]
    for n in nodes:
        no_memo, with_memo = _tv_both(n.name, nodes, edges)
        assert no_memo == with_memo


def test_total_value_memo_on_self_helps_loop():
    nodes = [Node(name="A", type="Learn", description="", value=5,
                  time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                  status="Open", context="Mind")]
    edges = [{"source": "A", "target": "A", "type": EDGE_HELPS}]
    no_memo, with_memo = _tv_both("A", nodes, edges)
    assert no_memo == with_memo


def test_total_value_memo_on_small_fully_connected():
    """n=5 fully-connected with Helps — small enough to finish quickly, dense enough
    to stress cycle handling."""
    n_nodes = 5
    nodes = [Node(name=f"N{i}", type="Learn", description="", value=5,
                  time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                  status="Open", context="Mind") for i in range(n_nodes)]
    edges = [{"source": f"N{i}", "target": f"N{j}", "type": EDGE_HELPS}
             for i in range(n_nodes) for j in range(n_nodes) if i != j]
    for n in nodes:
        no_memo, with_memo = _tv_both(n.name, nodes, edges)
        assert no_memo == with_memo


def test_total_value_memo_on_long_chain():
    """Linear chain N0 -> N1 -> ... -> N14 via Needs_Hard."""
    n_nodes = 15
    nodes = [Node(name=f"N{i}", type="Learn", description="", value=5,
                  time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                  status="Open", context="Mind") for i in range(n_nodes)]
    edges = [{"source": f"N{i}", "target": f"N{i+1}", "type": EDGE_NEEDS_HARD}
             for i in range(n_nodes - 1)]
    for n in nodes:
        no_memo, with_memo = _tv_both(n.name, nodes, edges)
        assert no_memo == with_memo


# ---------------------------------------------------------------------------
# score_nodes: current (memoized) vs baseline (unmemoized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", list(range(20)))
def test_score_nodes_current_vs_baseline(seed):
    nodes, edges = _random_graph(seed, n_nodes=15, edge_density=0.08)
    nodes_a = copy.deepcopy(nodes)
    nodes_b = copy.deepcopy(nodes)
    current = score_nodes(list(nodes_a), nodes_a, edges, HYPERS)
    baseline = _baseline_score_nodes(list(nodes_b), nodes_b, edges, HYPERS)
    assert _scores_equal(current, baseline), f"seed={seed} diverged"


@pytest.mark.parametrize("seed", list(range(5)))
def test_score_nodes_with_priority_goals(seed):
    nodes, edges = _random_graph(seed, n_nodes=12, edge_density=0.10)
    if len(nodes) >= 2:
        d0 = nodes[0].__dict__
        d1 = nodes[1].__dict__
        nodes[0] = Node(**{**d0, "type": "Goal"})
        nodes[1] = Node(**{**d1, "type": "Goal"})
    priority_goals = [nodes[0].name, nodes[1].name]
    nodes_a = copy.deepcopy(nodes)
    nodes_b = copy.deepcopy(nodes)
    current = score_nodes(list(nodes_a), nodes_a, edges, HYPERS, priority_goals=priority_goals)
    baseline = _baseline_score_nodes(list(nodes_b), nodes_b, edges, HYPERS, priority_goals=priority_goals)
    assert _scores_equal(current, baseline)


@pytest.mark.parametrize("seed", list(range(5)))
def test_score_nodes_with_custom_hyperparams(seed):
    hypers = {
        'w_v': 2.0, 'w_i': 0.5, 'd_H': 0.8, 'd_S': 0.1,
        'd_Syn_pair': 0.20, 'd_Syn_mul': 0.50,
        'w_e': 1.5, 'w_t': 1.2, 'beta': 0.7, 'goal_boost': 2.0,
    }
    nodes, edges = _random_graph(seed, n_nodes=12, edge_density=0.08)
    nodes_a = copy.deepcopy(nodes)
    nodes_b = copy.deepcopy(nodes)
    current = score_nodes(list(nodes_a), nodes_a, edges, hypers)
    baseline = _baseline_score_nodes(list(nodes_b), nodes_b, edges, hypers)
    assert _scores_equal(current, baseline)


def test_score_nodes_all_done_yields_all_negative_one():
    nodes, edges = _random_graph(seed=1, n_nodes=8)
    for n in nodes:
        n.status = "Done"
    nodes_a = copy.deepcopy(nodes)
    nodes_b = copy.deepcopy(nodes)
    current = score_nodes(list(nodes_a), nodes_a, edges, HYPERS)
    baseline = _baseline_score_nodes(list(nodes_b), nodes_b, edges, HYPERS)
    assert _scores_equal(current, baseline)
    for n in current:
        assert n.priority_score == -1.0


def test_score_nodes_active_subset_of_all_nodes():
    """active_nodes can be a filtered subset — exercise that call shape."""
    nodes, edges = _random_graph(seed=7, n_nodes=15, edge_density=0.1)
    # Take only the first 8 nodes as active
    active = nodes[:8]
    nodes_a = copy.deepcopy(nodes)
    active_a = [n for n in nodes_a if n.name in {a.name for a in active}]
    nodes_b = copy.deepcopy(nodes)
    active_b = [n for n in nodes_b if n.name in {a.name for a in active}]
    current = score_nodes(active_a, nodes_a, edges, HYPERS)
    baseline = _baseline_score_nodes(active_b, nodes_b, edges, HYPERS)
    assert _scores_equal(current, baseline)


# ---------------------------------------------------------------------------
# Real-database tests (opt-in if files exist)
# ---------------------------------------------------------------------------

def _real_db_path(name: str) -> Optional[Path]:
    candidate = Path(__file__).parent.parent / "data" / name
    return candidate if candidate.exists() else None


def _run_real_db_differential(monkeypatch, tmp_path, db_name: str):
    src = _real_db_path(db_name)
    if src is None:
        pytest.skip(f"{db_name} not present")

    target = tmp_path / "real_copy.db"
    shutil.copy(src, target)
    monkeypatch.setattr(database, "get_db_path", lambda: str(target))
    # Allow init_db to run on the copy so any schema migrations (e.g. drop
    # deprecated `progress` column) apply before GraphManager reads nodes.
    database._initialized = False
    database.init_db()

    mgr = GraphManager()
    all_nodes = mgr.get_all_nodes()
    edges = mgr.get_edges()
    active = list(all_nodes)

    hypers = ConfigManager.get_hyperparams()
    priority_goals = ConfigManager.get_priority_goals() or None

    nodes_all_a = copy.deepcopy(all_nodes)
    active_a = [n for n in nodes_all_a if n.name in {x.name for x in active}]
    nodes_all_b = copy.deepcopy(all_nodes)
    active_b = [n for n in nodes_all_b if n.name in {x.name for x in active}]

    current = score_nodes(active_a, nodes_all_a, edges, hypers, priority_goals=priority_goals)
    baseline = _baseline_score_nodes(active_b, nodes_all_b, edges, hypers, priority_goals=priority_goals)

    assert _scores_equal(current, baseline), (
        f"Real DB ({db_name}, {len(all_nodes)} nodes) scoring diverged"
    )
    return len(current)


def test_score_nodes_matches_on_real_sandbox_db(monkeypatch, tmp_path):
    n = _run_real_db_differential(monkeypatch, tmp_path, "sandbox_skilltree.db")
    assert n > 0


def test_score_nodes_matches_on_real_production_db(monkeypatch, tmp_path):
    _run_real_db_differential(monkeypatch, tmp_path, "skilltree.db")


# ---------------------------------------------------------------------------
# Mutation invariance: scoring after a mutation == baseline on same state
# ---------------------------------------------------------------------------

def _score_current(mgr: GraphManager, hypers: dict) -> Dict[str, float]:
    nodes = mgr.get_all_nodes()
    edges = mgr.get_edges()
    return {n.name: n.priority_score for n in score_nodes(
        copy.deepcopy(nodes), copy.deepcopy(nodes), edges, hypers)}


def _score_baseline(mgr: GraphManager, hypers: dict) -> Dict[str, float]:
    nodes = mgr.get_all_nodes()
    edges = mgr.get_edges()
    return {n.name: n.priority_score for n in _baseline_score_nodes(
        copy.deepcopy(nodes), copy.deepcopy(nodes), edges, hypers)}


def _seed_mgr(n=5):
    mgr = GraphManager()
    for i in range(n):
        mgr.add_node(Node(name=f"N{i}", type="Learn", description="", value=5,
                          time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                          status="Open", context="Mind"))
    return mgr


def test_mutation_add_node():
    mgr = _seed_mgr()
    mgr.add_edge("N0", "N1", EDGE_NEEDS_HARD)
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    mgr.add_node(Node(name="NEW", type="Action", description="", value=7,
                      time_o=2, time_m=3, time_p=6, interest=8, difficulty=4,
                      status="Open", context="Work"))
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


def test_mutation_add_edge():
    mgr = _seed_mgr()
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    mgr.add_edge("N0", "N1", EDGE_HELPS)
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


def test_mutation_remove_edge():
    mgr = _seed_mgr(n=4)
    mgr.add_edge("N0", "N1", EDGE_HELPS)
    mgr.add_edge("N1", "N2", EDGE_HELPS)
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    mgr.remove_edge("N0", "N1", EDGE_HELPS)
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


def test_mutation_update_node():
    mgr = _seed_mgr(n=4)
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    updated = mgr.get_node("N0")
    updated.value = 9
    updated.interest = 10
    mgr.update_node(updated)
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


def test_mutation_delete_node():
    mgr = _seed_mgr(n=4)
    mgr.add_edge("N0", "N1", EDGE_HELPS)
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    mgr.delete_node("N0")
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


def test_mutation_rename_node():
    mgr = _seed_mgr(n=4)
    mgr.add_edge("N0", "N1", EDGE_HELPS)
    hypers = ConfigManager.get_hyperparams()
    _ = _score_current(mgr, hypers)
    mgr.rename_node("N0", "N0_RENAMED")
    assert _score_current(mgr, hypers) == _score_baseline(mgr, hypers)


# ---------------------------------------------------------------------------
# Repeated-call consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", list(range(5)))
def test_score_nodes_repeated_calls_stable(seed):
    nodes, edges = _random_graph(seed, n_nodes=12, edge_density=0.1)
    nodes_a = copy.deepcopy(nodes)
    nodes_b = copy.deepcopy(nodes)
    nodes_c = copy.deepcopy(nodes)
    first = score_nodes(list(nodes_a), nodes_a, edges, HYPERS)
    second = score_nodes(list(nodes_b), nodes_b, edges, HYPERS)
    third = score_nodes(list(nodes_c), nodes_c, edges, HYPERS)
    assert _scores_equal(first, second)
    assert _scores_equal(second, third)
