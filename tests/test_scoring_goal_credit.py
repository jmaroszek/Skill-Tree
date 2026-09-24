"""A Goal credits every task in its hard subtree alike; a sub-Goal is a step.

A Goal's rating pays out as its work gets done, so a task deep in its hard
subtree earns as much of it as a direct prerequisite. A parent Goal's rating
mostly restates its sub-Goals, so a task under a sub-Goal earns the parent one
hop further on. Soft edges keep behaving like weaker Hard edges: prep that
reaches the subtree through a Soft edge pays the soft discount on the way in.
The Goal ranker averages the same kind of worth over a Goal's remaining work.
"""
import pytest

from config import PROFILES
from models import Node
from scoring import explain_score, focus_route_data

HP = dict(PROFILES['Sage'], future_work_half_credit_hours=0.0)
D_H, D_S = HP['d_H'], HP['d_S']


def node(name, **kw):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=10, time_m=10, time_p=10,
        context='Mind', status='Open'), **kw))


def goal(name, **kw):
    return node(name, type='Goal', time_mode='inherited', **kw)


def edge(a, b, kind='Needs_Hard'):
    return dict(source=a, target=b, type=kind)


def rows(name, nodes, edges, **kw):
    return {r['name']: r for r in explain_score(name, nodes, edges, HP, **kw)['contributors']}


def test_a_goal_credits_a_deep_task_like_a_direct_prerequisite():
    nodes = [node('A'), node('B'), node('C'), goal('G', value=9, interest=9)]
    edges = [edge('A', 'B'), edge('B', 'C'), edge('C', 'G')]
    deep = rows('A', nodes, edges)['G']
    direct = rows('C', nodes, edges)['G']
    assert deep['weight'] == pytest.approx(direct['weight']) == pytest.approx(D_H)
    assert deep['contribution'] == pytest.approx(direct['contribution'])
    assert deep['depth'] == 1
    # Ordinary work downstream still pays per step.
    assert rows('A', nodes, edges)['C']['weight'] == pytest.approx(D_H ** 2)


def test_soft_prep_for_a_goal_task_pays_the_soft_discount_on_the_way_in():
    nodes = [node('Prep'), node('Outside'), node('B'), node('C'), goal('G')]
    edges = [edge('Prep', 'B', 'Needs_Soft'), edge('B', 'C'), edge('C', 'G'),
             edge('Outside', 'Prep')]
    assert rows('Prep', nodes, edges)['G']['weight'] == pytest.approx(D_S * D_H)
    # A task that unlocks the prep is outside the subtree too: one more step.
    assert rows('Outside', nodes, edges)['G']['weight'] == pytest.approx(D_H * D_S * D_H)


def test_a_soft_edge_straight_into_a_goal_pays_the_soft_discount():
    nodes = [node('A'), goal('G')]
    assert rows('A', nodes, [edge('A', 'G', 'Needs_Soft')])['G']['weight'] == pytest.approx(D_S)


def test_a_parent_goal_is_one_step_beyond_its_sub_goal():
    nodes = [node('A'), node('B'), goal('Sub'), goal('Umbrella'), goal('Top')]
    edges = [edge('A', 'B'), edge('B', 'Sub'), edge('Sub', 'Umbrella'), edge('Umbrella', 'Top')]
    r = rows('A', nodes, edges)
    assert r['Sub']['weight'] == pytest.approx(D_H)
    assert r['Umbrella']['weight'] == pytest.approx(D_H ** 2)
    assert r['Top']['weight'] == pytest.approx(D_H ** 3)


def test_work_directly_under_a_parent_goal_earns_it_in_full():
    nodes = [node('A'), node('Direct'), goal('Sub'), goal('Umbrella')]
    edges = [edge('A', 'Sub'), edge('Sub', 'Umbrella'), edge('Direct', 'Umbrella')]
    assert rows('Direct', nodes, edges)['Umbrella']['weight'] == pytest.approx(D_H)
    assert rows('A', nodes, edges)['Umbrella']['weight'] == pytest.approx(D_H ** 2)


def test_inserting_a_goal_level_adds_a_discounted_share_not_a_full_one():
    flat = [node('A'), goal('Health', value=8, interest=9)]
    nested = flat + [goal('Nutrition', value=8, interest=9)]
    before = sum(r['contribution'] for r in rows('A', flat, [edge('A', 'Health')]).values())
    after = rows('A', nested, [edge('A', 'Nutrition'), edge('Nutrition', 'Health')])
    assert after['Health']['weight'] == pytest.approx(D_H ** 2)
    added = sum(r['contribution'] for r in after.values()) - before
    goal_credit = after['Nutrition']['contribution']
    assert added == pytest.approx(goal_credit - (D_H - D_H ** 2) * after['Health']['iv'])


def test_a_goal_reached_two_ways_takes_the_stronger():
    nodes = [node('A'), goal('Sub'), goal('Umbrella')]
    edges = [edge('A', 'Sub'), edge('Sub', 'Umbrella'), edge('A', 'Umbrella')]
    assert rows('A', nodes, edges)['Umbrella']['weight'] == pytest.approx(D_H)


def test_a_done_task_cuts_the_subtree_route():
    nodes = [node('A'), node('D', status='Done'), goal('G')]
    assert 'G' not in rows('A', nodes, [edge('A', 'D'), edge('D', 'G')])


def test_flat_goals_off_restores_per_step_goal_credit():
    nodes = [node('A'), node('B'), goal('G')]
    edges = [edge('A', 'B'), edge('B', 'G')]
    assert rows('A', nodes, edges, flat_goals=False)['G']['weight'] == pytest.approx(D_H ** 2)


def test_focus_draws_a_real_path_to_a_deep_goal():
    nodes = [node('A'), node('B'), node('C'), goal('G', value=10, interest=10)]
    edges = [edge('A', 'B'), edge('B', 'C'), edge('C', 'G')]
    contributors = explain_score('A', nodes, edges, HP)['contributors']
    focus = focus_route_data('A', contributors, 3, nodes, edges, HP)
    assert set(focus['subtree']) == {'A', 'B', 'C', 'G'}
    assert ('C', 'G', 'Needs_Hard') in focus['edge_rank']


def test_goal_ranking_counts_a_deep_task_like_a_direct_one():
    from goal_ranking import _rank_goals
    nodes = [node('A', value=8, interest=8), node('B', value=6, interest=6), goal('G', value=1, interest=1)]
    edges = [edge('A', 'B'), edge('B', 'G')]
    comp = _rank_goals([nodes[2]], nodes, edges, [], HP, with_components=True)[0][1]
    g = HP['value_exponent']
    iv = lambda v: HP['w_v'] * v ** g + HP['w_i'] * v ** g
    assert comp['tv'] == pytest.approx(iv(8) + iv(6) + 2 * D_H * iv(1))
