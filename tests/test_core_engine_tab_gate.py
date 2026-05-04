"""Tests for the Phase D core_engine tab-switch short-circuit guard.

Switching to Settings / Events / Analyze shouldn't trigger a full graph regen —
those tabs have their own refresh callbacks. The guard short-circuits to
no_update when the trigger is `main-tabs` and the destination tab is non-graph.
"""

import dash
import pytest

import callbacks
from callbacks import (
    _CORE_ENGINE_NUM_OUTPUTS,
    _NON_GRAPH_TABS,
    _EDITOR_UI_ONLY_TRIGGERS,
    _SIDEBAR_EDITOR_STYLE_IDX,
    _DETAILS_GOAL_SIDEBAR_STYLE_IDX,
    _EVENTS_SIDEBAR_STYLE_IDX,
    _core_engine_noop_tuple,
    _core_engine_editor_only_tuple,
)


def _core_engine_fn():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    # core_engine's first output is now the elements-pending-store (its data
    # is routed to cytoscape-graph.elements by a clientside callback that
    # injects pinned positions during freeze).
    target = [k for k in app.callback_map if k.startswith("..elements-pending-store.data")][0]
    cb = app.callback_map[target]["callback"]
    spec = app.callback_map[target]
    while hasattr(cb, "__wrapped__"):
        cb = cb.__wrapped__
    return cb, spec


def test_core_engine_arity_matches_constant():
    """Drift guard: if new Outputs are added, bump _CORE_ENGINE_NUM_OUTPUTS too."""
    _, spec = _core_engine_fn()
    actual = len(spec["output"]) if isinstance(spec.get("output"), list) else len(spec["outputs"])
    assert actual == _CORE_ENGINE_NUM_OUTPUTS, (
        f"core_engine has {actual} outputs but _CORE_ENGINE_NUM_OUTPUTS={_CORE_ENGINE_NUM_OUTPUTS}; "
        "update the constant in callbacks.py"
    )


def test_noop_tuple_arity():
    t = _core_engine_noop_tuple()
    assert len(t) == _CORE_ENGINE_NUM_OUTPUTS
    assert all(x is dash.no_update for x in t)


def test_non_graph_tabs_set_content():
    assert _NON_GRAPH_TABS == frozenset({"tab-settings", "tab-events", "tab-analyze"})


@pytest.mark.parametrize("tab", ["tab-settings", "tab-events", "tab-analyze"])
def test_core_engine_noop_on_non_graph_tab_switch(monkeypatch, tab):
    """Switching to a non-graph tab short-circuits to all no_update."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "main-tabs")
    # core_engine accepts positional args from Inputs + States; supply Nones and
    # let the guard fire before any of them are used.
    args = [None] * 83
    # active_tab sits at positional index 38
    args[38] = tab
    result = cb(*args)
    assert len(result) == _CORE_ENGINE_NUM_OUTPUTS
    assert all(r is dash.no_update for r in result), (
        f"expected all no_update for tab-switch to {tab}, got: {result}"
    )


@pytest.mark.parametrize("tab", ["tab-next", "tab-canvas", "tab-details"])
def test_core_engine_runs_on_graph_tabs(monkeypatch, tab):
    """Graph-facing tabs (Next, Nodes, Details) must NOT short-circuit."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "main-tabs")
    args = [None] * 83
    args[38] = tab
    # The rest of core_engine can fail downstream on None args — we only need
    # to verify the guard does NOT trigger. Catch the downstream exception and
    # assert it isn't a "tuple mismatch" / doesn't return the no_update tuple.
    try:
        result = cb(*args)
    except Exception:
        return  # good — guard didn't short-circuit; execution proceeded and failed later
    # If it did return, it should NOT be all no_update
    assert not all(r is dash.no_update for r in result), (
        f"core_engine unexpectedly short-circuited for graph tab {tab}"
    )


