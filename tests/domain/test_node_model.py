"""The Node model: its fields, expected time, and the modes it enforces."""
import pytest
from skilltree.domain.models import Node
from skilltree.domain.scoring import (intrinsic_value)
from support.graphs import make_node


# --- Fixtures ---



# ============================================================================
# Node Model Validation
# ============================================================================

class TestNodeModel:
    def test_value_clamped_high(self):
        node = make_node(value=15)
        assert node.value == 10

    def test_value_clamped_low(self):
        node = make_node(value=0)
        assert node.value == 1

    def test_interest_clamped(self):
        node = make_node(interest=15)
        assert node.interest == 10

    def test_difficulty_clamped(self):
        node = make_node(difficulty=15)
        assert node.difficulty == 10

    def test_time_coercion(self):
        node = make_node(time_o="1", time_m="2", time_p="3")
        assert isinstance(node.time_o, float)
        assert isinstance(node.time_m, float)
        assert isinstance(node.time_p, float)

    def test_to_dict_includes_computed_time(self):
        node = make_node()
        d = node.to_dict()
        assert 'time' in d
        assert d['time'] == node.time

    def test_from_dict_strips_time(self):
        d = make_node("X").to_dict()
        d['time'] = 999  # should be ignored
        node = Node.from_dict(d)
        assert node.time != 999

# ============================================================================
# Expected Time Estimation
# ============================================================================

class TestExpectedTime:
    def test_all_zeros_returns_default(self):
        node = make_node(time_o=0, time_m=0, time_p=0)
        assert node.time == 1.0

    def test_only_m_provided(self):
        node = make_node(time_o=0, time_m=5.0, time_p=0)
        assert node.time == 5.0

    def test_only_o_and_p_provided(self):
        # Middle filled with sqrt(4*9)=6, then Swanson-weighted.
        node = make_node(time_o=4.0, time_m=0, time_p=9.0)
        assert node.time == pytest.approx(.3 * 4.0 + .4 * 6.0 + .3 * 9.0)

    def test_equal_estimates(self):
        node = make_node(time_o=2.0, time_m=2.0, time_p=2.0)
        assert node.time == 2.0

    def test_tight_bracket(self):
        node = make_node(time_o=1.0, time_m=1.5, time_p=2.0)
        assert node.time == pytest.approx(.3 * 1.0 + .4 * 1.5 + .3 * 2.0)

    def test_wide_bracket_is_weighted_not_capped(self):
        # The upper estimate keeps its full 0.3 share however wide the bracket
        # gets — no regime switch, no blend weight.
        node = make_node(time_o=1.0, time_m=10.0, time_p=100.0)
        assert node.time == pytest.approx(.3 * 1.0 + .4 * 10.0 + .3 * 100.0)

    def test_estimate_rises_monotonically_with_the_upper_bound(self):
        widen = [make_node(time_o=2.0, time_m=5.0, time_p=p).time
                 for p in (10.0, 20.0, 40.0, 200.0)]
        assert widen == sorted(widen) and len(set(widen)) == 4

    def test_medium_uncertainty_within_bounds(self):
        node = make_node(time_o=2.0, time_m=5.0, time_p=10.0)
        assert 2.0 < node.time < 10.0

    def test_o_greater_than_m_clamped(self):
        # When o > m, the code clamps m = o
        node = make_node(time_o=5.0, time_m=2.0, time_p=10.0)
        assert node.time > 0

    def test_all_provided_standard(self):
        node = make_node(time_o=1.0, time_m=2.0, time_p=4.0)
        assert 1.0 <= node.time <= 4.0


# ============================================================================
# Container types always inherit time (model-level enforcement)
# ============================================================================

