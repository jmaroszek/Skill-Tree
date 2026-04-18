"""Phase E: tests for total_value memoization (cycle-safe) and community cache."""

import pytest
import networkx as nx

from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from scoring import total_value, score_nodes, build_adjacency


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(name, **kw):
    defaults = dict(
        name=name, type="Learn", description="", value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


HYPERS = {'w_v': 1.0, 'w_i': 1.0, 'd_H': 0.6, 'd_S': 0.25, 'd_Syn': 0.35}


def _tv_args(nodes, edges):
    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))
    return all_nodes_dict, H_out, S_out, Syn


def _call_tv(name, nodes, edges, memo=None):
    all_nodes_dict, H_out, S_out, Syn = _tv_args(nodes, edges)
    return total_value(
        name, set(), all_nodes_dict, H_out, S_out, Syn,
        HYPERS['w_v'], HYPERS['w_i'], HYPERS['d_H'], HYPERS['d_S'], HYPERS['d_Syn'],
        memo,
    )


# ---------------------------------------------------------------------------
# total_value memo parity
# ---------------------------------------------------------------------------

def test_total_value_memo_parity_on_dag():
    nodes = [_make_node(f"N{i}") for i in range(10)]
    edges = []
    for i in range(9):
        edges.append({"source": f"N{i}", "target": f"N{i+1}", "type": EDGE_NEEDS_HARD})

    for n in nodes:
        without = _call_tv(n.name, nodes, edges, memo=None)
        memo: dict = {}
        with_memo = _call_tv(n.name, nodes, edges, memo=memo)
        assert without == with_memo, f"mismatch for {n.name}: without={without}, with={with_memo}"


def test_total_value_memo_parity_on_cyclic_graph():
    """Primary cycle-safety gate: memo must agree with naive on graphs with cycles."""
    # 3-cycle via Helps: A -> B -> C -> A. Plus a bidirectional pair X <-> Y.
    nodes = [_make_node(n) for n in ("A", "B", "C", "X", "Y", "Z")]
    edges = [
        {"source": "A", "target": "B", "type": EDGE_HELPS},
        {"source": "B", "target": "C", "type": EDGE_HELPS},
        {"source": "C", "target": "A", "type": EDGE_HELPS},
        {"source": "X", "target": "Y", "type": EDGE_HELPS},
        {"source": "Y", "target": "X", "type": EDGE_HELPS},
        {"source": "Y", "target": "Z", "type": EDGE_NEEDS_SOFT},
    ]

    for n in nodes:
        without = _call_tv(n.name, nodes, edges, memo=None)
        memo: dict = {}
        with_memo = _call_tv(n.name, nodes, edges, memo=memo)
        assert without == with_memo, (
            f"cycle-unsafe memo: name={n.name}, without={without}, with={with_memo}"
        )


def test_total_value_memo_only_populates_for_outer_calls():
    """The memo dict must contain only outer-call keys; no inner traversal pollutes it."""
    nodes = [_make_node(n) for n in ("A", "B", "C", "D")]
    edges = [
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
        {"source": "B", "target": "C", "type": EDGE_NEEDS_HARD},
        {"source": "C", "target": "D", "type": EDGE_NEEDS_HARD},
    ]
    memo: dict = {}
    # Only call outer for "A" — inner recursion traverses B, C, D but memo
    # must remain {"A": ...} only.
    _call_tv("A", nodes, edges, memo=memo)
    assert set(memo.keys()) == {"A"}, (
        f"memo leaked inner results: {memo.keys()}"
    )


def test_total_value_memo_reuse_within_score_nodes_keeps_results_stable():
    """score_nodes scores cyclic-graph nodes and produces non-sentinel priorities for eligible nodes."""
    # No hard-prereq edges -> every node is eligible.  Use only Helps (cyclic safe).
    nodes = [_make_node(n, value=3) for n in ("A", "B", "C", "D")]
    edges = [
        {"source": "A", "target": "B", "type": EDGE_HELPS},
        {"source": "C", "target": "D", "type": EDGE_HELPS},
        {"source": "D", "target": "C", "type": EDGE_HELPS},  # bidirectional
    ]
    scored = score_nodes(list(nodes), nodes, edges, HYPERS)
    by_name = {n.name: n.priority_score for n in scored}
    # Eligible open nodes should receive a positive, non-sentinel score.
    for name in ("A", "B", "C", "D"):
        assert by_name[name] > 0, f"{name} score={by_name[name]}"


# ---------------------------------------------------------------------------
# detect_communities cache
# ---------------------------------------------------------------------------

def test_detect_communities_cache_hit_avoids_nx_call(monkeypatch):
    mgr = GraphManager()
    mgr.add_node(_make_node("A"))
    mgr.add_node(_make_node("B"))
    mgr.add_edge("A", "B", EDGE_NEEDS_HARD)

    # Call once to populate cache.
    mgr.detect_communities(method="components")
    # Now instrument nx.connected_components to count invocations.
    call_count = {"n": 0}
    orig = nx.connected_components
    def _tracked(*a, **kw):
        call_count["n"] += 1
        return orig(*a, **kw)
    monkeypatch.setattr(nx, "connected_components", _tracked)
    # Second call — cache hit, no nx call expected.
    mgr.detect_communities(method="components")
    assert call_count["n"] == 0, "cache miss: nx.connected_components called on repeat"


@pytest.mark.parametrize("mutate", [
    lambda m: m.add_node(_make_node("NewNode")),
    lambda m: m.add_edge("A", "B", EDGE_NEEDS_SOFT),
    lambda m: m.remove_edge("A", "B", EDGE_NEEDS_HARD),
    lambda m: m.delete_node("B"),
    lambda m: m.update_node(_make_node("A", description="updated")),
    lambda m: m.rename_node("A", "ARenamed"),
])
def test_detect_communities_cache_invalidated_by_mutation(mutate):
    mgr = GraphManager()
    mgr.add_node(_make_node("A"))
    mgr.add_node(_make_node("B"))
    mgr.add_edge("A", "B", EDGE_NEEDS_HARD)

    mgr.detect_communities(method="components")
    version_before = mgr._graph_version
    mutate(mgr)
    version_after = mgr._graph_version
    assert version_after > version_before, (
        f"mutation {mutate} failed to bump graph version: {version_before}->{version_after}"
    )


def test_graph_version_starts_at_zero():
    mgr = GraphManager()
    assert mgr._graph_version == 0


def test_community_cache_is_per_instance():
    mgr1 = GraphManager()
    mgr1.add_node(_make_node("X"))
    mgr1.detect_communities()
    mgr2 = GraphManager()  # fresh instance on same DB
    assert mgr2._community_cache == {}, "community cache should be per-instance, not module-global"


def test_detect_communities_returns_fresh_objects_not_cache_reference():
    """Callers that mutate returned sets must not affect cached state."""
    mgr = GraphManager()
    mgr.add_node(_make_node("A"))
    mgr.add_node(_make_node("B"))
    mgr.add_edge("A", "B", EDGE_NEEDS_HARD)

    first = mgr.detect_communities(method="components")
    # Mutate the returned sets (simulate an unruly caller).
    for s in first:
        s.add("MUTATED")
    # Re-fetch from cache — mutation must not have leaked.
    second = mgr.detect_communities(method="components")
    assert all("MUTATED" not in s for s in second)
