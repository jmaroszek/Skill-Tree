"""Goals rank by the average worth of the work left beneath them.

Every unfinished task in a Goal's hard subtree counts alike, however deep it
sits. A task is worth its own ratings plus the credit it earns for the Goals
above it (d_H for its nearest Goal, one more d_H per parent level), and a
Goal's base score is that worth summed over its tasks, divided by their summed
effort. So a Goal's size counts neither for nor against it, and neither does
how its work is drawn.
"""
import pytest

from config import PROFILES
from goal_ranking import _rank_goals, explain_goal
from models import EDGE_NEEDS_HARD, Node
from scoring import focus_route_data, intrinsic_value, perceived_cost

HP = dict(PROFILES['Sage'])
D_H = HP['d_H']


def node(name, **kw):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=10, time_m=10, time_p=10,
        context='Mind', status='Open'), **kw))


def goal(name, **kw):
    return node(name, type='Goal', time_mode='inherited', **kw)


def edge(a, b, kind='Needs_Hard'):
    return dict(source=a, target=b, type=kind)


def iv(n):
    return intrinsic_value(n, HP['w_v'], HP['w_i'], HP['value_exponent'])


def cost(n):
    return perceived_cost(n, HP['w_e'], HP['w_t'], HP['beta'])


def comps(nodes, edges, priority=()):
    goals = [n for n in nodes if n.type == 'Goal']
    return {g.name: c for g, c in _rank_goals(goals, nodes, edges, list(priority), HP,
                                              with_components=True)}


def test_base_score_is_worth_over_effort():
    a, b = node('A', value=8, interest=6), node('B', value=3, interest=9, difficulty=2)
    g = goal('G', value=7, interest=7)
    c = comps([a, b, g], [edge('A', 'B'), edge('B', 'G')])['G']
    worth = iv(a) + iv(b) + 2 * D_H * iv(g)
    assert c['tv'] == pytest.approx(worth)
    assert c['cost'] == pytest.approx(cost(a) + cost(b))
    assert c['raw'] == pytest.approx(worth / (cost(a) + cost(b)))


def test_more_work_of_the_same_quality_leaves_the_score_alone():
    small = [goal('Small')] + [node(f'S{i}') for i in range(2)]
    big = [goal('Big')] + [node(f'B{i}') for i in range(12)]
    edges = ([edge(f'S{i}', 'Small') for i in range(2)]
             + [edge(f'B{i}', 'Big') for i in range(12)])
    c = comps(small + big, edges)
    assert c['Big']['raw'] == pytest.approx(c['Small']['raw'])
    assert c['Big']['tv'] == pytest.approx(6 * c['Small']['tv'])


def test_a_chain_scores_the_same_as_a_fan():
    tasks = [node(f'T{i}', value=4 + i, interest=9 - i) for i in range(4)]
    fan = [edge(t.name, 'G') for t in tasks]
    chain = [edge('T0', 'T1'), edge('T1', 'T2'), edge('T2', 'T3'), edge('T3', 'G')]
    g = goal('G', value=9, interest=10)
    assert comps(tasks + [g], chain)['G']['raw'] == pytest.approx(
        comps(tasks + [g], fan)['G']['raw'])


def test_finished_work_and_optional_work_are_left_out():
    nodes = [node('Done', status='Done', value=10, interest=10), node('Left'),
             node('Soft', value=10, interest=10), node('Helps', value=10, interest=10),
             goal('G')]
    edges = [edge('Done', 'G'), edge('Left', 'G'), edge('Soft', 'G', 'Needs_Soft'),
             edge('Helps', 'G', 'Helps')]
    c = comps(nodes, edges)['G']
    assert c['n_tasks'] == 1
    assert c['tv'] == pytest.approx(iv(nodes[1]) + D_H * iv(nodes[4]))


def test_a_goal_with_no_work_left_scores_nothing():
    nodes = [node('A', status='Done'), goal('G'), goal('Empty')]
    c = comps(nodes, [edge('A', 'G')])
    assert c['G']['score'] == 0 and c['Empty']['score'] == 0


def test_a_sub_goal_is_a_step_and_a_task_is_worth_the_same_wherever_it_counts():
    """T sits under Sub, which sits under Parent. T earns d_H of Sub's rating and
    d_H**2 of Parent's, and carries that same worth into both Goals' averages."""
    t = node('T', value=6, interest=6)
    sub, parent = goal('Sub', value=9, interest=9), goal('Parent', value=4, interest=4)
    c = comps([t, sub, parent], [edge('T', 'Sub'), edge('Sub', 'Parent')])
    worth = iv(t) + D_H * iv(sub) + D_H ** 2 * iv(parent)
    assert c['Sub']['tv'] == pytest.approx(worth)
    assert c['Parent']['tv'] == pytest.approx(worth)
    assert c['Parent']['raw'] == pytest.approx(c['Sub']['raw'])


def test_priority_and_density_still_scale_the_score():
    nodes = [node('A'), node('B'), goal('G1', context='Mind'), goal('G2', context='Mind')]
    c = comps(nodes, [edge('A', 'G1'), edge('B', 'G2')], priority=['G1'])
    assert c['G1']['raw'] == pytest.approx(c['G2']['raw'])
    assert c['G1']['score'] == pytest.approx(c['G2']['score'] * HP['goal_boost'])
    assert c['G2']['density_mult'] == pytest.approx(2 ** -HP['alpha_goal'])


def test_explain_splits_worth_and_lists_every_task():
    t1, t2 = node('T1', value=8, interest=8), node('T2')
    sub, parent = goal('Sub', value=9, interest=9), goal('Parent', value=4, interest=4)
    nodes = [t1, t2, sub, parent]
    edges = [edge('T1', 'T2'), edge('T2', 'Sub'), edge('Sub', 'Parent')]
    bd, normalized = explain_goal('Sub', nodes, edges, HP, [])
    comp = bd['composition']
    assert comp['iv'] == pytest.approx(iv(t1) + iv(t2))
    assert comp['goal_credit'] == pytest.approx(2 * D_H * iv(sub))
    assert comp['other_goal_credit'] == pytest.approx(2 * D_H ** 2 * iv(parent))
    assert comp['total_value'] == pytest.approx(comps(nodes, edges)['Sub']['tv'])
    rows = {r['name']: r for r in bd['contributors']}
    assert set(rows) == {'T1', 'T2'}
    assert rows['T1']['depth'] == 2 and rows['T2']['depth'] == 1
    assert sum(r['pct_of_tv'] for r in rows.values()) == pytest.approx(100.0)
    assert bd['cost']['n_tasks'] == 2
    assert normalized is not None


def test_focus_draws_the_route_to_a_deep_task():
    nodes = [node('T1'), node('T2'), goal('G', value=9, interest=9)]
    edges = [edge('T1', 'T2'), edge('T2', 'G')]
    bd, _ = explain_goal('G', nodes, edges, HP, [])
    inverted = [{'source': e['target'], 'target': e['source'], 'type': e['type']}
                for e in edges if e['type'] == EDGE_NEEDS_HARD]
    focus = focus_route_data('G', bd['contributors'], 3, nodes, inverted, HP,
                             skip_done=False, flat_goals=False)
    assert set(focus['subtree']) == {'G', 'T1', 'T2'}
    assert ('T2', 'T1', 'Needs_Hard') in focus['edge_rank']
