"""Tests for explain_score — the per-node score decomposition.

Key invariant: the contributor list must sum exactly to the TotalValue
that score_nodes would compute (modulo float rounding). Everything else
is display metadata derived from the same weights.
"""

import math
import pytest

from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from scoring import (explain_score, total_value, build_adjacency,
                     focus_route_data)


def _node(name, **kw):
    defaults = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


HYPERS = {
    'w_v': 1.0, 'w_i': 1.0,
    'd_H': 0.6, 'd_S': 0.25,
    'd_Syn_pair': 0.10, 'd_Syn_mul': 0.40,
    'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85,
    'goal_boost': 1.5,
}


def _tv(name, nodes, edges):
    """Ground-truth TotalValue via the core scoring function."""
    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))
    return total_value(
        name, set(), all_nodes_dict, H_out, S_out, Syn,
        HYPERS['w_v'], HYPERS['w_i'], HYPERS['d_H'], HYPERS['d_S'],
        HYPERS['d_Syn_pair'], HYPERS['d_Syn_mul'],
        memo={},
    )


# ---------------------------------------------------------------------------
# Sum identity — the core correctness guarantee
# ---------------------------------------------------------------------------

def test_contributors_sum_equals_total_value_simple_chain():
    """S → A → B (all Hard). Contributions sum to TV(S)."""
    nodes = [_node("S", value=10, interest=8), _node("A", value=7, interest=6),
             _node("B", value=5, interest=4)]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)

    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    tv_truth = _tv("S", nodes, edges)
    assert math.isclose(contributed, tv_truth, rel_tol=1e-9)
    assert math.isclose(breakdown['composition']['total_value'], tv_truth, rel_tol=1e-9)


def test_known_weights_grandchild_hard_chain():
    """W(grandchild) along a pure-Hard chain = d_H²; contribution = W · IV."""
    nodes = [_node("S", value=10), _node("A"), _node("B", value=10)]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}

    iv_b = by_name['B']['iv']
    assert math.isclose(by_name['B']['weight'], HYPERS['d_H'] ** 2, rel_tol=1e-9)
    assert math.isclose(
        by_name['B']['contribution'], (HYPERS['d_H'] ** 2) * iv_b, rel_tol=1e-9,
    )
    assert by_name['B']['depth'] == 2
    assert by_name['B']['via'] == 'Hard'


