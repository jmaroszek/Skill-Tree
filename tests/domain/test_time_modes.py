"""Time and value modes, and keeping the time fields in step."""
from skilltree.domain.time import (
    resolve_time_mode, resolve_value_mode, sync_time_fields,
)


# ============================================================================
# resolve_time_mode
# ============================================================================

class TestResolveTimeMode:
    """Goal/Milestone container types must always inherit time from children;
    other types follow habit > inherited > manual based on form widget state.
    """

    def test_goal_forces_inherited_no_form_values(self):
        assert resolve_time_mode('Goal', [], []) == 'inherited'

    def test_goal_forces_inherited_even_when_habit_on(self):
        # Form lock makes this state unreachable in the UI, but the resolver
        # must enforce the invariant for any caller (convert-type, programmatic).
        assert resolve_time_mode('Goal', [], ['habit']) == 'inherited'

    def test_goal_forces_inherited_even_when_inherited_off(self):
        # User toggled off (somehow); resolver still enforces.
        assert resolve_time_mode('Goal', [], []) == 'inherited'

    def test_milestone_forces_inherited_no_form_values(self):
        assert resolve_time_mode('Milestone', [], []) == 'inherited'

    def test_milestone_forces_inherited_even_when_habit_on(self):
        assert resolve_time_mode('Milestone', [], ['habit']) == 'inherited'

    def test_milestone_forces_inherited_even_when_inherited_explicit(self):
        assert resolve_time_mode('Milestone', ['inherited'], []) == 'inherited'

    def test_learn_default_manual(self):
        assert resolve_time_mode('Learn', [], []) == 'manual'

    def test_learn_inherited_when_toggled(self):
        assert resolve_time_mode('Learn', ['inherited'], []) == 'inherited'

    def test_learn_habit_when_toggled(self):
        assert resolve_time_mode('Learn', [], ['habit']) == 'habit'

    def test_learn_habit_wins_over_inherited(self):
        # Mutual exclusivity is enforced upstream by enforce_time_mode_exclusivity,
        # but if both arrive here somehow, habit wins (matches existing precedent
        # in the original branched logic).
        assert resolve_time_mode('Learn', ['inherited'], ['habit']) == 'habit'

    def test_action_and_resource_follow_learn_rules(self):
        assert resolve_time_mode('Action', [], []) == 'manual'
        assert resolve_time_mode('Action', ['inherited'], []) == 'inherited'
        assert resolve_time_mode('Resource', [], ['habit']) == 'habit'

    def test_unknown_type_defaults_to_manual(self):
        # Unknown / None types are treated like Learn (no special-case force).
        assert resolve_time_mode(None, [], []) == 'manual'
        assert resolve_time_mode('Unknown', [], []) == 'manual'

    def test_none_form_values_safe(self):
        # Defensive: callers might pass None instead of empty lists.
        assert resolve_time_mode('Learn', None, None) == 'manual'
        assert resolve_time_mode('Goal', None, None) == 'inherited'


class TestResolveValueMode:
    """Milestones always inherit value (transparent checkpoints). Goals do
    NOT — they carry their own value. Otherwise the toggle decides.
    """

    def test_milestone_forces_inherited_no_toggle(self):
        assert resolve_value_mode('Milestone', []) == 'inherited'

    def test_milestone_forces_inherited_even_when_toggle_off(self):
        # User somehow cleared the (locked) toggle; resolver still enforces.
        assert resolve_value_mode('Milestone', []) == 'inherited'

    def test_milestone_inherited_when_toggle_on(self):
        assert resolve_value_mode('Milestone', ['inherited']) == 'inherited'

    def test_goal_not_forced(self):
        # Unlike time_mode, Goals are NOT forced to inherit value.
        assert resolve_value_mode('Goal', []) == 'manual'

    def test_goal_inherited_when_toggled(self):
        assert resolve_value_mode('Goal', ['inherited']) == 'inherited'

    def test_learn_default_manual(self):
        assert resolve_value_mode('Learn', []) == 'manual'

    def test_learn_inherited_when_toggled(self):
        assert resolve_value_mode('Learn', ['inherited']) == 'inherited'

    def test_action_and_resource_follow_learn_rules(self):
        assert resolve_value_mode('Action', []) == 'manual'
        assert resolve_value_mode('Resource', ['inherited']) == 'inherited'

    def test_unknown_type_defaults_to_toggle(self):
        assert resolve_value_mode(None, []) == 'manual'
        assert resolve_value_mode('Unknown', ['inherited']) == 'inherited'

    def test_none_toggle_value_safe(self):
        assert resolve_value_mode('Learn', None) == 'manual'
        assert resolve_value_mode('Milestone', None) == 'inherited'


# ============================================================================
# sync_time_fields
# ============================================================================

class TestSyncTimeFields:
    def test_week_edit_fills_the_rest_and_leaves_the_week_alone(self):
        assert sync_time_fields('setting-hpw', 2.86, 20, 80, 1040) == (2.86, None, 80.0, 1040.0)

    def test_rounded_day_echo_does_not_overwrite_the_week(self):
        # 20h/week displays as 2.86 h/day; that echo must not turn 20 into 20.02.
        assert sync_time_fields('setting-hpd', 2.86, 20, 80, 1040) == (None, None, None, None)

    def test_a_real_day_edit_still_updates_the_week(self):
        assert sync_time_fields('setting-hpd', 3, 20, 80, 1040) == (None, 21.0, 84.0, 1092.0)

    def test_month_and_year_edits_fill_the_rest(self):
        assert sync_time_fields('setting-hpm', 2.86, 20, 80, 1040) == (2.86, 20.0, None, 1040.0)
        assert sync_time_fields('setting-hpy', 2.86, 20, 80, 1040) == (2.86, 20.0, 80.0, None)

    def test_blank_or_junk_input_changes_nothing(self):
        assert sync_time_fields('setting-hpw', None, None, None, None) == (None,) * 4
        assert sync_time_fields('setting-hpw', None, 'abc', None, None) == (None,) * 4
        assert sync_time_fields(None, 1, 2, 3, 4) == (None,) * 4

    def test_typing_20_reaches_a_fixed_point(self):
        """Feed each output back in as the trigger until nothing changes."""
        vals = {'setting-hpd': None, 'setting-hpw': 20, 'setting-hpm': None, 'setting-hpy': None}
        order = ['setting-hpd', 'setting-hpw', 'setting-hpm', 'setting-hpy']
        pending = ['setting-hpw']
        for _ in range(10):
            if not pending:
                break
            trig = pending.pop(0)
            out = sync_time_fields(trig, *(vals[k] for k in order))
            for k, v in zip(order, out):
                if v is not None and vals[k] != v:
                    vals[k] = v
                    pending.append(k)
        assert not pending
        assert (vals['setting-hpw'], vals['setting-hpm'], vals['setting-hpy']) == (20, 80.0, 1040.0)
