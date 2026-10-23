"""The core callback's outputs, by name.

A CoreResponse sets only what changed; every other output stays no_update.
CORE_OUTPUTS maps each field to its Dash Output. `keyed` lets the callback
build a CoreResponse while Dash receives the outputs by name.
"""
import functools
from typing import NamedTuple

from dash import Output, no_update


class CoreResponse(NamedTuple):
    elements: object = no_update
    message: object = no_update
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
    # The modal's ratings and time sections and its notes prompt, sent with
    # the modal so a Milestone never shows the full form first.
    calibration_ratings_style: object = no_update
    calibration_time_style: object = no_update
    calibration_notes_placeholder: object = no_update
    # {"name", "via", "ts"} after a save commits, and only then. Callbacks
    # that act on a finished save listen here instead of to the Save buttons,
    # which fire whether or not the save goes through.
    save_result: object = no_update
    # The editor's Done switch and saved-form snapshot, when the node it shows
    # changed status outside the editor (editor form.follow_done_status).
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


CORE_OUTPUTS = dict(
    elements=Output('elements-pending-store', 'data', allow_duplicate=True),
    message=Output('save-output', 'children'),
    community_options=Output('filter-community', 'options'),
    search_options=Output('search-node', 'options'),
    editor_style=Output('sidebar-editor-container', 'style'),
    filter_context_options=Output('filter-context', 'options'),
    node_context_options=Output('node-context', 'options'),
    node_type_options=Output('node-type', 'options'),
    filter_type_options=Output('filter-node-type', 'options'),
    stylesheet=Output('cytoscape-graph', 'stylesheet'),
    clear_focus_style=Output('btn-clear-focus', 'style'),
    goal_style=Output('details-goal-sidebar', 'style', allow_duplicate=True),
    events_style=Output('events-sidebar-container', 'style', allow_duplicate=True),
    undo_open=Output('modal-undo-done-confirm', 'is_open'),
    undo_body=Output('undo-done-confirm-body', 'children'),
    undo_pending=Output('pending-undo-done-store', 'data'),
    calibration_open=Output('modal-time-calibration', 'is_open'),
    calibration_reference=Output('time-calibration-reference', 'children'),
    calibration_pending=Output('time-calibration-pending-store', 'data'),
    calibration_unit=Output('time-calibration-unit', 'value', allow_duplicate=True),
    calibration_title=Output('time-calibration-title', 'children', allow_duplicate=True),
    calibration_ratings_style=Output('calibration-vie-section', 'style', allow_duplicate=True),
    calibration_time_style=Output('calibration-time-section', 'style', allow_duplicate=True),
    calibration_notes_placeholder=Output('calibration-notes', 'placeholder', allow_duplicate=True),
    save_result=Output('editor-save-result-store', 'data'),
    editor_done=Output('node-status-done', 'value', allow_duplicate=True),
    editor_snapshot=Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
    reopen_open=Output('modal-editor-reopen-confirm', 'is_open', allow_duplicate=True),
    reopen_body=Output('editor-reopen-confirm-body', 'children'),
    reopen_pending=Output('editor-reopen-pending-store', 'data'),
    community_value=Output('filter-community', 'value', allow_duplicate=True),
    community_memory=Output('community-memory-store', 'data'),
)


def keyed(callback):
    """Let `callback` return a CoreResponse. Dash receives its fields by name."""
    @functools.wraps(callback)
    def wrapped(*args, **kwargs):
        return callback(*args, **kwargs)._asdict()
    return wrapped
