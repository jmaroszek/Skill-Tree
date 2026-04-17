"""Tests for the Phase B lazy tab population callback."""

import dash
import pytest
from dash import no_update
from dash.development.base_component import Component

import event_callbacks
from event_callbacks import register_event_callbacks


@pytest.fixture
def main_tabs_trigger(monkeypatch):
    """Simulate a user-click callback context: trigger == 'main-tabs'."""
    monkeypatch.setattr(event_callbacks, "get_trigger_id", lambda: "main-tabs")


def _find_component_by_id(root, target_id):
    """DFS into a Dash tree for the first component whose id == target_id."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        if not isinstance(node, Component):
            continue
        if getattr(node, "id", None) == target_id:
            return node
        children = getattr(node, "children", None)
        if children is not None:
            if isinstance(children, (list, tuple)):
                stack.extend(children)
            else:
                stack.append(children)
    return None


def _populate_fn():
    """Register callbacks on a fresh Dash app and return the raw populate function."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    target = [k for k in app.callback_map
              if "canvas-tab-content.children" in k
              and "details-tab-content.children" in k
              and "canvas-built-flag.data" in k][0]
    cb = app.callback_map[target]["callback"]
    while hasattr(cb, "__wrapped__"):
        cb = cb.__wrapped__
    return cb


def test_lazy_tab_placeholders_start_empty():
    from layout import build_app_layout
    root = build_app_layout(env="sandbox")
    for tab_id in (
        "canvas-tab-content",
        "details-tab-content",
        "events-tab-content",
        "analyze-tab-content",
        "settings-tab-content",
    ):
        comp = _find_component_by_id(root, tab_id)
        assert comp is not None, f"{tab_id} missing"
        assert comp.children == [], f"{tab_id} should start with empty children, got: {comp.children!r}"


def test_next_tab_is_not_empty():
    """Next tab ships populated — only non-Next tabs are lazy."""
    from layout import build_app_layout
    root = build_app_layout(env="sandbox")
    next_tab = _find_component_by_id(root, "next-tab-content")
    assert next_tab is not None
    assert next_tab.children  # non-empty


def test_built_flag_stores_present_and_default_false():
    from layout import build_app_layout
    root = build_app_layout(env="sandbox")
    for flag_id in (
        "canvas-built-flag",
        "details-built-flag",
        "events-built-flag",
        "analyze-built-flag",
        "settings-built-flag",
    ):
        store = _find_component_by_id(root, flag_id)
        assert store is not None, f"{flag_id} missing"
        assert store.data is False


@pytest.mark.parametrize("tab_id,out_idx,flag_idx", [
    ("tab-canvas", 0, 5),
    ("tab-details", 1, 6),
    ("tab-events", 2, 7),
    ("tab-analyze", 3, 8),
    ("tab-settings", 4, 9),
])
def test_populate_tab_content_first_activation_builds_tree(main_tabs_trigger, tab_id, out_idx, flag_idx):
    fn = _populate_fn()
    result = fn(tab_id, "", False, False, False, False, False)
    assert len(result) == 10
    assert result[out_idx] is not no_update, f"{tab_id} children should be populated"
    assert result[flag_idx] is True
    # All other outputs should remain no_update
    for i in range(10):
        if i != out_idx and i != flag_idx:
            assert result[i] is no_update, f"output idx {i} should be no_update when {tab_id} activates"


@pytest.mark.parametrize("tab_id", ["tab-canvas", "tab-details", "tab-events", "tab-analyze", "tab-settings"])
def test_populate_tab_content_second_activation_no_update(main_tabs_trigger, tab_id):
    """When the flag is already True, populate returns no_update for that tab."""
    fn = _populate_fn()
    flags = {"tab-canvas": 0, "tab-details": 1, "tab-events": 2, "tab-analyze": 3, "tab-settings": 4}
    flag_vals = [False] * 5
    flag_vals[flags[tab_id]] = True
    result = fn(tab_id, "", *flag_vals)
    assert all(r is no_update for r in result), f"{tab_id} already built -> all no_update; got {result}"


def test_populate_tab_content_next_tab_is_noop(main_tabs_trigger):
    """Switching to tab-next does not populate anything (Next was built eagerly)."""
    fn = _populate_fn()
    result = fn("tab-next", "", False, False, False, False, False)
    assert all(r is no_update for r in result)


def test_user_click_is_not_hijacked_by_stale_prefetch_trigger_value(main_tabs_trigger):
    """REGRESSION: after prefetch fires, prefetch_trigger keeps its last value.
    A subsequent user click must still build the clicked tab, not the stale one.
    """
    fn = _populate_fn()
    # Simulate the app state right after prefetch has completed:
    # - canvas and analyze built (prefetch wrote them)
    # - prefetch_trigger still holds 'prefetch-analyze' as its latest value
    # User now clicks Details (main-tabs fired, not prefetch-tab-trigger).
    result = fn("tab-details", "prefetch-analyze",
                True, False, False, True, False)  # canvas+analyze built
    # Details children slot (index 1) must be populated, not ignored.
    assert result[1] is not no_update, (
        "stale prefetch_trigger hijacked user click: details never built"
    )
    assert result[6] is True, "details-built-flag should flip to True"


def test_app_suppress_callback_exceptions_enabled(monkeypatch):
    import sys, threading, webbrowser, importlib
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    monkeypatch.setattr(webbrowser, "open", lambda *a, **kw: None)

    class _Noop:
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def cancel(self): pass

    monkeypatch.setattr(threading, "Timer", _Noop)
    sys.modules.pop("app", None)
    import app as app_module
    importlib.reload(app_module)
    assert app_module.app.config.suppress_callback_exceptions is True
