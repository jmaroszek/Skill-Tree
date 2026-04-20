"""Regression tests for the populate_editor callback output arity.

populate_editor declares 37 Outputs. Every return path must produce exactly
37 items. Two paths previously returned 36 and caused a
dash._grouping.SchemaLengthValidationError → HTTP 500 whenever they fired:

- the search-node path when the searched name does not resolve to a node
- the fall-through "no name / no data" path

This test pins every return path at registration time by invoking the
unwrapped callback directly with trigger contexts that exercise each branch.
"""

import dash

import callbacks
from callbacks import register_callbacks
from graph_manager import GraphManager
from models import Node


def _populate_editor_fn():
    """Register callbacks on a fresh Dash app and return the raw populate_editor function."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)
    # populate_editor's composite output starts with node-name.value
    target = [k for k in app.callback_map
              if "node-name.value" in k and "node-type.value" in k and "node-desc.value" in k][0]
    cb = app.callback_map[target]["callback"]
    while hasattr(cb, "__wrapped__"):
        cb = cb.__wrapped__
    return cb


POPULATE_EDITOR_NUM_OUTPUTS = 37


def _make_state_args():
    """Return the State positional args populate_editor expects (all None/defaults).

    Order: elements, ed_style, original_name, cur_name, cur_type, cur_desc,
    cur_context, cur_subctx, cur_status_done, cur_val, cur_interest, cur_diff,
    cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
    cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
    cur_obs, cur_drive, cur_website,
    cur_progress, cur_time_mode, cur_priority_rank, cur_competence,
    cur_aliases, pending_nav.
    """
    return [None] * 30


def _call_with_trigger(monkeypatch, trigger_id, inputs):
    """Invoke populate_editor with a monkeypatched trigger_id and the given 10 Input args."""
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger_id)
    fn = _populate_editor_fn()
    args = list(inputs) + _make_state_args()
    return fn(*args)


def test_populate_editor_search_unknown_node_returns_37_items(monkeypatch):
    """search-node path where resolved_name does not match any DB node."""
    # Inputs in order: tapNodeData, btn-add, btn-unsaved-discard,
    # btn-unsaved-save, search-node, background-click-input, btn-new-node,
    # edit-trigger-input, details-edit-trigger-input
    inputs = [None, None, None, None, "Nonexistent Node Name", None, None, None, None]
    result = _call_with_trigger(monkeypatch, "search-node", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"search-node unknown-node path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_fall_through_returns_37_items(monkeypatch):
    """Fall-through 'if not name or not data' path — no trigger, no data."""
    inputs = [None] * 9  # no cytoscape tap, no search, no trigger value
    result = _call_with_trigger(monkeypatch, "", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"fall-through path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_btn_add_path_returns_37_items(monkeypatch):
    """btn-add path hits the def_out branch."""
    inputs = [None, 1, None, None, None, None, None, None, None]
    result = _call_with_trigger(monkeypatch, "btn-add", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_successful_lookup_returns_37_items(monkeypatch):
    """Seed a node, search for it, and verify the happy path returns 37 items."""
    mgr = GraphManager()
    mgr.add_node(Node(
        name="TestNode", type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    inputs = [None, None, None, None, "TestNode", None, None, None, None]
    result = _call_with_trigger(monkeypatch, "search-node", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_all_return_paths_use_14_not_13(monkeypatch):
    """Static guard: the string literals in callbacks.py should never have *13
    suffix for populate_editor's no_update + options tuple pattern."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "callbacks.py").read_text(encoding="utf-8")
    # Extract the populate_editor function body (rough heuristic: between def populate_editor and the next top-level def)
    marker_start = src.index("def populate_editor(")
    # Find the next function def at the same indentation (4 spaces) — stops at the next @app.callback or def
    marker_end = src.index("\n    # --- Type-adaptive field visibility ---", marker_start)
    body = src[marker_start:marker_end]
    assert "[dash.no_update]*13" not in body and "[dash.no_update] * 13" not in body, (
        "populate_editor contains a return path with 13 trailing no_updates; should be 14 to match the 37-output schema"
    )
