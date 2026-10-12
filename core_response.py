"""Named response matching the core callback's stable Dash output order."""
from typing import NamedTuple
from dash import no_update


class CoreResponse(NamedTuple):
    elements: object = no_update
    message: object = no_update
    clear_disabled: object = no_update
    clear_intervals: object = no_update
    community_options: object = no_update
    search_options: object = no_update
    editor_style: object = no_update
    filter_context_options: object = no_update
    node_context_options: object = no_update
    node_type_options: object = no_update
    filter_type_options: object = no_update
    stylesheet: object = no_update
    clear_focus_style: object = no_update
    goal_style: object = no_update
    events_style: object = no_update
    undo_open: object = no_update
    undo_body: object = no_update
    undo_pending: object = no_update
    calibration_open: object = no_update
    calibration_reference: object = no_update
    calibration_pending: object = no_update
    calibration_unit: object = no_update
    calibration_title: object = no_update
    # {"name", "via", "ts"} after a save commits, and only then. Callbacks
    # that act on a finished save listen here instead of to the Save buttons,
    # which fire whether or not the save goes through.
    save_result: object = no_update
    # The editor's Done switch and saved-form snapshot, when the node it shows
    # changed status outside the editor (callback_helpers.follow_done_status).
    editor_done: object = no_update
    editor_snapshot: object = no_update
    # A save that would reopen Done nodes waits: the confirmation, what it
    # says, and which Save button to finish with once the user agrees.
    reopen_open: object = no_update
    reopen_body: object = no_update
    reopen_pending: object = no_update
    # The Community select's value, when the selected cluster's label changed
    # or the cluster is gone, and the members the selection stands for
    # (canvas_view.resolve_community).
    community_value: object = no_update
    community_memory: object = no_update
