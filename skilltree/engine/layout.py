"""The dialogs the core engine opens: undo Done, the auto-Done suggestion and group delete."""
import dash_bootstrap_components as dbc


# Confirmation modal for un-marking a Done node when downstream Done nodes
# would be re-blocked by the cascade. Lists the affected nodes and waits for
# explicit confirmation so the user knows their previously-Done dependents
# will flip to Blocked.
def build_undo_done_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Un-mark as Done?")),
        dbc.ModalBody(id="undo-done-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-undo-done-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Un-mark", id="btn-undo-done-confirm", color="warning", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-undo-done-confirm", size="sm", is_open=False, centered=True)


# Suggestion modal that fires when the last hard prerequisite of a Goal or
# inherited-time container becomes Done (never a Milestone). Offers a one-click
# "Mark Done" without forcing it — matches the user's preference that container
# completion remain explicit.
def build_auto_done_suggestion_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Mark Done?")),
        dbc.ModalBody(id="auto-done-suggestion-body"),
        dbc.ModalFooter([
            dbc.Button("Dismiss", id="btn-auto-done-dismiss", color="secondary", className="flex-fill me-2"),
            dbc.Button("Mark Done", id="btn-auto-done-confirm", color="primary", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-auto-done-suggestion", size="sm", is_open=False, centered=True)


# Used by the canvas context menu and Delete-key hotkey — handles one or many
# nodes. Distinct from the node-editor delete flow above, which always targets
# the single node currently open in the editor.
def build_group_delete_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
        dbc.ModalBody(id="group-delete-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-group-delete-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Delete", id="btn-group-delete-confirm", color="danger", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-group-delete-confirm", size="sm", is_open=False, centered=True)
