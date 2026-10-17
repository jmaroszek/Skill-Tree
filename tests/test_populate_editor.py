"""populate_editor: what each way of loading the node editor fills it with.

The callback returns its outputs by name (EDITOR_FILL). Dash refuses a
response that leaves one out, so every call here checks that each path
returns them all.
"""

import dash

from skilltree.domain.models import STATUS_OPEN, Node
from skilltree.features.editor.form import NEW_NODE_SNAPSHOT, RELATIONSHIP_FIELDS
from skilltree.engine.callbacks import register_engine_callbacks
from support.editor_forms import call
from skilltree.store.graph.manager import GraphManager
from support.triggers import fire
from skilltree.features.editor.callbacks import EDITOR_FILL, register_editor_callbacks
from skilltree.features.nodes.callbacks import register_nodes_callbacks
from support.callbacks import registered


def _populate_editor_fn():
    return registered(register_editor_callbacks)["populate_editor"]


def _call_with_trigger(monkeypatch, trigger_id, **values):
    """Invoke populate_editor as Dash would, for one trigger.

    Values name populate_editor's parameters (search_val, add_clicks, ...) or
    fields of the editor form it takes (editor_forms.call); the rest are None.
    """
    fire(trigger_id)
    result = call(_populate_editor_fn(), **values)
    assert set(result) == set(EDITOR_FILL)
    return result


def _node(name, **fields):
    values = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    values.update(fields)
    return Node(**values)


def test_every_snapshot_value_has_an_output():
    """The form is filled from its pristine snapshot. Only the Dormant
    section's value is shown elsewhere: dormancy.py reads the snapshot."""
    assert set(NEW_NODE_SNAPSHOT) - set(EDITOR_FILL) == {"dormancy"}


def test_a_loaded_form_shows_its_snapshot(monkeypatch):
    """What the form shows is the snapshot the unsaved-changes check
    compares it with, so a node that was only loaded never counts as edited."""
    GraphManager().add_node(_node("Loaded", type="Goal", description="notes",
                                  habit_intensity_unit="hr_per_week"))
    result = _call_with_trigger(monkeypatch, "search-node", search_val="Loaded")
    shown = set(NEW_NODE_SNAPSHOT) - {"dormancy"}
    assert {key: result[key] for key in shown} == {
        key: result["snapshot"][key] for key in shown}
    assert result["time_unit_prev"] == result["time_unit"]


def test_a_new_node_form_is_blank(monkeypatch):
    result = _call_with_trigger(monkeypatch, "btn-editor-new", editor_new_clicks=1)
    assert result["snapshot"] == NEW_NODE_SNAPSHOT
    assert result["n_type"] == ""  # the "Choose node type..." placeholder
    assert result["status_text"] == STATUS_OPEN
    assert (result["original_name"], result["search"], result["bridge"]) == (None, None, None)


def test_details_new_subtask_prefills_parent_in_shared_editor(monkeypatch):
    GraphManager().add_node(_node("Parent", type="Goal"))
    result = _call_with_trigger(monkeypatch, "details-add-choice-input",
                                details_add_choice="new|123", details_selected_node="Parent")
    assert result["name"] == ""
    assert result["e_supp_h"] == ["Parent"]
    assert result["snapshot"]["e_supp_h"] == ["Parent"]


def test_details_new_subtask_waits_for_unsaved_changes_then_prefills_parent(monkeypatch):
    GraphManager().add_node(_node("Parent", type="Goal"))
    editing = dict(ed_style={"transform": "translateX(0px)"}, name="Unsaved",
                   pristine_snapshot=NEW_NODE_SNAPSHOT, details_selected_node="Parent")
    pending = _call_with_trigger(monkeypatch, "details-add-choice-input",
                                 details_add_choice="new|123", **editing)
    assert pending["pending_nav"] == "__new_subtask__|Parent"
    assert pending["unsaved_open"] is True

    cleared = _call_with_trigger(monkeypatch, "btn-unsaved-discard",
                                 pending_nav=pending["pending_nav"], **editing)
    assert cleared["e_supp_h"] == ["Parent"]
    assert cleared["snapshot"]["e_supp_h"] == ["Parent"]


def test_searching_for_an_unknown_node_leaves_the_form(monkeypatch):
    result = _call_with_trigger(monkeypatch, "search-node", search_val="Nonexistent Node Name")
    assert result["name"] is dash.no_update


