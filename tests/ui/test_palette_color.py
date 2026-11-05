"""Bars and badges keep the curated palette until a color is changed, and then
follow it, muted the way that color's default was."""
import pytest

from skilltree.store import settings
from skilltree.store.settings import DEFAULT_NODE_COLORS
from skilltree.ui.color import MAX_LIGHTNESS, hex_to_oklch, muted_like, oklch_to_hex
from skilltree.ui.styles import BADGE_PALETTE, badge_style, palette_color

TYPES = ("Goal", "Action", "Learn", "Resource", "Milestone")


def _set(name, color):
    settings.NODE_COLORS.set({**settings.NODE_COLORS.get(), name: color})


@pytest.mark.parametrize("color", ["#0d6efd", "#d3c41d", "#123456", "#ffffff", "#000000"])
def test_oklch_comes_back_where_it_started(color):
    assert oklch_to_hex(*hex_to_oklch(color)) == color


def test_short_hex_and_rubbish():
    assert hex_to_oklch("#fff") == hex_to_oklch("#ffffff")
    assert hex_to_oklch("red") is None and hex_to_oklch(None) is None


@pytest.mark.parametrize("name", TYPES)
def test_default_colors_are_exactly_the_palette(name):
    assert palette_color(name) == BADGE_PALETTE[name][0]


@pytest.mark.parametrize("name", TYPES)
def test_a_changed_color_changes_the_bar(name):
    _set(name, "#2e8b57")
    assert palette_color(name) != BADGE_PALETTE[name][0]


@pytest.mark.parametrize("name", TYPES)
def test_a_changed_color_gets_its_defaults_treatment(name):
    default, curated = DEFAULT_NODE_COLORS[name], BADGE_PALETTE[name][0]
    picked = "#2e8b57"
    _set(name, picked)
    from_l, from_c, _ = hex_to_oklch(default)
    to_l, to_c, _ = hex_to_oklch(curated)
    got_l, got_c, _ = hex_to_oklch(palette_color(name))
    start_l, start_c, _ = hex_to_oklch(picked)
    assert got_l == pytest.approx(start_l + to_l - from_l, abs=0.01)
    assert got_c == pytest.approx(start_c * to_c / from_c, abs=0.01)


def test_a_color_near_the_default_stays_near_the_palette():
    default, curated = DEFAULT_NODE_COLORS["Learn"], BADGE_PALETTE["Learn"][0]
    near = muted_like(f"{default[:3]}{int(default[3:5], 16) + 1:02x}{default[5:]}", default, curated)
    distance = [a - b for a, b in zip(hex_to_oklch(near), hex_to_oklch(curated))]
    assert all(abs(d) < 0.02 for d in distance)


def test_a_light_pick_stays_dark_enough_for_white_text():
    assert hex_to_oklch(muted_like("#fefefe", DEFAULT_NODE_COLORS["Learn"],
                                   BADGE_PALETTE["Learn"][0]))[0] <= MAX_LIGHTNESS + 0.005


@pytest.mark.parametrize("name", [*TYPES, "Priority", "Open", "Done", "Blocked"])
@pytest.mark.parametrize("color", ["#fefefe", "#ffee00", "#101010"])
def test_badge_text_is_always_white(name, color):
    _set("Goal" if name == "Priority" else name, color)
    assert badge_style(name)["color"] == "#ffffff"


def test_priority_follows_goal():
    _set("Goal", "#2e8b57")
    assert palette_color("Priority") == palette_color("Goal")


def test_what_no_setting_stands_behind_stays():
    assert palette_color("EdgeHard") == BADGE_PALETTE["EdgeHard"][0]
    assert palette_color("Nothing", "#6c757d") == "#6c757d"
    assert badge_style("Nothing")["backgroundColor"] == "#444"


def test_a_rubbish_setting_keeps_the_palette():
    _set("Learn", "not a color")
    assert palette_color("Learn") == BADGE_PALETTE["Learn"][0]
