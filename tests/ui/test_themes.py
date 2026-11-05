"""Each theme is complete, and keeps its own colors."""
import re

import pytest

from skilltree.domain.themes import DEFAULT_THEME, THEME_MINIMAL, THEME_STEEL, THEMES
from skilltree.features.settings.draft import apply_settings
from skilltree.shell import build_index_string, with_theme
from skilltree.store import settings
from skilltree.store.resources import get_sections
from skilltree.ui import styles
from support.paths import asset_file


def _token_names(path):
    return set(re.findall(r"^\s*(--[\w-]+):", path.read_text(encoding="utf-8"), re.M))


def test_steel_only_overrides_tokens_that_exist():
    extra = _token_names(asset_file("theme_steel.css")) - _token_names(asset_file("tokens.css"))
    assert not extra


def test_the_page_opens_in_the_stored_theme():
    assert '<html data-theme="steel">' in with_theme(build_index_string(), THEME_STEEL)


def test_the_theme_defaults_to_minimal_and_ignores_rubbish():
    assert settings.THEME.get() == DEFAULT_THEME == THEME_MINIMAL
    settings.THEME.set("neon")
    assert settings.THEME.get() == DEFAULT_THEME


def test_each_theme_keeps_its_own_node_colors():
    settings.THEME.set(THEME_STEEL)
    assert settings.NODE_COLORS.get() == settings.STEEL_NODE_COLORS
    settings.NODE_COLORS.set({**settings.NODE_COLORS.get(), "Goal": "#123456"})
    settings.THEME.set(THEME_MINIMAL)
    assert settings.NODE_COLORS.get() == settings.DEFAULT_NODE_COLORS
    assert settings.NODE_COLORS.for_theme(THEME_STEEL)["Goal"] == "#123456"


def test_colors_stored_before_themes_existed_belong_to_steel():
    settings.SETTINGS["NODE_COLORS"].set({**settings.STEEL_NODE_COLORS, "Milestone": "#21b1c4"})
    assert settings.NODE_COLORS.for_theme(THEME_STEEL)["Milestone"] == "#21b1c4"
    assert settings.NODE_COLORS.for_theme(THEME_MINIMAL)["Milestone"] == (
        settings.DEFAULT_NODE_COLORS["Milestone"])


def test_a_draft_saves_its_colors_under_the_theme_it_chose():
    apply_settings({
        "theme": THEME_STEEL,
        "colors": {**settings.STEEL_NODE_COLORS, "Goal": "#abcdef"},
        "resource_sections": get_sections(),
    })
    assert settings.THEME.get() == THEME_STEEL
    assert settings.NODE_COLORS.for_theme(THEME_STEEL)["Goal"] == "#abcdef"
    assert settings.NODE_COLORS.for_theme(THEME_MINIMAL) == settings.DEFAULT_NODE_COLORS


@pytest.mark.parametrize("theme", THEMES)
def test_bars_and_badges_are_exactly_the_themes_palette(theme):
    settings.THEME.set(theme)
    for name in ("Goal", "Learn", "Action", "Resource", "Milestone"):
        assert styles.palette_color(name) == styles.badge_palette()[name][0]


def test_every_theme_has_the_same_badges():
    settings.THEME.set(THEME_STEEL)
    steel = set(styles.badge_palette())
    assert steel == set(styles.BADGE_PALETTE)


def test_the_canvas_stylesheet_follows_the_theme():
    def synergy():
        rule = next(r for r in styles.stylesheet() if r["selector"] == '[type = "Helps"]')
        return rule["style"]["line-color"]

    minimal = synergy()
    settings.THEME.set(THEME_STEEL)
    assert synergy() != minimal


def test_switching_theme_does_not_store_its_defaults_as_picks():
    settings.THEME.set(THEME_STEEL)
    apply_settings({
        "theme": THEME_MINIMAL,
        "colors": settings.NODE_COLORS.for_theme(THEME_MINIMAL),
        "resource_sections": get_sections(),
    })
    assert settings.THEME.get() == THEME_MINIMAL
    assert settings.SETTINGS["NODE_COLORS_MINIMAL"].get() == settings.DEFAULT_NODE_COLORS
    from skilltree.store.settings import read_stored
    assert not read_stored("NODE_COLORS_MINIMAL")


@pytest.mark.parametrize("theme, accent", [(THEME_MINIMAL, "#889eaa"), (THEME_STEEL, "#0d6efd")])
def test_the_accent_matches_the_themes_token(theme, accent):
    settings.THEME.set(theme)
    assert styles.accent_color() == accent
    sheet = "tokens.css" if theme == THEME_MINIMAL else "theme_steel.css"
    assert f"--st-accent: {accent};" in asset_file(sheet).read_text(encoding="utf-8")
