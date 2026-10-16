"""
Tests for the Time Calibration feature: the shared estimate blend, the
actual_time_* / calibration_dismissed columns, persistence round-trips,
the feature flag, and the review-cycle helpers.

Uses the temp-database fixture from conftest.py — never touches real data.
"""

from typing import Any

import pytest

from skilltree.domain.models import Node, expected_time_estimate, STATUS_DONE, STATUS_OPEN
from skilltree.store.graph.manager import GraphManager
from skilltree.store.commands import handle_save, prior_node_for_completion
from skilltree.store.settings import ConfigManager
from skilltree.features.editor.values import (
    _calibration_prepop,
    _calibration_review_queue,
    _calibration_unit_for,
    _calibration_modal_text,
)
from skilltree.domain.time import HOURS_PER_YEAR_MULT


@pytest.fixture
def mgr() -> GraphManager:
    """A GraphManager pointing at the per-test temp database."""
    return GraphManager()


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


# ============================================================================
# expected_time_estimate — shared by Node.time and the captured actual time
# ============================================================================

class TestExpectedTimeEstimate:
    def test_only_most_likely(self):
        assert expected_time_estimate(0, 5, 0) == 5

    def test_two_point_fills_middle_with_geometric_mean(self):
        # O and P only -> middle becomes sqrt(O*P)=6, then Swanson weights it.
        assert expected_time_estimate(4, 0, 9) == round(.3*4 + .4*6 + .3*9, 2)

    def test_all_missing_returns_one(self):
        assert expected_time_estimate(0, 0, 0) == 1.0

    def test_none_arguments_treated_as_zero(self):
        assert expected_time_estimate(None, None, None) == 1.0
        assert expected_time_estimate(None, 7, None) == 7

    def test_collapsed_bracket_returns_that_value(self):
        assert expected_time_estimate(2, 2, 2) == 2.0

    def test_three_point_is_swanson_weighted(self):
        assert expected_time_estimate(2, 4, 16) == round(.3*2 + .4*4 + .3*16, 2)

    def test_three_point_within_bounds(self):
        assert 2 <= expected_time_estimate(2, 4, 16) <= 16


class TestNodeTimeDelegates:
    def test_manual_node_uses_estimate(self):
        node = _make_node(time_o=0, time_m=5, time_p=0)
        assert node.time == 5

    def test_inherited_node_has_zero_time(self):
        node = _make_node(time_mode="inherited")
        assert node.time == 0.0


# ============================================================================
# calibration_dismissed field
# ============================================================================

class TestCalibrationDismissedField:
    def test_defaults_to_zero(self):
        assert _make_node().calibration_dismissed == 0

    def test_explicit_value(self):
        assert _make_node(calibration_dismissed=1).calibration_dismissed == 1

    def test_truthy_value_coerced_to_int(self):
        assert _make_node(calibration_dismissed=True).calibration_dismissed == 1

    def test_none_coerced_to_zero(self):
        assert _make_node(calibration_dismissed=None).calibration_dismissed == 0


# ============================================================================
# Persistence — new columns round-trip through the database
# ============================================================================

class TestCalibrationPersistence:
    def test_new_node_defaults(self, mgr):
        mgr.add_node(_make_node("Fresh"))
        node = mgr.get_node("Fresh")
        assert node.actual_time_lower is None
        assert node.actual_time_point is None
        assert node.actual_time_upper is None
        assert node.actual_time_unit is None
        assert node.calibration_dismissed == 0

    def test_actual_time_round_trip(self, mgr):
        node = _make_node("Logged")
        node.actual_time_lower = 10.0
        node.actual_time_point = 20.0
        node.actual_time_upper = 40.0
        node.actual_time_unit = "hours"
        mgr.add_node(node)

        fetched = mgr.get_node("Logged")
        assert fetched.actual_time_lower == 10.0
        assert fetched.actual_time_point == 20.0
        assert fetched.actual_time_upper == 40.0
        assert fetched.actual_time_unit == "hours"

    def test_update_node_persists_actual_time(self, mgr):
        mgr.add_node(_make_node("Edit"))
        node = mgr.get_node("Edit")
        node.actual_time_point = 33.0
        node.actual_time_unit = "weeks"
        mgr.update_node(node)

        assert mgr.get_node("Edit").actual_time_point == 33.0
        assert mgr.get_node("Edit").actual_time_unit == "weeks"

    def test_update_node_persists_dismissed_flag(self, mgr):
        mgr.add_node(_make_node("Dismissable"))
        node = mgr.get_node("Dismissable")
        node.calibration_dismissed = 1
        mgr.update_node(node)
        assert mgr.get_node("Dismissable").calibration_dismissed == 1

    def test_reflection_notes_round_trip(self, mgr):
        mgr.add_node(_make_node("Noted"))
        node = mgr.get_node("Noted")
        assert node.reflect_notes is None
        node.reflect_notes = "Email triage took longer than planned."
        mgr.update_node(node)
        assert mgr.get_node("Noted").reflect_notes == "Email triage took longer than planned."


