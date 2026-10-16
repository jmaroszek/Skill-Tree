"""Behavioral regression cases for unified, bounded synergy."""
import json
import math
import random

import pytest

from skilltree.features.details.explain import _contributor_hover
from skilltree.store.settings import ConfigManager, HYPERPARAMS_SCHEMA_VERSION, PROFILES
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from skilltree.domain.scoring import explain_score, focus_route_data, score_nodes
from skilltree.domain.synergy import partner_exposure, synergy_parameters


def node(name, hours=40, **fields):
    return Node(**dict(dict(name=name, type='Learn', description='', value=5,
        interest=5, difficulty=5, time_o=hours, time_m=hours, time_p=hours,
        status='Open', context='Mind'), **fields))


def edge(source, target, kind='Helps'):
    return dict(source=source, target=target, type=kind)


def explain(nodes, edges, profile='Sage', **overrides):
    hp = dict(PROFILES[profile], **overrides)
    bd = explain_score('A', nodes, edges, hp)
    scored = score_nodes([nodes[0]], nodes, edges, hp)[0]
    assert scored.total_value == bd['composition']['total_value']
    assert math.fsum(r['contribution'] for r in bd['contributors']) == scored.total_value
    return bd


@pytest.mark.parametrize('profile', PROFILES)
def test_one_partner_cross_context_and_completion(profile):
    nodes = [node('A'), node('B', context='Body')]
    edges = [edge('A', 'B')]
    hp = PROFILES[profile]
    own = (hp['w_v'] + hp['w_i']) * 5 ** hp['value_exponent']
    q = 1 / (1 + (40 / 1300) ** hp['future_work_exponent'])
    anticipation = hp['d_Syn_pair'] / hp['d_Syn_mul']
    expected = own * hp['d_Syn_mul'] * (1 - (1 - anticipation) ** hp['cross_context_mult']) * q
    before = explain(nodes, edges, profile)['composition']
    assert before['synergy'] == pytest.approx(expected)
    nodes[1].status = 'Done'
    after = explain(nodes, edges, profile)['composition']
    assert after['synergy'] == pytest.approx(own * hp['d_Syn_mul'])
    assert after['total_value'] >= before['total_value']
    if profile == 'Creator':
        assert before['total_value'] == pytest.approx(98.8076106817)
        assert after['total_value'] == pytest.approx(115)


def test_shared_partner_beneficiaries_never_enter_candidate_value():
    nodes = [node('A'), *[node(f'B{i}', context='Body') for i in range(10)],
             node('D', value=10, interest=10)]
    helps = [edge('A', n.name) for n in nodes[1:-1]]
    hard = [edge(n.name, 'D', 'Needs_Hard') for n in nodes[1:-1]]
    before = explain(nodes, helps, 'Creator')
    after = explain(nodes, helps + hard, 'Creator')
    assert after == before
    assert 'D' not in {r['name'] for r in after['contributors']}
    assert after['composition']['synergy'] < 2 * 1.3 * 50


def test_partner_ratings_and_partners_do_not_transfer_value():
    nodes = [node('A'), node('B'), node('C', value=10, interest=10)]
    edges = [edge('A', 'B')]
    before = explain(nodes, edges)
    nodes[1].value = nodes[1].interest = 10
    after = explain(nodes, edges + [edge('B', 'C')])
    assert after['composition'] == before['composition']
    assert 'C' not in {r['name'] for r in after['contributors']}


def test_duplicate_reverse_and_self_helps_edges_do_not_add_credit():
    nodes = [node('A'), node('B')]
    one = explain(nodes, [edge('A', 'B')])
    duplicate = explain(nodes, [edge('A', 'B'), edge('B', 'A'), edge('A', 'A')])
    assert duplicate == one