class TestContainerTypeTimeInheritance:
    """Goals and Milestones are container types: their time is the sum of their
    children's, never an own estimate. ``Node.__post_init__`` forces
    time_mode='inherited' for both, so the invariant holds on every read —
    including legacy DB rows and programmatic constructions that pass 'manual'.
    (This replaces an earlier one-time DB migration; enforcing at the model
    layer means there's no stored state to drift.)
    """

    def test_goal_forced_to_inherited_time(self):
        n = make_node("G", type="Goal", time_mode='manual')
        assert n.time_mode == 'inherited'

    def test_milestone_forced_to_inherited_time(self):
        n = make_node("M", type="Milestone", time_mode='manual')
        assert n.time_mode == 'inherited'

    def test_non_container_type_keeps_manual_time(self):
        n = make_node("L", type="Learn", time_mode='manual')
        assert n.time_mode == 'manual'

    def test_goal_inherited_time_persists_through_db(self, mgr):
        mgr.add_node(make_node("MigGoal", type="Goal", time_mode='manual'))
        assert mgr.get_node("MigGoal").time_mode == 'inherited'

    def test_goal_time_reads_as_zero(self):
        """Forced inherited time means Node.time short-circuits to 0 even with
        stored time_o/m/p."""
        n = make_node("G", type="Goal", time_mode='manual',
                       time_o=10, time_m=20, time_p=40)
        assert n.time == 0.0


# ============================================================================
# Node Model — time_mode validation
# ============================================================================

class TestTimeModeField:
    def test_default_is_manual(self):
        node = make_node()
        assert node.time_mode == 'manual'

    def test_inherited_accepted(self):
        node = make_node(time_mode='inherited')
        assert node.time_mode == 'inherited'

    def test_invalid_time_mode_defaults_to_manual(self):
        node = make_node(time_mode='auto')
        assert node.time_mode == 'manual'

    def test_time_mode_in_to_dict(self):
        node = make_node(time_mode='inherited')
        d = node.to_dict()
        assert d['time_mode'] == 'inherited'

    def test_time_mode_persisted_in_db(self, mgr):
        mgr.add_node(make_node("Inherited", time_mode='inherited'))
        node = mgr.get_node("Inherited")
        assert node.time_mode == 'inherited'

    def test_time_mode_manual_persisted_in_db(self, mgr):
        mgr.add_node(make_node("Manual", time_mode='manual'))
        node = mgr.get_node("Manual")
        assert node.time_mode == 'manual'

    def test_time_mode_updated(self, mgr):
        mgr.add_node(make_node("Node", time_mode='manual'))
        node = mgr.get_node("Node")
        node.time_mode = 'inherited'
        mgr.update_node(node)
        updated = mgr.get_node("Node")
        assert updated.time_mode == 'inherited'

    def test_inherited_preserves_omp_on_construction(self):
        # Preserved so a user who toggles inherited→manual gets their original
        # three-point estimate back. The .time property still returns 0 in
        # inherited mode, so the values are inert at read time.
        n = make_node(time_mode='inherited', time_o=10, time_m=20, time_p=30)
        assert n.time_o == 10.0 and n.time_m == 20.0 and n.time_p == 30.0

    def test_inherited_time_property_returns_zero(self):
        n = make_node(time_mode='inherited', time_o=10, time_m=20, time_p=30)
        assert n.time == 0.0

    def test_inherited_db_roundtrip_preserves_omp(self, mgr):
        mgr.add_node(make_node("Inh", time_mode='inherited', time_o=7, time_m=14, time_p=21))
        fetched = mgr.get_node("Inh")
        assert fetched.time_o == 7.0 and fetched.time_m == 14.0 and fetched.time_p == 21.0
        # And the property still reads as 0 — preservation is purely for the
        # round-trip when the user toggles back to manual.
        assert fetched.time == 0.0

    def test_toggle_inherited_to_manual_restores_estimates(self, mgr):
        """User adds a node with manual estimates, toggles to inherited, then
        back to manual — their original o/m/p must still be there."""
        mgr.add_node(make_node("Toggle", time_mode='manual',
                                time_o=2, time_m=4, time_p=8))
        # Toggle to inherited (preserving o/m/p in the form).
        node = mgr.get_node("Toggle")
        node.time_mode = 'inherited'
        mgr.update_node(node)
        # Toggle back to manual.
        node = mgr.get_node("Toggle")
        node.time_mode = 'manual'
        mgr.update_node(node)
        final = mgr.get_node("Toggle")
        assert final.time_mode == 'manual'
        assert final.time_o == 2.0 and final.time_m == 4.0 and final.time_p == 8.0
        # And the .time property now blends them as expected.
        assert final.time > 0.0