class TestHandleSavePreservesCalibration:
    """The editor form has no actual-time inputs, so handle_save must carry
    those fields (and the dismiss flag) over from the existing row."""

    def test_editor_save_preserves_actual_time_and_dismiss(self, mgr):
        node = _make_node("Existing")
        node.actual_time_lower = 5.0
        node.actual_time_point = 12.0
        node.actual_time_upper = 30.0
        node.actual_time_unit = "hours"
        node.calibration_dismissed = 1
        mgr.add_node(node)

        # Simulate an editor save (no actual-time fields in the form).
        handle_save(mgr, "Existing", "Learn", "edited desc", 6, 1, 2, 4, 5, 5,
                    [], "Mind", None, None,
                    [], [], [], [], [])

        saved = mgr.get_node("Existing")
        assert saved.description == "edited desc"
        assert saved.actual_time_lower == 5.0
        assert saved.actual_time_point == 12.0
        assert saved.actual_time_upper == 30.0
        assert saved.actual_time_unit == "hours"
        assert saved.calibration_dismissed == 1

    def test_editor_save_preserves_reflection_notes(self, mgr):
        node = _make_node("Reflected")
        node.reflect_notes = "Learned to batch."
        mgr.add_node(node)

        handle_save(mgr, "Reflected", "Learn", "edited desc", 6, 1, 2, 4, 5, 5,
                    [], "Mind", None, None,
                    [], [], [], [], [])

        assert mgr.get_node("Reflected").reflect_notes == "Learned to batch."


# ============================================================================
# Feature flag
# ============================================================================

class TestTimeCalibrationFlag:
    def test_defaults_enabled(self):
        assert ConfigManager.get_time_calibration_enabled() is True

    def test_set_and_get(self):
        ConfigManager.set_time_calibration_enabled(False)
        assert ConfigManager.get_time_calibration_enabled() is False
        ConfigManager.set_time_calibration_enabled(True)
        assert ConfigManager.get_time_calibration_enabled() is True


# ============================================================================
# _calibration_review_queue — eligibility for the review cycle
# ============================================================================

class TestCalibrationReviewQueue:
    def test_done_unrated_node_is_eligible(self, mgr):
        mgr.add_node(_make_node("DoneA", status=STATUS_DONE))
        assert _calibration_review_queue(mgr) == ["DoneA"]

    def test_open_node_excluded(self, mgr):
        mgr.add_node(_make_node("OpenA", status=STATUS_OPEN))
        assert _calibration_review_queue(mgr) == []

    def test_node_with_actual_time_excluded(self, mgr):
        node = _make_node("Rated", status=STATUS_DONE)
        node.actual_time_point = 12.0
        mgr.add_node(node)
        assert _calibration_review_queue(mgr) == []

    def test_dismissed_node_excluded(self, mgr):
        node = _make_node("Dismissed", status=STATUS_DONE)
        node.calibration_dismissed = 1
        mgr.add_node(node)
        assert _calibration_review_queue(mgr) == []

    def test_inherited_time_node_excluded(self, mgr):
        # Inherited-time nodes have no own estimate (time == 0) — nothing to
        # calibrate against.
        mgr.add_node(_make_node("Container", status=STATUS_DONE,
                                type="Goal", time_mode="inherited"))
        assert _calibration_review_queue(mgr) == []

    def test_queue_sorted_by_name(self, mgr):
        mgr.add_node(_make_node("Zeta", status=STATUS_DONE))
        mgr.add_node(_make_node("Alpha", status=STATUS_DONE))
        mgr.add_node(_make_node("Mu", status=STATUS_DONE))
        assert _calibration_review_queue(mgr) == ["Alpha", "Mu", "Zeta"]


# ============================================================================
# _calibration_unit_for — default Unit dropdown value
# ============================================================================

