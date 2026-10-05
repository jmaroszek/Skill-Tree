"""Ranking's scalar path preserves attribution and cannot reuse another policy."""
import math

import pytest

import scoring
from config import PROFILES
from models import Node, EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT


def value_graph():
    def node(name, **fields):
        values = dict(name=name, type='Learn', description='', value=7,
                      interest=4, difficulty=5, time_o=2, time_m=4, time_p=9,
                      status='Open', context='Mind')
        values.update(fields)
        return Node(**values)

    nodes = [node('A'), node('B'), node('C', context='Body'),
             node('Finished', status='Done', context='Body'),
             node('Checkpoint', type='Milestone'),
             node('Subgoal', type='Goal'), node('Goal', type='Goal')]
    edges = [dict(source=source, target=target, type=kind)
             for source, target, kind in [
                 ('A', 'Checkpoint', EDGE_NEEDS_HARD),
                 ('Checkpoint', 'B', EDGE_NEEDS_HARD),
                 ('C', 'B', EDGE_NEEDS_HARD),
                 ('B', 'Subgoal', EDGE_NEEDS_HARD),
                 ('Subgoal', 'Goal', EDGE_NEEDS_HARD),
                 ('A', 'C', EDGE_NEEDS_SOFT),
                 ('C', 'Goal', EDGE_NEEDS_SOFT),
                 ('Finished', 'Goal', EDGE_NEEDS_SOFT),
                 ('A', 'C', EDGE_HELPS),
                 ('A', 'Finished', EDGE_HELPS),
             ]]
    by_name = {n.name: n for n in nodes}
    hard, soft, synergy, _ = scoring.build_adjacency(edges, set(by_name))
    return by_name, hard, soft, synergy


def value_params(profile='Sage'):
    hp = PROFILES[profile]
    return {key: hp[key] for key in (
        'w_v', 'w_i', 'd_H', 'd_S', 'd_Syn_pair', 'd_Syn_mul',
        'cross_context_mult', 'value_exponent',
        'future_work_half_credit_hours', 'future_work_exponent')}


@pytest.mark.parametrize('profile', PROFILES)
@pytest.mark.parametrize('skip_done,flat_goals', [(True, True), (False, False),
                                               (True, False), (False, True)])
@pytest.mark.parametrize('visited', [frozenset(), frozenset({'C'})])
def test_scalar_total_matches_attribution_exactly(profile, skip_done, flat_goals, visited):
    nodes, hard, soft, synergy = value_graph()
    params = value_params(profile)
    for name in nodes:
        total = scoring.total_value(name, visited, nodes, hard, soft, synergy,
                                    **params, skip_done=skip_done, flat_goals=flat_goals)
        if name in visited:
            assert total == 0.0
            continue
        partners = {name: synergy.get(name, set()) - visited}
        rows = scoring._value_contributions(
            name, nodes, hard, soft, partners,
            **{key: value for key, value in params.items() if key != 'd_Syn_mul'},
            skip_done=skip_done, flat_goals=flat_goals)
        done = sum(nodes[partner].status == 'Done' for partner in partners[name]
                   if partner != name)
        kick = scoring.intrinsic_value(nodes[name], params['w_v'], params['w_i'],
                                       params['value_exponent']) * params['d_Syn_mul'] * math.sqrt(done)
        assert total == math.fsum(row['contribution'] for row in rows) + kick


def test_repeated_value_reuses_scalar_without_rebuilding_contributions(monkeypatch):
    graph = value_graph()
    memo = {}
    expected = scoring.total_value('A', set(), *graph, **value_params(), memo=memo)

    def unexpected(*args, **kwargs):
        pytest.fail('A second scoring pass rebuilt the same value contributions')

    monkeypatch.setattr(scoring, '_value_contributions', unexpected)
    assert scoring.total_value('A', set(), *graph, **value_params(), memo=memo) == expected


@pytest.mark.parametrize('change', [
    {'w_v': 2.0}, {'w_i': 2.0}, {'d_H': 0.3}, {'d_S': 0.2},
    {'d_Syn_pair': 0.4}, {'d_Syn_mul': 0.8}, {'cross_context_mult': 2.5},
    {'value_exponent': 1.5}, {'future_work_half_credit_hours': 10.0},
    {'future_work_exponent': 0.95}, {'skip_done': False}, {'flat_goals': False},
    {'visited': {'C'}},
])
def test_scalar_cache_separates_value_parameters_and_excluded_partners(change):
    graph = value_graph()
    params = dict(value_params(), visited=set())
    memo = {}
    scoring.total_value('A', all_nodes=graph[0], H_out=graph[1], S_out=graph[2],
                        Syn=graph[3], **params, memo=memo)
    params.update(change)
    cached = scoring.total_value('A', all_nodes=graph[0], H_out=graph[1], S_out=graph[2],
                                 Syn=graph[3], **params, memo=memo)
    fresh = scoring.total_value('A', all_nodes=graph[0], H_out=graph[1], S_out=graph[2],
                                Syn=graph[3], **params)
    assert cached == fresh


def test_missing_or_already_visited_node_has_no_value():
    graph = value_graph()
    assert scoring.total_value('Missing', set(), *graph, **value_params(), memo={}) == 0.0
    assert scoring.total_value('A', {'A'}, *graph, **value_params(), memo={}) == 0.0
