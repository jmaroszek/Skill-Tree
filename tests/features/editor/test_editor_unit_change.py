"""Changing an estimate's unit keeps the estimate.

The numbers were rounded to two decimals, whatever their size. 100 hours became
0.1 years, which is 104 hours on the way back, and a few hours became 0 years.
"""
import pytest

from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.values import reexpressed_estimate
from skilltree.store import settings
from support.callbacks import registered


def _convert(new_unit, value, prev_unit):
    fn = registered(register_editor_callbacks)["convert_time_unit"]
    return fn(new_unit, value, value, value, prev_unit)[1]


@pytest.mark.parametrize("value, shown", [
    (0, 0), (None, 0),
    (40.0, 40),
    (12.3456, 12.35),
    (1234.5678, 1234.57),
    (0.5, 0.5),
    (0.123456, 0.1235),
    (0.0012345, 0.001234),
])
def test_an_estimate_keeps_two_decimals_or_four_significant_digits(value, shown):
    assert reexpressed_estimate(value) == pytest.approx(shown, abs=1e-9)


@pytest.mark.parametrize("hours", [100, 3, 2.5, 1, 40])
@pytest.mark.parametrize("unit", ["days", "weeks", "months", "years"])
def test_there_and_back_gives_the_hours_it_started_with(hours, unit):
    assert _convert("hours", _convert(unit, hours, "hours"), unit) == hours


@pytest.mark.parametrize("hours", [1000, 1234, 7654])
@pytest.mark.parametrize("unit", ["days", "weeks", "months", "years"])
def test_a_long_estimate_there_and_back_moves_by_a_tiny_fraction(hours, unit):
    back = _convert("hours", _convert(unit, hours, "hours"), unit)

    assert back == pytest.approx(hours, rel=1e-3)


def test_a_small_estimate_in_a_large_unit_is_not_zero():
    years = _convert("years", 3, "hours")

    assert years > 0
    assert years * settings.time_multiplier("years") == pytest.approx(3, abs=0.01)
