"""Tests for the v2 normalized time term and the hyperparameter migration.

The v1 cost term was ``w_t * t**beta``, which entangled two separate concerns:
beta set the curvature of the time penalty *and* silently scaled its
magnitude, because ``t**beta`` shrinks as beta falls. v2 divides by a fixed
reference first, so beta is curvature only and w_t is the sole magnitude knob.

These tests pin the three properties that make the change safe: the reference
is a constant, the reparameterization is exact, and an existing stored bundle
keeps the cost curve it already had.
"""

import json

import pytest

from config import (
    ConfigManager,
    DEFAULT_HYPERPARAMS,
    HYPERPARAMS_SCHEMA_VERSION,
    PROFILES,
)
from models import Node
from scoring import (
    GOAL_TIME_REF_HOURS,
    TIME_REF_HOURS,
    intrinsic_value,
    perceived_cost,
    score_nodes,
    time_cost_term,
)


def _node(name="N", **kw):
    base = dict(name=name, type="Learn", description="", value=5, interest=5,
                difficulty=5, time_o=10, time_m=10, time_p=10,
                context="Ctx", subcontext=None, status="Open")
    base.update(kw)
    return Node(**base)


# ============================================================================
# time_cost_term
# ============================================================================

class TestTimeCostTerm:
    def test_equals_w_t_at_the_reference_for_any_beta(self):
        """The whole point of normalizing: w_t is the term's value at t=ref."""
        for beta in (0.2, 0.5, 0.6, 0.85, 1.0):
            assert time_cost_term(TIME_REF_HOURS, 6.0, beta) == pytest.approx(6.0)

    def test_zero_time_costs_nothing(self):
        assert time_cost_term(0.0, 6.0, 0.6) == 0.0

    def test_negative_time_costs_nothing(self):
        """Defensive: a bad estimate must not produce a complex or negative term."""
        assert time_cost_term(-5.0, 6.0, 0.6) == 0.0

    def test_lower_beta_flattens_the_curve(self):
        """Curvature moves with beta while the value at the reference does not."""
        short, long_ = 4.0, 400.0
        steep = time_cost_term(long_, 6.0, 0.85) / time_cost_term(short, 6.0, 0.85)
        flat = time_cost_term(long_, 6.0, 0.45) / time_cost_term(short, 6.0, 0.45)
        assert flat < steep

    def test_accepts_an_alternate_reference(self):
        assert time_cost_term(GOAL_TIME_REF_HOURS, 7.0, 0.7,
                              ref=GOAL_TIME_REF_HOURS) == pytest.approx(7.0)


# ============================================================================
# Exact reparameterization
# ============================================================================

class TestReparameterizationIsExact:
    @pytest.mark.parametrize("beta", [0.45, 0.60, 0.85, 0.95])
    @pytest.mark.parametrize("t", [1.0, 7.5, 40.0, 180.0, 316.0])
    def test_scaled_w_t_reproduces_the_v1_term(self, beta, t):
        """w_t_v2 = w_t_v1 * ref**beta must give back the v1 time term exactly."""
        w_t_v1 = 1.0
        w_t_v2 = w_t_v1 * (TIME_REF_HOURS ** beta)
        assert time_cost_term(t, w_t_v2, beta) == pytest.approx(w_t_v1 * (t ** beta))

    def test_full_cost_matches_v1_after_conversion(self):
        node = _node(difficulty=5, time_o=80, time_m=80, time_p=80)
        beta, w_e, w_t_v1 = 0.85, 2.5, 1.0
        v1 = 1.0 + w_e * 5 + w_t_v1 * (80.0 ** beta)
        v2 = perceived_cost(node, w_e=w_e,
                            w_t=w_t_v1 * (TIME_REF_HOURS ** beta), beta=beta)
        assert v2 == pytest.approx(v1)


# ============================================================================
# Hyperparameter migration (v1 -> v2)
# ============================================================================

