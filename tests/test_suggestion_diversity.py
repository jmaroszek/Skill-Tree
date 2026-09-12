"""Behavioral contracts for hierarchical suggestion variety."""
from types import SimpleNamespace
import json
import pytest

from config import ConfigManager, PROFILES
from models import Node
from scoring import score_nodes, variety_divisors

SAGE = PROFILES['Sage']


def entry(name, merit=100, context='Science', subcontext='Biology'):
    return (name, context, subcontext, merit)


def order(pool, hyperparams=SAGE):
    """Names in the order the variety walk selected them."""
    return list(variety_divisors(pool, hyperparams))


def _node(name, **kw):
    defaults = dict(name=name, type="Learn", description="", value=5,
                    time_o=1.0, time_m=2.0, time_p=4.0, interest=5,
                    difficulty=5, status="Open", context="Science",
                    subcontext="Biology")
    defaults.update(kw)
    return Node(**defaults)


# ---------------------------------------------------------------------------
# The premium curve
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('previous,subcontext,threshold', [
    (1, 'Computers', 105), (1, 'Biology', 115),
    (3, 'Computers', 110.25), (3, 'Biology', 132.25),
])
def test_premiums_are_total_and_accumulate(previous, subcontext, threshold):
    """The subcontext premium includes the context one, and both compound."""
    taken = [entry(str(i), 1000) for i in range(previous)]
    outsider = entry('Outside', context='Art')
    for offset, expected in [(-.001, 'Outside'), (.001, 'Repeat')]:
        repeat = entry('Repeat', threshold + offset, subcontext=subcontext)
        assert order(taken + [repeat, outsider])[previous] == expected


def test_zero_premiums_leave_merit_alone():
    pool = [entry('Low', 1), entry('High', 2)]
    assert variety_divisors(pool, PROFILES['Compounder']) == {}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_selection_is_independent_of_input_order():
    pool = [entry(str(i), 100 - i / 10, context=str(i % 3), subcontext=str(i % 5))
            for i in range(30)]
    assert order(list(reversed(pool))) == order(pool)
    assert len(set(order(pool))) == 30


def test_ties_break_on_merit_then_name():
    # Rounding collapses these two, so only the exact merit separates them.
    assert order([entry('Lower', 1.001), entry('Higher', 1.002)])[0] == 'Higher'
    assert order([entry('Z'), entry('A')])[0] == 'A'


def test_buckets_are_identified_by_the_pair_not_the_label():
    """'Biology' under Art is not a repetition of 'Biology' under Science."""
    taken = entry('Taken', 1000)
    art = entry('Art', context='Art')
    sibling = entry('Sibling', 104, subcontext='Computers')  # needs > 105
    assert order([taken, sibling, art])[1] == 'Art'

    # A node with no subcontext sits in its own bucket under its context,
    # and repeats against other broad nodes there.
    broad_taken = entry('Broad taken', 1000, subcontext=None)
    broad = entry('Broad', 114, subcontext=None)  # needs > 115
    assert order([broad_taken, broad, art])[1] == 'Art'


# ---------------------------------------------------------------------------
# Variety is part of the score, not of a list
# ---------------------------------------------------------------------------

def test_scores_do_not_depend_on_which_nodes_were_scored():
    """A filtered view must not change any node's number."""
    nodes = [_node('A', value=9), _node('B', value=7), _node('C', value=5),
             _node('D', value=8, context='Art')]
    hp = {**SAGE, 'context_weights': {}}
    whole = {n.name: n.priority_score for n in score_nodes(nodes, nodes, [], hp)}
    for node in nodes:
        alone = score_nodes([node], nodes, [], hp)[0]
        assert alone.priority_score == whole[node.name]
    # ... and the second Science node really is discounted, wherever it
    # was scored from.
    scored = {n.name: n for n in score_nodes(nodes, nodes, [], hp)}
    assert scored['A'].variety['divisor'] == 1.0
    assert scored['B'].variety['divisor'] > 1.0


def test_ranked_scores_never_ascend():
    nodes = [_node(str(i), value=(i % 9) + 1, interest=(i % 7) + 1,
                   context=str(i % 3), subcontext=str(i % 5)) for i in range(40)]
    scores = [n.priority_score for n in score_nodes(nodes, nodes, [], SAGE)
              if n.priority_score >= 0]
    assert scores == sorted(scores, reverse=True)


def test_now_nodes_neither_earn_nor_spend_a_repetition():
    """Now nodes have their own Next-tab section and sit outside the pool."""
    nodes = [_node('Busy', value=9, now=1), _node('Next', value=7)]
    scored = {n.name: n for n in score_nodes(nodes, nodes, [], SAGE)}
    assert scored['Busy'].variety is None
    assert scored['Next'].variety['divisor'] == 1.0


# ---------------------------------------------------------------------------
# Next-tab tiering
# ---------------------------------------------------------------------------

def test_pins_lead_the_list_and_now_nodes_are_dropped(monkeypatch):
    import next_callbacks
    pin = SimpleNamespace(name='Pin', priority_score=1, now=0)
    repeat = SimpleNamespace(name='Repeat', priority_score=110, now=0)
    outsider = SimpleNamespace(name='Outside', priority_score=100, now=0)
    now = SimpleNamespace(name='Now', priority_score=1000, now=1)
    manager = SimpleNamespace(
        get_all_nodes=lambda: [pin, repeat, outsider, now],
        filter_nodes=lambda nodes, filters: [n for n in nodes if n.name != 'Pin'],
        calculate_priority_scores=lambda nodes, **kw: sorted(
            nodes, key=lambda n: -n.priority_score),
    )
    monkeypatch.setattr(next_callbacks, 'manager', manager)
    monkeypatch.setattr(ConfigManager, 'get_override_node_set', lambda manager: {'Pin'})
    assert [n.name for n in next_callbacks.get_suggestions(count=3)] == \
        ['Pin', 'Repeat', 'Outside']
    assert [n.name for n in next_callbacks.get_suggestions(count=1)] == ['Pin']


# ---------------------------------------------------------------------------
# Settings migration
# ---------------------------------------------------------------------------

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


@pytest.mark.parametrize('old,new', [('Curious','Explorer'), ('Sprinter','Glider'), ('Industrious','Pragmatist')])
def test_legacy_profile_alias_migrates_without_write(old, new):
    ConfigManager._set_db_value('HP_PROFILE', old)
    ConfigManager._set_db_value('HYPERPARAMS', json.dumps({'_schema': 3}))
    hp = ConfigManager.get_hyperparams()
    assert hp['suggestion_context_premium'] == PROFILES[new]['suggestion_context_premium']
    assert hp['suggestion_subcontext_premium'] == PROFILES[new]['suggestion_subcontext_premium']
    assert ConfigManager._get_db_value('HP_PROFILE') == old
