"""Tests for habit-mode time estimation: conversion math, schema round-trip,
mode transitions, and validation.

Habit mode lets the user enter a (duration, intensity) breakdown that gets
converted to total hours and written into time_o/m/p. The breakdown is
preserved on the node so re-opening the editor restores the distributed
view, and is also preserved through manual/inherited toggles so the user
can switch back to habit mode without re-typing.
"""

import math

import pytest

from callback_helpers import (
    habit_to_hours, compute_habit_time_omp, handle_save,
    habit_editor_view, habit_preview_text, parse_habit_days,
)
from graph_manager import GraphManager
from models import Node


# ============================================================================
# habit_to_hours — pure conversion math
# ============================================================================

class TestHabitToHours:
    def test_min_per_day_six_weeks(self):
        # 6 weeks × 30 min/day = 42 days × 0.5 h = 21 h
        assert habit_to_hours(6, 'weeks', 30, 'min_per_day') == 21.0

    def test_min_per_week_six_weeks(self):
        # 6 weeks × 20 min/week = 6 × (20/60) h = 2.0 h
        assert habit_to_hours(6, 'weeks', 20, 'min_per_week') == 2.0

    def test_hr_per_day_six_weeks(self):
        # 6 weeks × 0.5 hr/day = 42 × 0.5 = 21 h
        assert habit_to_hours(6, 'weeks', 0.5, 'hr_per_day') == 21.0

    def test_hr_per_week_six_weeks(self):
        # 6 weeks × 1 hr/week = 6 h
        assert habit_to_hours(6, 'weeks', 1, 'hr_per_week') == 6.0

    def test_zero_duration(self):
        assert habit_to_hours(0, 'weeks', 30, 'min_per_day') == 0.0

    def test_zero_intensity(self):
        assert habit_to_hours(6, 'weeks', 0, 'min_per_day') == 0.0

    def test_none_inputs(self):
        assert habit_to_hours(None, 'weeks', 30, 'min_per_day') == 0.0
        assert habit_to_hours(6, 'weeks', None, 'min_per_day') == 0.0

    def test_days_unit(self):
        # 30 days × 30 min/day = 30 × 0.5 = 15 h
        assert habit_to_hours(30, 'days', 30, 'min_per_day') == 15.0

    def test_months_unit(self):
        # 1 month (30-day approx) × 30 min/day = 15 h
        assert habit_to_hours(1, 'months', 30, 'min_per_day') == 15.0

    def test_years_unit(self):
        # 1 year (365-day approx) × 30 min/day = 182.5 h
        assert habit_to_hours(1, 'years', 30, 'min_per_day') == 182.5

    def test_none_intensity_unit_defaults_to_min_per_day(self):
        # None falls back to 'min_per_day' via the `or` clause.
        assert habit_to_hours(6, 'weeks', 30, None) == 21.0


class TestComputeHabitTimeOmp:
    def test_pert_bands(self):
        # 6 weeks × (15/30/45) min/day → (10.5, 21, 31.5) h
        o, m, p = compute_habit_time_omp(6, 'weeks', 15, 30, 45, 'min_per_day')
        assert o == 10.5
        assert m == 21.0
        assert p == 31.5

    def test_zero_intensity_returns_zero_band(self):
        o, m, p = compute_habit_time_omp(6, 'weeks', 0, 0, 0, 'min_per_day')
        assert (o, m, p) == (0.0, 0.0, 0.0)

    def test_per_session_bands_with_days(self):
        # 6 weeks × (10/15/20) min × 3 days/wk → (3.0, 4.5, 6.0) h
        o, m, p = compute_habit_time_omp(
            6, 'weeks', 10, 15, 20, 'min_per_session', [0, 3, 4])
        assert (o, m, p) == (3.0, 4.5, 6.0)


# ============================================================================
# Per-session (weekday) cadence — the new Apple-style scheduler
# ============================================================================