class TestCalibrationUnitFor:
    """Band boundaries are derived from the configured time settings so the
    tests hold regardless of the hours-per-week / -month values."""

    @staticmethod
    def _bands():
        s = ConfigManager.get_time_settings()
        hw = s.get('hours_per_week', 40)
        hm = s.get('hours_per_month', 160)
        hy = HOURS_PER_YEAR_MULT * hm
        return hw, hm, hy

    def test_small_estimate_is_hours(self):
        hw, _, _ = self._bands()
        assert _calibration_unit_for(hw / 14) == "hours"

    def test_day_scale_estimate_is_days(self):
        hw, _, _ = self._bands()
        assert _calibration_unit_for(hw / 2) == "days"

    def test_week_scale_estimate_is_weeks(self):
        hw, hm, _ = self._bands()
        assert _calibration_unit_for((hw + hm) / 2) == "weeks"

    def test_month_scale_estimate_is_months(self):
        _, hm, hy = self._bands()
        assert _calibration_unit_for((hm + hy) / 2) == "months"

    def test_year_scale_capped_to_months(self):
        # The dropdown offers only hours/weeks/months — years cap to months.
        _, _, hy = self._bands()
        assert _calibration_unit_for(hy * 2) == "months"

    def test_zero_estimate_is_hours(self):
        assert _calibration_unit_for(0) == "hours"


# ============================================================================
# _calibration_modal_text — (title, prompt) for the modal
# ============================================================================

class TestCalibrationModalText:
    def test_title_is_node_name(self):
        title, _ = _calibration_modal_text(_make_node("Stoicism"))
        assert title == "Stoicism"

    def test_prompt_recalls_estimate(self):
        node = _make_node("Estimated", time_o=0, time_m=80, time_p=0)
        _, prompt = _calibration_modal_text(node)
        assert "You estimated" in prompt
        assert "How long did it actually take?" in prompt

    def test_prompt_without_estimate_is_plain(self):
        node = _make_node("Container", type="Goal", time_mode="inherited")
        _, prompt = _calibration_modal_text(node)
        assert prompt == "How long did it actually take?"


class TestCalibrationPrepopulation:
    def test_lifecycle_dates_do_not_create_an_actual_time_suggestion(self):
        node = _make_node(
            "Completed",
            status=STATUS_DONE,
            time_o=0,
            time_m=80,
            time_p=0,
            start_date="2026-01-01",
            done_date="2026-02-01",
        )

        lower, point, upper, unit, value, interest, difficulty, notes = (
            _calibration_prepop(node)
        )

        assert (lower, point, upper) == (None, None, None)
        assert unit == _calibration_unit_for(node.time)
        assert (value, interest, difficulty) == (5, 5, 5)
        assert notes == ""

    def test_saved_notes_come_back(self):
        node = _make_node("Rated", status=STATUS_DONE, reflect_notes="Slower than hoped.")
        assert _calibration_prepop(node)[-1] == "Slower than hoped."

    def test_saved_ratings_come_back_instead_of_the_estimates(self):
        # A ratings-only reflection stays in the review queue. Prefilled with
        # the estimates, its next Submit wrote them over the saved answers.
        node = _make_node("Units", status=STATUS_DONE, value=7, interest=6,
                          difficulty=4, reflect_value=9, reflect_interest=3,
                          reflect_difficulty=8)
        assert _calibration_prepop(node)[4:7] == (9, 3, 8)

    def test_a_rating_left_unsaved_starts_at_the_estimate(self):
        node = _make_node("Units", status=STATUS_DONE, value=7, interest=6,
                          difficulty=4, reflect_value=9)
        assert _calibration_prepop(node)[4:7] == (9, 6, 4)

    def test_saved_actual_times_come_back_in_a_fitting_unit(self):
        # A node reopened and finished again keeps its first finish's times.
        ConfigManager.set_time_settings({'hours_per_week': 20, 'hours_per_month': 80})
        node = _make_node("Again", status=STATUS_DONE, time_o=1, time_m=2, time_p=4,
                          actual_time_lower=40.0, actual_time_point=56.0)

        lower, point, upper, unit = _calibration_prepop(node)[:4]

        assert unit == _calibration_unit_for(56.0) == "weeks"
        assert (lower, point, upper) == (2.0, 2.8, None)


# ============================================================================
# prior_node_for_completion — the Done-transition pre-check in core_engine
# ============================================================================

class TestPriorNodeForCompletion:
    def test_existing_node_found_by_current_name(self, mgr):
        mgr.add_node(_make_node("Stoicism", status=STATUS_DONE))
        node = prior_node_for_completion(mgr, "Stoicism", "Stoicism")
        assert node is not None and node.status == STATUS_DONE

    def test_rename_falls_back_to_original_name(self, mgr):
        # Regression: renaming a Done node ("FIRE app" → "FIRE App") must not
        # be misread as a brand-new completion — the rename hasn't been
        # committed yet when the completion check runs, so the lookup has to
        # fall back to the pre-save name.
        mgr.add_node(_make_node("FIRE app", status=STATUS_DONE))
        node = prior_node_for_completion(mgr, "FIRE App", "FIRE app")
        assert node is not None and node.status == STATUS_DONE

    def test_brand_new_node_returns_none(self, mgr):
        assert prior_node_for_completion(mgr, "Fresh Node", None) is None

    def test_rename_of_open_node_reports_open(self, mgr):
        mgr.add_node(_make_node("draft", status=STATUS_OPEN))
        node = prior_node_for_completion(mgr, "Draft", "draft")
        assert node is not None and node.status == STATUS_OPEN


