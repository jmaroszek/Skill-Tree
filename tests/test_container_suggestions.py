"""Behavioral tests for the Details empty-state Explore ranking."""

from typing import Any

import pytest

from callback_helpers import rank_details_suggestions
from models import (
    EDGE_NEEDS_HARD,
    EDGE_NEEDS_SOFT,
    STATUS_DONE,
    Node,
)


HYPERPARAMS = {
    "w_v": 1.0,
    "w_i": 0.0,
    "value_exponent": 1.0,
    "d_H": 1.0,
    "d_S": 0.4,
    "cross_context_mult": 1.0,
    "suggestion_context_premium": 0.0,
    "suggestion_subcontext_premium": 0.0,
    "context_weights": {},
}


def _node(name: str, **overrides: Any) -> Node:
    defaults: dict[str, Any] = {
        "name": name,
        "type": "Learn",
        "description": "A test node",
        "value": 5,
        "time_o": 1.0,
        "time_m": 2.0,
        "time_p": 4.0,
        "interest": 5,
        "difficulty": 5,
        "status": "Open",
        "context": "Mind",
    }
    defaults.update(overrides)
    return Node(**defaults)


def _container(name: str, **overrides: Any) -> Node:
    overrides.setdefault("time_mode", "inherited")
    overrides.setdefault("value_mode", "inherited")
    return _node(name, **overrides)


def _edge(source: str, target: str, edge_type: str = EDGE_NEEDS_HARD):
    return {"source": source, "target": target, "type": edge_type}


def _rank(nodes, edges, **overrides):
    return rank_details_suggestions(
        nodes, edges, HYPERPARAMS, count=overrides.pop("count", 10),
        **overrides,
    )


def test_returns_all_container_modes_but_not_leaf_or_milestone():
    strict = _container("Strict")
    value_only = _container("ValueOnly", time_mode="manual")
    goal = _node("Goal", type="Goal", value_mode="manual")
    milestone = _node("Checkpoint", type="Milestone")
    children = [
        _node("Strict child"),
        _node("Value child"),
        _node("Goal child"),
        _node("Milestone child"),
        _node("Plain leaf"),
    ]
    nodes = [strict, value_only, goal, milestone, *children]
    edges = [
        _edge("Strict child", "Strict"),
        _edge("Value child", "ValueOnly"),
        _edge("Goal child", "Goal"),
        _edge("Milestone child", "Checkpoint"),
    ]

    names = [suggestion.node.name for suggestion in _rank(nodes, edges)]

    assert set(names) == {"Strict", "ValueOnly", "Goal"}
    assert "Checkpoint" not in names
    assert "Plain leaf" not in names


def test_ranks_by_incoming_required_scope_not_forward_unlocks():
    """Regression: the old forward scorer tied these and chose alphabetically."""
    rich = _container("ZRich")
    sparse = _container("ASparse")
    rich_children = [_node(f"Rich child {index}", value=8) for index in range(4)]
    sparse_child = _node("Sparse child", value=8)
    nodes = [sparse, sparse_child, rich, *rich_children]
    edges = [
        *[_edge(child.name, rich.name) for child in rich_children],
        _edge(sparse_child.name, sparse.name),
    ]

    results = _rank(nodes, edges)

    assert [result.node.name for result in results][:2] == ["ZRich", "ASparse"]
    assert results[0].remaining_count == 4
    assert results[0].scope_value == pytest.approx(32.0)
    assert results[0].scope_value > results[1].scope_value


def test_uses_only_hard_prerequisites_to_define_scope():
    hard = _container("Hard scope")
    soft_only = _container("Soft only")
    hard_child = _node("Hard child", value=7)
    soft_child = _node("Soft child", value=10)
    nodes = [hard, soft_only, hard_child, soft_child]
    edges = [
        _edge(hard_child.name, hard.name),
        _edge(soft_child.name, hard.name, EDGE_NEEDS_SOFT),
        _edge(soft_child.name, soft_only.name, EDGE_NEEDS_SOFT),
    ]

    results = _rank(nodes, edges)

    assert [result.node.name for result in results] == ["Hard scope"]
    assert results[0].scope_value == pytest.approx(7.0)
    assert results[0].remaining_count == 1


def test_excludes_inactive_roots_and_zeroes_completed_prerequisite_value():
    active = _container("Active")
    done_root = _container("Done root", status=STATUS_DONE)
    dormant_root = _container("Dormant root", dormant=1)
    done_child = _node("Done child", value=10, status=STATUS_DONE)
    open_child = _node("Open child", value=4)
    nodes = [active, done_root, dormant_root, done_child, open_child]
    edges = [
        _edge(done_child.name, active.name),
        _edge(open_child.name, active.name),
        _edge(open_child.name, done_root.name),
        _edge(open_child.name, dormant_root.name),
    ]

    results = _rank(nodes, edges)

    assert [result.node.name for result in results] == ["Active"]
    assert results[0].remaining_count == 1
    assert results[0].total_count == 2
    assert results[0].scope_value == pytest.approx(4.0)


