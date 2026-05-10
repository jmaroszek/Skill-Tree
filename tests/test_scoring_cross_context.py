"""Tests for the Creator-profile cross_context_mult hyperparameter.

The multiplier scales the Helps pair bonus (d_Syn_pair * tv(partner)) when
the partner sits in a different context from the start node. Same-context
partners and Hard/Soft cascade are unaffected. Default is 1.0 → no
behavioral change from prior versions.
"""

import math

from models import Node, EDGE_HELPS, EDGE_NEEDS_HARD
from scoring import total_value, build_adjacency, explain_score


def _node(name, ctx="Mind", **kw):
    defaults = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context=ctx,
    )
    defaults.update(kw)
    return Node(**defaults)


BASE = dict(
    w_v=1.0, w_i=1.0, d_H=0.6, d_S=0.40,
    d_Syn_pair=0.10, d_Syn_mul=0.40,
)


def _tv(name, nodes, edges, **overrides):
    """Compute TotalValue with the given hyperparam overrides."""
    hp = {**BASE, **overrides}
    all_nodes_dict = {n.name: n for n in nodes}
    H_out, S_out, Syn, _ = build_adjacency(edges, set(all_nodes_dict.keys()))
    return total_value(
        name, set(), all_nodes_dict, H_out, S_out, Syn,
        hp['w_v'], hp['w_i'], hp['d_H'], hp['d_S'],
        hp['d_Syn_pair'], hp['d_Syn_mul'],
        memo={},
        cross_context_mult=hp.get('cross_context_mult', 1.0),
    )


# ---------------------------------------------------------------------------
# Same-context synergy is untouched by cross_context_mult
# ---------------------------------------------------------------------------

def test_same_context_synergy_unchanged_by_multiplier():
    """A and B in same context, Helps-linked. cross_context_mult should be a no-op."""
    nodes = [_node("A", ctx="Mind", value=8), _node("B", ctx="Mind", value=6)]
    edges = [{"source": "A", "target": "B", "type": EDGE_HELPS}]

    tv_baseline = _tv("A", nodes, edges)
    tv_boosted = _tv("A", nodes, edges, cross_context_mult=5.0)
    assert math.isclose(tv_baseline, tv_boosted, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Cross-context synergy gets the multiplier on the pair bonus
# ---------------------------------------------------------------------------

def test_cross_context_synergy_scales_with_multiplier():
    """A in Mind, B in Body, Helps-linked. mult=2.0 should add d_Syn_pair * IV(B)."""
    nodes = [_node("A", ctx="Mind", value=8), _node("B", ctx="Body", value=6)]
    edges = [{"source": "A", "target": "B", "type": EDGE_HELPS}]

    tv_at_1 = _tv("A", nodes, edges, cross_context_mult=1.0)
    tv_at_2 = _tv("A", nodes, edges, cross_context_mult=2.0)

    # IV(B) = w_v*6 + w_i*5 = 11. Pair bonus at mult=1.0 is 0.10 * 11 = 1.10;
    # at mult=2.0 it is 0.20 * 11 = 2.20. So tv_at_2 - tv_at_1 == 1.10.
    iv_b = BASE['w_v'] * 6 + BASE['w_i'] * 5
    delta_expected = (2.0 - 1.0) * BASE['d_Syn_pair'] * iv_b
    assert math.isclose(tv_at_2 - tv_at_1, delta_expected, rel_tol=1e-9)


def test_cross_context_only_affects_pair_bonus_not_done_multiplier():
    """Done synergy partners give iv * (1 + d_Syn_mul * sqrt(count)).

    That multiplier is context-blind by design — it kicks in on the start
    node's own intrinsic value regardless of where its Done partners live.
    """
    nodes = [
        _node("A", ctx="Mind", value=10),
        _node("B", ctx="Body", value=6, status="Done"),
    ]
    edges = [{"source": "A", "target": "B", "type": EDGE_HELPS}]

    tv_at_1 = _tv("A", nodes, edges, cross_context_mult=1.0)
    tv_at_3 = _tv("A", nodes, edges, cross_context_mult=3.0)

    # When B is Done, the pair bonus still fires (B's TV is positive), so
    # the multiplier still applies on that path. But the "Done multiplier
    # on intrinsic" component (iv_A * (1 + d_Syn_mul * sqrt(1))) is
    # identical in both runs, so the difference equals the pair-bonus
    # scaling only.
    iv_b = BASE['w_v'] * 6 + BASE['w_i'] * 5
    delta_expected = (3.0 - 1.0) * BASE['d_Syn_pair'] * iv_b
    assert math.isclose(tv_at_3 - tv_at_1, delta_expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Hard/Soft cascade is unaffected
# ---------------------------------------------------------------------------

def test_hard_cascade_unaffected_by_cross_context_mult():
    """Hard prereqs across contexts should not get the synergy multiplier."""
    nodes = [_node("A", ctx="Mind", value=8), _node("B", ctx="Body", value=10)]
    # A unlocks B via Hard — A is the prereq, B is the dependent
    edges = [{"source": "A", "target": "B", "type": EDGE_NEEDS_HARD}]

    tv_at_1 = _tv("A", nodes, edges, cross_context_mult=1.0)
    tv_at_5 = _tv("A", nodes, edges, cross_context_mult=5.0)
    assert math.isclose(tv_at_1, tv_at_5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# explain_score breakdown reflects the multiplier
# ---------------------------------------------------------------------------

def test_explain_score_breakdown_matches_cross_context_tv():
    """explain_score's contributor weights must reproduce the scaled TV."""
    nodes = [_node("A", ctx="Mind", value=8), _node("B", ctx="Body", value=6)]
    edges = [{"source": "A", "target": "B", "type": EDGE_HELPS}]

    hp = {**BASE, 'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85,
          'goal_boost': 1.5, 'alpha': 0.0, 'cross_context_mult': 2.0}
    breakdown = explain_score("A", nodes, edges, hp)

    tv_truth = _tv("A", nodes, edges, cross_context_mult=2.0)
    contributed = sum(c['contribution'] for c in breakdown['contributors'])
    assert math.isclose(contributed, tv_truth, rel_tol=1e-9)


def test_explain_score_missing_context_falls_back_safely():
    """If start or partner has context=None, multiplier should not apply."""
    nodes = [_node("A", ctx=None, value=8), _node("B", ctx="Body", value=6)]
    edges = [{"source": "A", "target": "B", "type": EDGE_HELPS}]

    tv_at_1 = _tv("A", nodes, edges, cross_context_mult=1.0)
    tv_at_5 = _tv("A", nodes, edges, cross_context_mult=5.0)
    # context=None on either endpoint means "no context check possible" —
    # fall back to no-multiplier behavior so we never accidentally boost
    # an uncategorized node into the top of the list.
    assert math.isclose(tv_at_1, tv_at_5, rel_tol=1e-9)
