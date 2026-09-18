"""Regression coverage for Details local-view controls and layout-only gears."""

from pathlib import Path

from config import ConfigManager
from details_layout import build_graph_settings_panel, build_details_tab_content
from layout import build_app_layout
from sidebars_layout import build_filters_content


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif isinstance(children, str):
        yield children
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _ids(component):
    return [getattr(item, "id", None) for item in _walk(component)
            if getattr(item, "id", None)]


def _text(component):
    return " ".join(item for item in _walk(component) if isinstance(item, str))


def _by_id(component, component_id):
    return next(item for item in _walk(component)
                if getattr(item, "id", None) == component_id)


def test_filters_keep_general_order_and_have_no_canvas_view():
    content = build_filters_content()
    ids = _ids(content)

    assert ids.index("filter-context") < ids.index("filter-subcontext")
    assert ids.index("filter-subcontext") < ids.index("filter-node-type")
    assert "filter-local-view" not in ids
    assert "filter-max-depth" not in ids
    assert "filter-cross-links" not in ids
    assert "Canvas View" not in _text(content)
    # Layout physics belong to the graph-settings panel, not the filters
    # sidebar — Settle lives beside the sliders it re-runs.
    assert "btn-sidebar-relayout" not in ids
    assert "Settle" not in _text(content)


def test_obsolete_canvas_view_settings_are_not_filter_defaults():
    defaults = ConfigManager._FILTER_DEFAULTS

    assert "local_view" not in defaults
    assert "max_depth" not in defaults
    assert "cross_links" not in defaults


def test_details_controls_replace_transitive_with_cross_links():
    content = build_details_tab_content()
    ids = _ids(content)

    assert "details-include-transitive" not in ids
    assert "details-include-transitive-top" not in ids
    assert "details-show-cross-links" in ids
    assert "details-show-cross-links-top" in ids
    assert ids.index("details-include-soft-needs") < ids.index("details-show-cross-links")
    assert ids.index("details-show-cross-links") < ids.index("details-include-synergies")
    assert ids.index("details-include-synergies") < ids.index("details-hide-done")
    assert ids.index("details-hide-done") < ids.index("details-hide-blocked")


def test_max_depth_lives_in_the_details_graph_settings_panel():
    """Depth moved out of the toggles row, so it has no -top twin to sync."""
    content = build_details_tab_content()
    ids = _ids(content)
    depth = _by_id(content, "details-max-depth")

    assert depth.value == 6
    assert depth.marks == {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "All"}
    assert "details-max-depth-top" not in ids
    assert ids.count("details-max-depth") == 1
    # It sits inside the graph-settings panel, ahead of the physics sliders.
    assert ids.index("details-graph-settings-panel") < ids.index("details-max-depth") \
        or ids.index("details-max-depth") < ids.index("details-graph-settings-edge-length")


def test_details_panel_opts_into_max_depth_but_others_do_not():
    detail = build_graph_settings_panel("d-layout", max_depth_id="details-max-depth")
    plain = build_graph_settings_panel("p-layout")

    assert "details-max-depth" in _ids(detail)
    assert "Max Depth" in _text(detail)
    # Opt-in only: the Nodes and Events canvases show the whole graph, so they
    # get no depth control.
    assert "Max Depth" not in _text(plain)
    assert not [i for i in _ids(plain) if "max-depth" in str(i)]


def test_app_layout_has_no_global_local_view_stores():
    layout = build_app_layout([], env="sandbox")
    ids = _ids(layout)

    assert "filter-local-view-state-store" not in ids
    assert "filter-local-view-root-store" not in ids
    assert "events-local-root-store" not in ids


def test_graph_layout_panel_contains_only_layout_controls():
    panel = build_graph_settings_panel("test-graph-layout")
    ids = _ids(panel)
    text = _text(panel)

    assert "Graph Layout" in text
    assert "Max Depth" not in text
    assert "Neighbors" not in text
    assert "test-graph-layout-max-depth" not in ids
    assert "test-graph-layout-neighbor-links" not in ids
    assert "test-graph-layout-animate" in ids
    assert "test-graph-layout-freeze-rerender" in ids


def test_graph_layout_panel_scrolls_within_a_short_canvas():
    """A shared panel must not lose controls when its canvas is short."""
    css = (Path(__file__).resolve().parents[1] / "assets" / "theme.css").read_text()
    rule_start = css.index(".graph-settings-panel {")
    rule = css[rule_start:css.index("}\n", rule_start) + 1]

    assert "box-sizing: border-box" in rule
    assert "max-height: calc(100% - 72px)" in rule
    assert "overflow-y: auto" in rule


def test_graph_layout_sliders_use_qualitative_endpoint_labels():
    panel = build_graph_settings_panel("test-graph-layout")

    edge_length = _by_id(panel, "test-graph-layout-edge-length")
    gravity = _by_id(panel, "test-graph-layout-gravity")
    repulsion = _by_id(panel, "test-graph-layout-repulsion")
    edge_length_axis = _by_id(panel, "test-graph-layout-edge-length-axis")
    gravity_axis = _by_id(panel, "test-graph-layout-gravity-axis")
    repulsion_axis = _by_id(panel, "test-graph-layout-repulsion-axis")

    assert edge_length.marks is None
    assert gravity.marks is None
    assert repulsion.marks is None
    assert _text(edge_length_axis) == "Short Long"
    assert _text(gravity_axis) == "Weak Strong"
    assert _text(repulsion_axis) == "Weak Strong"


def test_events_layout_panel_has_smooth_and_freeze():
    panel = build_graph_settings_panel(
        "test-events-layout", defaults_getter=ConfigManager.get_events_graph_layout_defaults
    )
    ids = _ids(panel)

    assert "test-events-layout-animate" in ids
    assert "test-events-layout-freeze-rerender" in ids


def test_events_tab_content_graph_settings_include_smooth_toggle():
    from events_layout import build_events_tab_content

    content = build_events_tab_content()
    ids = _ids(content)

    assert "events-graph-settings-animate" in ids