def test_diamond_counts_beneficiary_once():
    """S→A→D and S→B→D — W(D) = 2 * d_H²."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("D", value=10, interest=0)]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "S", "target": "B", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "D", "type": EDGE_NEEDS_HARD},
        {"source": "B", "target": "D", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['D']['weight'], HYPERS['d_H'] ** 2, rel_tol=1e-9)

    # Sum identity still holds
    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    assert math.isclose(contributed, _tv("S", nodes, edges), rel_tol=1e-9)


def test_synergy_seed_weight_and_via():
    """Pure synergy neighbor: W(z) = d_Syn_pair (additive bonus), via='Synergy', depth=1.

    The multiplicative kick on intrinsic is *not* a per-contributor weight — it
    only fires when partners are Done, and is tracked separately in
    `composition['iv_multiplier_contribution']`. With Z status='Open' the
    contributor sum equals TV(S) on its own.
    """
    nodes = [_node("S"), _node("Z", value=10, interest=0)]
    edges = [{"source": "S", "target": "Z", "type": EDGE_HELPS}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['Z']['weight'], HYPERS['d_Syn_pair'], rel_tol=1e-9)
    assert by_name['Z']['depth'] == 1
    assert by_name['Z']['via'] == 'Synergy'

    # Z is Open, so the multiplicative kick is inactive (multiplier == 1.0).
    assert math.isclose(breakdown['composition']['iv_multiplier'], 1.0)
    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    assert math.isclose(contributed, _tv("S", nodes, edges), rel_tol=1e-9)


def test_soft_edge_contribution():
    """W(target) across a Soft edge = d_S."""
    nodes = [_node("S"), _node("T", value=8, interest=2)]
    edges = [{"source": "S", "target": "T", "type": EDGE_NEEDS_SOFT}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['T']['weight'], HYPERS['d_S'], rel_tol=1e-9)
    assert by_name['T']['via'] == 'Soft'


def test_syn_then_hard_cascade():
    """S synergy→Z, Z hard→D. W(D) = d_Syn_pair * d_H."""
    nodes = [_node("S"), _node("Z"), _node("D", value=10, interest=0)]
    edges = [
        {"source": "S", "target": "Z", "type": EDGE_HELPS},
        {"source": "Z", "target": "D", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['D']['weight'], HYPERS['d_Syn_pair'] * HYPERS['d_H'], rel_tol=1e-9)
    # via is propagated from Z, which itself was via='Synergy'
    assert by_name['D']['via'] == 'Synergy'
    assert by_name['D']['depth'] == 2


# ---------------------------------------------------------------------------
# Composition bucketing
# ---------------------------------------------------------------------------

def test_composition_buckets_sum_to_tv():
    """iv + hard + soft + synergy must equal total_value in composition dict."""
    nodes = [
        _node("S", value=10, interest=5),
        _node("H", value=6, interest=0),
        _node("So", value=4, interest=0),
        _node("Sy", value=8, interest=0),
    ]
    edges = [
        {"source": "S", "target": "H", "type": EDGE_NEEDS_HARD},
        {"source": "S", "target": "So", "type": EDGE_NEEDS_SOFT},
        {"source": "S", "target": "Sy", "type": EDGE_HELPS},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    comp = breakdown['composition']
    assert math.isclose(
        comp['iv'] + comp['hard_cascade'] + comp['soft_cascade'] + comp['synergy'],
        comp['total_value'],
        rel_tol=1e-9,
    )


# ---------------------------------------------------------------------------
# Ineligibility paths
# ---------------------------------------------------------------------------

def test_blocked_status_marks_ineligible_but_keeps_breakdown():
    nodes = [_node("S", status="Blocked", value=10, interest=5)]
    breakdown = explain_score("S", nodes, [], HYPERS)
    assert breakdown['eligible'] is False
    assert breakdown['block_reason'] == "Blocked"
    assert breakdown['score'] == -1.0
    # IV/Cost/TV still computed
    assert breakdown['intrinsic']['iv'] > 0
    assert breakdown['composition']['total_value'] > 0


def test_goal_node_reports_reason():
    nodes = [_node("G", type="Goal", value=10, interest=5)]
    breakdown = explain_score("G", nodes, [], HYPERS)
    assert breakdown['eligible'] is False
    assert breakdown['block_reason'] == "Goals are not ranked"


def test_milestone_node_reports_reason():
    nodes = [_node("M", type="Milestone", value=10, interest=5)]
    breakdown = explain_score("M", nodes, [], HYPERS)
    assert breakdown['eligible'] is False
    assert breakdown['block_reason'] == "Milestones are not ranked"


def test_container_node_reports_reason():
    """A node with both modes inherited is a pure container — explain_score
    surfaces it as ineligible with a dedicated reason so the user sees why
    they aren't getting a score (and the children rank instead)."""
    nodes = [_node("C", value_mode="inherited", time_mode="inherited")]
    breakdown = explain_score("C", nodes, [], HYPERS)
    assert breakdown['eligible'] is False
    assert breakdown['block_reason'] == "Its children are recommended instead"
    assert breakdown['score'] == -1.0