class TestCalibrationModalLayout:
    def test_ratings_come_before_time_then_notes(self):
        from skilltree.features.review.layout import build_time_calibration_modal
        text = repr(build_time_calibration_modal())
        order = [text.index(marker) for marker in
                 ("calibration-value", "time-calibration-lower", "calibration-notes")]
        assert order == sorted(order)


# --- Submitted actual times: order, zeros, and an unchanged Submit ---------

@pytest.mark.parametrize("entered, expected", [
    ((2, 3, 5), (2.0, 3.0, 5.0)),
    ((5, 3, 2), (2.0, 3.0, 5.0)),       # typed back to front
    ((5, None, 2), (2.0, None, 5.0)),   # two-point, reversed
    ((0, 3, -1), (None, 3.0, None)),    # zero and negative are no data
    (("", None, float("nan")), (None, None, None)),
])
def test_actual_bracket_hours(entered, expected):
    from skilltree.domain.time import actual_bracket_hours
    assert actual_bracket_hours(entered, 1.0) == expected


def test_an_unchanged_submit_keeps_the_stored_hours():
    from skilltree.domain.time import actual_bracket_hours
    stored = (20 / 7, 40 / 7, None)   # shown in days as 1.0 and 2.0 at 20/7 h a day
    shown = tuple(None if h is None else round(h / (20 / 7), 2) for h in stored)

    assert actual_bracket_hours(shown, 20 / 7, stored) == stored
    # A changed field is written as typed.
    assert actual_bracket_hours((1.0, 3.0, None), 20 / 7, stored) == (
        stored[0], 3.0 * 20 / 7, None)


def test_recorded_zeros_are_no_actual_time():
    item = Node(name="Z", type="Learn", description="", value=5, time_o=1,
                time_m=2, time_p=4, interest=5, difficulty=5, status="Done",
                context="Mind", actual_time_lower=0, actual_time_point=0,
                actual_time_upper=0)
    assert item.actual_time is None


# ============================================================================
# Milestones reflect in notes alone
# ============================================================================

@pytest.fixture
def calibration_handlers(monkeypatch):
    import dash
    from skilltree.features.review import calibration as calibration_callbacks
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    calibration_callbacks.register_calibration_callbacks(app)
    handlers = {}
    for spec in app.callback_map.values():
        fn = spec.get('callback')
        while hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__
        if fn is not None:
            handlers[fn.__name__] = fn
    return handlers


class TestMilestoneReflection:
    def test_milestone_reflects_in_notes_only(self, mgr):
        from skilltree.features.editor.values import reflects_in_notes_only
        assert reflects_in_notes_only(_make_node("M", type="Milestone", time_mode='inherited'))
        assert not reflects_in_notes_only(_make_node("A", type="Action"))
        assert not reflects_in_notes_only(None)

    def test_modal_hides_ratings_and_time_for_a_milestone(self, mgr, calibration_handlers):
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited', status=STATUS_DONE))
        mgr.add_node(_make_node("A", type="Action", status=STATUS_DONE))
        show = calibration_handlers['show_estimated_ratings']
        hidden = {"display": "none"}
        ratings, time_section, placeholder = show({'mode': 'single', 'node': 'M'})
        assert (ratings, time_section) == (hidden, hidden)
        assert "project" not in placeholder
        ratings, time_section, placeholder = show({'mode': 'single', 'node': 'A'})
        assert ratings != hidden and time_section == {}
        assert "project" in placeholder

    def test_submit_saves_only_the_notes(self, mgr, calibration_handlers, monkeypatch):
        from skilltree.features.review import calibration as calibration_callbacks
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited', status=STATUS_DONE))
        monkeypatch.setattr(calibration_callbacks, 'get_trigger_id',
                            lambda: 'btn-time-calibration-submit')
        result = calibration_handlers['handle_time_calibration'](
            1, 0, 0, 3, 4, 5, 'hours', 5, 5, 5, "  Hit it in week 4.  ",
            {'mode': 'single', 'node': 'M'})
        saved = mgr.get_node("M")
        assert saved.reflect_notes == "Hit it in week 4."
        assert saved.reflect_value is None and saved.reflect_interest is None
        assert saved.reflect_difficulty is None
        assert saved.actual_time is None
        assert result[2] == "Logged reflection for 'M'."
