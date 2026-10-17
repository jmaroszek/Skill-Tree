"""Tests for the core_engine gates: the tab-switch short-circuit, the editor
open and close short-circuit, and which outputs a render sends.

Only tab-canvas shows `cytoscape-graph`, so only a switch to it needs a graph
regen. Every other tab refreshes its own content, and the guard short-circuits
to no_update when the trigger is `main-tabs` and the destination is one of them.
"""
import inspect

import dash
import pytest

from skilltree.engine import callbacks
from skilltree.engine.callbacks import _EDITOR_UI_ONLY_TRIGGERS, _NON_GRAPH_TABS
from skilltree.engine.response import CORE_OUTPUTS, CoreResponse
from skilltree.engine import sidebars
from skilltree.services import AppServices
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED
from support.triggers import fire
from support.callbacks import app_with, unwrapped

SIDEBAR_FIELDS = ("editor_style", "goal_style", "events_style")


def _core_engine_fn():
    app = app_with(callbacks.register_engine_callbacks)
    spec = next(spec for key, spec in app.callback_map.items()
                if key.startswith("..elements-pending-store.data"))
    return unwrapped(spec["callback"]), spec


def _call(cb, **values):
    """Call core_engine with every argument None except those given."""
    kwargs = dict.fromkeys(inspect.signature(cb).parameters)
    kwargs.update(values)
    return cb(**kwargs)


def test_every_response_field_is_an_output():
    _, spec = _core_engine_fn()
    assert len(spec["output"]) == len(CoreResponse._fields)
    assert tuple(CORE_OUTPUTS) == CoreResponse._fields


def test_non_graph_tabs_set_content():
    assert _NON_GRAPH_TABS == frozenset({
        "tab-events", "tab-analyze", "tab-details", "tab-next",
    })


@pytest.mark.parametrize("tab", ["tab-events", "tab-analyze", "tab-details", "tab-next"])
def test_core_engine_noop_on_non_graph_tab_switch(monkeypatch, tab):
    """Switching to a non-graph tab short-circuits to all no_update."""
    cb, _ = _core_engine_fn()
    fire("main-tabs")
    result = _call(cb, active_tab=tab)
    assert all(r is dash.no_update for r in result), (
        f"expected all no_update for tab-switch to {tab}, got: {result}"
    )


def test_core_engine_runs_on_graph_tabs(monkeypatch):
    """tab-canvas owns cytoscape-graph, so it must NOT short-circuit."""
    cb, _ = _core_engine_fn()
    fire("main-tabs")
    # The rest of core_engine can fail downstream on None arguments. All that
    # matters is that the guard didn't short-circuit.
    try:
        result = _call(cb, active_tab="tab-canvas")
    except Exception:
        return
    assert not all(r is dash.no_update for r in result), (
        "core_engine unexpectedly short-circuited for tab-canvas"
    )


def test_core_engine_runs_when_trigger_is_not_main_tabs(monkeypatch):
    """Data-mutation triggers (save, toggle-done) must run regardless of active_tab."""
    cb, _ = _core_engine_fn()
    fire("btn-save")
    try:
        result = _call(cb, active_tab="tab-analyze")
    except Exception:
        return  # the body ran and failed on None arguments, as expected
    assert not all(r is dash.no_update for r in result)


# ---------------------------------------------------------------------------
# Editor-UI-only short-circuit: edit-trigger-input / details-edit-trigger-input
# / btn-close-editor / btn-goals-toggle alone should skip the expensive path
# and send only the three sidebar styles.
# ---------------------------------------------------------------------------


def test_editor_ui_only_triggers_set_content():
    assert _EDITOR_UI_ONLY_TRIGGERS == frozenset({
        'edit-trigger-input', 'details-edit-trigger-input',
        'btn-close-editor', 'btn-goals-toggle', 'btn-add',
    })


def _only_sidebars_change(result, trigger):
    for field in result._fields:
        if field not in SIDEBAR_FIELDS:
            assert getattr(result, field) is dash.no_update, (
                f"{field} should be no_update when short-circuiting on {trigger}")


@pytest.mark.parametrize("trigger", ['edit-trigger-input', 'details-edit-trigger-input'])
def test_edit_trigger_short_circuits_and_opens_editor(monkeypatch, trigger):
    """An Edit trigger alone short-circuits and opens the sidebar (translateX(0px))."""
    cb, _ = _core_engine_fn()
    fire(trigger)
    result = _call(cb, edit_trigger_data="NodeX|123", details_edit_trigger_data="NodeX|123")
    ed = result.editor_style
    assert isinstance(ed, dict), f"ed_style should be a dict, got {type(ed)}"
    assert ed.get('transform') == 'translateX(0px)', f"editor should open, got {ed}"
    # Scoring and the canvas did NOT run.
    _only_sidebars_change(result, trigger)


def test_btn_goals_toggle_short_circuits_and_closes_editor(monkeypatch):
    """btn-goals-toggle alone short-circuits and closes the editor."""
    cb, _ = _core_engine_fn()
    fire("btn-goals-toggle")
    result = _call(cb)
    assert isinstance(result.editor_style, dict)
    assert result.editor_style.get('transform') == SIDEBAR_TRANSLATE_CLOSED
    _only_sidebars_change(result, "btn-goals-toggle")


