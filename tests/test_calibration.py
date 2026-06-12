"""
Tests for the Time Calibration feature: the shared estimate blend, the
actual_time_* / calibration_dismissed columns, persistence round-trips,
the feature flag, and the review-cycle helpers.

Uses the temp-database fixture from conftest.py — never touches real data.
"""

import math
from typing import Any

import pytest

from models import Node, blend_time_estimate, STATUS_DONE, STATUS_OPEN
from graph_manager import GraphManager
from callback_helpers import handle_save, prior_node_for_completion
from config import ConfigManager
from callbacks import (
    _calibration_review_queue,
    _calibration_unit_for,
    _calibration_modal_text,
)


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
# blend_time_estimate — shared by Node.time and the captured actual time
# ============================================================================

class TestBlendTimeEstimate:
    def test_only_most_likely(self):
        assert blend_time_estimate(0, 5, 0) == 5

    def test_two_point_is_geometric_mean(self):
        # O and P only -> sqrt(O * P)
        assert blend_time_estimate(4, 0, 9) == math.sqrt(36)

    def test_all_missing_returns_one(self):
        assert blend_time_estimate(0, 0, 0) == 1.0

    def test_none_arguments_treated_as_zero(self):
        assert blend_time_estimate(None, None, None) == 1.0
        assert blend_time_estimate(None, 7, None) == 7

    def test_three_point_low_uncertainty_is_arithmetic(self):
        # ratio P/O == 1 -> pure arithmetic PERT mean (2+4*2+2)/6 == 2.0
        assert blend_time_estimate(2, 2, 2) == 2.0

    def test_three_point_blend_within_bounds(self):
        result = blend_time_estimate(2, 4, 16)
        assert 2 <= result <= 16


class TestNodeTimeDelegates:
    def test_manual_node_uses_blend(self):
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
                    [], "Mind", None, "", "", "",
                    [], [], [], [], [])

        saved = mgr.get_node("Existing")
        assert saved.description == "edited desc"
        assert saved.actual_time_lower == 5.0
        assert saved.actual_time_point == 12.0
        assert saved.actual_time_upper == 30.0
        assert saved.actual_time_unit == "hours"
        assert saved.calibration_dismissed == 1


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
        hy = ConfigManager.HOURS_PER_YEAR_MULT * hm
        return hw, hm, hy

    def test_small_estimate_is_hours(self):
        hw, _, _ = self._bands()
        assert _calibration_unit_for(hw / 2) == "hours"

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