class TestPerSessionCadence:
    def test_example_15min_three_days_six_weeks(self):
        # 6 weeks × 15 min × {Mon,Thu,Fri} = 6 × 3 × 0.25 h = 4.5 h
        assert habit_to_hours(6, 'weeks', 15, 'min_per_session', [0, 3, 4]) == 4.5

    def test_all_seven_days_equals_legacy_per_day(self):
        every_day = habit_to_hours(6, 'weeks', 30, 'min_per_session',
                                   [0, 1, 2, 3, 4, 5, 6])
        assert every_day == habit_to_hours(6, 'weeks', 30, 'min_per_day') == 21.0

    def test_no_days_selected_is_zero(self):
        assert habit_to_hours(6, 'weeks', 15, 'min_per_session', []) == 0.0
        assert habit_to_hours(6, 'weeks', 15, 'min_per_session', None) == 0.0

    def test_hours_per_session(self):
        # 2 weeks × 1 hr × 2 days/wk = 2 × 2 × 1 = 4.0 h
        assert habit_to_hours(2, 'weeks', 1, 'hr_per_session', [0, 1]) == 4.0

    def test_days_accepts_csv_string(self):
        assert habit_to_hours(6, 'weeks', 15, 'min_per_session', '0,3,4') == 4.5

    def test_days_unit_duration(self):
        # 14 days = 2 weeks × 15 min × 3 days/wk = 2 × 3 × 0.25 = 1.5 h
        assert habit_to_hours(14, 'days', 15, 'min_per_session', [0, 3, 4]) == 1.5


class TestParseHabitDays:
    def test_csv_string(self):
        assert parse_habit_days('0,3,4') == [0, 3, 4]

    def test_list_passthrough(self):
        assert parse_habit_days([1, 2]) == [1, 2]

    def test_none_defaults_to_all_seven(self):
        assert parse_habit_days(None) == [0, 1, 2, 3, 4, 5, 6]

    def test_drops_out_of_range(self):
        assert parse_habit_days('0,9,4,-1') == [0, 4]


class TestHabitEditorView:
    def test_per_day_maps_to_all_seven_unchanged(self):
        unit, o, m, p, days = habit_editor_view('min_per_day', 10, 20, 30, '0,3')
        assert unit == 'min_per_session'
        assert (o, m, p) == (10, 20, 30)
        assert days == [0, 1, 2, 3, 4, 5, 6]

    def test_per_week_spreads_across_seven_preserving_total(self):
        # 7 hr/week → minutes: 420 min/week / 7 days = 60 min/session.
        unit, o, m, p, days = habit_editor_view('hr_per_week', 7, 7, 7, None)
        assert unit == 'min_per_session'
        assert (o, m, p) == (60.0, 60.0, 60.0)
        assert days == [0, 1, 2, 3, 4, 5, 6]
        # Total is preserved: 7 hr/week = 60 min/session × 7 days.
        assert habit_to_hours(2, 'weeks', 60.0, 'min_per_session', days) == \
            habit_to_hours(2, 'weeks', 7, 'hr_per_week')

    def test_hours_per_session_converted_to_minutes(self):
        # A legacy hr_per_session node displays as minutes (×60).
        unit, o, m, p, days = habit_editor_view(
            'hr_per_session', 1, 1, 1, '0,3')
        assert unit == 'min_per_session'
        assert (o, m, p) == (60, 60, 60)
        assert days == [0, 3]

    def test_per_session_passthrough(self):
        unit, o, m, p, days = habit_editor_view(
            'min_per_session', 15, 15, 15, '0,3,4')
        assert unit == 'min_per_session'
        assert days == [0, 3, 4]


class TestHabitPreviewText:
    def test_per_session_preview(self):
        txt = habit_preview_text(6, 'weeks', 15, 'min_per_session', [0, 3, 4])
        assert '4.5 h' in txt
        assert '3 days/wk' in txt

    def test_zero_returns_empty(self):
        assert habit_preview_text(0, 'weeks', 15, 'min_per_session', [0]) == ""


# ============================================================================
# Node validation (__post_init__) — accept new mode + clamp invalid units
# ============================================================================

