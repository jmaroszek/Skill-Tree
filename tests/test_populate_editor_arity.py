"""Regression tests for the populate_editor callback output arity.

populate_editor declares 43 Outputs (33 form fields + editor-pristine-snapshot
+ node-value-mode + 8 habit-mode fields, incl. the weekday picker). Every
return path must produce exactly 43 items, or Dash throws
SchemaLengthValidationError → HTTP 500.

This test pins every return path at registration time by invoking the
unwrapped callback directly with trigger contexts that exercise each branch.
"""

import dash

import callbacks
from callback_helpers import NEW_NODE_SNAPSHOT
from callbacks import register_callbacks
from editor_forms import call
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


POPULATE_EDITOR_NUM_OUTPUTS = 43


def _call_with_trigger(monkeypatch, trigger_id, **values):
    """Invoke populate_editor as Dash would, with a monkeypatched trigger_id.

    Values name populate_editor's parameters (search_val, add_clicks, ...) or
    fields of the editor form it takes (editor_forms.call); the rest are None.
    """
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: trigger_id)
    return call(_populate_editor_fn(), **values)


def test_details_new_subtask_prefills_parent_in_shared_editor(monkeypatch):
    manager = GraphManager()
    manager.add_node(Node(
        name="Parent", type="Goal", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    result = _call_with_trigger(monkeypatch, "details-add-choice-input",
                                details_add_choice="new|123", details_selected_node="Parent")
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS
    assert result[0] == ""
    assert result[15] == ["Parent"]
    assert result[33]["e_supp_h"] == ["Parent"]


def test_details_new_subtask_waits_for_unsaved_changes_then_prefills_parent(monkeypatch):
    manager = GraphManager()
    manager.add_node(Node(
        name="Parent", type="Goal", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    editing = dict(ed_style={"transform": "translateX(0px)"}, name="Unsaved",
                   pristine_snapshot=NEW_NODE_SNAPSHOT, details_selected_node="Parent")
    pending = _call_with_trigger(monkeypatch, "details-add-choice-input",
                                 details_add_choice="new|123", **editing)
    assert pending[31] == "__new_subtask__|Parent"
    assert pending[32] is True

    cleared = _call_with_trigger(monkeypatch, "btn-unsaved-discard",
                                 pending_nav=pending[31], **editing)
    assert cleared[15] == ["Parent"]
    assert cleared[33]["e_supp_h"] == ["Parent"]


def test_populate_editor_search_unknown_node_returns_all_items(monkeypatch):
    """search-node path where resolved_name does not match any DB node."""
    result = _call_with_trigger(monkeypatch, "search-node", search_val="Nonexistent Node Name")
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"search-node unknown-node path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_fall_through_returns_all_items(monkeypatch):
    """Fall-through 'if not name or not data' path — no trigger, no data."""
    # No cytoscape tap, no search, no trigger value.
    result = _call_with_trigger(monkeypatch, "")
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS, (
        f"fall-through path returned {len(result)} items, expected {POPULATE_EDITOR_NUM_OUTPUTS}"
    )


def test_populate_editor_btn_add_path_returns_all_items(monkeypatch):
    """btn-add (toolbar toggle) returns the all-no_update branch — it preserves
    the form rather than clearing it. Still must produce the full output arity."""
    result = _call_with_trigger(monkeypatch, "btn-add", add_clicks=1)
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_successful_lookup_returns_all_items(monkeypatch):
    """Seed a node, search for it, and verify the happy path returns every item."""
    mgr = GraphManager()
    mgr.add_node(Node(
        name="TestNode", type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    ))
    result = _call_with_trigger(monkeypatch, "search-node", search_val="TestNode")
    assert len(result) == POPULATE_EDITOR_NUM_OUTPUTS


def test_populate_editor_includes_dormant_nodes_in_relationship_fields(monkeypatch):
    """Dormant nodes remain selectable and existing dormant edges round-trip."""
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
    result = _call_with_trigger(monkeypatch, "edit-trigger-input",
                                edit_trigger_val="TargetGoal|123")
    # Output index 13 is `edge-needs-hard.value` (see Output declaration order).
    needs_hard_value = result[13]
    assert "ActivePrereq" in needs_hard_value
    assert "DormantPrereq" in needs_hard_value
    # Output indices 18-22 are the five relationship dropdown option lists.
    for options in result[18:23]:
        assert {option["value"] for option in options} == {
            "ActivePrereq", "DormantPrereq"
        }


def test_populate_editor_loads_a_dormant_node_found_by_search(monkeypatch):
    """There is one node editor. Searching for a dormant node loads it,
    rather than opening the sidebar on whatever was loaded before."""
    GraphManager().add_node(Node(
        name="Sleeper", type="Action", description="asleep", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind", dormant=1,
    ))
    result = _call_with_trigger(monkeypatch, "search-node", search_val="Sleeper")
    assert result[0] == "Sleeper"
    assert result[2] == "asleep"
    assert result[26] == "Sleeper"  # node-original-name
    assert result[33]["dormancy"]["dormant"] is True


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
