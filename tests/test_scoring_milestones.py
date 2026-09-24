"""Milestones are not steps.

A Milestone tracks progress and holds no work, so the work on either side of
it sits one step apart, in both node scoring and the Goal ranker.
"""
import pytest

from config import PROFILES
from models import Node
from scoring import explain_score

HP = dict(PROFILES['Sage'], future_work_half_credit_hours=0.0)
D_H, D_S = HP['d_H'], HP['d_S']


def node(name, **kw):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=10, time_m=10, time_p=10,
        context='Mind', status='Open'), **kw))


def milestone(name, **kw):
    return node(name, type='Milestone', **kw)


def goal(name, **kw):
    return node(name, type='Goal', time_mode='inherited', **kw)


def edge(a, b, kind='Needs_Hard'):
    return dict(source=a, target=b, type=kind)


def rows(name, nodes, edges):
    return {r['name']: r for r in explain_score(name, nodes, edges, HP)['contributors']}


# --------------------------------------------------------------- Milestones

def test_a_milestone_is_not_a_step():
    direct = rows('A', [node('A'), node('B')], [edge('A', 'B')])
    through = rows('A', [node('A'), milestone('M'), node('B')],
                   [edge('A', 'M'), edge('M', 'B')])
    assert through['B']['weight'] == pytest.approx(direct['B']['weight']) == pytest.approx(D_H)
    assert through['B']['contribution'] == pytest.approx(direct['B']['contribution'])
    assert through['B']['depth'] == direct['B']['depth'] == 1


def test_a_chain_of_milestones_is_not_a_step_either():
    nodes = [node('A'), milestone('M1'), milestone('M2'), node('B'), node('C')]
    edges = [edge('A', 'M1'), edge('M1', 'M2'), edge('M2', 'B'), edge('B', 'C')]
    r = rows('A', nodes, edges)
    assert r['B']['weight'] == pytest.approx(D_H)
    assert r['C']['weight'] == pytest.approx(D_H ** 2)
    assert r['C']['depth'] == 2


def test_a_soft_edge_into_a_milestone_still_pays_the_soft_discount():
    nodes = [node('A'), milestone('M'), node('B')]
    r = rows('A', nodes, [edge('A', 'M', 'Needs_Soft'), edge('M', 'B')])
    assert r['B']['weight'] == pytest.approx(D_S)


def test_a_learn_container_still_counts_as_a_step():
    """Containers group stages of real work, so only Milestones are free."""
    nodes = [node('A'), node('Stage', time_mode='inherited', value_mode='inherited'), node('B')]
    r = rows('A', nodes, [edge('A', 'Stage'), edge('Stage', 'B')])
    assert r['B']['weight'] == pytest.approx(D_H ** 2)


# --------------------------------------------------------------- Goal ranking

def test_goal_ranking_frees_milestones_too():
    from goal_ranking import _rank_goals
    hp = dict(HP)
    nodes = [node('A', value=8, interest=8), milestone('M'), node('B', value=6, interest=6),
             goal('G', value=1, interest=1)]
    edges = [edge('A', 'B'), edge('B', 'M'), edge('M', 'G')]
    comp = _rank_goals([nodes[3]], nodes, edges, [], hp, with_components=True)[0][1]
    g = hp['value_exponent']
    iv = lambda v: hp['w_v'] * v ** g + hp['w_i'] * v ** g
    assert comp['tv'] == pytest.approx(iv(8) + iv(6) + 2 * D_H * iv(1))
    assert comp['n_tasks'] == 2