class TestNodePostInit:
    def _node(self, **overrides):
        defaults = dict(
            name='Test', type='Action', description='', value=5,
            time_o=0, time_m=0, time_p=0, interest=5, difficulty=5,
            status='Open', context='Mind',
        )
        defaults.update(overrides)
        return Node(**defaults)

    def test_habit_mode_accepted(self):
        n = self._node(time_mode='habit')
        assert n.time_mode == 'habit'

    def test_invalid_time_mode_falls_back_to_manual(self):
        n = self._node(time_mode='bogus')
        assert n.time_mode == 'manual'

    def test_invalid_duration_unit_falls_back_to_weeks(self):
        n = self._node(habit_duration_unit='fortnights')
        assert n.habit_duration_unit == 'weeks'

    def test_invalid_intensity_unit_falls_back_to_min_per_day(self):
        n = self._node(habit_intensity_unit='pulses_per_aeon')
        assert n.habit_intensity_unit == 'min_per_day'

    def test_per_session_units_accepted(self):
        assert self._node(habit_intensity_unit='min_per_session').habit_intensity_unit == 'min_per_session'
        assert self._node(habit_intensity_unit='hr_per_session').habit_intensity_unit == 'hr_per_session'

    def test_habit_days_default_all_seven(self):
        assert self._node().habit_days == '0,1,2,3,4,5,6'

    def test_habit_days_coerced_from_list_sorted_deduped(self):
        n = self._node(habit_days=[4, 0, 4, 3])
        assert n.habit_days == '0,3,4'

    def test_habit_days_drops_out_of_range(self):
        n = self._node(habit_days='0,9,4,-2')
        assert n.habit_days == '0,4'

    def test_habit_duration_coerced_to_float(self):
        n = self._node(habit_duration='6')
        assert n.habit_duration == 6.0

    def test_habit_intensity_coerced_to_float(self):
        n = self._node(
            habit_intensity_o='15', habit_intensity_m='30', habit_intensity_p='45',
        )
        assert (n.habit_intensity_o, n.habit_intensity_m, n.habit_intensity_p) == (
            15.0, 30.0, 45.0,
        )

    def test_node_time_property_unaffected_by_habit_mode(self):
        # Habit mode does NOT short-circuit Node.time — only inherited does.
        # When in habit mode, the caller has written computed time_o/m/p
        # so the PERT blend produces the right value.
        n = self._node(
            time_mode='habit',
            time_o=10.5, time_m=21.0, time_p=31.5,
        )
        # Should be a positive number near the PERT blend, not 0.
        assert n.time > 0


# ============================================================================
# Schema round-trip — DB persists all six habit fields and Node.time still works
# ============================================================================

class TestSchemaRoundTrip:
    def test_habit_node_persists_and_reads_back(self):
        mgr = GraphManager()
        original = Node(
            name='MeditatePractice', type='Action',
            description='Daily meditation 30 min', value=7,
            time_o=10.5, time_m=21.0, time_p=31.5,
            interest=8, difficulty=4, status='Open', context='Mind',
            time_mode='habit',
            habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=15.0, habit_intensity_m=30.0, habit_intensity_p=45.0,
            habit_intensity_unit='min_per_day',
        )
        mgr.add_node(original)
        roundtripped = mgr.get_node('MeditatePractice')
        assert roundtripped is not None
        assert roundtripped.time_mode == 'habit'
        assert roundtripped.habit_duration == 6.0
        assert roundtripped.habit_duration_unit == 'weeks'
        assert roundtripped.habit_intensity_o == 15.0
        assert roundtripped.habit_intensity_m == 30.0
        assert roundtripped.habit_intensity_p == 45.0
        assert roundtripped.habit_intensity_unit == 'min_per_day'
        # Node.time uses the stored time_o/m/p — habit mode doesn't zero them.
        assert roundtripped.time > 0

    def test_habit_days_persists_and_reads_back(self):
        mgr = GraphManager()
        mgr.add_node(Node(
            name='WeekdayHabit', type='Action', description='', value=5,
            time_o=3, time_m=4.5, time_p=6, interest=5, difficulty=5,
            status='Open', context='Mind',
            time_mode='habit', habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=10, habit_intensity_m=15, habit_intensity_p=20,
            habit_intensity_unit='min_per_session', habit_days='0,3,4',
        ))
        fetched = mgr.get_node('WeekdayHabit')
        assert fetched.habit_intensity_unit == 'min_per_session'
        assert fetched.habit_days == '0,3,4'

    def test_update_preserves_habit_breakdown(self):
        mgr = GraphManager()
        node = Node(
            name='ColdExposure', type='Action', description='', value=5,
            time_o=2, time_m=2, time_p=2, interest=5, difficulty=5,
            status='Open', context='Body',
            time_mode='habit',
            habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=10.0, habit_intensity_m=20.0, habit_intensity_p=30.0,
            habit_intensity_unit='min_per_week',
        )
        mgr.add_node(node)
        # Update the description; habit fields should survive untouched.
        node.description = 'Updated'
        mgr.update_node(node)
        fetched = mgr.get_node('ColdExposure')
        assert fetched.habit_intensity_unit == 'min_per_week'
        assert fetched.habit_duration == 6.0
        assert fetched.habit_intensity_m == 20.0


