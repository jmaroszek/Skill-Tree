"""Done nodes earn the nodes upstream of them nothing.

A Done node's value is already banked. Crediting it again to an open
prerequisite, soft prep or Helps partner rewards work for a payoff that has
already happened. The Goal ranker is the one exception: it deliberately
counts finished prerequisites as part of a Goal's value.
"""
import math

import pytest

from config import ConfigManager, PROFILES
from models import Node
from scoring import build_adjacency, explain_score, focus_route_data, score_nodes, total_value

HP = PROFILES['Sage']


def node(name, hours=10, **kw):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=hours, time_m=hours, time_p=hours,
        context='Mind', status='Open'), **kw))


def edge(a, b, kind='Needs_Hard'):
    return dict(source=a, target=b, type=kind)


def contributors(name, nodes, edges):
    return {r['name']: r for r in explain_score(name, nodes, edges, HP)['contributors']}


def tv(name, nodes, edges):
    return score_nodes([n for n in nodes if n.name == name], nodes, edges, HP)[0].total_value


def test_done_soft_dependent_pays_nothing():
    nodes = [node('A'), node('D', value=9)]
    edges = [edge('A', 'D', 'Needs_Soft')]
    open_tv = tv('A', nodes, edges)
    nodes[1].status = 'Done'
    assert 'D' not in contributors('A', nodes, edges)
    assert tv('A', nodes, edges) < open_tv
    assert tv('A', nodes, edges) == pytest.approx(contributors('A', nodes, edges)['A']['contribution'])


def test_value_does_not_route_through_a_done_node():
    # A preps D, which unlocks C. With D Done, C no longer waits on A at all.
    nodes = [node('A'), node('D', status='Done'), node('C', value=9)]
    edges = [edge('A', 'D', 'Needs_Soft'), edge('D', 'C')]
    assert set(contributors('A', nodes, edges)) == {'A'}


def test_open_route_around_a_done_node_still_counts():
    nodes = [node('A'), node('D', status='Done'), node('B'), node('C', value=9)]
    edges = [edge('A', 'D'), edge('D', 'C'), edge('A', 'B'), edge('B', 'C')]
    rows = contributors('A', nodes, edges)
    assert set(rows) == {'A', 'B', 'C'}
    assert rows['C']['depth'] == 2


def test_done_goal_pays_nothing():
    nodes = [node('A'), node('G', type='Goal', value=10, status='Done')]
    assert set(contributors('A', nodes, [edge('A', 'G')])) == {'A'}


def test_done_helps_partner_gives_the_multiplier_but_no_pair_bonus():
    nodes = [node('A'), node('B', status='Done'), node('C', value=9)]
    edges = [edge('A', 'B', 'Helps'), edge('B', 'C')]
    bd = explain_score('A', nodes, edges, HP)
    assert {r['name'] for r in bd['contributors']} == {'A'}
    comp = bd['composition']
    assert comp['done_synergy_count'] == 1
    assert comp['synergy'] == 0
    iv = comp['iv']
    assert comp['total_value'] == pytest.approx(iv * (1 + HP['d_Syn_mul']))
    assert tv('A', nodes, edges) == pytest.approx(comp['total_value'])


def test_total_value_skips_done_by_default():
    nodes = {n.name: n for n in [node('A'), node('D', status='Done')]}
    H_out, S_out, Syn, _ = build_adjacency([edge('A', 'D')], set(nodes))
    args = (nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.4, 0.1, 0.4)
    assert total_value('A', set(), *args) == pytest.approx(10.0)
    assert total_value('A', set(), *args, skip_done=False) == pytest.approx(16.0)


def test_focus_does_not_draw_a_route_through_a_done_node():
    nodes = [node('A'), node('D', status='Done'), node('B'), node('C', value=9)]
    edges = [edge('A', 'D'), edge('D', 'C'), edge('A', 'B'), edge('B', 'C')]
    rows = explain_score('A', nodes, edges, HP)['contributors']
    focus = focus_route_data('A', rows, 3, nodes, edges, HP)
    assert 'D' not in focus['subtree']
    assert ('B', 'C', 'Needs_Hard') in focus['edge_rank']


def test_goal_ranking_still_counts_finished_prerequisites():
    from goal_ranking import _rank_goals, explain_goal
    nodes = [node('A', status='Done'), node('B'), node('G', type='Goal')]
    edges = [edge('A', 'G'), edge('B', 'G')]
    comp = _rank_goals([nodes[2]], nodes, edges, [], HP, with_components=True)[0][1]
    bd, _ = explain_goal('G', nodes, edges, HP, [])
    assert {r['name'] for r in bd['contributors']} == {'A', 'B', 'G'}
    assert bd['composition']['total_value'] == pytest.approx(comp['tv'])


def test_marking_a_dependent_done_rescores_through_the_cache():
    from graph_manager import GraphManager
    manager = GraphManager()
    ConfigManager.set_show_scoring_perf(False)
    for n in [node('A'), node('D', value=9)]:
        manager.add_node(n)
    manager.add_edge('A', 'D', 'Needs_Soft')

    def score():
        return manager.calculate_priority_scores([manager.get_node('A')])[0].total_value

    before = score()
    d = manager.get_node('D')
    d.status = 'Done'
    manager.update_node(d)
    after = score()
    assert after < before
    assert math.isclose(after, GraphManager().calculate_priority_scores(
        [manager.get_node('A')])[0].total_value)
