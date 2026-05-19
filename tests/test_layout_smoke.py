"""Smoke tests for tab builders and the top-level layout construction."""

import pytest
from dash.development.base_component import Component


def _collect_ids(component):
    """Yield every id found in a Dash component tree."""
    found = set()
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        if not isinstance(node, Component):
            continue
        nid = getattr(node, "id", None)
        if nid is not None:
            found.add(nid if isinstance(nid, str) else repr(nid))
        children = getattr(node, "children", None)
        if children is not None:
            if isinstance(children, (list, tuple)):
                stack.extend(children)
            else:
                stack.append(children)
    return found


def test_build_app_layout_returns_tab_containers_and_settings_modal():
    from layout import build_app_layout
    root = build_app_layout(initial_elements=[], env="sandbox")
    ids = _collect_ids(root)
    for tab_id in (
        "next-tab-content",
        "canvas-tab-content",
        "details-tab-content",
        "events-tab-content",
        "analyze-tab-content",
        "settings-modal",
    ):
        assert tab_id in ids, f"{tab_id!r} missing from layout; found ids (sample): {sorted(ids)[:20]}"


def test_build_app_layout_has_main_tabs_and_default_next():
    from layout import build_app_layout
    root = build_app_layout(initial_elements=[], env="sandbox")
    ids = _collect_ids(root)
    assert "main-tabs" in ids


@pytest.mark.parametrize("import_path,func_name", [
    ("details_layout", "build_details_tab_content"),
    ("events_layout", "build_events_tab_content"),
    ("settings_layout", "build_settings_modal"),
    ("analyze_layout", "build_analyze_tab_content"),
])
def test_tab_builder_smoke(import_path, func_name):
    import importlib
    mod = importlib.import_module(import_path)
    builder = getattr(mod, func_name)
    result = builder()
    assert result is not None
    _ = result.to_plotly_json()
