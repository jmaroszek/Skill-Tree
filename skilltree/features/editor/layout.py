"""The node editor's layout."""
import dash
import dash_bootstrap_components as dbc
from dash import html


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
