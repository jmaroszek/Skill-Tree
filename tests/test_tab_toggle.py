"""Tests for the toggle_tab_content callback that drives tab visibility."""

import dash
import pytest
from event_callbacks import register_event_callbacks


TAB_IDS = ["tab-next", "tab-canvas", "tab-details", "tab-events", "tab-analyze"]

# index positions in the callback's 5-tuple output
TAB_INDEX = {
    "tab-next": 0,
    "tab-canvas": 1,
    "tab-details": 2,
    "tab-events": 3,
    "tab-analyze": 4,
}


def _toggle_fn():
    """Register event callbacks on a fresh Dash app and return the raw toggle function."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    key = [k for k in app.callback_map
           if "next-tab-content.style" in k and "canvas-tab-content.style" in k][0]
    cb = app.callback_map[key]["callback"]
    while hasattr(cb, "__wrapped__"):
        cb = cb.__wrapped__
    return cb


@pytest.mark.parametrize("active_tab", TAB_IDS)
def test_toggle_tab_content_only_target_visible(active_tab):
    fn = _toggle_fn()
    styles = fn(active_tab)
    assert len(styles) == 5
    for idx, style in enumerate(styles):
        is_target = idx == TAB_INDEX[active_tab]
        if is_target:
            assert style["display"] != "none", f"target tab {active_tab} should be visible (index {idx}): {style}"
            assert style["visibility"] == "visible"
        else:
            assert style["display"] == "none", f"non-target index {idx} should be hidden: {style}"
            assert style["visibility"] == "hidden"


@pytest.mark.parametrize("active_tab", TAB_IDS)
def test_toggle_tab_content_preserves_position_keys(active_tab):
    fn = _toggle_fn()
    styles = fn(active_tab)
    for style in styles:
        assert style.get("position") == "absolute"
        assert style.get("width") == "100%"
        assert style.get("height") == "100%"
        assert style.get("top") == "0"
        assert style.get("left") == "0"


def test_toggle_tab_content_returns_five_styles():
    fn = _toggle_fn()
    styles = fn("tab-next")
    assert isinstance(styles, tuple) and len(styles) == 5
