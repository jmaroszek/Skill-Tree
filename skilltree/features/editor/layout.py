"""The node editor's layout."""
import dash
import dash_bootstrap_components as dbc
from dash import html
from skilltree.store.settings import ConfigManager
from skilltree.ui import tokens
from skilltree.ui.components.ratings_table import (
    HEADER_CELL_STYLE,
)
from skilltree.ui.components.ratings_table import build_popup_table_rows
from skilltree.ui.kit import edit_button
from skilltree.ui.kit import panel_close_button


def render_alias_rows(aliases, input_type="alias-input", remove_type="btn-alias-remove"):
    """Build the alias input rows (one unified field per alias, trailing ×).

    Shared by the main node editor and the add-node modals (dormant / subtask);
    callers pass the prefixed pattern-matching id types so each surface keeps
    its own component namespace. Mirrors render_resource_sections' visual style.
    """
    alias_list = aliases or ['']
    rows = []
    for i, val in enumerate(alias_list):
        rows.append(html.Div([
            dbc.Input(id={'type': input_type, 'index': i}, type='text',
                      value=val or '', placeholder='Enter alias...'),
            dbc.Button(html.I(className='bi bi-x-lg'),
                       id={'type': remove_type, 'index': i}, title='Remove alias',
                       className='editor-icon-btn editor-icon-btn-danger'),
        ], className='d-flex editor-field-group mb-1'))
    return rows


def alias_rows_label(aliases):
    """Return the singular/plural label for the rendered alias row count."""
    return "Alias" if len(aliases or ['']) == 1 else "Aliases"


def update_alias_rows(trigger, current_values, stored_values, aliases_open,
                      add_button_id, remove_button_type):
    """Apply one add/remove action to an editor's repeatable alias rows.

    The first click on the Name-label ``+`` reveals the existing first row;
    later clicks add rows. Removing the final row closes the optional section,
    ready for the next ``+`` click to reveal a fresh blank row.
    """
    aliases = (list(current_values) if current_values
               else list(stored_values or ['']))
    collapse_update = dash.no_update

    if trigger == add_button_id:
        if aliases_open:
            aliases.append('')
        collapse_update = True
    elif (isinstance(trigger, dict)
          and trigger.get('type') == remove_button_type):
        idx = trigger.get('index')
        if isinstance(idx, int) and 0 <= idx < len(aliases):
            aliases.pop(idx)
            if not aliases:
                collapse_update = False

    return aliases, collapse_update


def build_unsaved_changes_modal():
    return dbc.Modal([
        # close_button=False removes the header X so the modal can only be resolved
        # via one of the three footer actions. backdrop="static" + keyboard=False
        # block backdrop-click and Esc dismissals; Bootstrap auto-plays its built-in
        # "shake" animation on the modal when the static backdrop is clicked.
        dbc.ModalHeader(dbc.ModalTitle("Unsaved Changes"), close_button=False),
        dbc.ModalBody("You have unsaved changes. Please choose an action to continue."),
        dbc.ModalFooter([
            dbc.Button("Discard", id="btn-unsaved-discard", color="danger", className="flex-fill me-2"),
            dbc.Button("Edit", id="btn-unsaved-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Save", id="btn-unsaved-save", color="success", className="flex-fill"),
        ], className="d-flex flex-nowrap"),
    ], id="modal-unsaved-changes", size="sm", is_open=False, centered=True,
       backdrop="static", keyboard=False)


def build_delete_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
        # Names the node when it opens (callbacks.toggle_delete_modal).
        dbc.ModalBody("Are you sure you want to delete this node? This action cannot be undone.",
                      id="node-delete-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-node-delete-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Delete", id="btn-node-delete-confirm", color="danger", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-node-delete-confirm", size="sm", is_open=False, centered=True)


# The same question for a node editor save: a new Hard prerequisite that isn't
# Done reopens the Done node it leads to. core_engine holds the save, and its
# Save button runs it again once the user agrees.
def build_editor_reopen_confirm_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Reopen Done Nodes?")),
        dbc.ModalBody(id="editor-reopen-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-editor-reopen-cancel", color="secondary", className="flex-fill me-2"),
            dbc.Button("Save", id="btn-editor-reopen-confirm", color="warning", className="flex-fill"),
        ], className="d-flex"),
    ], id="modal-editor-reopen-confirm", size="sm", is_open=False, centered=True)


def build_ratings_popup():
    return html.Div([
        # Draggable header
        html.Div([
            html.Span("Ratings Reference", style={"fontWeight": "600", "fontSize": tokens.FS_MD}),
            edit_button("btn-ratings-edit", "Edit definitions",
                        className_extra="ms-2"),
            panel_close_button("btn-ratings-close", "Close ratings reference",
                               style={"marginLeft": "auto"}),
        ], id="ratings-popup-header", className="d-flex align-items-center", style={
            "cursor": "move",
            "padding": "8px 10px",
            "backgroundColor": tokens.BG_RAISED,
            "borderBottom": f"1px solid {tokens.BORDER_PANEL}",
            "borderRadius": "6px 6px 0 0",
            "flexShrink": "0",
            "userSelect": "none",
        }),
        # Scrollable body
        html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("#", style={**HEADER_CELL_STYLE, "width": "36px"}),
                    html.Th("Value", style=HEADER_CELL_STYLE),
                    html.Th("Interest", style=HEADER_CELL_STYLE),
                    html.Th("Effort", style=HEADER_CELL_STYLE),
                ])),
                html.Tbody(
                    id="ratings-popup-table-body",
                    children=build_popup_table_rows(ConfigManager.get_ratings_definitions()),
                ),
            ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": tokens.FS_CAP, "color": tokens.TEXT_PRIMARY}),
        ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
    ], id="ratings-popup", style={
        "display": "none",
        "flexDirection": "column",
        "position": "fixed",
        "top": "120px",
        "left": "420px",
        "width": "960px",
        "height": "auto",
        "maxHeight": "calc(100vh - 160px)",
        "minWidth": "400px",
        "minHeight": "200px",
        "zIndex": 9998,
        "backgroundColor": tokens.BG_PANEL,
        "border": f"1px solid {tokens.BORDER_PANEL}",
        "borderRadius": "6px",
        "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
        "resize": "both",
        "overflow": "hidden",
    })


def build_ratings_editor_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Ratings Definitions")),
        dbc.ModalBody(
            html.Div(id="ratings-editor-body"),
            style={"maxHeight": "70vh", "overflowY": "auto"},
        ),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-ratings-editor-cancel", color="secondary", className="me-auto"),
            dbc.Button("Save", id="btn-ratings-editor-save", color="primary"),
        ]),
    ], id="modal-ratings-editor", size="xl", is_open=False, centered=True,
       scrollable=True)
