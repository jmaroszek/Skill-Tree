"""The Settings modal exposes user decisions, not implementation tuning."""

from settings_layout import build_settings_modal


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
    assert "setting-context-weights-container" in components
    assert "setting-show-scoring-perf" in components
    assert "setting-now-node-cap" in components


def test_context_priorities_live_in_contexts_with_plain_language():
    modal = build_settings_modal()
    contexts_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-contexts"
    )
    scoring_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-scoring"
    )

    assert "setting-context-weights-container" in _by_id(contexts_tab)
    assert "setting-context-weights-container" not in _by_id(scoring_tab)
    copy = _text(contexts_tab)
    assert "influence what appears next" in copy
    assert "Doubling a weight" not in copy


def test_context_sorting_offers_only_defined_order_or_alphabetical():
    components = _by_id(build_settings_modal())
    for component_id in (
            "setting-context-sort-mode", "setting-subcontext-sort-mode"):
        assert components[component_id].options == [
            {"label": "Defined order", "value": "definition"},
            {"label": "Alphabetical", "value": "alphabetical"},
        ]


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
    assert "Manage reflections from the journal icon" not in text


def test_path_fields_are_responsive_but_visually_bounded():
    modal = build_settings_modal()
    paths_tab = next(
        component for component in _walk(modal)
        if getattr(component, "tab_id", None) == "tab-paths"
    )
    containers = [
        component for component in _walk(paths_tab)
        if getattr(component, "style", None) == {
            "width": "100%", "maxWidth": "640px"
        }
    ]

    assert len(containers) == 1
    assert "Paths" not in _text(paths_tab)
    assert {
        "setting-obsidian-path", "setting-gdrive-path"
    }.issubset(_by_id(containers[0]))


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
