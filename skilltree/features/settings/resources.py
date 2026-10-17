"""The Resources page of Settings: one form row per named section, and its
callbacks."""
import uuid

import dash
from dash import ALL, MATCH, Input, Output, State, ctx

from skilltree.features.settings.layout import build_resource_setting_rows
from skilltree.runtime.file_picker import spawn_local_file_picker
from skilltree.store.resources import (
    MAX_SECTIONS,
    get_sections,
    live_sections,
    section_link_counts,
)


def section_form_rows(store, names, name_ids, roots, root_ids,
                       use_roots, use_root_ids):
    """Overlay mounted form values on the ordered section draft.

    Only live cards mount their fields, so a removed section keeps its stored
    values. A section whose Root folder switch is off saves no root, whatever
    its hidden field still holds.
    """
    rows = [dict(row) for row in (store or get_sections())]
    by_id = {row["id"]: row for row in rows}
    for values, ids, field in ((names, name_ids, "name"),
                               (roots, root_ids, "root_path"),
                               (use_roots, use_root_ids, "use_root")):
        for value, component_id in zip(values or [], ids or []):
            row = by_id.get(component_id["index"])
            if row is None:
                continue
            if field == "use_root":
                row[field] = "enabled" in (value or [])
            else:
                row[field] = value
    for row in rows:
        if row.get("use_root") is False:
            row["root_path"] = ""
    return rows


# The mounted Resource-card fields, as the State list every callback that
# reads the draft passes to section_form_rows (after the store).
SECTION_FORM_STATES = [
    State({'type': f'resource-section-{field}', 'index': ALL}, prop)
    for field in ('name', 'root', 'root-enabled')
    for prop in ('value', 'id')
]


def register_resource_settings_callbacks(app, services):
    # --- Settings: Resource cards ---
    # The draft reloads when Settings opens and after a save lands, so a
    # removed card stops showing once its removal is real.
    @app.callback(
        Output('resource-section-settings-store', 'data'),
        Input('settings-modal', 'is_open'),
        Input('settings-save-status', 'children'),
        prevent_initial_call=True,
    )
    def load_resource_sections(is_open, save_status):
        if ctx.triggered_id == 'settings-save-status':
            if not str(save_status or '').startswith('Settings saved'):
                return dash.no_update
            return get_sections()
        return get_sections() if is_open else dash.no_update

    @app.callback(
        Output('resource-section-settings-rows', 'children'),
        Output('resource-section-limit-msg', 'children'),
        Input('resource-section-settings-store', 'data'),
    )
    def render_resource_section_settings(rows):
        rows = rows if rows is not None else get_sections()
        # The limit note stays up while you're still at the limit, and
        # clears once a removal makes room.
        full = len(live_sections(rows)) >= MAX_SECTIONS
        return (build_resource_setting_rows(rows, section_link_counts()),
                dash.no_update if full else '')

    @app.callback(
        Output({'type': 'resource-section-root-options', 'index': ALL}, 'is_open'),
        Input({'type': 'resource-section-root-enabled', 'index': ALL}, 'value'),
    )
    def toggle_resource_root_options(values):
        return ['enabled' in (value or []) for value in values]

    # Browser fallback. In the desktop window assets/editor/resource_picker.js
    # answers the click with the native folder dialog, and Dash never sees it.
    @app.callback(
        Output({'type': 'resource-section-root', 'index': MATCH}, 'value'),
        Input({'type': 'resource-section-root-browse', 'index': MATCH}, 'n_clicks'),
        State({'type': 'resource-section-root', 'index': MATCH}, 'value'),
        prevent_initial_call=True,
    )
    def browse_resource_root(n_clicks, current):
        if not n_clicks:
            return dash.no_update
        picked = spawn_local_file_picker(current or '', 'Select folder', None,
                                         directory=True)
        return picked or dash.no_update

    @app.callback(
        Output('resource-section-settings-store', 'data', allow_duplicate=True),
        Output('resource-section-limit-msg', 'children', allow_duplicate=True),
        Input('btn-resource-section-add', 'n_clicks'),
        Input({'type': 'resource-section-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'resource-section-undelete', 'index': ALL}, 'n_clicks'),
        State('resource-section-settings-store', 'data'),
        *SECTION_FORM_STATES,
        prevent_initial_call=True,
    )
    def modify_resource_sections(_add, _remove, _undelete, store, *form):
        # Re-rendered cards mount fresh buttons; only a click counts.
        if not ctx.triggered[0].get('value'):
            return dash.no_update, dash.no_update
        rows = section_form_rows(store, *form)
        trigger = ctx.triggered_id
        limit_note = f'You can have up to {MAX_SECTIONS} resources. Remove one to add another.'
        if trigger == 'btn-resource-section-add':
            if len(live_sections(rows)) >= MAX_SECTIONS:
                return dash.no_update, limit_note
            used_names = {(row.get('name') or '').casefold()
                          for row in live_sections(rows)}
            name = 'New Resource'
            suffix = 2
            while name.casefold() in used_names:
                name = f'New Resource {suffix}'
                suffix += 1
            rows.append({'id': uuid.uuid4().hex, 'name': name, 'root_path': '', 'position': len(rows), 'new': True})
            return rows, dash.no_update
        if not isinstance(trigger, dict):
            return dash.no_update, dash.no_update
        row = next((row for row in rows if row['id'] == trigger['index']), None)
        if row is None:
            return dash.no_update, dash.no_update
        if trigger['type'] == 'resource-section-undelete':
            if len(live_sections(rows)) >= MAX_SECTIONS:
                return dash.no_update, limit_note
            row.pop('deleted', None)
        elif row.get('new'):
            # Never saved, so there is nothing to hold for an undo.
            rows.remove(row)
        else:
            row['deleted'] = True
        return rows, dash.no_update
