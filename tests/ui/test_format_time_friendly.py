"""Hours shown in the friendliest unit."""
from skilltree.store import settings
from skilltree.ui.components.duration import format_time_friendly, time_unit


# ============================================================================
# Settings — format_time_friendly
# ============================================================================

class TestFormatTimeFriendly:
    def test_zero_hours(self):
        assert format_time_friendly(0) == "0h"

    def test_none_hours(self):
        assert format_time_friendly(None) == "0h"

    def test_negative_hours(self):
        assert format_time_friendly(-5) == "0h"

    def test_small_hours(self):
        result = format_time_friendly(1.2)
        assert result == "1.2h"

    def test_integer_hours_no_decimal(self):
        result = format_time_friendly(1.0)
        assert result == "1h"  # Should not show ".0"

    def test_exactly_one_week(self):
        hw = settings.TIME_SETTINGS.get().get('hours_per_week', 40)
        result = format_time_friendly(float(hw))
        assert "w" in result

    def test_exactly_one_month(self):
        hm = settings.TIME_SETTINGS.get().get('hours_per_month', 160)
        result = format_time_friendly(float(hm))
        assert "m" in result

    def test_weeks_format(self):
        # With default 40h/week, 80h = 2w
        settings.TIME_SETTINGS.set({'hours_per_week': 40, 'hours_per_month': 160})
        result = format_time_friendly(80.0)
        assert result == "2w"

    def test_months_format(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 40, 'hours_per_month': 160})
        result = format_time_friendly(320.0)
        assert result == "2m"

    def test_years_format(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 40, 'hours_per_month': 160})
        # 13 months = 1 year; 2 years = 26 months = 4160 hours
        result = format_time_friendly(4160.0)
        assert result == "2y"

    def test_exactly_one_year(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
        # 1 year = 13 × 80 = 1040h
        result = format_time_friendly(1040.0)
        assert result == "1y"

    def test_year_threshold_just_under(self):
        # Just below 1 year should still display as months.
        settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
        result = format_time_friendly(1039.0)
        assert result.endswith("m")

    def test_integer_argument_all_branches(self):
        """Regression: callers (e.g. the Analyze throughput axis-tick
        generator) pass plain ints. round(int, 1) returns an int, and
        int.is_integer() doesn't exist before Python 3.12 — so on the app's
        3.10 runtime an int argument used to raise AttributeError and 500 the
        Analyze tab. Every magnitude branch must accept an int."""
        settings.TIME_SETTINGS.set({'hours_per_week': 35, 'hours_per_month': 140})
        assert format_time_friendly(4) == "4h"      # hours branch
        assert format_time_friendly(10) == "2d"     # days branch
        assert format_time_friendly(70) == "2w"     # weeks branch
        assert format_time_friendly(280) == "2m"    # months branch
        assert format_time_friendly(3640) == "2y"   # years branch
        # force_one_decimal path with an int must also not raise.
        assert format_time_friendly(4, force_one_decimal=True) == "4.0h"

    def test_time_unit_is_the_unit_format_time_friendly_uses(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
        assert time_unit(0) == (1.0, "h")
        assert time_unit(2.8) == (1.0, "h")
        assert time_unit(20 / 7) == (20 / 7, "d")
        assert time_unit(19.9) == (20 / 7, "d")
        assert time_unit(20) == (20.0, "w")
        assert time_unit(80) == (80.0, "m")
        assert time_unit(1040) == (1040.0, "y")
        for hours in (2, 8, 45, 300, 2500):
            size, suffix = time_unit(hours)
            assert format_time_friendly(hours).endswith(suffix)