def test_respects_filtered_candidates_and_visible_priority_seeds():
    a = _container("A")
    b = _container("B")
    a_child = _node("A child")
    b_child = _node("B child")
    nodes = [a, b, a_child, b_child]
    edges = [_edge(a_child.name, a.name), _edge(b_child.name, b.name)]

    filtered = _rank(nodes, edges, candidate_names={"A"})
    seeded = _rank(nodes, edges, seed_names=("A",))

    assert [result.node.name for result in filtered] == ["A"]
    assert [result.node.name for result in seeded] == ["B"]


def test_direct_parent_child_repeat_waits_for_independent_branch():
    parent = _container("Parent")
    child = _container("Child")
    independent = _container("Independent")
    deep_leaf = _node("Deep leaf", value=10)
    parent_leaf = _node("Parent leaf", value=10)
    independent_leaf = _node("Independent leaf", value=1)
    nodes = [
        parent, child, independent, deep_leaf, parent_leaf, independent_leaf,
    ]
    edges = [
        _edge(deep_leaf.name, child.name),
        _edge(child.name, parent.name),
        _edge(parent_leaf.name, parent.name),
        _edge(independent_leaf.name, independent.name),
    ]

    names = [
        result.node.name for result in _rank(nodes, edges, count=2)
    ]

    assert names == ["Parent", "Independent"]


def test_nested_fallback_can_fill_list_when_no_independent_branch_remains():
    parent = _container("Parent")
    child = _container("Child")
    deep_leaf = _node("Deep leaf", value=10)
    parent_leaf = _node("Parent leaf", value=10)
    nodes = [parent, child, deep_leaf, parent_leaf]
    edges = [
        _edge(deep_leaf.name, child.name),
        _edge(child.name, parent.name),
        _edge(parent_leaf.name, parent.name),
    ]

    names = [result.node.name for result in _rank(nodes, edges, count=2)]

    assert names == ["Parent", "Child"]


def test_priority_hierarchy_seed_steers_first_choice_to_another_branch():
    parent = _container("Priority parent")
    child = _container("Nested child")
    independent = _container("Independent")
    deep_leaf = _node("Deep leaf", value=10)
    independent_leaf = _node("Independent leaf", value=1)
    nodes = [parent, child, independent, deep_leaf, independent_leaf]
    edges = [
        _edge(deep_leaf.name, child.name),
        _edge(child.name, parent.name),
        _edge(independent_leaf.name, independent.name),
    ]

    results = _rank(
        nodes, edges, count=1, seed_names=(parent.name,)
    )

    assert [result.node.name for result in results] == ["Independent"]


def test_configured_context_variety_can_beat_a_close_repeat():
    a_best = _container("A best", context="Mind")
    a_next = _container("A next", context="Mind")
    b = _container("B", context="Body")
    a_best_child = _node("A best child", value=10, context="Mind")
    a_next_child = _node("A next child", value=9, context="Mind")
    b_child = _node("B child", value=6, context="Body")
    nodes = [a_best, a_next, b, a_best_child, a_next_child, b_child]
    edges = [
        _edge(a_best_child.name, a_best.name),
        _edge(a_next_child.name, a_next.name),
        _edge(b_child.name, b.name),
    ]
    hyperparams = {
        **HYPERPARAMS,
        "suggestion_context_premium": 100.0,
        "suggestion_subcontext_premium": 100.0,
    }

    results = rank_details_suggestions(
        nodes, edges, hyperparams, count=2
    )

    assert [result.node.name for result in results] == ["A best", "B"]


def test_count_limit_and_ties_are_deterministic():
    alpha = _container("Alpha")
    zebra = _container("Zebra")
    alpha_child = _node("Alpha child", value=5)
    zebra_child = _node("Zebra child", value=5)
    edges = [
        _edge(alpha_child.name, alpha.name),
        _edge(zebra_child.name, zebra.name),
    ]

    forward = _rank(
        [zebra, zebra_child, alpha, alpha_child], edges, count=1
    )
    reverse = _rank(
        [alpha_child, alpha, zebra_child, zebra], edges, count=1
    )

    assert [result.node.name for result in forward] == ["Alpha"]
    assert [result.node.name for result in reverse] == ["Alpha"]
    assert _rank(
        [alpha, alpha_child], [_edge(alpha_child.name, alpha.name)], count=0
    ) == []