def test_completed_partner_uses_capped_candidate_base_including_inherited_value():
    nodes = [node('A', value_mode='inherited'), node('B', status='Done'),
             *[node(f'D{i}', value=10, interest=10) for i in range(4)]]
    edges = [edge('A', 'B'), *[edge('A', n.name, 'Needs_Soft') for n in nodes[2:]]]
    comp = explain(nodes, edges)['composition']
    assert comp['iv'] == 0
    assert comp['soft_cascade'] > 200
    assert comp['synergy'] == pytest.approx(.4 * 200)
    assert comp['total_value'] == pytest.approx(comp['soft_cascade'] + 80)
    assert explain(nodes, [edge('A', 'B')])['composition']['synergy'] == 0


def test_mixed_hard_soft_and_synergy_channels_keep_one_row_per_name():
    nodes = [node('A'), node('B', value=1, interest=1)]
    edges = [edge('A', 'B'), edge('A', 'B', 'Needs_Hard'), edge('A', 'B', 'Needs_Soft')]
    bd = explain(nodes, edges)
    rows = {r['name']: r for r in bd['contributors']}
    assert len(rows) == len(bd['contributors']) == 2
    row = rows['B']
    assert row['channels']['Hard'] > 0
    assert row['channels']['Soft'] == 0
    assert row['channels']['Synergy'] > row['channels']['Hard']
    assert row['contribution'] == sum(row['channels'].values())
    focus = focus_route_data('A', bd['contributors'], 3, nodes, edges, PROFILES['Sage'])
    assert focus['edge_rank'] == {('A', 'B', 'Helps'): 1}
    hover = _contributor_hover(row)
    assert 'Reinforces this project' in hover
    assert 'Passes on 53%' in hover  # Ordinary channel only: .6 * q(40).


def test_completed_partner_hover_does_not_claim_to_pass_its_own_value():
    bd = explain([node('A'), node('B', status='Done')], [edge('A', 'B')])
    row = next(r for r in bd['contributors'] if r['name'] == 'B')
    hover = _contributor_hover(row)
    assert 'Finished partner' in hover
    assert 'Passes on' not in hover


def test_partner_exposure_counts_unique_required_work_and_ignores_optional_work():
    nodes = [node('A', 10), node('B', 20), node('C', 30), node('D', 40), node('Optional', 5000)]
    edges = [edge('A', 'B'), edge('A', 'C', 'Needs_Hard'),
             edge('C', 'B', 'Needs_Hard'), edge('D', 'C', 'Needs_Hard'),
             edge('D', 'B', 'Needs_Hard'), edge('Optional', 'B', 'Needs_Soft')]
    bd = explain(nodes, edges)
    row = next(r for r in bd['contributors'] if r['name'] == 'B')
    assert row['synergy_detail']['remaining_hours'] == 90
    nodes[3].status = 'Done'
    updated = explain(nodes, edges)
    row = next(r for r in updated['contributors'] if r['name'] == 'B')
    assert row['synergy_detail']['remaining_hours'] == 50


@pytest.mark.parametrize('profile', PROFILES)
def test_random_fixed_base_completion_added_partners_and_order(profile):
    rng = random.Random(105)
    hp = PROFILES[profile]
    for _ in range(30):
        nodes = [node('A', value=rng.randint(1, 10), interest=rng.randint(1, 10))]
        nodes += [node(f'B{i}', rng.uniform(1, 5000),
                       context=rng.choice(['Mind', 'Body', None]),
                       status=rng.choice(['Open', 'Done'])) for i in range(rng.randint(1, 20))]
        edges = [edge('A', n.name) for n in nodes[1:]]
        before = explain(nodes, edges, profile)
        comp = before['composition']
        assert 0 <= comp['synergy'] <= 2 * hp['d_Syn_mul'] * comp['iv'] + 1e-9
        nodes[1].status = 'Done'
        after = explain(nodes, edges, profile)
        assert after['composition']['synergy'] + 1e-9 >= comp['synergy']
        reordered = explain([nodes[0], *reversed(nodes[1:])], list(reversed(edges)), profile)
        assert reordered == after
        nodes.append(node('Extra', status='Done'))
        added = explain(nodes, edges + [edge('A', 'Extra')], profile)
        assert added['composition']['synergy'] + 1e-9 >= after['composition']['synergy']
        scaled = explain(nodes, edges + [edge('A', 'Extra')], profile,
                         w_v=hp['w_v'] * 3, w_i=hp['w_i'] * 3)
        assert scaled['composition']['total_value'] == pytest.approx(3 * added['composition']['total_value'])


