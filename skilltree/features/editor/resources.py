"""The node editor's Resources: rows of links, grouped by section.

One set of pattern-matched callbacks serves every section; a row's id index
is "<section id>:<row>". Opening a link goes through resource_links'
opener, which asks first when a link would run a program, hand itself to
another app, or reach another computer.
"""
import json
import logging

import dash
from dash import Input, Output, State, ALL, ctx

from skilltree.ui.notices import error

from skilltree.ui.kit import hint
from skilltree.features.editor.form import resource_link_values
from skilltree.runtime.file_picker import spawn_local_file_picker
from skilltree.store.resources import get_sections, store_path
from skilltree.runtime.opener import NeedsConfirmation, open_resource
from dash import html
from skilltree.ui.kit import add_button
import dash_bootstrap_components as dbc

logger = logging.getLogger(__name__)


def register_resource_link_callbacks(app, services):
    """Register the editor's Resources callbacks. ``services`` is unused: links
    are read and saved through resource_links, not the graph managers."""
    # --- Resources ---
    # One set of pattern-matched callbacks serves every section. A row's id
    # index is "<section id>:<row>", so a trigger names both. Each change draws
    # the rows it leaves, as a node load does (view.editor_view). They used to be
    # drawn from a store by a callback of their own, a pass later, so a load
    # showed its links after the rest of the form.
    _ROWS = Output('editor-resources', 'children', allow_duplicate=True)

    # A Settings save can add, rename or remove sections. Redraw them around
    # what the user has typed, not the links last loaded.
    @app.callback(
        _ROWS,
        Input('settings-version-store', 'data'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def keep_typed_links_across_settings_save(_version, values, ids):
        return _with_rows(resource_link_values(values, ids))

    @app.callback(
        _ROWS,
        Input({'type': 'resource-add', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def modify_resource_links(_adds, _removes, _browses, values, ids):
        return _with_rows(_modified_links(values, ids))

    def _modified_links(values, ids):
        trigger = ctx.triggered_id
        # A re-render mounts fresh buttons that match these ALL inputs; only a
        # real click carries n_clicks.
        if not isinstance(trigger, dict) or not ctx.triggered[0].get('value'):
            return dash.no_update
        links = resource_link_values(values, ids)
        if trigger['type'] == 'resource-add':
            links[trigger['index']] = (links.get(trigger['index']) or []) + ['']
            return links
        section_id, _, index_text = trigger['index'].rpartition(':')
        index = int(index_text)
        items = links.get(section_id) or ['']
        if index >= len(items):
            return dash.no_update
        if trigger['type'] == 'resource-remove':
            if len(items) < 2:
                return dash.no_update
            items.pop(index)
        else:
            section = next((s for s in get_sections() if s['id'] == section_id), None)
            if section is None:
                return dash.no_update
            picked = spawn_local_file_picker(section['root_path'],
                                             f"Select {section['name']} file",
                                             [("All files", "*.*")])
            if not picked:
                return dash.no_update
            items[index] = store_path(picked, section['root_path'])
        links[section_id] = items
        return links

    @app.callback(
        Output('notice-store', 'data', allow_duplicate=True),
        Output('confirm-open-link', 'message'),
        Output('confirm-open-link', 'displayed'),
        Output('pending-open-link', 'data'),
        Input({'type': 'resource-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def open_resource_link(_clicks, values, ids):
        unchanged = (dash.no_update,) * 3
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0].get('value'):
            return (dash.no_update,) + unchanged
        key = trigger['index']
        section_id = key.rpartition(':')[0]
        section = next((s for s in get_sections() if s['id'] == section_id), None)
        if section is None:
            return (error('That resource no longer exists.'),) + unchanged
        value = next((value for value, item_id in zip(values, ids)
                      if item_id['index'] == key), '')
        try:
            open_resource(value, section)
            return (dash.no_update,) + unchanged
        except NeedsConfirmation as ask:
            return dash.no_update, str(ask), True, {"section": section_id, "link": value}
        except Exception as exc:
            return (_open_failed(section, exc),) + unchanged

    # A yes in the dialog above.
    @app.callback(
        Output('notice-store', 'data', allow_duplicate=True),
        Input('confirm-open-link', 'submit_n_clicks'),
        State('pending-open-link', 'data'),
        prevent_initial_call=True,
    )
    def open_confirmed_link(submitted, pending):
        if not submitted or not isinstance(pending, dict):
            return dash.no_update
        section = next((s for s in get_sections() if s['id'] == pending.get('section')), None)
        if section is None:
            return error('That resource no longer exists.')
        try:
            open_resource(pending.get('link', ''), section, confirmed=True)
            return dash.no_update
        except Exception as exc:
            return _open_failed(section, exc)

    def _open_failed(section, exc):
        # A missing file or an unset root folder is expected, and its text
        # says what to fix. The log keeps it for anything stranger.
        logger.warning("Opening a %s link failed: %s", section['name'], exc)
        return error(f"Couldn't open that {section['name']} link. {exc}")

    # The desktop window's native picker (assets/editor/resource_picker.js) reports
    # its choice here; the browser fallback runs in modify_resource_links.
    @app.callback(
        _ROWS,
        Input('electron-file-picked-input', 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def receive_electron_file_pick(payload, values, ids):
        try:
            selected = json.loads(payload)
            section_id, _, index_text = selected['index'].rpartition(':')
            section = next(s for s in get_sections() if s['id'] == section_id)
            links = resource_link_values(values, ids)
            links[section_id][int(index_text)] = store_path(selected['path'],
                                                            section['root_path'])
            return _with_rows(links)
        except (KeyError, ValueError, TypeError, IndexError, AttributeError, StopIteration):
            return _with_rows(dash.no_update)


def _with_rows(links):
    """The rows that show ``links``."""
    if links is dash.no_update:
        return dash.no_update
    return render_resource_sections(links)


def render_resource_sections(links):
    """The node editor's Resources: one labeled block of link rows per section.

    Each row is an input plus trailing browse / open / remove icons in one
    .editor-field-group. A section always shows at least one (empty) row. The
    row index rides in the id ("<section>:<i>") so one set of pattern-matched
    callbacks serves every section.
    """
    blocks = []
    for section in get_sections():
        section_id = section['id']
        values = (links or {}).get(section_id) or ['']
        rows = []
        for index, value in enumerate(values):
            key = f"{section_id}:{index}"
            children = [dbc.Input(id={'type': 'resource-link', 'index': key},
                                  value=value, type='text', placeholder='Path or URL...'),
                        html.Button(html.I(className='bi bi-folder2-open'),
                                   id={'type': 'resource-browse', 'index': key},
                                   type='button', className='btn btn-primary editor-icon-btn', **hint('Browse', label=True)),
                        # An empty row has nothing to open. It's drawn hidden, in
                        # the same paint as the row: link_open_visibility.js only
                        # follows typing, a frame later.
                        html.Button(html.I(className='bi bi-box-arrow-up-right'),
                                   id={'type': 'resource-open', 'index': key},
                                   type='button',
                                   className='btn btn-primary editor-icon-btn'
                                   + ('' if (value or '').strip() else ' d-none'),
                                   **hint('Open', label=True))]
            if len(values) > 1:
                children.append(html.Button(html.I(className='bi bi-x-lg'),
                           id={'type': 'resource-remove', 'index': key},
                           type='button', className='btn btn-primary editor-icon-btn editor-icon-btn-danger',
                           **hint('Remove link', label=True)))
            rows.append(html.Div(children, className='d-flex editor-field-group mb-1'))
        blocks.append(html.Div([
            html.Div([dbc.Label(section['name'], className='mb-0'),
                      add_button({'type': 'resource-add', 'index': section_id}, "Add link")],
                     className='d-flex align-items-center mt-2 mb-1'),
            html.Div(rows),
        ], **{'data-resource-root': section['root_path'],
              'data-resource-id': section_id}))
    return blocks