# ============================================================================
# Node Model — value_mode validation
# ============================================================================

class TestValueModeField:
    def test_default_is_manual(self):
        node = make_node()
        assert node.value_mode == 'manual'

    def test_inherited_accepted(self):
        node = make_node(value_mode='inherited')
        assert node.value_mode == 'inherited'

    def test_invalid_value_mode_defaults_to_manual(self):
        node = make_node(value_mode='auto')
        assert node.value_mode == 'manual'

    def test_value_mode_in_to_dict(self):
        node = make_node(value_mode='inherited')
        d = node.to_dict()
        assert d['value_mode'] == 'inherited'

    def test_value_mode_persisted_in_db(self, mgr):
        mgr.add_node(make_node("Inh", value_mode='inherited'))
        node = mgr.get_node("Inh")
        assert node.value_mode == 'inherited'

    def test_value_mode_manual_persisted_in_db(self, mgr):
        mgr.add_node(make_node("Man", value_mode='manual'))
        node = mgr.get_node("Man")
        assert node.value_mode == 'manual'

    def test_value_mode_updated(self, mgr):
        mgr.add_node(make_node("X", value_mode='manual'))
        node = mgr.get_node("X")
        node.value_mode = 'inherited'
        mgr.update_node(node)
        updated = mgr.get_node("X")
        assert updated.value_mode == 'inherited'

    def test_inherited_preserves_vid_on_construction(self):
        """v/i/d are preserved when value_mode='inherited' so a toggle back
        to 'manual' restores the user's original ratings. Mirrors the
        time_mode precedent."""
        n = make_node(value_mode='inherited', value=8, interest=9, difficulty=4)
        assert n.value == 8 and n.interest == 9 and n.difficulty == 4

    def test_inherited_zeroes_intrinsic_value(self):
        """`intrinsic_value()` returns 0 when value_mode='inherited' regardless
        of the underlying v/i/d ratings — the node becomes a pure structural
        conduit and contributes no own-IV bump to its descendants."""
        n = make_node(value_mode='inherited', value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 0.0

    def test_manual_uses_full_intrinsic_value(self):
        n = make_node(value_mode='manual', value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 20.0

    def test_inherited_db_roundtrip_preserves_vid(self, mgr):
        mgr.add_node(make_node("R", value_mode='inherited',
                                value=7, interest=8, difficulty=6))
        fetched = mgr.get_node("R")
        assert fetched.value == 7 and fetched.interest == 8 and fetched.difficulty == 6
        # And the IV reads as 0 — preservation is purely for the round-trip
        # when the user toggles back to manual.
        assert intrinsic_value(fetched, 1.0, 1.0) == 0.0

    def test_toggle_inherited_to_manual_restores_ratings(self, mgr):
        """Add manual, toggle to inherited, toggle back — original ratings still there."""
        mgr.add_node(make_node("T", value_mode='manual',
                                value=6, interest=7, difficulty=8))
        node = mgr.get_node("T")
        node.value_mode = 'inherited'
        mgr.update_node(node)
        node = mgr.get_node("T")
        node.value_mode = 'manual'
        mgr.update_node(node)
        final = mgr.get_node("T")
        assert final.value_mode == 'manual'
        assert final.value == 6 and final.interest == 7 and final.difficulty == 8
        # And the IV is back to its full value.
        assert intrinsic_value(final, 1.0, 1.0) == 13.0

    def test_independent_of_time_mode(self):
        """value_mode and time_mode are orthogonal flags."""
        n1 = make_node(time_mode='inherited', value_mode='manual',
                        value=5, interest=5)
        assert intrinsic_value(n1, 1.0, 1.0) == 10.0  # value still contributes
        assert n1.time == 0.0  # time still inherited

        n2 = make_node(time_mode='manual', value_mode='inherited',
                        value=5, interest=5)
        assert intrinsic_value(n2, 1.0, 1.0) == 0.0  # value zeroed
        assert n2.time > 0.0  # time still manual
