"""Regression tests for the populate_editor callback output arity.

populate_editor declares 45 Outputs (35 form fields + editor-pristine-snapshot
+ node-value-mode + 8 habit-mode fields, incl. the weekday picker). Every
return path must produce exactly 45 items, or Dash throws
SchemaLengthValidationError → HTTP 500.

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


POPULATE_EDITOR_NUM_OUTPUTS = 45


def _make_state_args():
    """Return the State positional args populate_editor expects (all None/defaults).

    Order: elements, ed_style, original_name, cur_name, cur_type, cur_desc,
    cur_context, cur_subctx, cur_status_done, cur_val, cur_interest, cur_diff,
    cur_time_o, cur_time_m, cur_time_p, cur_time_unit,
    cur_needs_h, cur_needs_s, cur_supp_h, cur_supp_s, cur_helps,
    cur_obs, cur_drive, cur_website,
    cur_time_mode, cur_priority_rank,
    cur_aliases, pending_nav, pristine_snapshot, cur_value_mode,
    cur_time_habit_mode, cur_habit_duration, cur_habit_duration_unit,
    cur_habit_int_o, cur_habit_int_m, cur_habit_int_p, cur_habit_int_unit,
    cur_habit_days.
    """
    return [None] * 38


def _call_with_trigger(monkeypatch, trigger_id, inputs):
    """Invoke populate_editor with a monkeypatched trigger_id and the given 10 Input args."""
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger_id)
    fn = _populate_editor_fn()
    args = list(inputs) + _make_state_args()
    return fn(*args)


def test_populate_editor_search_unknown_node_returns_44_items(monkeypatch):
    """search-node path where resolved_name does not match any DB node."""
    # Inputs in order: tapNodeData, btn-add, btn-unsaved-discard,
    # btn-unsaved-save, search-node, background-click-input, btn-new-node,
    # edit-trigger-input, details-edit-trigger-input
    inputs = [None, None, None, None, "Nonexistent Node Name", None, None, None, None]
    result = _call_with_trigger(monkeypatch, "search-node", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"search-node unknown-node path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_fall_through_returns_44_items(monkeypatch):
    """Fall-through 'if not name or not data' path — no trigger, no data."""
    inputs = [None] * 9  # no cytoscape tap, no search, no trigger value
    result = _call_with_trigger(monkeypatch, "", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"fall-through path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_btn_add_path_returns_44_items(monkeypatch):
    """btn-add path hits the def_out branch."""
    inputs = [None, 1, None, None, None, None, None, None, None]
    result = _call_with_trigger(monkeypatch, "btn-add", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_successful_lookup_returns_44_items(monkeypatch):
    """Seed a node, search for it, and verify the happy path returns 44 items."""
    mgr = GraphManager()
    mgr.add_node(Node(
        name="TestNode", type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    inputs = [None, None, None, None, "TestNode", None, None, None, None]
    result = _call_with_trigger(monkeypatch, "search-node", inputs)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_filters_dormant_prereqs_from_edge_values(monkeypatch):
    """Regression: dcc.Dropdown silently filters its initial value to entries
    in `options` (which exclude dormant nodes), but on subsequent value updates
    it does NOT re-filter — so re-opening the same node would inflate the form
    State to include dormant items, breaking the X-close dirty check.
    populate_editor must write the already-filtered value to keep State stable
    across opens."""
    from models import EDGE_NEEDS_HARD
    mgr = GraphManager()
    mgr.add_node(Node(
        name="ActivePrereq", type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    mgr.add_node(Node(
        name="DormantPrereq", type="Action", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind", dormant=1,
    ))
    mgr.add_node(Node(
        name="TargetGoal", type="Goal", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    mgr.add_edge("ActivePrereq", "TargetGoal", EDGE_NEEDS_HARD)
    mgr.add_edge("DormantPrereq", "TargetGoal", EDGE_NEEDS_HARD)
    # Open the editor for TargetGoal via the edit-trigger path.
    # Inputs: tap, btn-add, discard, save, search, bg, new-node, edit-trigger, details-edit-trigger
    inputs = [None, None, None, None, None, None, None, "TargetGoal|123", None]
    result = _call_with_trigger(monkeypatch, "edit-trigger-input", inputs)
    # Output index 13 is `edge-needs-hard.value` (see Output declaration order).
    needs_hard_value = result[13]
    assert "ActivePrereq" in needs_hard_value
    assert "DormantPrereq" not in needs_hard_value, (
        f"populate_editor leaked a dormant prereq into the dropdown value: {needs_hard_value}"
    )


def test_populate_editor_all_return_paths_use_22_not_21(monkeypatch):
    """Static guard: every early-return filler in populate_editor must carry
    22 trailing no_updates, not 21.

    The schema is 18 + 5 + 22 = 45 outputs (the +22 includes node-value-mode
    plus 8 habit-mode fields, incl. the weekday picker). A leftover *21 means
    someone added an Output without bumping the early-return filler arrays."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "callbacks.py").read_text(encoding="utf-8")
    marker_start = src.index("def populate_editor(")
    marker_end = src.index("\n    # --- Type-adaptive field visibility ---", marker_start)
    body = src[marker_start:marker_end]
    assert "[dash.no_update]*21" not in body and "[dash.no_update] * 21" not in body, (
        "populate_editor contains a return path with 21 trailing no_updates; should be 22 to match the 45-output schema"
    )
