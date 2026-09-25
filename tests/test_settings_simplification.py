"""The Settings modal exposes user decisions, not implementation tuning."""

from settings_layout import build_settings_modal
from models import STATUS_BLOCKED


def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    if not hasattr(component, "to_plotly_json"):
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _by_id(root):
    return {
        component.id: component
        for component in _walk(root)
        if isinstance(getattr(component, "id", None), str)
    }


def _text(component):
    return " ".join(
        child
        for item in _walk(component)
        for child in ([getattr(item, "children", None)]
                      if isinstance(getattr(item, "children", None), str) else [])
    )


def test_settings_keep_profiles_context_priorities_and_startup_summary():
    modal = build_settings_modal()
    components = _by_id(modal)

    options = components["setting-hp-profile"].options
    assert [option["value"] for option in options] == [
        "Sage", "Explorer", "Compounder", "Pragmatist", "Creator", "Glider"
    ]
    # Context priorities are edited on each context's own row.
    assert "setting-context-editor" in components
    assert "setting-show-scoring-perf" in components
    assert "setting-now-node-cap" in components


def test_context_priorities_live_in_contexts_with_plain_language():
    modal = build_settings_modal()
    contexts_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-contexts"
    )
    recommendations_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-recommendations"
    )

    assert "setting-context-editor" in _by_id(contexts_tab)
    assert "setting-context-editor" not in _by_id(recommendations_tab)
    copy = _text(contexts_tab)
    assert "scales a context's tasks in the rankings" in copy
    assert "Doubling a weight" not in copy


def test_context_sorting_offers_only_defined_order_or_alphabetical():
    modal = build_settings_modal()
    components = _by_id(modal)
    for component_id in (
            "setting-context-sort-mode", "setting-subcontext-sort-mode"):
        assert components[component_id].options == [
            {"label": "Defined order", "value": "definition"},
            {"label": "Alphabetical", "value": "alphabetical"},
        ]

    contexts_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-contexts"
    )
    copy = _text(contexts_tab)
    assert "Dropdown Order" in copy
    assert copy.count("Use the order defined above, or sort alphabetically.") == 1
    assert "Context Dropdown Order" not in copy
    assert "Subcontext Dropdown Order" not in copy


def test_name_formatting_offers_only_the_three_supported_modes():
    modal = build_settings_modal()
    components = _by_id(modal)

    assert components["setting-name-format-mode"].options == [
        {"label": "Keep as entered", "value": "none"},
        {"label": "Title Case", "value": "title"},
        {"label": "Sentence case", "value": "sentence"},
    ]
    assert "setting-titlecase-options" in components
    assert "setting-linter-enabled" not in components
    assert "Name Formatting" in _text(modal)
    assert "Choose how node names and aliases are capitalized when saved." in _text(modal)
    assert "Changing this setting will not affect existing nodes." in _text(modal)
    assert "Name Linter" not in _text(modal)
    assert "ignored when checking for duplicate names" not in _text(modal)


def test_single_setting_sections_do_not_repeat_their_labels():
    modal = build_settings_modal()
    text = _text(modal)

    assert sum(
        getattr(component, "children", None) == "Scoring Profile"
        for component in _walk(modal)
    ) == 1
    assert not any(
        getattr(component, "children", None) == "Priorities"
        for component in _walk(modal)
    )
    assert sum(
        getattr(component, "children", None) == "Maximum Now Nodes"
        and getattr(component, "className", None) != "visually-hidden"
        for component in _walk(modal)
    ) == 1
    assert "Max Now Nodes" not in text
    assert "Maximum number of nodes that can be flagged Now at once" not in text
    assert "Set the maximum number of active projects you can have at once." in text
    assert "Manage reflections from the journal icon" not in text


def test_graph_statistics_uses_concise_user_facing_description():
    """The section is named for what it shows, not for when it runs.

    It was "Startup Analysis", which described the timing and left the content
    to be guessed at; the toggle beside it already says "Run on startup".
    """
    modal = build_settings_modal()
    recommendations_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-recommendations"
    )
    copy = _text(recommendations_tab)
    components = list(_walk(recommendations_tab))
    expected = ("Shows node and edge counts, and how long scoring took, "
                "on the Home tab.")
    description_index = next(
        index for index, component in enumerate(components)
        if getattr(component, "children", None) == expected
    )
    toggle_index = next(
        index for index, component in enumerate(components)
        if getattr(component, "id", None) == "setting-show-scoring-perf"
    )

    assert "Graph Statistics" in copy
    assert "Startup Analysis" not in copy
    assert expected in copy
    assert "records the first scoring run after launch" not in copy
    assert description_index < toggle_index


