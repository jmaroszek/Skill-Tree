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
    }
    assert removed.isdisjoint(components)
