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
from skilltree.engine.callbacks import _NON_GRAPH_TABS
from skilltree.engine.response import CORE_OUTPUTS, CoreResponse
from skilltree.services import AppServices
from skilltree.store.graph.manager import GraphManager
from support.triggers import fire
from support.callbacks import app_with, unwrapped
from support.graphs import make_node



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


@pytest.mark.parametrize("input_id", [
    'edit-trigger-input', 'details-edit-trigger-input', 'btn-goals-toggle', 'btn-editor-new',
    'btn-add', 'btn-close-editor', 'btn-unsaved-discard'])
def test_what_only_moves_a_sidebar_never_reaches_the_core_engine(input_id):
    """left_panel.js and populate_editor answer these, and a render shouldn't."""
    inputs = {**callbacks.CORE_ACTIONS, **callbacks.CORE_RENDERS}
    assert input_id not in {dep.component_id for dep in inputs.values()}


def test_page_load_leaves_the_layouts_resets_alone(monkeypatch):
    """The layout already holds the empty message and the closed undo and
    calibration modals. Restating them on load woke six startup callbacks
    that only reset again."""
    cb, _ = _core_engine_fn()
    fire()
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda *a: set())
    out = _call(cb)

    assert out.elements is not dash.no_update
    for field in ("notice",
                  "undo_open", "undo_body", "undo_pending",
                  "calibration_open", "calibration_reference",
                  "calibration_pending"):
        assert getattr(out, field) is dash.no_update, field


def test_a_render_leaves_the_modals_alone(monkeypatch):
    """It arrives after an action's answer as easily as before it, and an action
    may just have opened one of them."""
    cb, _ = _core_engine_fn()
    fire("search-node")
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda *a: {"search-node"})
    out = _call(cb, search_val="Nothing")

    assert out.elements is not dash.no_update
    for field in ("notice", "undo_open", "undo_pending", "calibration_open",
                  "calibration_pending", "save_result", "left_panel"):
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
    assert _render(monkeypatch, "", "tab-next").elements["deferred"] is True
    assert isinstance(_render(monkeypatch, "", "tab-canvas").elements, list)


def test_a_tab_switch_leaves_the_resets_alone(monkeypatch):
    out = _render(monkeypatch, "main-tabs", "tab-canvas")
    assert isinstance(out.elements, list)
    assert out.notice is dash.no_update


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


def test_a_run_with_nothing_to_say_leaves_the_message_alone(monkeypatch):
    """Saving a rename clears the node picker, which runs the callback again.
    That run wiped the save's confirmation."""
    assert _render(monkeypatch, "search-node", "tab-canvas").notice is dash.no_update


def test_a_deferred_canvas_still_reports_a_change(monkeypatch):
    """The canvas hasn't loaded, so a render sends a marker. If that marker
    never changed, its stamp wouldn't fire and graph-version-store would miss
    every change until the canvas loaded."""
    before = _render(monkeypatch, "", "tab-next").elements
    GraphManager().add_node(make_node("New"))
    after = _render(monkeypatch, "", "tab-next").elements
    assert after["deferred"] is True and after != before
