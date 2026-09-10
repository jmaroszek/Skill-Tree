"""Behavioral contracts for unique benefits and required completion work."""
import json
import math
import random

import networkx as nx
import pytest

from config import ConfigManager, PROFILES
from models import Node
from scoring import explain_score, score_nodes


def node(name, hours=10, **kw):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=hours, time_m=hours, time_p=hours,
        context='Mind', status='Open'), **kw))


def edge(a, b, kind='Needs_Hard'):
    return dict(source=a, target=b, type=kind)


def rows(nodes, edges, **hp):
    return {r['name']: r for r in explain_score('A', nodes, edges,
        dict(PROFILES['Sage'], **hp))['contributors']}


def test_shared_required_work_and_other_branch_are_counted_once():
    nodes = [node('A', 4), node('Shared', 100), node('B', 1000),
             node('C', 30), node('D', 20)]
    edges = [edge('A', 'D'), edge('Shared', 'B'), edge('Shared', 'C'),
             edge('B', 'D'), edge('C', 'D')]
    result = rows(nodes, edges)
    assert result['A']['remaining_hours'] == 0
    assert result['A']['future_discount'] == 1
    assert result['D']['remaining_hours'] == 1150
    nodes[2].status = 'Done'
    assert rows(nodes, edges)['D']['remaining_hours'] == 150


def test_optional_work_does_not_dilute_an_existing_benefit():
    nodes = [node('A'), node('D', 40), node('Optional', 10000)]
    base = rows(nodes, [edge('A', 'D')])
    extra = rows(nodes, [edge('A', 'D'), edge('Optional', 'D', 'Needs_Soft')])
    assert extra['D']['contribution'] == base['D']['contribution']
    nodes[1].time_o = nodes[1].time_m = nodes[1].time_p = 4000
    assert rows(nodes, [edge('A', 'D')])['D']['contribution'] < base['D']['contribution']


def test_half_credit_and_independent_shape():
    ns = [node('A'), node('D', 1300)]
    r = rows(ns, [edge('A', 'D')], future_work_exponent=0.9, beta=0.2)
    assert r['D']['future_discount'] == .5
    assert rows(ns, [edge('A', 'D')], future_work_half_credit_hours=0)['D']['future_discount'] == 1


@pytest.mark.parametrize('profile', list(PROFILES))
def test_independent_enumerated_path_and_hard_closure_oracle(profile):
    """Small DAG oracle enumerates paths, independently of production traversal."""
    rng = random.Random(71)
    ns = [node(chr(65+i), rng.randint(1, 200)) for i in range(7)]
    es = [edge(ns[i].name, ns[j].name, rng.choice(['Needs_Hard', 'Needs_Soft']))
          for i in range(7) for j in range(i+1, 7) if rng.random() < .6]
    es += [edge('A', 'B', 'Helps'), edge('A', 'C', 'Helps')]
    hp = PROFILES[profile]
    graph = nx.DiGraph(); graph.add_nodes_from(n.name for n in ns)
    hard = nx.DiGraph(); hard.add_nodes_from(graph)
    for e in es:
        if e['type'] != 'Helps':
            graph.add_edge(e['source'], e['target'], discount=hp['d_H'] if e['type']=='Needs_Hard' else hp['d_S'])
        if e['type'] == 'Needs_Hard':
            hard.add_edge(e['source'], e['target'])
    byname = {n.name:n for n in ns}
    expected = {}
    for seed, coefficient in [('A', 1), ('B', hp['d_Syn_pair']), ('C', hp['d_Syn_pair'])]:
        for target in graph:
            paths = [[seed]] if seed == target else list(nx.all_simple_paths(graph, seed, target))
            if not paths or not coefficient:
                continue
            weight = max(math.prod(graph[a][b]['discount'] for a,b in zip(path,path[1:])) for path in paths)
            required = (nx.ancestors(hard,target) | {target}) - {'A'}
            hours = sum(byname[x].time for x in required) if target != 'A' else 0
            discount = 1/(1+(hours/hp['future_work_half_credit_hours'])**hp['future_work_exponent'])
            intrinsic = (hp['w_v']+hp['w_i'])*5**hp['value_exponent']
            expected[target] = expected.get(target,0) + weight*coefficient*intrinsic*discount
    bd = explain_score('A', ns, es, hp)
    assert {r['name']:r['contribution'] for r in bd['contributors']} == pytest.approx(expected)
    ranked = score_nodes([ns[0]], ns, es, hp)
    assert ranked[0].total_value == pytest.approx(sum(expected.values()))
    comp = bd['composition']
    assert sum(comp[k] for k in ['iv','hard_cascade','soft_cascade','synergy','iv_multiplier_contribution']) == pytest.approx(comp['total_value'])


