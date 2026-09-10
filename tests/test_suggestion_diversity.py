"""Behavioral contracts for hierarchical suggestion selection."""
from types import SimpleNamespace
import json
import pytest

from callback_helpers import assemble_suggestions
from config import ConfigManager, PROFILES


def node(name, merit=100, context='Science', subcontext='Biology'):
    return SimpleNamespace(name=name, priority_score=round(merit, 2),
                           priority_score_exact=merit, context=context, subcontext=subcontext)


@pytest.mark.parametrize('previous,subcontext,threshold', [
    (1, 'Computers', 105), (1, 'Biology', 115),
    (3, 'Computers', 110.25), (3, 'Biology', 132.25),
])
def test_premiums_are_total_and_accumulate(previous, subcontext, threshold):
    pins = [node(str(i)) for i in range(previous)]
    outsider = node('Outside', context='Art')
    for offset, expected in [(-.001, 'Outside'), (.001, 'Repeat')]:
        repeat = node('Repeat', threshold + offset, subcontext=subcontext)
        assert assemble_suggestions([repeat, outsider], 1, PROFILES['Sage'], pins)[0].name == expected


def test_prefix_stability_ties_and_merit_are_preserved():
    nodes = [node(str(i), 100 - i / 10, context=str(i % 3), subcontext=str(i % 5)) for i in range(30)]
    before = [vars(n).copy() for n in nodes]
    full = assemble_suggestions(nodes, 30, PROFILES['Sage'])
    assert assemble_suggestions(list(reversed(nodes)), 10, PROFILES['Sage']) == full[:10]
    assert before == [vars(n) for n in nodes]
    assert assemble_suggestions(nodes, 0, PROFILES['Sage']) == []
    assert len({n.name for n in full}) == 30
    tied = [node('Z'), node('A')]
    assert assemble_suggestions(tied, 1, PROFILES['Sage'])[0].name == 'A'


def test_exact_merit_and_disabled_profile():
    nodes = [node('Lower', 1.001), node('Higher', 1.002)]
    assert nodes[0].priority_score == nodes[1].priority_score
    assert assemble_suggestions(nodes, 2, PROFILES['Compounder'], [node('Pin')])[0].name == 'Higher'


def test_bucket_identity_and_unselected_inventory():
    pin = node('Pin')
    other = node('Other', context='Art')  # Same subcontext label, distinct bucket.
    sibling = node('Sibling', 104, subcontext='Computers')
    low = [node(str(i), .1, context='Art') for i in range(100)]
    assert assemble_suggestions([sibling, other] + low, 1, PROFILES['Sage'], [pin]) == [other]
    broad = node('Broad', 114, subcontext=None)
    assert assemble_suggestions([broad, other], 1, PROFILES['Sage'], [node('Broad pin', subcontext=None)]) == [other]


@pytest.mark.parametrize('profile', list(PROFILES) + ['Custom'])
def test_migration_uses_named_profile_without_writing(profile):
    raw = json.dumps(dict(_schema=3, alpha=.8, alpha_goal=.42, w_t=6,
                          future_work_half_credit_hours=444, future_work_exponent=.7))
    ConfigManager._set_db_value('HYPERPARAMS', raw)
    ConfigManager._set_db_value('HP_PROFILE', profile)
    hp = ConfigManager.get_hyperparams()
    assert 'alpha' not in hp
    expected = PROFILES.get(profile, PROFILES['Sage'])
    for key in ('suggestion_context_premium', 'suggestion_subcontext_premium'):
        assert hp[key] == expected[key]
    assert (hp['alpha_goal'], hp['w_t'], hp['future_work_half_credit_hours'], hp['future_work_exponent']) == (.42, 6, 444, .7)
    assert ConfigManager._get_db_value('HYPERPARAMS') == raw
    ConfigManager.set_hyperparams(hp)
    assert ConfigManager.get_hyperparams() == hp


def test_next_pins_seed_selection_and_excluded_pins_do_not(monkeypatch):
    import next_callbacks
    pins = [node('Pin', 1)]
    repeat = node('Repeat', 110)
    outsider = node('Outside', context='Art')
    now = node('Now', 1000)
    for n in pins + [repeat, outsider, now]: n.now = n is now
    manager = SimpleNamespace(
        get_all_nodes=lambda: pins + [repeat, outsider, now],
        filter_nodes=lambda nodes, filters: [n for n in nodes if n.name != 'Pin'],
        calculate_priority_scores=lambda nodes, **kwargs: sorted(nodes, key=lambda n: -n.priority_score_exact),
    )
    monkeypatch.setattr(next_callbacks, 'manager', manager)
    monkeypatch.setattr(ConfigManager, 'get_override_node_set', lambda manager: {'Pin'})
    assert [n.name for n in next_callbacks.get_suggestions(count=2)] == ['Pin', 'Outside']
    assert [n.name for n in next_callbacks.get_suggestions(count=1)] == ['Pin']
    assert [n.name for n in next_callbacks.get_suggestions(count=1, exclude_override=True)] == ['Repeat']


@pytest.mark.parametrize('old,new', [('Curious','Explorer'), ('Sprinter','Glider'), ('Industrious','Pragmatist')])
def test_legacy_profile_alias_migrates_without_write(old, new):
    ConfigManager._set_db_value('HP_PROFILE', old)
    ConfigManager._set_db_value('HYPERPARAMS', json.dumps({'_schema': 3}))
    hp = ConfigManager.get_hyperparams()
    assert hp['suggestion_context_premium'] == PROFILES[new]['suggestion_context_premium']
    assert hp['suggestion_subcontext_premium'] == PROFILES[new]['suggestion_subcontext_premium']
    assert ConfigManager._get_db_value('HP_PROFILE') == old
