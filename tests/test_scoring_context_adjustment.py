"""Tests for context-aware adjustments in priority scoring.

Covers the two post-TV/cost multipliers added to `score_nodes`:
- Context weights (user-assigned, per parent context, subcontexts inherit)
- Density normalization via `1 / n_active^alpha` keyed on
  (context, subcontext) bucket.

Both default to no-op (weight=1.0, alpha=0.0) — the regression check ensures
existing behavior is preserved when those defaults are in place.
"""

import pytest

import database
from models import Node, EDGE_NEEDS_HARD
from scoring import score_nodes, explain_score


@pytest.fixture
def temp_database(monkeypatch, tmp_path):
    """Per-test SQLite file so GraphManager-based tests stay isolated."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


def _node(name, **kw):
    defaults = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


BASE_HYPERS = {
    'w_v': 1.0, 'w_i': 1.0,
    'd_H': 0.6, 'd_S': 0.25, 'd_Syn': 0.35,
    'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85,
    'goal_boost': 1.5,
}


# ---------------------------------------------------------------------------
# Regression — default hypers preserve pre-feature behavior
# ---------------------------------------------------------------------------

def test_alpha_zero_and_empty_weights_is_no_op():
    """alpha=0.0 with no weights must match baseline (no post-score mult)."""
    nodes = [
        _node("A", value=8, interest=7, context="Mind"),
        _node("B", value=5, interest=5, context="Life"),
        _node("C", value=3, interest=2, context="Life"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 0.0, 'context_weights': {}}
    scored_on = score_nodes(nodes, nodes, [], hp)
    scored_off = score_nodes(nodes, nodes, [], BASE_HYPERS)
    assert {n.name: n.priority_score for n in scored_on} == \
           {n.name: n.priority_score for n in scored_off}


# ---------------------------------------------------------------------------
# Density normalization
# ---------------------------------------------------------------------------

def test_alpha_full_inverts_dominance_toward_smaller_bucket():
    """alpha=1.0 fully cancels density: smaller bucket wins per-node."""
    big = [_node(f"L{i}", context="Life", subcontext=None) for i in range(20)]
    small = [_node(f"M{i}", context="Mind", subcontext=None) for i in range(5)]
    nodes = big + small
    hp = {**BASE_HYPERS, 'alpha': 1.0, 'context_weights': {}}
    scored = score_nodes(nodes, nodes, [], hp)

    life_scores = [n.priority_score for n in scored if n.context == "Life"]
    mind_scores = [n.priority_score for n in scored if n.context == "Mind"]
    # Identical node ratings → per-node raw score equal; alpha=1.0 divides by
    # bucket size, so Mind (n=5) nodes score 4x higher than Life (n=20).
    assert min(mind_scores) > max(life_scores)


def test_alpha_half_compensates_without_inverting():
    """alpha=0.5 narrows the gap but preserves ranking within buckets."""
    big = [_node(f"L{i}", value=8, context="Life") for i in range(4)]
    small = [_node(f"M{i}", value=8, context="Mind") for i in range(1)]
    nodes = big + small
    hp = {**BASE_HYPERS, 'alpha': 0.5, 'context_weights': {}}
    scored = score_nodes(nodes, nodes, [], hp)

    m_score = next(n.priority_score for n in scored if n.name == "M0")
    l_score = next(n.priority_score for n in scored if n.name == "L0")
    # Mind bucket has 1 node (mult=1), Life has 4 (mult=1/sqrt(4)=0.5).
    # So Mind/Life ratio is ~2.0 (within 2-decimal rounding).
    assert abs(m_score / l_score - 2.0) < 0.05


def test_density_keys_on_context_subcontext_pair():
    """Subcontexts bucket separately — normalization happens at that level."""
    # Life/A has 4 nodes; Life/B has 1 node. alpha=1.0 fully normalizes.
    # Using larger value reduces the impact of 2-decimal rounding on the ratio.
    nodes = [
        _node(f"A{i}", value=10, interest=10, context="Life", subcontext="A")
        for i in range(4)
    ] + [_node("B0", value=10, interest=10, context="Life", subcontext="B")]
    hp = {**BASE_HYPERS, 'alpha': 1.0, 'context_weights': {}}
    scored = score_nodes(nodes, nodes, [], hp)
    a_score = next(n.priority_score for n in scored if n.name == "A0")
    b_score = next(n.priority_score for n in scored if n.name == "B0")
    # Life/A nodes get mult = 1/4; Life/B gets mult = 1/1 → B scores 4x higher.
    assert abs(b_score / a_score - 4.0) < 0.1


def test_done_and_blocked_excluded_from_density_count():
    """Done/Blocked nodes don't dilute the active-node bucket."""
    nodes = [
        _node("Active", context="Life"),
        _node("Done1", context="Life", status="Done"),
        _node("Done2", context="Life", status="Done"),
        _node("Solo", context="Mind"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 1.0, 'context_weights': {}}
    scored = score_nodes(nodes, nodes, [], hp)
    active = next(n.priority_score for n in scored if n.name == "Active")
    solo = next(n.priority_score for n in scored if n.name == "Solo")
    # Life has 1 ACTIVE node (Done ones excluded); Mind has 1. So scores equal.
    assert abs(active - solo) < 0.02


# ---------------------------------------------------------------------------
# Context weights
# ---------------------------------------------------------------------------

def test_weight_doubles_score_in_context():
    nodes = [
        _node("M0", context="Mind"),
        _node("L0", context="Life"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 0.0, 'context_weights': {"Mind": 2.0}}
    scored = score_nodes(nodes, nodes, [], hp)
    m = next(n.priority_score for n in scored if n.name == "M0")
    l = next(n.priority_score for n in scored if n.name == "L0")
    assert abs(m / l - 2.0) < 0.02


def test_weight_halves_score():
    nodes = [
        _node("M0", context="Mind"),
        _node("L0", context="Life"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 0.0, 'context_weights': {"Mind": 0.5}}
    scored = score_nodes(nodes, nodes, [], hp)
    m = next(n.priority_score for n in scored if n.name == "M0")
    l = next(n.priority_score for n in scored if n.name == "L0")
    assert abs(m / l - 0.5) < 0.02


def test_subcontexts_inherit_parent_weight():
    """A node in Mind/Rational picks up Mind's weight."""
    nodes = [
        _node("Ratl", context="Mind", subcontext="Rational"),
        _node("Sens", context="Mind", subcontext="Sensory"),
        _node("Life0", context="Life"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 0.0, 'context_weights': {"Mind": 3.0}}
    scored = score_nodes(nodes, nodes, [], hp)
    ratl = next(n.priority_score for n in scored if n.name == "Ratl")
    sens = next(n.priority_score for n in scored if n.name == "Sens")
    life = next(n.priority_score for n in scored if n.name == "Life0")
    # Both Mind subnodes triple; Life unchanged.
    assert abs(ratl / life - 3.0) < 0.02
    assert abs(sens / life - 3.0) < 0.02


def test_weights_and_alpha_compose():
    """Both multipliers apply together."""
    # Use larger values so the base score is large enough that 2-decimal
    # rounding at each multiplication step doesn't dominate the ratio.
    nodes = [
        _node(f"L{i}", value=10, interest=10, context="Life") for i in range(4)
    ] + [_node("M0", value=10, interest=10, context="Mind")]
    hp = {**BASE_HYPERS, 'alpha': 0.5,
          'context_weights': {"Mind": 2.0, "Life": 1.0}}
    scored = score_nodes(nodes, nodes, [], hp)
    m = next(n.priority_score for n in scored if n.name == "M0")
    l = next(n.priority_score for n in scored if n.name == "L0")
    # Mind: base × 2.0 × (1/1^0.5) = base × 2.0
    # Life: base × 1.0 × (1/4^0.5) = base × 0.5
    # Ratio = 4.0
    assert abs(m / l - 4.0) < 0.1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_context_does_not_crash():
    """Nodes without a context should still score without error."""
    nodes = [
        _node("A", context=None, subcontext=None),
        _node("B", context=None, subcontext=None),
        _node("C", context="Mind"),
    ]
    hp = {**BASE_HYPERS, 'alpha': 0.5, 'context_weights': {"Mind": 2.0}}
    scored = score_nodes(nodes, nodes, [], hp)
    # Nodes A and B share a (None, None) bucket of size 2; get no weight boost.
    # Node C is alone in Mind and gets weight 2.0.
    scores = {n.name: n.priority_score for n in scored}
    assert scores["A"] > 0 and scores["B"] > 0 and scores["C"] > 0


def test_weight_for_context_with_no_active_nodes_is_ignored():
    """Weights for absent contexts don't affect anything."""
    nodes = [_node("M0", context="Mind")]
    hp = {**BASE_HYPERS, 'alpha': 0.0,
          'context_weights': {"Mind": 1.0, "Ghost": 99.0}}
    scored = score_nodes(nodes, nodes, [], hp)
    # M0 gets its Mind weight (1.0 = no-op); Ghost weight is ignored entirely.
    baseline = score_nodes(nodes, nodes, [], BASE_HYPERS)
    assert scored[0].priority_score == baseline[0].priority_score


# ---------------------------------------------------------------------------
# explain_score — context_adjustment block is correct and inspectable
# ---------------------------------------------------------------------------

def test_explain_score_reports_context_adjustment():
    nodes = [
        _node("A", context="Life") for _ in range(1)
    ] + [_node("B", context="Life"),
         _node("C", context="Life"),
         _node("M", context="Mind")]
    nodes[0] = _node("A", context="Life")  # keep naming stable
    hp = {**BASE_HYPERS, 'alpha': 0.5, 'context_weights': {"Life": 2.0}}
    breakdown = explain_score("A", nodes, [], hp)
    adj = breakdown['context_adjustment']
    assert adj['weight'] == 2.0
    assert adj['n_bucket'] == 3  # Life nodes: A, B, C
    assert adj['alpha'] == 0.5
    # density_mult = 1 / 3^0.5
    assert abs(adj['density_mult'] - (1.0 / (3 ** 0.5))) < 1e-6
    assert abs(adj['combined_multiplier'] - adj['weight'] * adj['density_mult']) < 1e-6


def test_explain_score_no_context_uses_neutral_adjustment():
    nodes = [_node("A", context=None)]
    hp = {**BASE_HYPERS, 'alpha': 0.0}
    breakdown = explain_score("A", nodes, [], hp)
    adj = breakdown['context_adjustment']
    assert adj['weight'] == 1.0
    assert adj['density_mult'] == 1.0
    assert adj['combined_multiplier'] == 1.0


# ---------------------------------------------------------------------------
# Cascade + post-score composition
# ---------------------------------------------------------------------------

def test_memo_survives_alpha_change(temp_database):
    """Graph-manager-level TV memo must NOT invalidate when alpha changes.

    The cascade (TV) does not depend on alpha; only the post-score multiplier
    does. GraphManager's cache_key is narrowed to TV-affecting keys so that
    changes to alpha/weights/cost params don't cause needless recomputation.
    """
    from graph_manager import GraphManager
    from config import ConfigManager

    mgr = GraphManager()
    mgr.add_node(_node("A", context="Mind"))
    mgr.add_node(_node("B", context="Life"))

    # First scoring call populates the memo under current hyperparams.
    ConfigManager.set_hyperparams({**BASE_HYPERS, 'alpha': 0.0})
    mgr.calculate_priority_scores(mgr.get_all_nodes())
    memo_id_before = id(mgr._scoring_memo)
    key_before = mgr._scoring_memo_key

    # Change alpha — must NOT flush the memo (alpha is post-score).
    ConfigManager.set_hyperparams({**BASE_HYPERS, 'alpha': 0.5})
    mgr.calculate_priority_scores(mgr.get_all_nodes())
    assert id(mgr._scoring_memo) == memo_id_before, \
        "Memo was replaced when alpha changed — invalidation key is too broad"
    assert mgr._scoring_memo_key == key_before

    # Sanity: a TV-affecting change (d_H) DOES flush the memo.
    ConfigManager.set_hyperparams({**BASE_HYPERS, 'd_H': 0.3})
    mgr.calculate_priority_scores(mgr.get_all_nodes())
    assert mgr._scoring_memo_key != key_before, \
        "Memo stayed valid after d_H change — should have invalidated"


def test_memo_survives_context_weights_change(temp_database):
    """Same invariant for context_weights changes."""
    from graph_manager import GraphManager
    from config import ConfigManager

    mgr = GraphManager()
    mgr.add_node(_node("A", context="Mind"))

    ConfigManager.set_hyperparams(BASE_HYPERS)
    ConfigManager.set_context_weights({})
    mgr.calculate_priority_scores(mgr.get_all_nodes())
    key_before = mgr._scoring_memo_key

    ConfigManager.set_context_weights({"Mind": 2.0})
    mgr.calculate_priority_scores(mgr.get_all_nodes())
    assert mgr._scoring_memo_key == key_before, \
        "Memo was invalidated by context_weights change"


def test_adjustment_applies_after_tv_over_cost():
    """Post-score multipliers scale the final score, not TV/cost inputs."""
    # Chain A -Hard-> B so TV(A) includes B's contribution.
    nodes = [_node("A", value=8, context="Mind"),
             _node("B", value=5, context="Mind")]
    edges = [{"source": "A", "target": "B", "type": EDGE_NEEDS_HARD}]
    base = score_nodes(list(nodes), nodes, edges, BASE_HYPERS)
    base_a = next(n.priority_score for n in base if n.name == "A")

    hp = {**BASE_HYPERS, 'alpha': 0.0, 'context_weights': {"Mind": 2.0}}
    boosted = score_nodes(list(nodes), nodes, edges, hp)
    boosted_a = next(n.priority_score for n in boosted if n.name == "A")

    assert abs(boosted_a / base_a - 2.0) < 0.02