def test_scoring_profile_help_explains_recommendation_tradeoffs_plainly():
    modal = build_settings_modal()
    copy = _text(_by_id(modal)["popover-hp-profile-info"])

    assert "want the graph to speak for itself" in copy
    assert "curiosity more influence" in copy
    assert "foundational work that will unlock many later steps" in copy
    assert "priority goal" in copy
    assert "connects and combines different areas" in copy
    assert "shorter, easier work" in copy
    for technical_phrase in (
            "cascade", "Synergies", "Priority-Goal boost", "Soft edges"):
        assert technical_phrase not in copy


def test_resources_tab_holds_resource_cards_in_a_bounded_column():
    modal = build_settings_modal()
    resources_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-resources"
    )
    containers = [
        component for component in _walk(resources_tab)
        if getattr(component, "style", None) == {
            "width": "100%", "maxWidth": "640px"
        }
    ]

    assert len(containers) == 1
    ids = _by_id(containers[0])
    assert {"resource-section-settings-store", "resource-section-settings-rows",
            "btn-resource-section-add"} <= set(ids)
    assert " Add resource" in ids["btn-resource-section-add"].children


def test_type_and_status_colors_show_their_hex():
    from settings_callbacks import _build_status_color_rows, _build_type_color_rows

    colors = {"Done": "#123456", "Learn": "#abcdef"}
    rows = [
        *_build_status_color_rows(colors),
        *_build_type_color_rows(["Learn"], colors),
    ]
    inputs = [
        component for component in _walk(rows)
        if getattr(component, "type", None) == "color"
    ]

    # A colour the user has set shows that colour; one they have not falls back
    # to that key's shipped default rather than a single generic grey, which is
    # what every unset swatch used to show regardless of what it was for.
    from config import DEFAULT_NODE_COLORS

    values = {component.value for component in inputs}
    assert {"#123456", "#abcdef"} <= values
    assert DEFAULT_NODE_COLORS[STATUS_BLOCKED] in values
    assert "#6c757d" not in values, (
        "An unset swatch is showing the old generic grey instead of its default")
    # Type and status rows show the selected value for exact-colour and
    # contrast lookups.
    assert "#abcdef" in _text(_build_type_color_rows(["Learn"], colors))
    status_text = _text(_build_status_color_rows(colors))
    assert "#123456" in status_text
    assert DEFAULT_NODE_COLORS[STATUS_BLOCKED] in status_text
    assert DEFAULT_NODE_COLORS["Now"] in status_text


def test_technical_and_maintenance_controls_are_not_user_facing():
    components = _by_id(build_settings_modal())
    removed = {
        "hp-wv", "hp-wi", "hp-dh", "hp-ds", "hp-dsyn-pair",
        "hp-dsyn-mul", "hp-cross-context-mult", "hp-we", "hp-wt",
        "hp-beta", "hp-goal-boost", "hp-context-repeat",
        "hp-subcontext-repeat", "hp-future-hours", "hp-future-exponent",
        "setting-next-table-rows", "setting-graph-edge-length",
        "setting-details-graph-edge-length", "setting-events-graph-edge-length",
        "setting-monte-carlo-trials", "setting-estimate-correlation",
        "setting-unblocking-steps", "btn-run-perf-profile",
        "btn-repair-graph", "btn-restore-graph-layout",
        "setting-node-types",
    }
    assert removed.isdisjoint(components)


def _tab_ids(tab):
    return set(_by_id(tab))


def test_tabs_group_settings_by_what_they_adjust():
    """Five tabs, no Misc: each answers one question about the app."""
    modal = build_settings_modal()
    tabs = {
        component.tab_id: component for component in _walk(modal)
        if getattr(component, "tab_id", None)
    }
    assert list(tabs) == [
        "tab-recommendations", "tab-contexts", "tab-editing",
        "tab-appearance", "tab-resources",
    ]
    assert [tab.label for tab in tabs.values()] == [
        "Recommendations", "Contexts", "Editing", "Appearance", "Resources",
    ]
    assert _by_id(modal)["settings-modal-tabs"].active_tab == "tab-recommendations"

    assert {"setting-hp-profile", "setting-now-node-cap",
            "setting-show-scoring-perf"} <= _tab_ids(tabs["tab-recommendations"])
    assert {"setting-name-format-mode", "setting-hpd", "setting-default-time-unit",
            "setting-time-calibration-enabled"} <= _tab_ids(tabs["tab-editing"])
    appearance = _tab_ids(tabs["tab-appearance"])
    assert "setting-node-shapes-container" in appearance
    assert "setting-name-format-mode" not in appearance