def test_nothing_to_load_leaves_the_form(monkeypatch):
    """No tap, no search, no trigger value."""
    result = _call_with_trigger(monkeypatch, "")
    assert result["name"] is dash.no_update


def test_the_toolbar_toggle_leaves_the_form(monkeypatch):
    """btn-add only opens and closes the editor, so reopening shows the node
    loaded before. The relationship options are refreshed all the same."""
    result = _call_with_trigger(monkeypatch, "btn-add", add_clicks=1)
    assert result["name"] is dash.no_update
    assert all(isinstance(result[f"{key}_options"], list) for key in RELATIONSHIP_FIELDS)


def test_a_node_found_by_search_loads(monkeypatch):
    GraphManager().add_node(_node("TestNode"))
    result = _call_with_trigger(monkeypatch, "search-node", search_val="TestNode")
    assert (result["name"], result["original_name"]) == ("TestNode", "TestNode")
    assert result["unsaved_open"] is False and result["pending_nav"] is None


def test_populate_editor_includes_dormant_nodes_in_relationship_fields(monkeypatch):
    """Dormant nodes remain selectable and existing dormant edges round-trip."""
    from skilltree.domain.models import EDGE_NEEDS_HARD
    mgr = GraphManager()
    mgr.add_node(_node("ActivePrereq"))
    mgr.add_node(_node("DormantPrereq", type="Action", dormant=1))
    mgr.add_node(_node("TargetGoal", type="Goal"))
    mgr.add_edge("ActivePrereq", "TargetGoal", EDGE_NEEDS_HARD)
    mgr.add_edge("DormantPrereq", "TargetGoal", EDGE_NEEDS_HARD)
    # Open the editor for TargetGoal via the edit-trigger path.
    result = _call_with_trigger(monkeypatch, "edit-trigger-input",
                                edit_trigger_val="TargetGoal|123")
    assert "ActivePrereq" in result["e_needs_h"]
    assert "DormantPrereq" in result["e_needs_h"]
    for key in RELATIONSHIP_FIELDS:
        assert {option["value"] for option in result[f"{key}_options"]} == {
            "ActivePrereq", "DormantPrereq"
        }


def test_populate_editor_loads_a_dormant_node_found_by_search(monkeypatch):
    """There is one node editor. Searching for a dormant node loads it,
    rather than opening the sidebar on whatever was loaded before."""
    GraphManager().add_node(_node("Sleeper", type="Action", description="asleep", dormant=1))
    result = _call_with_trigger(monkeypatch, "search-node", search_val="Sleeper")
    assert result["name"] == "Sleeper"
    assert result["desc"] == "asleep"
    assert result["original_name"] == "Sleeper"
    assert result["snapshot"]["dormancy"]["dormant"] is True


def test_a_tap_on_a_node_deleted_meanwhile_leaves_the_form(monkeypatch):
    """The canvas can still show a node the database no longer has."""
    result = _call_with_trigger(monkeypatch, "cytoscape-graph",
                                tapped_node={"id": "Gone", "label": "Gone"})
    assert result["name"] is dash.no_update


def test_revert_reloads_the_loaded_node(monkeypatch):
    """Revert puts back what is stored, dropping the unsaved edit."""
    GraphManager().add_node(_node("Plain", description="stored"))
    result = _call_with_trigger(monkeypatch, "btn-revert", revert_clicks=1,
                                original_name="Plain", name="Plain",
                                desc="unsaved edit")
    assert (result["name"], result["desc"]) == ("Plain", "stored")
    assert result["snapshot"]["desc"] == "stored"


def test_revert_of_a_node_deleted_meanwhile_leaves_the_form(monkeypatch):
    result = _call_with_trigger(monkeypatch, "btn-revert", revert_clicks=1,
                                original_name="Gone", name="Gone")
    assert (result["name"], result["desc"]) == (dash.no_update, dash.no_update)


def test_revert_does_not_go_through_the_edit_trigger(services):
    """The Edit trigger's payload was built wrong, so Revert reloaded
    nothing, and the trigger switches to the Nodes tab from Details."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_engine_callbacks(app, services)
    register_editor_callbacks(app, services)
    register_nodes_callbacks(app, services)
    for key, spec in app.callback_map.items():
        if "edit-trigger-input.value" in key:
            assert all(dep["id"] != "btn-revert" for dep in spec["inputs"])
