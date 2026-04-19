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


def test_graph_version_monotonic_across_instances():
    """Version is class-level (shared across instances) so every GraphManager
    reading the same DB sees the same cache-invalidation signal. All we can
    assert is that mutations advance it."""
    mgr = GraphManager()
    before = mgr._graph_version
    mgr.add_node(_make_node("VersionBumpNode"))
    mgr2 = GraphManager()
    assert mgr2._graph_version > before
    assert mgr2._graph_version == mgr._graph_version


def test_community_cache_is_per_instance():
    mgr1 = GraphManager()
    mgr1.add_node(_make_node("X"))
    mgr1.detect_communities()
    mgr2 = GraphManager()  # fresh instance on same DB
    assert mgr2._community_cache == {}, "community cache should be per-instance, not module-global"


def test_scoring_memo_reused_across_calls_on_same_version():
    """The GraphManager scoring memo should persist between calls when the
    graph hasn't mutated and hyperparams haven't changed. This means a filter
    toggle or priority-goal change doesn't re-walk the total_value cascade.
    """
    mgr = GraphManager()
    mgr.add_node(_make_node("A", value=5))
    mgr.add_node(_make_node("B", value=5))
    mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)

    mgr.calculate_priority_scores([mgr.get_node("A"), mgr.get_node("B")])
    memo_after_first = mgr._scoring_memo
    assert len(memo_after_first) >= 1, "memo should be populated after scoring"

    # Second call with same graph — same dict instance, same contents.
    mgr.calculate_priority_scores([mgr.get_node("A")])
    assert mgr._scoring_memo is memo_after_first, (
        "memo dict should not be replaced when graph version is unchanged"
    )


def test_scoring_memo_invalidated_on_graph_mutation():
    """Any _bump_version must invalidate the scoring memo."""
    mgr = GraphManager()
    mgr.add_node(_make_node("A", value=5))
    mgr.add_node(_make_node("B", value=5))
    mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)

    mgr.calculate_priority_scores([mgr.get_node("A")])
    first_memo = mgr._scoring_memo
    first_key = mgr._scoring_memo_key

    mgr.add_node(_make_node("C", value=3))
    mgr.calculate_priority_scores([mgr.get_node("A")])
    assert mgr._scoring_memo_key != first_key, "cache key should advance on mutation"
    assert mgr._scoring_memo is not first_memo, "memo dict should be replaced"


def test_scoring_memo_survives_cosmetic_edit():
    """Editing non-scoring fields (description, paths, etc.) must NOT
    invalidate the scoring memo — that's the whole point of the fingerprint.
    """
    mgr = GraphManager()
    mgr.add_node(_make_node("A", value=5, description="original"))
    mgr.add_node(_make_node("B", value=5))
    mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)

    mgr.calculate_priority_scores([mgr.get_node("A")])
    first_memo = mgr._scoring_memo
    first_scoring_key = mgr._scoring_memo_key
    graph_ver_before = mgr._graph_version

    # Cosmetic edit: description change only. graph_version advances
    # (so UI re-renders), but scoring_version must NOT advance.
    cosmetic = _make_node("A", value=5, description="updated")
    mgr.update_node(cosmetic)
    assert mgr._graph_version > graph_ver_before, "graph version should still bump for UI"

    mgr.calculate_priority_scores([mgr.get_node("A")])
    assert mgr._scoring_memo is first_memo, (
        "cosmetic edit wrongly invalidated the scoring memo"
    )
    assert mgr._scoring_memo_key == first_scoring_key


def test_scoring_memo_invalidated_on_scoring_field_edit():
    """Editing a scoring-relevant field (value, status, ...) must invalidate."""
    mgr = GraphManager()
    mgr.add_node(_make_node("A", value=5))

    mgr.calculate_priority_scores([mgr.get_node("A")])
    first_key = mgr._scoring_memo_key

    # Value change → scoring-relevant.
    updated = _make_node("A", value=9)
    mgr.update_node(updated)

    mgr.calculate_priority_scores([mgr.get_node("A")])
    assert mgr._scoring_memo_key != first_key, (
        "value edit failed to invalidate the scoring memo"
    )


def test_scoring_memo_invalidated_on_hyperparam_change(monkeypatch):
    """Changing hyperparameters must invalidate the scoring memo even when
    the graph is untouched."""
    from config import ConfigManager
    mgr = GraphManager()
    mgr.add_node(_make_node("A"))

    base = ConfigManager.get_hyperparams()
    monkeypatch.setattr(ConfigManager, "get_hyperparams", classmethod(lambda cls: dict(base, w_v=1.0)))
    mgr.calculate_priority_scores([mgr.get_node("A")])
    first_key = mgr._scoring_memo_key

    monkeypatch.setattr(ConfigManager, "get_hyperparams", classmethod(lambda cls: dict(base, w_v=2.0)))
    mgr.calculate_priority_scores([mgr.get_node("A")])
    assert mgr._scoring_memo_key != first_key, "cache key should advance on hyperparam change"


def test_goal_subtree_cache_hit_avoids_db(monkeypatch):
    """Repeat lookups for the same (goal, edge_types) on an unchanged graph
    must not re-query the DB — select_detail_node fires this 4x per call."""
    mgr = GraphManager()
    mgr.add_node(_make_node("Root", type="Goal"))
    mgr.add_node(_make_node("A"))
    mgr.add_node(_make_node("B"))
    mgr.add_edge("A", "Root", EDGE_NEEDS_HARD)
    mgr.add_edge("B", "A", EDGE_NEEDS_HARD)

    first = mgr.get_goal_subtree("Root")
    assert first == {"A", "B"}

    # Instrument get_connection after first call to prove the cache is used.
    call_count = {"n": 0}
    orig = mgr.get_connection
    def _tracked(*a, **kw):
        call_count["n"] += 1
        return orig(*a, **kw)
    monkeypatch.setattr(mgr, "get_connection", _tracked)

    second = mgr.get_goal_subtree("Root")
    assert second == first
    assert call_count["n"] == 0, "cache miss: DB queried despite unchanged graph"


def test_goal_subtree_cache_invalidated_by_mutation():
    mgr = GraphManager()
    mgr.add_node(_make_node("Root", type="Goal"))
    mgr.add_node(_make_node("A"))
    mgr.add_edge("A", "Root", EDGE_NEEDS_HARD)

    first = mgr.get_goal_subtree("Root")
    assert first == {"A"}

    mgr.add_node(_make_node("B"))
    mgr.add_edge("B", "A", EDGE_NEEDS_HARD)

    second = mgr.get_goal_subtree("Root")
    assert second == {"A", "B"}, "cache not invalidated after edge addition"


def test_goal_subtree_cache_separates_edge_type_combos():
    """Same goal with different edge_types must not share a cache entry."""
    mgr = GraphManager()
    mgr.add_node(_make_node("Root", type="Goal"))
    mgr.add_node(_make_node("Hard"))
    mgr.add_node(_make_node("Soft"))
    mgr.add_edge("Hard", "Root", EDGE_NEEDS_HARD)
    mgr.add_edge("Soft", "Root", EDGE_NEEDS_SOFT)

    hard_only = mgr.get_goal_subtree("Root", edge_types=(EDGE_NEEDS_HARD,))
    both = mgr.get_goal_subtree("Root", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
    assert hard_only == {"Hard"}
    assert both == {"Hard", "Soft"}


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