def test_btn_close_editor_short_circuits_and_closes_when_form_blank(monkeypatch):
    """btn-close-editor alone short-circuits; closes the editor when form has no content."""
    cb, _ = _core_engine_fn()
    fire("btn-close-editor")
    # Stub out the unsaved-changes check — a blank form, no pending nav.
    monkeypatch.setattr(sidebars, "is_form_dirty_vs_snapshot", lambda *a, **kw: False)
    result = _call(cb)
    assert isinstance(result.editor_style, dict)
    assert result.editor_style.get('transform') == SIDEBAR_TRANSLATE_CLOSED


def test_edit_trigger_batched_with_other_input_does_not_short_circuit(monkeypatch):
    """If edit-trigger-input fires batched with a non-editor Input, the full path must run."""
    cb, _ = _core_engine_fn()
    fire("edit-trigger-input", "search-node")
    try:
        result = _call(cb, edit_trigger_data="NodeX|123")
    except Exception:
        return  # the full path ran and failed on None arguments: no short-circuit
    # It must not be the editor-only response: something besides the
    # sidebars was computed.
    computed = [field for field in result._fields
                if field not in SIDEBAR_FIELDS and getattr(result, field) is not dash.no_update]
    assert computed, ("batched edit-trigger+search-node should have run the full "
                      "path; the short-circuit fired instead")


def test_page_load_leaves_the_layouts_resets_alone(monkeypatch):
    """The layout already holds the empty message and the closed undo and
    calibration modals. Restating them on load woke six startup callbacks
    that only reset again."""
    cb, _ = _core_engine_fn()
    fire()
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda *a: set())
    out = _call(cb)

    assert out.elements is not dash.no_update
    for field in ("message", "clear_disabled", "clear_intervals",
                  "undo_open", "undo_body", "undo_pending",
                  "calibration_open", "calibration_reference",
                  "calibration_pending"):
        assert getattr(out, field) is dash.no_update, field


def _render(monkeypatch, trigger, active_tab, stamp=None, search=None):
    """Run core_engine for one trigger, with the Nodes tab state given."""
    cb, _ = _core_engine_fn()
    fire(trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids",
                        lambda *a: {trigger} if trigger else set())
    return _call(cb, active_tab=active_tab, canvas_stamp=stamp, f_search=search)


def test_the_nodes_canvas_loads_on_its_first_visit(monkeypatch):
    """Its ingest and cold layout used to hold up the startup cover for about
    a second. Until the canvas loads, a render sends a marker instead."""
    from skilltree.ui.canvas.view import CANVAS_DEFERRED

    assert _render(monkeypatch, "", "tab-next").elements == CANVAS_DEFERRED
    assert isinstance(_render(monkeypatch, "", "tab-canvas").elements, list)


def test_a_tab_switch_leaves_the_resets_alone(monkeypatch):
    out = _render(monkeypatch, "main-tabs", "tab-canvas")
    assert isinstance(out.elements, list)
    assert out.message is dash.no_update


def test_a_loaded_canvas_stays_current_in_the_background(monkeypatch):
    out = _render(monkeypatch, "filter-context", "tab-next",
                  stamp={"loaded": True, "nodes": 3})
    assert isinstance(out.elements, list)


def test_returning_to_a_loaded_canvas_sends_nothing(monkeypatch):
    """Every render keeps a loaded canvas current, so a visit needs no regen."""
    out = _render(monkeypatch, "main-tabs", "tab-canvas",
                  stamp={"loaded": True, "nodes": 3})
    assert all(value is dash.no_update for value in out)


@pytest.mark.parametrize("trigger", sorted(callbacks._FILTER_TRIGGERS))
def test_a_filter_change_sends_only_the_view(monkeypatch, trigger):
    """A filter starts the Nodes layout. The save message, the modals, the
    option lists and the stylesheet each woke callbacks inside it. The
    Community selection is part of the view, and moves only when its
    cluster does."""
    out = _render(monkeypatch, trigger, "tab-canvas")
    assert isinstance(out.elements, list)
    assert isinstance(out.community_options, list)
    for field in out._fields:
        if field not in ("elements", "community_options",
                         "community_value", "community_memory"):
            assert getattr(out, field) is dash.no_update, field
    assert out.community_value is dash.no_update  # "All" stays "All"


def test_the_search_query_reaches_the_canvas_filters(monkeypatch):
    seen = []
    real = callbacks.build_filters

    def spy(*args, **kwargs):
        filters = real(*args, **kwargs)
        seen.append(filters)
        return filters

    monkeypatch.setattr(callbacks, "build_filters", spy)
    _render(monkeypatch, "filter-search-query", "tab-canvas",
            search={"text": "skill tree", "descriptions": True})
    assert seen[-1]["search"] == "skill tree"
    assert seen[-1]["search_descriptions"] is True


def test_the_registered_callback_hands_dash_its_outputs_by_name():
    """Dash receives a dict keyed by CORE_OUTPUTS, whatever the response sets."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_engine_callbacks(app, AppServices())
    target = [k for k in app.callback_map if k.startswith("..elements-pending-store.data")][0]
    keyed = app.callback_map[target]["callback"].__wrapped__
    fire("main-tabs")
    out = keyed(**dict.fromkeys(inspect.signature(keyed).parameters,
                                None) | {"active_tab": "tab-next"})
    assert set(out) == set(CORE_OUTPUTS)
    assert all(value is dash.no_update for value in out.values())
