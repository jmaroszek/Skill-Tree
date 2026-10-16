"""Redundant Hard edges never change a score.

A Hard edge that a longer Hard path already implies adds no ordering, so
scoring reads the transitive reduction (scoring._drop_redundant_hard).
Eligibility still reads every edge.
"""
from skilltree.domain.models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
from skilltree.domain.scoring import _drop_redundant_hard, build_adjacency, explain_score, score_nodes
from skilltree.domain.goals import _rank_goals

HP = {'w_v': 1.0, 'w_i': 1.0, 'd_H': 0.6, 'd_S': 0.3, 'w_e': 1.5, 'w_t': 6.0,
      'beta': 0.6, 'value_exponent': 2.0, 'goal_boost': 1.0}


def _node(name, **kw):
    fields = dict(name=name, type='Learn', description='', value=5, interest=5,
                  difficulty=5, time_o=10, time_m=20, time_p=40,
                  status='Open', context='Mind')
    fields.update(kw)
    return Node(**fields)


def _hard(source, target):
    return {'source': source, 'target': target, 'type': EDGE_NEEDS_HARD}


def _scores(nodes, edges):
    return {n.name: n.priority_score for n in score_nodes(nodes, nodes, edges, HP)}


def test_reduction_drops_only_implied_edges():
    H_out = {'A': ['B', 'C', 'D'], 'B': ['C'], 'C': [], 'D': []}
    assert _drop_redundant_hard(H_out) == {'A': ['B', 'D'], 'B': ['C'], 'C': [], 'D': []}


def test_reduction_leaves_a_cyclic_graph_alone():
    H_out = {'A': ['B'], 'B': ['A']}
    assert _drop_redundant_hard(H_out) is H_out


def test_build_adjacency_keeps_every_edge_for_eligibility():
    edges = [_hard('A', 'B'), _hard('B', 'C'), _hard('A', 'C')]
    H_out, _, _, Hard_in = build_adjacency(edges, {'A', 'B', 'C'})
    assert H_out['A'] == ['B']
    assert sorted(Hard_in['C']) == ['A', 'B']


def test_shortcut_between_tasks_changes_no_score():
    nodes = [_node('A'), _node('B', value_mode='inherited'),
             _node('C', value=10, interest=10)]
    chain = [_hard('A', 'B'), _hard('B', 'C')]
    assert _scores(nodes, chain + [_hard('A', 'C')]) == _scores(nodes, chain)


def test_soft_shortcut_still_counts():
    """Only Hard edges are reduced: a Soft edge is a different relationship,
    and here its route (d_S = 0.9) beats the Hard chain (d_H**2 = 0.36)."""
    nodes = [_node('A'), _node('B'), _node('C', value=10, interest=10)]
    chain = [_hard('A', 'B'), _hard('B', 'C')]
    soft = {'source': 'A', 'target': 'C', 'type': EDGE_NEEDS_SOFT}
    strong = dict(HP, d_S=0.9)
    with_soft = {n.name: n.priority_score
                 for n in score_nodes(nodes, nodes, chain + [soft], strong)}
    without = {n.name: n.priority_score for n in score_nodes(nodes, nodes, chain, strong)}
    assert with_soft['A'] > without['A']


def test_task_linked_past_its_sub_goal_changes_no_score():
    nodes = [_node('T'), _node('Sub', type='Goal', time_mode='inherited', value=8),
             _node('Top', type='Goal', time_mode='inherited', value=10, interest=10)]
    nested = [_hard('T', 'Sub'), _hard('Sub', 'Top')]
    with_shortcut = nested + [_hard('T', 'Top')]
    assert _scores(nodes, with_shortcut) == _scores(nodes, nested)
    goals = [n for n in nodes if n.type == 'Goal']
    assert (_rank_goals(goals, nodes, with_shortcut, [], HP, with_scores=True)
            == _rank_goals(goals, nodes, nested, [], HP, with_scores=True))


def test_explain_matches_without_shortcut():
    nodes = [_node('A'), _node('B'), _node('C', value=10, interest=10)]
    chain = [_hard('A', 'B'), _hard('B', 'C')]
    a = explain_score('A', nodes, chain + [_hard('A', 'C')], HP)
    b = explain_score('A', nodes, chain, HP)
    assert a['composition'] == b['composition']