class TestHyperparamMigration:
    def test_v1_bundle_is_rescaled(self):
        hp = ConfigManager._migrate_hyperparams(
            {**DEFAULT_HYPERPARAMS, "w_t": 1.0, "beta": 0.85})
        assert hp["w_t"] == pytest.approx(TIME_REF_HOURS ** 0.85)
        assert hp["_schema"] == HYPERPARAMS_SCHEMA_VERSION

    def test_migration_is_idempotent(self):
        once = ConfigManager._migrate_hyperparams(
            {**DEFAULT_HYPERPARAMS, "w_t": 1.0, "beta": 0.85})
        twice = ConfigManager._migrate_hyperparams(dict(once))
        assert twice["w_t"] == pytest.approx(once["w_t"])

    def test_v2_bundle_is_untouched(self):
        hp = {**DEFAULT_HYPERPARAMS, "w_t": 6.0, "beta": 0.60,
              "_schema": HYPERPARAMS_SCHEMA_VERSION}
        assert ConfigManager._migrate_hyperparams(dict(hp))["w_t"] == 6.0

    def test_migration_uses_the_bundles_own_beta(self):
        """Each profile had its own beta, so the conversion factor differs."""
        hp = ConfigManager._migrate_hyperparams(
            {**DEFAULT_HYPERPARAMS, "w_t": 4.0, "beta": 0.95})
        assert hp["w_t"] == pytest.approx(4.0 * (TIME_REF_HOURS ** 0.95))

    def test_stored_v1_row_is_migrated_on_read(self):
        ConfigManager._set_db_value(
            "HYPERPARAMS", json.dumps({"w_t": 1.0, "beta": 0.85, "w_e": 2.5}))
        hp = ConfigManager.get_hyperparams()
        assert hp["w_t"] == pytest.approx(TIME_REF_HOURS ** 0.85)
        assert hp["w_e"] == 2.5

    def test_set_hyperparams_stamps_the_schema_version(self):
        ConfigManager.set_hyperparams({**DEFAULT_HYPERPARAMS})
        raw = json.loads(ConfigManager._get_db_value("HYPERPARAMS"))
        assert raw["_schema"] == HYPERPARAMS_SCHEMA_VERSION
        # And a round trip does not rescale an already-current bundle.
        assert ConfigManager.get_hyperparams()["w_t"] == DEFAULT_HYPERPARAMS["w_t"]

    def test_absent_row_returns_defaults_unscaled(self):
        assert ConfigManager.get_hyperparams()["w_t"] == DEFAULT_HYPERPARAMS["w_t"]

    def test_migrated_bundle_preserves_the_v1_ranking(self):
        """The migration must not re-sort an existing user's Next list."""
        nodes = [
            _node("Short", value=4, interest=4, difficulty=3,
                  time_o=3, time_m=3, time_p=3),
            _node("Mid", value=7, interest=6, difficulty=5,
                  time_o=40, time_m=40, time_p=40),
            _node("Long", value=9, interest=8, difficulty=6,
                  time_o=200, time_m=200, time_p=200),
        ]
        v1 = {**DEFAULT_HYPERPARAMS, "w_v": 1.0, "w_i": 1.0,
              "w_e": 2.5, "w_t": 1.0, "beta": 0.85, "alpha": 0.0,
              # This test pins the w_t rescaling, so hold the value shape
              # linear; value_exponent is exercised separately.
              "value_exponent": 1.0}
        migrated = ConfigManager._migrate_hyperparams(dict(v1))

        ranked = score_nodes([n for n in nodes], list(nodes), [], migrated)
        got = {n.name: n.priority_score for n in ranked}

        for n in nodes:
            iv = 1.0 * n.value + 1.0 * n.interest
            cost = 1.0 + 2.5 * n.difficulty + 1.0 * (n.time ** 0.85)
            assert got[n.name] == pytest.approx(round(iv / cost, 2), abs=0.01)


# ============================================================================
# Profile table invariants
# ============================================================================

class TestProfileTable:
    REQUIRED = set(DEFAULT_HYPERPARAMS) - {"_schema"}

    def test_every_profile_defines_every_knob(self):
        for name, hp in PROFILES.items():
            missing = self.REQUIRED - set(hp)
            assert not missing, f"{name} is missing {sorted(missing)}"

    def test_sage_is_the_default_bundle(self):
        assert PROFILES["Sage"] is DEFAULT_HYPERPARAMS

    def test_profiles_are_pairwise_distinct(self):
        seen = {}
        for name, hp in PROFILES.items():
            key = tuple(sorted((k, hp[k]) for k in self.REQUIRED))
            assert key not in seen, f"{name} is identical to {seen[key]}"
            seen[key] = name

    def test_no_two_profiles_share_a_cost_curve(self):
        """Sage, Explorer and Creator shared one cost curve before the retune.

        They are allowed to again, but Compounder, Pragmatist and Glider carry
        the profile system's spread on the cost axis and must stay distinct.
        """
        curves = {n: (PROFILES[n]["beta"], PROFILES[n]["w_t"], PROFILES[n]["w_e"])
                  for n in ("Sage", "Compounder", "Pragmatist", "Glider")}
        assert len(set(curves.values())) == len(curves)

    def test_discount_convention_holds(self):
        """docs/scoring.md states 0 < d_S < d_H < 1 for every profile."""
        for name, hp in PROFILES.items():
            assert 0 < hp["d_S"] < hp["d_H"] < 1, name

    def test_beta_stays_inside_the_safe_window(self):
        """Below ~0.42 the time coefficient flips sign and long tasks win."""
        for name, hp in PROFILES.items():
            assert 0.45 <= hp["beta"] <= 1.0, name

    def test_glider_is_the_most_time_penalising_profile(self):
        """Glider's short-task bias is deliberate; guard it against a retune."""
        at_ref = {n: time_cost_term(200.0, hp["w_t"], hp["beta"])
                  for n, hp in PROFILES.items()}
        assert max(at_ref, key=at_ref.get) == "Glider"


# ============================================================================
# alpha_goal survives a Settings save
# ============================================================================

