"""Tests for explain_score — the per-node score decomposition.

Key invariant: the contributor list must sum exactly to the TotalValue
that score_nodes would compute (modulo float rounding). Everything else
is display metadata derived from the same weights.
"""

import math
import pytest

from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from scoring import (explain_score, total_value, build_adjacency,
                     shortest_paths_focus_data)


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
    'd_H': 0.6, 'd_S': 0.25, 'd_Syn': 0.35,
    'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85,
    'goal_boost': 1.5,
}


def _tv(name, nodes, edges):
    """Ground-truth TotalValue via the core scoring function."""
    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))
    return total_value(
        name, set(), all_nodes_dict, H_out, S_out, Syn,
        HYPERS['w_v'], HYPERS['w_i'], HYPERS['d_H'], HYPERS['d_S'], HYPERS['d_Syn'],
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


def test_diamond_paths_sum_both_weights():
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
    assert math.isclose(by_name['D']['weight'], 2 * HYPERS['d_H'] ** 2, rel_tol=1e-9)

    # Sum identity still holds
    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    assert math.isclose(contributed, _tv("S", nodes, edges), rel_tol=1e-9)


def test_synergy_seed_weight_and_via():
    """Pure synergy neighbor: W(z) = d_Syn, via='Synergy', depth=1."""
    nodes = [_node("S"), _node("Z", value=10, interest=0)]
    edges = [{"source": "S", "target": "Z", "type": EDGE_HELPS}]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['Z']['weight'], HYPERS['d_Syn'], rel_tol=1e-9)
    assert by_name['Z']['depth'] == 1
    assert by_name['Z']['via'] == 'Synergy'

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
    """S synergy→Z, Z hard→D. W(D) = d_Syn * d_H."""
    nodes = [_node("S"), _node("Z"), _node("D", value=10, interest=0)]
    edges = [
        {"source": "S", "target": "Z", "type": EDGE_HELPS},
        {"source": "Z", "target": "D", "type": EDGE_NEEDS_HARD},
    ]
    breakdown = explain_score("S", nodes, edges, HYPERS)
    by_name = {c['name']: c for c in breakdown['contributors']}
    assert math.isclose(by_name['D']['weight'], HYPERS['d_Syn'] * HYPERS['d_H'], rel_tol=1e-9)
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
    assert breakdown['block_reason'] == "Missing prereqs: P1"


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


def test_inherited_time_cost_uses_override():
    """A time_mode='inherited' node must compute cost with time=1.0."""
    nodes = [_node("S", time_mode='inherited', difficulty=4)]
    breakdown = explain_score("S", nodes, [], HYPERS)
    assert breakdown['cost']['time_overridden'] is True
    # cost = 1 + 4*2.5 + 1^0.85 * 1.0 = 1 + 10 + 1 = 12
    assert math.isclose(breakdown['cost']['cost'], 12.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# shortest_paths_focus_data — path reconstruction for canvas highlighting
# ---------------------------------------------------------------------------

def test_paths_simple_hard_chain():
    """S → A → B via Hard. Rank-1 target B. All nodes/edges take rank 1."""
    nodes = [_node("S"), _node("A"), _node("B")]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
    ]
    pi = shortest_paths_focus_data("S", [(1, "B")], nodes, edges)
    assert set(pi['subtree']) == {"S", "A", "B"}
    assert pi['node_rank'] == {"S": 1, "A": 1, "B": 1}
    assert pi['edge_rank'] == {
        ("S", "A", EDGE_NEEDS_HARD): 1,
        ("A", "B", EDGE_NEEDS_HARD): 1,
    }
    assert pi['target_labels'] == {"B": "#1"}


def test_paths_diamond_picks_one_representative():
    """S→A→D and S→B→D — BFS picks the first-enqueued path."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("D")]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "S", "target": "B", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "D", "type": EDGE_NEEDS_HARD},
        {"source": "B", "target": "D", "type": EDGE_NEEDS_HARD},
    ]
    pi = shortest_paths_focus_data("S", [(1, "D")], nodes, edges)
    assert len(pi['subtree']) == 3
    assert {"S", "D"}.issubset(set(pi['subtree']))
    intermediate = (set(pi['subtree']) - {"S", "D"}).pop()
    assert intermediate in {"A", "B"}
    assert pi['target_labels'] == {"D": "#1"}


def test_paths_synergy_seeded():
    """S syn→Z, Z→T hard. Path uses the synergy edge from S to Z."""
    nodes = [_node("S"), _node("Z"), _node("T")]
    edges = [
        {"source": "S", "target": "Z", "type": EDGE_HELPS},
        {"source": "Z", "target": "T", "type": EDGE_NEEDS_HARD},
    ]
    pi = shortest_paths_focus_data("S", [(1, "T")], nodes, edges)
    assert set(pi['subtree']) == {"S", "Z", "T"}
    assert pi['edge_rank'] == {
        ("S", "Z", EDGE_HELPS): 1,
        ("Z", "T", EDGE_NEEDS_HARD): 1,
    }


def test_paths_min_rank_wins_on_shared_prefix():
    """S→A→B and A→C. Rank 1 = B, rank 2 = C. Shared S, A stay rank 1."""
    nodes = [_node("S"), _node("A"), _node("B"), _node("C")]
    edges = [
        {"source": "S", "target": "A", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "C", "type": EDGE_NEEDS_HARD},
    ]
    pi = shortest_paths_focus_data(
        "S", [(1, "B"), (2, "C")], nodes, edges,
    )
    assert pi['node_rank'] == {"S": 1, "A": 1, "B": 1, "C": 2}
    assert pi['edge_rank'] == {
        ("S", "A", EDGE_NEEDS_HARD): 1,
        ("A", "B", EDGE_NEEDS_HARD): 1,
        ("A", "C", EDGE_NEEDS_HARD): 2,
    }
    assert pi['target_labels'] == {"B": "#1", "C": "#2"}


def test_paths_unreachable_target_skipped():
    """If a target has no path from source, it's silently dropped."""
    nodes = [_node("S"), _node("A"), _node("X")]
    edges = [{"source": "S", "target": "A", "type": EDGE_NEEDS_HARD}]
    pi = shortest_paths_focus_data(
        "S", [(1, "A"), (2, "X")], nodes, edges,
    )
    assert "X" not in pi['target_labels']
    assert "X" not in pi['node_rank']
    assert pi['target_labels'] == {"A": "#1"}
    assert set(pi['subtree']) == {"S", "A"}


def test_paths_target_equals_source():
    """Asking for the source as a target returns the source alone."""
    nodes = [_node("S")]
    pi = shortest_paths_focus_data("S", [(1, "S")], nodes, [])
    assert pi['subtree'] == ["S"]
    assert pi['node_rank'] == {"S": 1}
    assert pi['edge_rank'] == {}
    assert pi['target_labels'] == {"S": "#1"}


def test_paths_no_targets_still_lights_source():
    """Empty targets list → source lit, nothing else."""
    nodes = [_node("S"), _node("A")]
    edges = [{"source": "S", "target": "A", "type": EDGE_NEEDS_HARD}]
    pi = shortest_paths_focus_data("S", [], nodes, edges)
    assert pi['subtree'] == ["S"]
    assert pi['target_labels'] == {}


def test_paths_missing_source_returns_empty():
    """Source not in all_nodes → empty return, no crash."""
    pi = shortest_paths_focus_data("ghost", [(1, "anything")], [], [])
    assert pi == {'subtree': [], 'node_rank': {},
                  'edge_rank': {}, 'target_labels': {}}
