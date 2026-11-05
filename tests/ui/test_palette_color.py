"""Bars and badges use the node colors, so a color means one thing everywhere."""
import pytest

from skilltree.store import settings
from skilltree.ui.styles import BADGE_PALETTE, badge_style, palette_color

TYPES = ("Goal", "Action", "Learn", "Resource", "Milestone")
STATUSES = ("Open", "Done", "Blocked")


def _set(name, color):
    settings.NODE_COLORS.set({**settings.NODE_COLORS.get(), name: color})


@pytest.mark.parametrize("name", [*TYPES, *STATUSES, "Now"])
def test_a_bar_and_a_badge_are_the_node_color(name):
    assert palette_color(name) == settings.default_node_colors()[name]
    _set(name, "#2e8b57")
    assert palette_color(name) == "#2e8b57"
    assert badge_style(name)["backgroundColor"] == "#2e8b57"


@pytest.mark.parametrize("name", [*TYPES, *STATUSES, "Now", "Priority", "EventTriggered"])
def test_badge_text_on_a_node_color_is_white(name):
    assert badge_style(name)["color"] == "#ffffff"


def test_priority_follows_goal():
    _set("Goal", "#2e8b57")
    assert palette_color("Priority") == "#2e8b57"


def test_a_fired_event_follows_done():
    _set("Done", "#2e8b57")
    assert palette_color("EventTriggered") == "#2e8b57"


def test_what_has_no_node_color_stays_in_the_palette():
    assert palette_color("EdgeHard") == BADGE_PALETTE["EdgeHard"][0]
    assert badge_style("EdgeHard")["color"] == BADGE_PALETTE["EdgeHard"][1]
    assert palette_color("Nothing", "#6c757d") == "#6c757d"
    assert badge_style("Nothing")["backgroundColor"] == "#444"
