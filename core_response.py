"""Named response matching the core callback's stable Dash output order."""
from typing import NamedTuple
from dash import no_update


class CoreResponse(NamedTuple):
    elements: object = no_update
    message: object = no_update
    suggestions: object = no_update
    hard_chains: object = no_update
    soft_chains: object = no_update
    synergies: object = no_update
    description: object = no_update
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