def test_missing_hard_prereqs_are_listed():
    nodes = [
        _node("S"),
        _node("P1", status="Open"),
        _node("P2", status="Done"),
    ]
    edges = [
        {"source": "P1", "target": "S", "type": EDGE_NEEDS_HARD},
        {"source": "P2", "target": "S", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    assert breakdown['eligible'] is False
    assert breakdown['block_reason'] == "Waiting on P1"


def test_all_prereqs_done_is_eligible():
    nodes = [
        _node("S", value=10, interest=5),
        _node("P1", status="Done"),
    ]
    edges = [{"source": "P1", "target": "S", "type": EDGE_NEEDS_HARD}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    assert breakdown['eligible'] is True
    assert breakdown['block_reason'] is None
    assert breakdown['score'] > 0


# ---------------------------------------------------------------------------
# Goal boost + self entry
# ---------------------------------------------------------------------------

def test_goal_boost_applied_when_in_priority_subtree():
    nodes = [
        _node("S", value=10, interest=0),
        _node("G", type="Goal", value=1, interest=1),
    ]
    edges = [{"source": "S", "target": "G", "type": EDGE_NEEDS_HARD}]
    breakdown = explain_score("S", nodes, edges, HYPERS, priority_goals=["G"])
    assert breakdown['goal_boost'] is not None
    assert breakdown['goal_boost']['goal'] == "G"
    assert breakdown['goal_boost']['rank'] == 1
    assert math.isclose(breakdown['goal_boost']['multiplier'], HYPERS['goal_boost'])
    assert breakdown['score'] > breakdown['raw_score']


def test_self_contributor_always_present_and_labeled():
    nodes = [_node("S", value=7, interest=3)]
    breakdown = explain_score("S", nodes, [], HYPERS)
    self_entries = [c for c in breakdown['contributors'] if c['name'] == "S"]
    assert len(self_entries) == 1
    self_c = self_entries[0]
    assert self_c['depth'] == 0
    assert self_c['via'] == 'Self'
    assert math.isclose(self_c['weight'], 1.0)


def test_returns_none_for_unknown_node():
    assert explain_score("ghost", [], [], HYPERS) is None


def test_inherited_time_cost_uses_zero_override():
    """A time_mode='inherited' node is a container — its marginal time is 0.

    The cost still picks up the base 1.0 plus difficulty contribution, so the
    denominator stays positive. Compare against the legacy behavior (time=1.0)
    that mistakenly added a phantom unit of cost across inherited chains.
    """
    nodes = [_node("S", time_mode='inherited', difficulty=4)]
    breakdown = explain_score("S", nodes, [], HYPERS)
    assert breakdown['cost']['time_overridden'] is True
    assert breakdown['cost']['time'] == 0.0
    # cost = 1 + 4*2.5 + 0^0.85 * 1.0 = 1 + 10 + 0 = 11
    assert math.isclose(breakdown['cost']['cost'], 11.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# focus_route_data — distinct value routes for canvas highlighting
# ---------------------------------------------------------------------------

def _row(name, contribution=1.0, via='Hard'):
    """A contributor row with just the fields focus_route_data reads."""
    return {'name': name, 'contribution': contribution, 'via': via}


def _hard(source, target):
    return {"source": source, "target": target, "type": EDGE_NEEDS_HARD}


def test_focus_contributor_past_a_route_end_extends_that_route():
    """S → A → B. B lies past A, so tracing both draws one route, not two."""
    nodes = [_node("S"), _node("A"), _node("B")]
    edges = [_hard("S", "A"), _hard("A", "B")]
    pi = focus_route_data("S", [_row("A", 3.0), _row("B", 2.0)], 3,
                          nodes, edges, HYPERS)
    assert pi['node_rank'] == {"S": 1, "A": 1, "B": 1}
    assert pi['edge_rank'] == {("S", "A", EDGE_NEEDS_HARD): 1,
                               ("A", "B", EDGE_NEEDS_HARD): 1}
    assert pi['target_labels'] == {"A": "#1"}


def test_focus_contributor_already_on_a_route_adds_nothing():
    """B ranks above A but A sits on B's route, so A is already drawn."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("C")]
    edges = [_hard("S", "A"), _hard("A", "B"), _hard("S", "C")]
    pi = focus_route_data("S", [_row("B", 3.0), _row("A", 2.0), _row("C", 1.0)], 2,
                          nodes, edges, HYPERS)
    assert pi['target_labels'] == {"B": "#1", "C": "#2"}
    assert pi['node_rank'] == {"S": 1, "A": 1, "B": 1, "C": 2}


def test_focus_branch_off_a_route_middle_starts_a_new_route():
    """S → A → B and A → C. C leaves route 1 at A, which isn't its end."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("C")]
    edges = [_hard("S", "A"), _hard("A", "B"), _hard("A", "C")]
    contributors = [_row("A", 3.0), _row("B", 2.0), _row("C", 1.0)]
    pi = focus_route_data("S", contributors, 2, nodes, edges, HYPERS)
    assert pi['node_rank'] == {"S": 1, "A": 1, "B": 1, "C": 2}
    assert pi['edge_rank'] == {("S", "A", EDGE_NEEDS_HARD): 1,
                               ("A", "B", EDGE_NEEDS_HARD): 1,
                               ("A", "C", EDGE_NEEDS_HARD): 2}
    assert pi['target_labels'] == {"A": "#1", "C": "#2"}


def test_focus_stops_once_k_routes_are_drawn():
    """Three separate branches, two routes asked for: the third is left out."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("C")]
    edges = [_hard("S", "A"), _hard("S", "B"), _hard("S", "C")]
    contributors = [_row("A", 3.0), _row("B", 2.0), _row("C", 1.0)]
    pi = focus_route_data("S", contributors, 2, nodes, edges, HYPERS)
    assert pi['target_labels'] == {"A": "#1", "B": "#2"}
    assert "C" not in pi['node_rank']


def test_focus_follows_the_strongest_route_not_the_fewest_hops():
    """Three Hard hops (0.6³ = 0.216) outweigh two Soft hops (0.25² = 0.0625).

    The score credits T through P and Q, so that is the route drawn, even
    though the Soft route through Y is shorter.
    """
    nodes = [_node(n) for n in ("S", "Y", "P", "Q", "T")]
    edges = [
        {"source": "S", "target": "Y", "type": EDGE_NEEDS_SOFT},
        {"source": "Y", "target": "T", "type": EDGE_NEEDS_SOFT},
        _hard("S", "P"), _hard("P", "Q"), _hard("Q", "T"),
    ]
    pi = focus_route_data("S", [_row("T")], 1, nodes, edges, HYPERS)
    assert set(pi['node_rank']) == {"S", "P", "Q", "T"}
    assert set(pi['edge_rank']) == {("S", "P", EDGE_NEEDS_HARD),
                                    ("P", "Q", EDGE_NEEDS_HARD),
                                    ("Q", "T", EDGE_NEEDS_HARD)}


def test_focus_synergy_route_uses_the_stored_helps_edge():
    """Z helps S (stored Z → S) and unlocks T. T's credit arrives through Z."""
    nodes = [_node("S"), _node("Z"), _node("T")]
    edges = [
        {"source": "Z", "target": "S", "type": EDGE_HELPS},
        _hard("Z", "T"),
    ]
    contributors = explain_score("S", nodes, edges, HYPERS)['contributors']
    pi = focus_route_data("S", contributors, 3, nodes, edges, HYPERS)
    assert pi['edge_rank'] == {("Z", "S", EDGE_HELPS): 1,
                               ("Z", "T", EDGE_NEEDS_HARD): 1}
    assert pi['target_labels'] == {"Z": "#1"}


def test_focus_skips_contributors_that_contribute_nothing():
    """A zero-value node (a Milestone, say) isn't a contributor worth tracing."""
    nodes = [_node("S"), _node("M"), _node("A")]
    edges = [_hard("S", "M"), _hard("S", "A")]
    pi = focus_route_data("S", [_row("A", 1.0), _row("M", 0.0)], 3,
                          nodes, edges, HYPERS)
    assert "M" not in pi['node_rank']
    assert pi['target_labels'] == {"A": "#1"}


def test_focus_source_alone_and_self_row_ignored():
    """Only the node itself contributes: the source is lit, nothing else."""
    nodes = [_node("S"), _node("A")]
    pi = focus_route_data("S", [_row("S", 10.0, via='Self')], 3,
                          nodes, [_hard("S", "A")], HYPERS)
    assert pi == {'subtree': ["S"], 'node_rank': {"S": 1},
                  'edge_rank': {}, 'target_labels': {}}


def test_focus_missing_source_returns_empty():
    """Source not in all_nodes → empty return, no crash."""
    pi = focus_route_data("ghost", [_row("anything")], 3, [], [], HYPERS)
    assert pi == {'subtree': [], 'node_rank': {},
                  'edge_rank': {}, 'target_labels': {}}


# ---------------------------------------------------------------------------
# M3 hybrid synergy — pair bonus + completion multiplier
# ---------------------------------------------------------------------------

def test_m3_synergy_partner_open_no_multiplier():
    """Synergy partner is Open: pair bonus active, multiplier dormant."""
    s = _node("S", value=10, interest=2)
    z = _node("Z", value=8, interest=4, status="Open")
    nodes = [s, z]
    edges = [{"source": "S", "target": "Z", "type": EDGE_HELPS}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    comp = breakdown['composition']

    # Multiplier neutral → contribution to TV is 0
    assert math.isclose(comp['iv_multiplier'], 1.0)
    assert math.isclose(comp['iv_multiplier_contribution'], 0.0)
    assert comp['done_synergy_count'] == 0

    # Pair bonus shows up in the synergy bucket
    from scoring import intrinsic_value
    iv_z = intrinsic_value(z, HYPERS['w_v'], HYPERS['w_i'])
    expected_pair_bonus = HYPERS['d_Syn_pair'] * iv_z
    assert math.isclose(comp['synergy'], expected_pair_bonus, rel_tol=1e-9)


def test_m3_synergy_partner_done_multiplies_intrinsic():
    """One Done synergy partner: iv_multiplier = 1 + d_Syn_mul."""
    s = _node("S", value=10, interest=2)
    z = _node("Z", value=8, interest=4, status="Done")
    nodes = [s, z]
    edges = [{"source": "S", "target": "Z", "type": EDGE_HELPS}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    comp = breakdown['composition']

    expected_multiplier = 1.0 + HYPERS['d_Syn_mul']
    assert math.isclose(comp['iv_multiplier'], expected_multiplier, rel_tol=1e-9)
    assert comp['done_synergy_count'] == 1

    from scoring import intrinsic_value
    iv_s = intrinsic_value(s, HYPERS['w_v'], HYPERS['w_i'])
    expected_kick = iv_s * HYPERS['d_Syn_mul']
    assert math.isclose(comp['iv_multiplier_contribution'], expected_kick, rel_tol=1e-9)

    # Total TV includes additive contributors AND the multiplicative kick
    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    expected_tv = contributed + comp['iv_multiplier_contribution']
    assert math.isclose(comp['total_value'], expected_tv, rel_tol=1e-9)
    # Cross-check against ground truth
    assert math.isclose(comp['total_value'], _tv("S", nodes, edges), rel_tol=1e-9)


def test_m3_two_done_synergy_partners_accumulate_sublinearly():
    """Two Done synergy partners: multiplier = 1 + sqrt(2) * d_Syn_mul.

    Sub-linear (sqrt) accumulation prevents dense synergy hubs from running
    away. With 2 partners the kick is sqrt(2)≈1.414× the single-partner
    value, not 2× (which would let an N-partner hub get N× boost). 1
    partner still gives exactly d_Syn_mul (sqrt(1)=1), preserving simple
    cases.
    """
    import math
    nodes = [_node("S", value=10, interest=0),
             _node("Z1", value=4, interest=0, status="Done"),
             _node("Z2", value=4, interest=0, status="Done")]
    edges = [
        {"source": "S", "target": "Z1", "type": EDGE_HELPS},
        {"source": "S", "target": "Z2", "type": EDGE_HELPS},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    comp = breakdown['composition']

    expected_multiplier = 1.0 + math.sqrt(2) * HYPERS['d_Syn_mul']
    assert math.isclose(comp['iv_multiplier'], expected_multiplier, rel_tol=1e-9)
    assert comp['done_synergy_count'] == 2


def test_m3_pure_dag_node_unaffected_by_synergy_params():
    """A node with no synergy edges: multiplier == 1, no synergy contribution.

    Score should be identical regardless of the d_Syn_pair / d_Syn_mul values.
    """
    nodes = [_node("S", value=10), _node("A", value=8), _node("B", value=6)]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
    ]
    breakdown_default = explain_score("S", nodes, edges, HYPERS)
    bizarre_hp = dict(HYPERS, d_Syn_pair=0.99, d_Syn_mul=10.0)
    breakdown_bizarre = explain_score("S", nodes, edges, bizarre_hp)

    assert math.isclose(
        breakdown_default['composition']['total_value'],
        breakdown_bizarre['composition']['total_value'],
        rel_tol=1e-9,
    )
    assert breakdown_default['composition']['iv_multiplier'] == 1.0
    assert breakdown_bizarre['composition']['iv_multiplier'] == 1.0


def test_m3_multiplier_does_not_amplify_cascade():
    """The multiplier applies to intrinsic only, not to Hard/Soft cascade.

    S has a Done synergy partner Z and a Hard prereq P. The Hard cascade
    contribution P → S is unaffected by the multiplier; only S's intrinsic
    value is amplified.
    """
    s = _node("S", value=10, interest=2)
    p = _node("P", value=8, interest=6, status="Open")
    z = _node("Z", value=4, interest=3, status="Done")
    nodes = [s, p, z]
    edges = [
        {"source": "S", "target": "P", "type": EDGE_NEEDS_HARD},
        {"source": "S", "target": "Z", "type": EDGE_HELPS},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    comp = breakdown['composition']

    from scoring import intrinsic_value
    iv_s = intrinsic_value(s, HYPERS['w_v'], HYPERS['w_i'])
    iv_p = intrinsic_value(p, HYPERS['w_v'], HYPERS['w_i'])
    iv_z = intrinsic_value(z, HYPERS['w_v'], HYPERS['w_i'])

    # cascade is d_H * iv_p (unscaled — multiplier doesn't touch it)
    assert math.isclose(comp['hard_cascade'], HYPERS['d_H'] * iv_p, rel_tol=1e-9)
    # additive synergy bonus is d_Syn_pair * iv_z (unscaled)
    assert math.isclose(comp['synergy'], HYPERS['d_Syn_pair'] * iv_z, rel_tol=1e-9)
    # multiplier kick is iv_s * d_Syn_mul — applies to intrinsic only
    assert math.isclose(comp['iv_multiplier_contribution'],
                        iv_s * HYPERS['d_Syn_mul'], rel_tol=1e-9)