def test_core_engine_runs_when_trigger_is_not_main_tabs(monkeypatch):
    """Data-mutation triggers (save, toggle-done) must run regardless of active_tab."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-save")
    args = [None] * 83
    args[38] = "tab-settings"  # even though tab is non-graph, trigger is not main-tabs
    try:
        result = cb(*args)
    except Exception:
        return  # guard didn't short-circuit; body ran and failed on None args — expected
    assert not all(r is dash.no_update for r in result)


# ---------------------------------------------------------------------------
# Editor-UI-only short-circuit: edit-trigger-input / details-edit-trigger-input
# / btn-close-editor / btn-goals-toggle alone should skip the expensive path
# and return only the three sidebar-style slots populated.
# ---------------------------------------------------------------------------


def test_editor_ui_only_triggers_set_content():
    assert _EDITOR_UI_ONLY_TRIGGERS == frozenset({
        'edit-trigger-input', 'details-edit-trigger-input',
        'btn-close-editor', 'btn-goals-toggle',
    })


def test_editor_only_tuple_arity_and_slots():
    """_core_engine_editor_only_tuple fills only the three sidebar slots."""
    t = _core_engine_editor_only_tuple("ed", "goal", "events")
    assert len(t) == _CORE_ENGINE_NUM_OUTPUTS
    assert t[_SIDEBAR_EDITOR_STYLE_IDX] == "ed"
    assert t[_DETAILS_GOAL_SIDEBAR_STYLE_IDX] == "goal"
    assert t[_EVENTS_SIDEBAR_STYLE_IDX] == "events"
    # Every other slot is no_update
    for i, slot in enumerate(t):
        if i in (_SIDEBAR_EDITOR_STYLE_IDX, _DETAILS_GOAL_SIDEBAR_STYLE_IDX, _EVENTS_SIDEBAR_STYLE_IDX):
            continue
        assert slot is dash.no_update, f"slot {i} should be no_update"


@pytest.mark.parametrize("trigger", ['edit-trigger-input', 'details-edit-trigger-input'])
def test_edit_trigger_short_circuits_and_opens_editor(monkeypatch, trigger):
    """An Edit trigger alone short-circuits and opens the sidebar (translateX(0px))."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger)
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: frozenset({trigger}))
    args = [None] * 83
    # edit_trigger_data / details_edit_trigger_data positional indexes: 32, 33
    args[32] = "NodeX|123"
    args[33] = "NodeX|123"
    result = cb(*args)
    assert len(result) == _CORE_ENGINE_NUM_OUTPUTS
    ed = result[_SIDEBAR_EDITOR_STYLE_IDX]
    assert isinstance(ed, dict), f"ed_style should be a dict, got {type(ed)}"
    assert ed.get('transform') == 'translateX(0px)', f"editor should open, got {ed}"
    # Every non-sidebar slot is no_update — scoring + elements did NOT run.
    for i, slot in enumerate(result):
        if i in (_SIDEBAR_EDITOR_STYLE_IDX, _DETAILS_GOAL_SIDEBAR_STYLE_IDX, _EVENTS_SIDEBAR_STYLE_IDX):
            continue
        assert slot is dash.no_update, f"slot {i} should be no_update when short-circuiting on {trigger}"


def test_btn_goals_toggle_short_circuits_and_closes_editor(monkeypatch):
    """btn-goals-toggle alone short-circuits and closes the editor (translateX(-380px))."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-goals-toggle")
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: frozenset({"btn-goals-toggle"}))
    args = [None] * 83
    result = cb(*args)
    ed = result[_SIDEBAR_EDITOR_STYLE_IDX]
    assert isinstance(ed, dict)
    assert ed.get('transform') == 'translateX(-380px)'


def test_btn_close_editor_short_circuits_and_closes_when_form_blank(monkeypatch):
    """btn-close-editor alone short-circuits; closes the editor when form has no content."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-close-editor")
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: frozenset({"btn-close-editor"}))
    # Stub out the unsaved-changes check — a blank form, no pending nav.
    monkeypatch.setattr(callbacks, "is_form_dirty_vs_snapshot", lambda *a, **kw: False)
    args = [None] * 83
    result = cb(*args)
    ed = result[_SIDEBAR_EDITOR_STYLE_IDX]
    assert isinstance(ed, dict)
    assert ed.get('transform') == 'translateX(-380px)'


def test_edit_trigger_batched_with_other_input_does_not_short_circuit(monkeypatch):
    """If edit-trigger-input fires batched with a non-editor Input, the full path must run."""
    cb, _ = _core_engine_fn()
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "edit-trigger-input")
    # Simulate batched fire: edit-trigger AND search-node both triggered.
    monkeypatch.setattr(callbacks, "get_all_triggered_ids",
                         lambda: frozenset({"edit-trigger-input", "search-node"}))
    args = [None] * 83
    args[32] = "NodeX|123"
    try:
        result = cb(*args)
    except Exception:
        return  # full path entered and failed on None args downstream — proves no short-circuit
    # If it did return, it must NOT be the minimal editor-only tuple shape:
    # at least one output beyond the three sidebar slots must have been computed
    # (i.e. not no_update). Otherwise we'd know the short-circuit mistakenly fired.
    non_sidebar_updates = [
        i for i, v in enumerate(result)
        if i not in (_SIDEBAR_EDITOR_STYLE_IDX, _DETAILS_GOAL_SIDEBAR_STYLE_IDX, _EVENTS_SIDEBAR_STYLE_IDX)
        and v is not dash.no_update
    ]
    assert non_sidebar_updates, (
        "batched edit-trigger+search-node should have run the full path and updated "
        "non-sidebar outputs; short-circuit fired incorrectly"
    )