class TestKnobsSurviveSave:
    """The Settings form has no input for alpha_goal.

    Before this guard the saved bundle simply omitted the key, and
    get_hyperparams merged Sage's default back in — quietly resetting the Goal
    ranker for every other profile. Explorer wants 0.50 and Compounder 0.00,
    so the reset was a real behaviour change, not a rounding difference.
    """

    def test_named_profiles_resolve_to_their_own_value(self):
        from settings_callbacks import _profile_knob
        for name, hp in PROFILES.items():
            assert _profile_knob(name, 'alpha_goal') == hp['alpha_goal'], name

    def test_custom_keeps_the_stored_value(self):
        from settings_callbacks import _profile_knob
        ConfigManager.set_hyperparams({**DEFAULT_HYPERPARAMS, 'alpha_goal': 0.42})
        assert _profile_knob('Custom', 'alpha_goal') == 0.42

    def test_unknown_profile_falls_back_to_the_stored_value(self):
        from settings_callbacks import _profile_knob
        ConfigManager.set_hyperparams({**DEFAULT_HYPERPARAMS, 'alpha_goal': 0.11})
        assert _profile_knob('NoSuchProfile', 'alpha_goal') == 0.11

    def test_profiles_do_not_all_share_one_alpha_goal(self):
        """Guards against a retune that flattens the knob into irrelevance."""
        assert len({hp['alpha_goal'] for hp in PROFILES.values()}) >= 4


# ============================================================================
# value_exponent: making the cascade discriminate by quality, not just count
# ============================================================================

class TestValueExponent:
    """The cascade sums IV over a node's descendants.

    A sum of many similar terms tracks how MANY terms there are more than how
    large each one is, so at exponent 1.0 total value behaves largely like a
    descendant count. Raising the exponent widens the gap between ratings so
    that unlocking valuable work separates from unlocking trivial work.
    """

    @staticmethod
    def _chain(tag, rating, k=8):
        parent = _node(tag, value=5, interest=5, difficulty=4,
                       time_o=40, time_m=40, time_p=40)
        kids = [_node(f"{tag}{j}", value=rating, interest=rating, difficulty=4,
                      time_o=40, time_m=40, time_p=40, status="Blocked")
                for j in range(k)]
        edges = [{'source': tag, 'target': f"{tag}{j}", 'type': 'Needs_Hard'}
                 for j in range(k)]
        return [parent] + kids, edges

    def _tv(self, rating, exponent):
        nodes, edges = self._chain("P", rating)
        hp = {**DEFAULT_HYPERPARAMS, 'value_exponent': exponent, 'alpha': 0.0}
        ranked = score_nodes(list(nodes), list(nodes), edges, hp)
        return next(n.total_value for n in ranked if n.name == "P")

    def test_default_is_greater_than_one(self):
        """A linear default would leave the cascade behaving as a count."""
        assert DEFAULT_HYPERPARAMS['value_exponent'] > 1.0

    def test_exponent_widens_the_valuable_vs_trivial_gap(self):
        linear = self._tv(9, 1.0) / self._tv(2, 1.0)
        convex = self._tv(9, 2.0) / self._tv(2, 2.0)
        assert convex > linear * 2

    def test_exponent_one_reproduces_linear_weighting(self):
        n = _node(value=7, interest=3)
        assert intrinsic_value(n, 1.0, 1.0, 1.0) == pytest.approx(10.0)
        # And the default argument keeps legacy three-arg callers linear.
        assert intrinsic_value(n, 1.0, 1.0) == pytest.approx(10.0)

    def test_exponent_applies_to_both_ratings(self):
        n = _node(value=3, interest=4)
        assert intrinsic_value(n, 1.0, 1.0, 2.0) == pytest.approx(9 + 16)
        assert intrinsic_value(n, 2.0, 0.5, 2.0) == pytest.approx(2 * 9 + 0.5 * 16)

    def test_inherited_value_mode_still_zeroes_out(self):
        n = _node(value=10, interest=10, value_mode='inherited')
        assert intrinsic_value(n, 1.0, 1.0, 2.5) == 0.0

    def test_never_zeroes_a_low_rated_node(self):
        """Unlike a baseline-subtraction form, a power keeps 1/1 above zero.

        A node the user rated at the floor should rank last, not vanish from
        the cascade entirely on the strength of one pessimistic rating.
        """
        n = _node(value=1, interest=1)
        for g in (1.0, 2.0, 3.0):
            assert intrinsic_value(n, 1.0, 1.0, g) > 0

    def test_profiles_spread_the_exponent(self):
        vals = {hp['value_exponent'] for hp in PROFILES.values()}
        assert len(vals) >= 3, "the exponent should differentiate profiles"

    def test_exponent_is_in_the_tv_cache_key(self):
        """Omitting it would leave rankings stale after a profile switch.

        CLAUDE.md calls this out specifically: a scoring-relevant field that is
        missing from the invalidation key makes rankings silently go stale.
        """
        import inspect
        import graph_manager
        src = inspect.getsource(graph_manager.GraphManager.calculate_priority_scores)
        assert 'value_exponent' in src
