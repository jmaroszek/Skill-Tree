"""Context weights remain; legacy task density no longer affects merit."""

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
    'd_H': 0.6, 'd_S': 0.25,
    'd_Syn_pair': 0.10, 'd_Syn_mul': 0.40,
    'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85,
    'goal_boost': 1.5,
    # Suggestion variety is off here: these cases stack same-context nodes
    # deliberately, and the repetition discount would confound the context
    # weight and density effects they exist to measure.
    'suggestion_context_premium': 0.0, 'suggestion_subcontext_premium': 0.0,
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


@pytest.mark.parametrize('alpha', [0, .3, .5, 1, 1.5])
@pytest.mark.parametrize('subcontext', [None, 'Area'])
def test_legacy_density_does_not_change_merit(alpha, subcontext):
    nodes = [_node('Target', context='Life', subcontext=subcontext)]
    hp = {**BASE_HYPERS, 'alpha': alpha}
    alone = score_nodes(nodes, nodes, [], hp)[0].priority_score_exact
    nodes += [_node(f'Other{i}', context='Life', subcontext=subcontext) for i in range(20)]
    scored = score_nodes(nodes, nodes, [], hp)
    assert next(n.priority_score_exact for n in scored if n.name == 'Target') == alone
    adj = explain_score('Target', nodes, [], hp)['context_adjustment']
    assert adj['density_mult'] == 1
    assert adj['alpha'] == 0


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


def test_weights_apply_and_legacy_alpha_is_ignored():
    """Explicit context weights remain meaningful after density retirement."""
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
    assert m / l == pytest.approx(2.0)



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
    assert adj['n_bucket'] == 1  # Retired density has neutral compatibility fields.
    assert adj['alpha'] == 0.0
    assert adj['density_mult'] == 1.0
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


# ---------------------------------------------------------------------------
# Weight migration helper — rename / merge / skip scenarios
# ---------------------------------------------------------------------------

class TestMigrateContextWeights:
    """Covers _migrate_context_weights: the pure helper that resolves weights
    after contexts are renamed, merged, or removed via the migration dialog."""

    def _call(self, old_weights, pending_weights, new_contexts, rename_map):
        from settings_callbacks import _migrate_context_weights
        return _migrate_context_weights(
            old_weights, pending_weights, new_contexts, rename_map,
        )

    def test_rename_carries_weight(self):
        """Health → Body, where Body was not previously weighted.

        Source weight carries to target name."""
        out = self._call(
            old_weights={"Health": 2.0},
            pending_weights={"Health": 2.0, "Body": 1.0},
            new_contexts=["Body"],
            rename_map={"Health": "Body"},
        )
        assert out == {"Body": 2.0}

    def test_merge_respects_existing_target_weight(self):
        """Health → Body, where Body already has a non-default weight.

        Target's explicit weight wins; source's weight is discarded."""
        out = self._call(
            old_weights={"Health": 2.0, "Body": 3.0},
            pending_weights={"Health": 2.0, "Body": 3.0},
            new_contexts=["Body"],
            rename_map={"Health": "Body"},
        )
        assert out == {"Body": 3.0}

    def test_merge_into_default_target_carries_source(self):
        """Health → Body, where Body's weight is the default 1.0.

        User hasn't deliberately weighted the target, so source wins."""
        out = self._call(
            old_weights={"Health": 2.0, "Body": 1.0},
            pending_weights={"Health": 2.0, "Body": 1.0},
            new_contexts=["Body"],
            rename_map={"Health": "Body"},
        )
        assert out == {"Body": 2.0}

    def test_skip_drops_weights_for_removed_contexts(self):
        """Empty rename_map (skip or no-migration path) → filter only."""
        out = self._call(
            old_weights={"Health": 2.0, "Body": 1.0},
            pending_weights={"Health": 2.0, "Body": 1.0},
            new_contexts=["Body"],
            rename_map={},
        )
        assert out == {"Body": 1.0}

    def test_untouched_context_keeps_weight(self):
        """Context present in both old and new contexts retains its weight."""
        out = self._call(
            old_weights={"Mind": 3.0},
            pending_weights={"Mind": 3.0},
            new_contexts=["Mind"],
            rename_map={},
        )
        assert out == {"Mind": 3.0}

    def test_rename_target_missing_from_new_contexts_is_ignored(self):
        """Defensive: if the rename target somehow isn't in new_contexts,
        the rename is a no-op (shouldn't happen in practice)."""
        out = self._call(
            old_weights={"Health": 2.0},
            pending_weights={"Health": 2.0},
            new_contexts=["Mind"],  # neither Health nor Body
            rename_map={"Health": "Body"},
        )
        assert out == {}


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
