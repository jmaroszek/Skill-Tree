"""Calendar-duration conversion: one forward rule, one inverse rule.

These used to be four hand-written copies of the same 7/30/365 arithmetic, and
the two inverses disagreed — the edit form knew about years while the dormant
table did not, so a one-year delay round-tripped as "365 days". The tests below
pin the shared rule from both directions so the pair cannot drift apart again.
"""

import pytest

from duration_ui import duration_to_days, days_to_duration, format_duration_days


# (days, form pair, display text)
CASES = [
    (0,   (0, "days"),      "None"),
    (1,   (1, "days"),      "1 day"),
    (2,   (2, "days"),      "2 days"),
    (7,   (1, "weeks"),     "1 week"),
    (14,  (2, "weeks"),     "2 weeks"),
    (30,  (1, "months"),    "1 month"),
    (60,  (2, "months"),    "2 months"),
    (365, (1, "years"),     "1 year"),
    (730, (2, "years"),     "2 years"),
]


@pytest.mark.parametrize("days,form,text", CASES)
def test_inverse_agrees_with_itself(days, form, text):
    assert days_to_duration(days) == form
    assert format_duration_days(days) == text


@pytest.mark.parametrize("days,form,_text", CASES)
def test_round_trip(days, form, _text):
    value, unit = form
    assert duration_to_days(value, unit) == days


@pytest.mark.parametrize("value,unit,days", [
    (1, "days", 1), (3, "weeks", 21), (4, "months", 120), (2, "years", 730),
])
def test_forward_multipliers(value, unit, days):
    assert duration_to_days(value, unit) == days


class TestGreedyButExact:
    """The inverse takes the largest unit that divides exactly — never an
    approximation. The form holds one number and one select, so a single unit
    is all it can carry."""

    def test_a_year_and_a_bit_stays_in_weeks(self):
        assert days_to_duration(700) == (100, "weeks")
        assert format_duration_days(700) == "100 weeks"

    def test_a_value_divisible_by_nothing_stays_in_days(self):
        assert days_to_duration(45) == (45, "days")
        assert format_duration_days(45) == "45 days"

    def test_a_year_is_not_three_hundred_and_sixty_five_days(self):
        # The regression this consolidation exists for: 365 % 30 == 5 and
        # 365 % 7 == 1, so the old display formatter fell through to days
        # while the edit form said "1 year".
        assert format_duration_days(365) == "1 year"


class TestDefensiveInputs:
    def test_none_and_blank_are_zero(self):
        assert duration_to_days(None, "weeks") == 0
        assert duration_to_days("", "years") == 0
        assert days_to_duration(None) == (0, "days")
        assert format_duration_days(None) == "None"

    def test_an_unrecognized_unit_is_read_as_days(self):
        assert duration_to_days(5, "fortnights") == 5

    def test_a_non_numeric_value_does_not_raise(self):
        assert duration_to_days("soon", "weeks") == 0

    def test_negatives_read_as_no_delay(self):
        assert days_to_duration(-3) == (0, "days")
        assert format_duration_days(-3) == "None"

    def test_the_zero_label_is_caller_supplied(self):
        assert format_duration_days(0, zero="—") == "—"