def test_goal_scope_and_explanation_exclude_optional_work_and_second_discount():
    from analyze_callbacks import _rank_goals, explain_goal
    ns = [node('A'), node('D', type='Goal'), node('Optional', 10000)]
    es = [edge('A','D')]
    hp = dict(PROFILES['Sage'], future_work_half_credit_hours=1)
    base = _rank_goals([ns[1]],ns,es,[],hp,with_components=True)[0][1]
    extra = es+[edge('Optional','D','Needs_Soft'),edge('Optional','D','Helps')]
    actual = _rank_goals([ns[1]],ns,extra,[],hp,with_components=True)[0][1]
    assert actual == base
    bd,_ = explain_goal('D',ns,extra,hp,[])
    assert bd['composition']['total_value'] == actual['tv']
    assert {r['name'] for r in bd['contributors']} == {'A','D'}
    assert all(r['future_discount']==1 for r in bd['contributors'])


@pytest.mark.parametrize('schema,exponent', [(1,1.0),(2,2.0),(3,2.0)])
def test_migration_preserves_rating_generation_and_does_not_rescale_v2(schema, exponent):
    stored = dict(_schema=schema,w_t=6,beta=.6)
    ConfigManager._set_db_value('HYPERPARAMS',json.dumps(stored))
    hp = ConfigManager.get_hyperparams()
    assert hp['value_exponent'] == exponent
    assert hp['w_t'] == pytest.approx(6*40**.6 if schema==1 else 6)
    ConfigManager.set_hyperparams(hp)
    assert ConfigManager.get_hyperparams() == hp


def test_partial_v1_bundle_uses_legacy_cost_defaults():
    ConfigManager._set_db_value('HYPERPARAMS', json.dumps({'w_v': 2}))
    hp = ConfigManager.get_hyperparams()
    assert hp['w_e'] == 2.5
    assert hp['beta'] == .85
    assert hp['w_t'] == pytest.approx(40**.85)
    assert hp['value_exponent'] == 1


def test_cached_required_work_updates_after_remote_prerequisite_edit():
    from graph_manager import GraphManager
    manager = GraphManager()
    ConfigManager.set_show_scoring_perf(False)
    for n in [node('A'),node('B',100),node('D')]: manager.add_node(n)
    manager.add_edge('A','D','Needs_Hard')
    manager.add_edge('B','D','Needs_Hard')
    def score():
        return manager.calculate_priority_scores([manager.get_node('A')])[0].total_value
    before = score()
    b = manager.get_node('B');b.time_o=b.time_m=b.time_p=10000
    manager.update_node(b)
    after = score()
    assert after < before
    fresh = GraphManager().calculate_priority_scores([manager.get_node('A')])[0].total_value
    assert after == fresh


def test_future_settings_callback_arity_and_profile_load():
    import inspect
    from dash import Input, State, Output
    from settings_callbacks import register_settings_callbacks

    class Registry:
        def __init__(self): self.callbacks = {}
        def clientside_callback(self, *args, **kwargs): pass
        def callback(self, *dependencies, **kwargs):
            def register(fn):
                self.callbacks[fn.__name__] = (fn, dependencies)
                return fn
            return register

    registry = Registry()
    register_settings_callbacks(registry)
    for name in ['load_settings', 'apply_profile', 'save_settings']:
        fn, deps = registry.callbacks[name]
        assert len(inspect.signature(fn).parameters) == sum(isinstance(d, (Input, State)) for d in deps)
    load, deps = registry.callbacks['load_settings']
    assert len(load(False)) == sum(isinstance(d, Output) for d in deps)
    ConfigManager.set_hyperparams(dict(PROFILES['Sage'], future_work_half_credit_hours=400,
                                      future_work_exponent=.8))
    loaded = load(True)
    outputs = [d for d in deps if isinstance(d, Output)]
    assert len(loaded) == len(outputs)
    values = {d.component_id: value for d, value in zip(outputs, loaded)}
    assert values['hp-context-repeat'] == 5
    assert values['hp-subcontext-repeat'] == 15
    assert loaded[-2:] == (400, .8)
    apply, deps = registry.callbacks['apply_profile']
    assert len(apply('Custom')) == sum(isinstance(d, Output) for d in deps)
    assert apply('Compounder')[-2:] == (1300, .5)
    outputs = [d for d in deps if isinstance(d, Output)]
    for name, hp in PROFILES.items():
        loaded = apply(name)
        assert len(loaded) == len(outputs)
        values = {d.component_id: value for d, value in zip(outputs, loaded)}
        assert values['hp-context-repeat'] == hp['suggestion_context_premium']
        assert values['hp-subcontext-repeat'] == hp['suggestion_subcontext_premium']

    save, _ = registry.callbacks['save_settings']
    args = {key: None for key in inspect.signature(save).parameters}
    args.update(n_clicks=1, context_repeat=20, subcontext_repeat=10)
    before = ConfigManager._get_db_value('HYPERPARAMS')
    assert 'at least' in save(**args)[0]
    assert ConfigManager._get_db_value('HYPERPARAMS') == before