# ============================================================================
# Mode transitions — habit → manual → habit preserves the breakdown
# ============================================================================

class TestModeTransitions:
    def test_habit_to_manual_preserves_breakdown(self):
        mgr = GraphManager()
        node = Node(
            name='Habit1', type='Action', description='', value=5,
            time_o=21.0, time_m=21.0, time_p=21.0,
            interest=5, difficulty=5, status='Open', context='Mind',
            time_mode='habit',
            habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=30.0, habit_intensity_m=30.0, habit_intensity_p=30.0,
            habit_intensity_unit='min_per_day',
        )
        mgr.add_node(node)

        # Flip to manual without zeroing habit fields (mirrors the editor's
        # toggle-OFF behavior, which preserves breakdown for re-toggle).
        node.time_mode = 'manual'
        mgr.update_node(node)

        fetched = mgr.get_node('Habit1')
        assert fetched.time_mode == 'manual'
        assert fetched.habit_duration == 6.0
        assert fetched.habit_intensity_m == 30.0

    def test_inherited_to_habit_via_update(self):
        mgr = GraphManager()
        node = Node(
            name='Container', type='Goal', description='', value=5,
            time_o=0, time_m=0, time_p=0, interest=5, difficulty=5,
            status='Open', context='Mind', time_mode='inherited',
        )
        mgr.add_node(node)

        # Flip to habit mode with a fresh breakdown.
        node.time_mode = 'habit'
        node.habit_duration = 4.0
        node.habit_duration_unit = 'weeks'
        node.habit_intensity_o = 20
        node.habit_intensity_m = 30
        node.habit_intensity_p = 40
        node.habit_intensity_unit = 'min_per_day'
        node.time_o, node.time_m, node.time_p = compute_habit_time_omp(
            4.0, 'weeks', 20, 30, 40, 'min_per_day',
        )
        mgr.update_node(node)

        fetched = mgr.get_node('Container')
        assert fetched.time_mode == 'habit'
        assert fetched.time_m > 0  # 4 × 7 × 0.5 = 14h


# ============================================================================
# handle_save — habit kwargs flow through to the persisted Node
# ============================================================================

class TestHandleSaveWithHabit:
    def test_handle_save_persists_habit_kwargs(self):
        mgr = GraphManager()
        msg = handle_save(
            mgr,
            name='HabitTest', n_type='Action', desc='', val=5,
            time_o=21.0, time_m=21.0, time_p=21.0,
            interest=5, diff=5,
            status_done=[], context='Mind', subctx=None,
            obs_path=None, drive_path=None, website_path=None,
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            time_mode='habit',
            habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=30.0, habit_intensity_m=30.0, habit_intensity_p=30.0,
            habit_intensity_unit='min_per_day',
        )
        assert 'Added' in msg
        node = mgr.get_node('HabitTest')
        assert node.time_mode == 'habit'
        assert node.habit_duration == 6.0
        assert node.habit_intensity_unit == 'min_per_day'
        assert node.time_m == 21.0

    def test_handle_save_persists_habit_days(self):
        mgr = GraphManager()
        handle_save(
            mgr,
            name='WeekdaySave', n_type='Action', desc='', val=5,
            time_o=3.0, time_m=4.5, time_p=6.0,
            interest=5, diff=5,
            status_done=[], context='Mind', subctx=None,
            obs_path=None, drive_path=None, website_path=None,
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            time_mode='habit',
            habit_duration=6.0, habit_duration_unit='weeks',
            habit_intensity_o=10.0, habit_intensity_m=15.0, habit_intensity_p=20.0,
            habit_intensity_unit='min_per_session', habit_days=[0, 3, 4],
        )
        node = mgr.get_node('WeekdaySave')
        assert node.habit_intensity_unit == 'min_per_session'
        assert node.habit_days == '0,3,4'


# ============================================================================
# Migration idempotency — re-running init_db doesn't fail
# ============================================================================

class TestMigrationIdempotency:
    def test_double_init_db_does_not_raise(self):
        import database
        database._initialized = False
        database.init_db()
        # Reset the flag so the second call actually runs the DDL/migrations
        # (init_db short-circuits when _initialized is True).
        database._initialized = False
        database.init_db()  # should not raise even though columns exist
