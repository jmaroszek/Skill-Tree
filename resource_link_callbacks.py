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

from callback_helpers import (render_resource_sections, resource_link_values,
                              spawn_local_file_picker)
from prerender import prerendered
from resource_links import NeedsConfirmation, get_sections, open_resource, store_path

logger = logging.getLogger(__name__)


def register_resource_link_callbacks(app, services=None):
    """Register the editor's Resources callbacks. ``services`` is unused: links
    are read and saved through resource_links, not the graph managers."""
    # --- Resources ---
    # One set of pattern-matched callbacks serves every section. A row's id
    # index is "<section id>:<row>", so a trigger names both.
    @app.callback(
        Output('editor-resources', 'children'),
        Input('resource-links-store', 'data'),
        prevent_initial_call=True,
    )
    @prerendered
    def render_resources(links):
        return render_resource_sections(links)

    # A Settings save can add, rename or remove sections. Redraw them around
    # what the user has typed, not the links last loaded.
    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
        Input('settings-save-status', 'children'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def keep_typed_links_across_settings_save(_status, values, ids):
        return resource_link_values(values, ids)

    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
        Input({'type': 'resource-add', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'resource-link', 'index': ALL}, 'value'),
        State({'type': 'resource-link', 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def modify_resource_links(_adds, _removes, _browses, values, ids):
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
            filetypes = ([("Markdown files", "*.md"), ("All files", "*.*")]
                         if section['kind'] == 'obsidian' else [("All files", "*.*")])
            picked = spawn_local_file_picker(section['root_path'],
                                             f"Select {section['name']} file", filetypes)
            if not picked:
                return dash.no_update
            items[index] = store_path(picked, section['root_path'])
        links[section_id] = items
        return links

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
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
            return ('That resource no longer exists.',) + unchanged
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
        Output('save-output', 'children', allow_duplicate=True),
        Input('confirm-open-link', 'submit_n_clicks'),
        State('pending-open-link', 'data'),
        prevent_initial_call=True,
    )
    def open_confirmed_link(submitted, pending):
        if not submitted or not isinstance(pending, dict):
            return dash.no_update
        section = next((s for s in get_sections() if s['id'] == pending.get('section')), None)
        if section is None:
            return 'That resource no longer exists.'
        try:
            open_resource(pending.get('link', ''), section, confirmed=True)
            return dash.no_update
        except Exception as exc:
            return _open_failed(section, exc)

    def _open_failed(section, exc):
        # A missing file or an unset root folder is expected, and its text
        # says what to fix. The log keeps it for anything stranger.
        logger.warning("Opening a %s link failed: %s", section['name'], exc)
        return f"Error opening {section['name']}: {exc}"

    # The desktop window's native picker (assets/resource_picker.js) reports
    # its choice here; the browser fallback runs in modify_resource_links.
    @app.callback(
        Output('resource-links-store', 'data', allow_duplicate=True),
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
            return links
        except (KeyError, ValueError, TypeError, IndexError, AttributeError, StopIteration):
            return dash.no_update
