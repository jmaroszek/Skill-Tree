"""Tests for the Phase D core_engine tab-switch short-circuit guard.

Switching to Settings / Events / Analyze shouldn't trigger a full graph regen —
those tabs have their own refresh callbacks. The guard short-circuits to
no_update when the trigger is `main-tabs` and the destination tab is non-graph.
"""

import dash
import pytest

import callbacks
from callbacks import _CORE_ENGINE_NUM_OUTPUTS, _NON_GRAPH_TABS, _core_engine_noop_tuple


def _core_engine_fn():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    # core_engine's output key starts with '..cytoscape-graph.elements..'
    target = [k for k in app.callback_map if k.startswith("..cytoscape-graph.elements")][0]
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
    args = [None] * 70
    # active_tab sits at positional index 38 (see core_engine signature; total 71 args)
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
    args = [None] * 70
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
    args = [None] * 70
    args[38] = "tab-settings"  # even though tab is non-graph, trigger is not main-tabs
    try:
        result = cb(*args)
    except Exception:
        return  # guard didn't short-circuit; body ran and failed on None args — expected
    assert not all(r is dash.no_update for r in result)
