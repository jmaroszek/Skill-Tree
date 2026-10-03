"""Work time versus calendar time in the app's wording.

A day, week, month or year in a time estimate is the productive hours set in
Settings, not a stretch of the calendar. These pin the places that say so: the
tooltip text, which quotes the live hour rates, and the heading that carries it.
"""

import duration_ui
from config import ConfigManager
from duration_ui import time_estimates_heading, work_time_tooltip, work_time_unit_items

DEFAULT_RATES = {"hours_per_week": 20, "hours_per_month": 80}


def _text(component):
    """All the text under a Dash component, in order."""
    if isinstance(component, str):
        return component
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, (list, tuple)):
        children = [children]
    return " ".join(_text(child) for child in children)


class TestUnitsLine:
    def test_default_rates_read_in_hours(self):
        assert (work_time_unit_items(DEFAULT_RATES)
                == ["1 d = 2.9 h (day)", "1 w = 20 h (week)", "1 m = 80 h (month)",
                    "1 y = 1,040 h (year)"])

    def test_a_tuned_rate_flows_through(self):
        items = work_time_unit_items({"hours_per_week": 35, "hours_per_month": 140})
        assert items == ["1 d = 5 h (day)", "1 w = 35 h (week)", "1 m = 140 h (month)",
                         "1 y = 1,820 h (year)"]

    def test_the_app_reads_the_saved_settings(self, temp_database):
        settings = dict(ConfigManager.get_time_settings())
        settings.update(hours_per_week=10, hours_per_month=40)
        ConfigManager.set_time_settings(settings)
        assert (work_time_unit_items()
                == ["1 d = 1.4 h (day)", "1 w = 10 h (week)", "1 m = 40 h (month)",
                    "1 y = 520 h (year)"])


class TestTooltipText:
    def test_estimate_says_work_time_and_quotes_the_rates(self):
        text = _text(work_time_tooltip("estimate", DEFAULT_RATES))
        assert "not calendar time" in text
        assert "1 w = 20 h" in text
        assert "Expected" not in text
        assert "seventh" not in text

    def test_habit_separates_calendar_duration_from_work_minutes(self):
        text = _text(work_time_tooltip("habit"))
        assert "Duration is calendar time" in text
        assert "Minutes per session is work time" in text
        assert "1 w =" not in text

    def test_actual_asks_for_work_time_and_not_the_bracket_mean(self):
        text = _text(work_time_tooltip("actual", DEFAULT_RATES))
        assert "Enter work time" in text
        assert "1 w = 20 h" in text
        assert "Expected" not in text


class TestHeading:
    def test_the_heading_carries_a_hover_not_an_info_button(self):
        heading = time_estimates_heading("node")
        title, tooltip = heading.children
        assert title.children == "Time Estimates"
        assert tooltip.target == title.id == "node-time-heading"
        assert tooltip.id == "node-time-heading-tooltip"
        assert "info-btn" not in _text(heading)


def test_simulation_axis_titles_name_every_unit_as_work_time():
    assert set(duration_ui._UNIT_TITLES.values()) == {
        "Work hours", "Work days", "Work weeks", "Work months", "Work years"}
