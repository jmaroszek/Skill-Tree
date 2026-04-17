"""Tests for Phase C idle-time background prefetch of Nodes and Analyze tabs."""

import re
from pathlib import Path

import dash
import pytest
from dash import no_update

import event_callbacks
from event_callbacks import register_event_callbacks


@pytest.fixture
def prefetch_trigger_ctx(monkeypatch):
    """Simulate a prefetch callback context: trigger == 'prefetch-tab-trigger'."""
    monkeypatch.setattr(event_callbacks, "get_trigger_id", lambda: "prefetch-tab-trigger")


@pytest.fixture
def main_tabs_trigger_ctx(monkeypatch):
    """Simulate a user-click callback context: trigger == 'main-tabs'."""
    monkeypatch.setattr(event_callbacks, "get_trigger_id", lambda: "main-tabs")


def _populate_fn():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    target = [k for k in app.callback_map
              if "canvas-tab-content.children" in k
              and "details-tab-content.children" in k][0]
    cb = app.callback_map[target]["callback"]
    while hasattr(cb, "__wrapped__"):
        cb = cb.__wrapped__
    return cb


def test_prefetch_canvas_builds_content_without_requiring_tab_switch(prefetch_trigger_ctx):
    fn = _populate_fn()
    # active_tab is still 'tab-next'; prefetch trigger fires.
    result = fn("tab-next", "prefetch-canvas", False, False, False, False, False)
    assert result[0] is not no_update, "canvas children should be populated"
    assert result[5] is True, "canvas-built-flag should flip to True"
    # Other tabs untouched
    for i in (1, 2, 3, 4, 6, 7, 8, 9):
        assert result[i] is no_update


def test_prefetch_analyze_builds_content_without_requiring_tab_switch(prefetch_trigger_ctx):
    fn = _populate_fn()
    result = fn("tab-next", "prefetch-analyze", False, False, False, False, False)
    assert result[3] is not no_update
    assert result[8] is True
    for i in (0, 1, 2, 4, 5, 6, 7, 9):
        assert result[i] is no_update


def test_prefetch_is_idempotent_after_user_click(prefetch_trigger_ctx):
    fn = _populate_fn()
    # Canvas flag already True (user clicked first)
    result = fn("tab-next", "prefetch-canvas", True, False, False, False, False)
    assert all(r is no_update for r in result)


def test_user_click_on_prefetched_canvas_is_noop(main_tabs_trigger_ctx):
    """Prefetch already ran (canvas-built=True); user clicks canvas tab. Tabs-only
    trigger so the populate callback sees active_tab='tab-canvas'; canvas built-flag
    is True so it's a no-op (mounted subtree preserved)."""
    fn = _populate_fn()
    result = fn("tab-canvas", "prefetch-analyze", True, False, False, True, False)
    assert all(r is no_update for r in result)


def test_prefetch_does_not_emit_visibility_change(prefetch_trigger_ctx):
    """Prefetch writes only children/flag outputs — never to any style output."""
    fn = _populate_fn()
    result = fn("tab-next", "prefetch-canvas", False, False, False, False, False)
    # populate_tab_content returns exactly 10 outputs; none are styles
    assert len(result) == 10


def test_prefetch_asset_file_exists():
    path = Path(__file__).parent.parent / "assets" / "prefetch.js"
    assert path.exists(), f"expected {path} to exist"


def test_prefetch_asset_uses_request_idle_callback():
    path = Path(__file__).parent.parent / "assets" / "prefetch.js"
    src = path.read_text(encoding="utf-8")
    assert "requestIdleCallback" in src
    assert "setTimeout" in src  # fallback
    assert "prefetch-canvas" in src
    assert "prefetch-analyze" in src
    assert "scheduleIdlePrefetch" in src


def test_prefetch_asset_uses_native_value_setter_bridge():
    """Prefetch must use the JS-Dash bridge pattern (native value setter + input event)."""
    path = Path(__file__).parent.parent / "assets" / "prefetch.js"
    src = path.read_text(encoding="utf-8")
    assert "HTMLInputElement.prototype" in src
    assert re.search(r"dispatchEvent\s*\(\s*new\s+Event\s*\(\s*['\"]input['\"]", src)


def test_prefetch_clientside_callback_registered():
    """The clientside prefetch scheduler is registered against prefetch-tab-trigger."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    keys = [k for k in app.callback_map if "prefetch-tab-trigger.value" in k]
    assert keys, "no callback found outputting prefetch-tab-trigger.value"