def test_cache_refreshes_after_completion_reopening_work_context_and_edge_changes():
    ConfigManager.set_hp_profile('Creator')
    ConfigManager.set_show_scoring_perf(False)
    manager = GraphManager()
    for n in [node('A'), node('B', context='Body'), node('C', 200, status='Done')]:
        manager.add_node(n)
    manager.add_edge('A', 'B', 'Helps')
    manager.add_edge('C', 'B', 'Needs_Hard')

    def score():
        current = manager.calculate_priority_scores([manager.get_node('A')])[0].total_value
        fresh = GraphManager().calculate_priority_scores([manager.get_node('A')])[0].total_value
        assert current == fresh
        return current

    before = score()
    b = manager.get_node('B'); b.status = 'Done'; manager.update_node(b)
    done = score()
    assert done > before
    b = manager.get_node('B'); b.status = 'Open'; manager.update_node(b)
    assert score() == before
    c = manager.get_node('C'); c.status = 'Open'
    c.time_o = c.time_m = c.time_p = 2000; manager.update_node(c)
    slower = score()
    assert slower < before
    b = manager.get_node('B'); b.context = 'Mind'; manager.update_node(b)
    same_context = score()
    assert same_context < slower
    manager.remove_edge('A', 'B', 'Helps')
    assert score() < same_context


@pytest.mark.parametrize('pair,strength', [(.1, .4), (.7, .2), (.3, 0), (0, 0)])
def test_v5_custom_settings_migrate_without_writing_or_losing_other_preferences(pair, strength):
    raw = json.dumps(dict(_schema=5, d_Syn_pair=pair, d_Syn_mul=strength,
                         w_t=8.7, future_work_half_credit_hours=777))
    ConfigManager._set_db_value('HYPERPARAMS', raw)
    hp = ConfigManager.get_hyperparams()
    assert hp['d_Syn_pair'] == pair
    assert hp['d_Syn_mul'] == max(pair, strength)
    assert hp['w_t'] == 8.7
    assert hp['future_work_half_credit_hours'] == 777
    assert ConfigManager._get_db_value('HYPERPARAMS') == raw
    ConfigManager.set_hyperparams(hp)
    stored = json.loads(ConfigManager._get_db_value('HYPERPARAMS'))
    assert stored['_schema'] == HYPERPARAMS_SCHEMA_VERSION == 6
    assert ConfigManager.get_hyperparams() == hp


def test_partial_override_uses_the_selected_profile_when_normalizing():
    ConfigManager.set_hp_profile('Creator')
    ConfigManager.set_hyperparams({'d_Syn_pair': .9})
    assert ConfigManager.get_hyperparams()['d_Syn_mul'] == 1.3
    ConfigManager.set_hyperparams({'d_Syn_pair': 2})
    assert ConfigManager.get_hyperparams()['d_Syn_mul'] == 2


@pytest.mark.parametrize('key', ['d_Syn_pair', 'd_Syn_mul', 'cross_context_mult'])
@pytest.mark.parametrize('bad', [-1, float('nan'), float('inf'), 'broken', None])
def test_invalid_synergy_override_is_rejected_before_writing(key, bad):
    before = ConfigManager._get_db_value('HYPERPARAMS')
    with pytest.raises(ValueError, match='finite nonnegative'):
        ConfigManager.set_hyperparams({key: bad})
    assert ConfigManager._get_db_value('HYPERPARAMS') == before


def test_exposure_boundary_and_numerical_stability():
    assert synergy_parameters(.8, .2) == (.8, 1, 1)
    assert synergy_parameters(0, 0) == (0, 0, 1)
    assert partner_exposure(1, 0, .5) == 0
    assert partner_exposure(1, 2, .5) == .5
    assert partner_exposure(0, 2, .5) == 0
    assert partner_exposure(.25, 1e300, .5) == .5
    assert partner_exposure(1e-20, 1, .5) == pytest.approx(5e-21, abs=0, rel=1e-12)
