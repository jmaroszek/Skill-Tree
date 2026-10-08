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


def test_filters_open_on_the_whole_graph_every_session():
    """Filters are session state: no Memory switch, no restored values.

    A narrowing that outlives a restart silently scopes every ranking the app
    produces, and the user has no way to tell. Opening on the full graph makes
    any narrowing a deliberate act taken in view of its effect.
    """
    content = build_filters_content()
    ids = _ids(content)

    assert "filter-remember" not in ids
    assert "Memory" not in _text(content)

    assert _by_id(content, "filter-node-type").value == []
    assert _by_id(content, "filter-value").value == [1, 10]
    assert _by_id(content, "filter-interest").value == [1, 10]
    assert _by_id(content, "filter-difficulty").value == [1, 10]
    assert _by_id(content, "filter-time-min").value is None
    assert _by_id(content, "filter-time").value is None
    assert _by_id(content, "filter-time-unit").value == "hours"
    assert _by_id(content, "filter-done").value == []
    assert _by_id(content, "filter-dormant").value == []
    assert _by_id(content, "community-method").value == "louvain"
    assert _by_id(content, "filter-community").value == "All"
    assert _by_id(content, "filter-context").value == []
    assert _by_id(content, "filter-subcontext").value == []
    assert _by_id(content, "filter-text").value == ""
    assert _by_id(content, "filter-text-scope").value == []
    assert _by_id(content, "filter-search-query").data is None


def test_search_leads_the_filters_sidebar_and_applies_on_enter():
    content = build_filters_content()
    ids = _ids(content)

    assert ids.index("filter-text") < ids.index("filter-text-scope")
    assert ids.index("filter-text-scope") < ids.index("filter-context")
    # A layout per keystroke is the cost on a large graph; Enter or blur only.
    assert _by_id(content, "filter-text").debounce is True
    # The descriptions switch is the one the store's callback looks for.
    scope = _by_id(content, "filter-text-scope")
    assert [o["value"] for o in scope.options] == ["descriptions"]
    assert scope.switch is True


def test_the_editor_separates_search_from_general_like_every_other_section():
    from sidebars_layout import build_node_editor_content

    items = list(_walk(build_node_editor_content()))
    kinds = [type(item).__name__ for item in items]
    general = next(i for i, item in enumerate(items)
                   if kinds[i] == "H5" and _text(item) == "General")
    search = next(i for i, item in enumerate(items)
                  if getattr(item, "id", None) == "search-node")

    assert "Hr" in kinds[search:general]


def test_field_focus_rings_are_for_the_keyboard_only():
    """A click draws nothing; Tab draws the ring (html.keyboard-mode)."""
    css = (Path(__file__).resolve().parents[1] / "assets" / "theme.css").read_text()
    quiet = css[css.index(".form-control:focus,"):]
    quiet = quiet[:quiet.index("}")]
    ring = css[css.index("html.keyboard-mode .form-control:focus,"):]
    ring = ring[:ring.index("}")]

    assert "box-shadow: none" in quiet
    assert "--st-field-focus-ring" not in quiet
    assert "--st-field-focus-ring" in ring


def test_filter_defaults_match_the_clear_filters_reset():
    """The sidebar's opening values and "Clear Filters" must not drift apart.

    clear_filters returns a bare tuple positioned against its Output list, so
    nothing but this test ties the two together.
    """
    content = build_filters_content()
    # Output order in callbacks.clear_filters, minus filter-subcontext (reset
    # clientside) — see the note above that callback.
    reset = dict(zip(
        ["filter-node-type", "filter-context", "community-method",
         "filter-community", "filter-value", "filter-interest",
         "filter-difficulty", "filter-time-min", "filter-time",
         "filter-time-unit", "filter-done", "filter-dormant",
         "filter-text", "filter-text-scope"],
        ([], [], 'louvain', 'All', [1, 10], [1, 10], [1, 10], None, None,
         'hours', [], [], '', []),
    ))
    for component_id, cleared in reset.items():
        assert _by_id(content, component_id).value == cleared, component_id


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


def test_native_picker_tries_below_before_using_overflow_fallbacks():
    css = (Path(__file__).resolve().parents[1] / "assets" / "dropdowns.css").read_text()
    supports = css[css.index("@supports (appearance: base-select)") :]
    picker_start = supports.index("select::picker(select) {")
    picker = supports[picker_start:supports.index("}", picker_start)]

    assert "position-try-order: normal;" in picker
    # With no cap the UA stretches the list to the room left below the trigger
    # and never flips above, so a trigger near the window's edge got a sliver.
    assert "max-height: 320px;" in picker


def test_multi_selects_have_no_select_all():
    css = (Path(__file__).resolve().parents[1] / "assets" / "dropdowns.css").read_text()
    rule = css[css.index(".dash-dropdown-actions {"):]

    assert "display: none !important;" in rule[:rule.index("}")]


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
