"""The dialog that asks where nodes go when Settings removes their context:
its layout, its per-node and bulk choices, and applying them."""
import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, ctx, html

from skilltree.domain.contexts import sort_subcontexts
from skilltree.features.settings.contexts import editor_state
from skilltree.features.settings.draft import apply_settings
from skilltree.store import database
from skilltree.store.settings import ConfigManager
from skilltree.ui.dash_tools import get_trigger_id

logger = logging.getLogger(__name__)


def _orphan_name_label(n):
    """Returns the display label for an orphan node in the migration modal.

    Plain string for live nodes; a Span with a muted "(dormant — in event: X)"
    suffix for dormant orphans so the user understands they're remapping nodes
    that aren't currently on the canvas.
    """
    is_dormant = bool(getattr(n, 'dormant', False))
    if not is_dormant:
        return n.name
    events = getattr(n, 'events', None) or []
    if events:
        suffix = f" (dormant — in event: {', '.join(events)})"
    else:
        suffix = " (dormant)"
    return html.Span([
        n.name,
        html.Span(suffix,
                  className="text-muted small ms-1",
                  style={"fontStyle": "italic"}),
    ])


def build_migration_content(orphans_by_field, new_values_by_field,
                            subcontexts_by_context=None, rename_map=None):
    """Build dynamic migration modal body from orphan data.

    Per-node design: every affected node gets its own (context, subcontext)
    dropdown so heterogeneous remaps are possible. Each affected-value group
    also has a "Bulk apply" row for the common case where all nodes in a
    group should go to the same target.

    `rename_map` pre-fills per-node defaults to (new_ctx, original_subcontext)
    for a known rename. The Contexts editor carries renames onto the nodes
    before this dialog opens, so from Settings it is empty and only genuine
    removals arrive here.

    Args:
        orphans_by_field: {'context': {'OldCtx': [n_obj, ...]}, 'type': {...}, 'subcontext': {...}}
            Each n_obj must expose .name, and (for context orphans) .subcontext.
        new_values_by_field: {'context': [...], 'type': [...], 'subcontext': [...]}
        subcontexts_by_context: {ctx_name: [sub, ...]} for the post-save state.
        rename_map: {old_ctx: new_ctx} for detected pure renames.

    Returns:
        Tuple of (children list for modal body, mapping dict).
        Mapping: {
            "type":      [{"field": "type",       "old_value": ..., "node_name": ...}, ...],
            "ctx_nodes": [{"field": "context",    "old_value": ..., "node_name": ..., "group_idx": int}, ...],
            "sub_nodes": [{"field": "subcontext", "old_value": ..., "node_name": ..., "group_idx": int}, ...],
        }
        ctx_nodes/sub_nodes are ordered to match the per-node dropdown indices
        (`migration-cgc-node` / `migration-cgs-node` etc.).
    """
    rename_map = rename_map or {}
    children = []
    type_mapping = []
    ctx_node_entries = []
    sub_node_entries = []
    type_idx = 0

    # --- Type changes (one dropdown per node, grouped by old value) ---
    type_orphans = orphans_by_field.get('type', {})
    if type_orphans:
        new_vals = new_values_by_field.get('type', [])
        children.append(html.H5("Type Changes", className="mt-3 mb-2"))
        for old_val, nodes in type_orphans.items():
            options = [{"label": v, "value": v} for v in new_vals]
            default_val = new_vals[0] if new_vals else None
            children.append(dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(old_val),
                        html.Span(f" — {len(nodes)} node{'s' if len(nodes) != 1 else ''} affected",
                                  className="text-muted ms-1"),
                    ], className="mb-2"),
                    *[
                        dbc.Row([
                            dbc.Col(html.Span(_orphan_name_label(n), className="small",
                                              style={"lineHeight": "38px"}), width=5),
                            dbc.Col(dbc.Select(
                                id={"type": "migration-dropdown", "index": type_idx + i},
                                options=options,  # type: ignore[reportArgumentType]
                                value=default_val,
                                placeholder="Reassign to...",
                                size="sm",
                            ), width=7),
                        ], className="mb-1")
                        for i, n in enumerate(nodes)
                    ],
                ])
            ], className="mb-2"))
            for n in nodes:
                type_mapping.append({"field": "type", "old_value": old_val, "node_name": n.name})
                type_idx += 1

    new_ctx_vals = new_values_by_field.get('context', [])
    subcontexts_map = subcontexts_by_context or {}

    ctx_options = [{"label": v, "value": v} for v in new_ctx_vals]
    ctx_options += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]

    def _sub_options_for(ctx_val):
        mode = ConfigManager.get_subcontext_sort_mode()
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = sort_subcontexts(subcontexts_map.get(ctx_val, []), mode)
        else:
            subs = sort_subcontexts(
                [s for ss in subcontexts_map.values() for s in ss], mode
            )
        opts = [{"label": s, "value": s} for s in subs]
        opts += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]
        return opts, (subs[0] if subs else "__keep__")

    def _bulk_row(group_i, ctx_dd_type, sub_dd_type, btn_type, ctx_default, sub_opts, sub_default):
        return dbc.Row([
            dbc.Col(html.Small("Bulk apply:", className="text-muted fw-bold"),
                    width=4, className="d-flex align-items-center"),
            dbc.Col(dbc.Select(
                id={"type": ctx_dd_type, "index": group_i},
                options=ctx_options,  # type: ignore[reportArgumentType]
                value=ctx_default,
                size="sm",
            ), width=3),
            dbc.Col(dbc.Select(
                id={"type": sub_dd_type, "index": group_i},
                options=sub_opts,  # type: ignore[reportArgumentType]
                value=sub_default,
                size="sm",
            ), width=3),
            dbc.Col(dbc.Button("Apply to all", id={"type": btn_type, "index": group_i},
                               color="secondary", size="sm", className="w-100"), width=2),
        ], className="mb-2 pb-2 border-bottom")

    def _per_node_row(node_idx, name, ctx_dd_type, sub_dd_type, ctx_default, sub_opts, sub_default):
        return dbc.Row([
            dbc.Col(html.Span(name, className="small"),
                    width=4, className="d-flex align-items-center"),
            dbc.Col(dbc.Select(
                id={"type": ctx_dd_type, "index": node_idx},
                options=ctx_options,  # type: ignore[reportArgumentType]
                value=ctx_default,
                size="sm",
            ), width=4),
            dbc.Col(dbc.Select(
                id={"type": sub_dd_type, "index": node_idx},
                options=sub_opts,  # type: ignore[reportArgumentType]
                value=sub_default,
                size="sm",
            ), width=4),
        ], className="mb-1")

    header_row = dbc.Row([
        dbc.Col(html.Small("", className="text-muted fw-bold"), width=4),
        dbc.Col(html.Small("Context", className="text-muted fw-bold"), width=4),
        dbc.Col(html.Small("Subcontext", className="text-muted fw-bold"), width=4),
    ], className="mb-1 px-1")

    # --- Context changes ---
    ctx_orphans = orphans_by_field.get('context', {})
    if ctx_orphans:
        children.append(html.H5("Context Changes", className="mt-3 mb-2"))
        for group_i, (old_val, nodes) in enumerate(ctx_orphans.items()):
            renamed_to = rename_map.get(old_val)
            bulk_ctx_default = renamed_to or (new_ctx_vals[0] if new_ctx_vals else "__keep__")
            bulk_sub_opts, bulk_sub_default = _sub_options_for(bulk_ctx_default)
            if renamed_to:
                bulk_sub_default = "__keep__"

            node_rows = []
            for n in nodes:
                node_idx = len(ctx_node_entries)
                node_orig_sub = getattr(n, 'subcontext', None)
                if renamed_to:
                    new_subs = subcontexts_map.get(renamed_to, [])
                    node_default_ctx = renamed_to
                    sub_opts, fallback_default = _sub_options_for(renamed_to)
                    if node_orig_sub and node_orig_sub in new_subs:
                        node_default_sub = node_orig_sub
                    elif node_orig_sub:
                        node_default_sub = "__clear__"
                    else:
                        node_default_sub = fallback_default
                else:
                    node_default_ctx = bulk_ctx_default
                    sub_opts, node_default_sub = _sub_options_for(node_default_ctx)
                node_rows.append(_per_node_row(
                    node_idx, _orphan_name_label(n), "migration-cgc-node", "migration-cgs-node",
                    node_default_ctx, sub_opts, node_default_sub,
                ))
                ctx_node_entries.append({
                    "field": "context",
                    "old_value": old_val,
                    "node_name": n.name,
                    "group_idx": group_i,
                })

            scroll_style = {"maxHeight": "40vh", "overflowY": "auto"} if len(nodes) > 12 else {}
            header_extra = (html.Span(f" → {renamed_to}", className="text-success ms-1")
                            if renamed_to else None)
            children.append(dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(old_val),
                        header_extra,
                        html.Span(f" — {len(nodes)} node{'s' if len(nodes) != 1 else ''}",
                                  className="text-muted ms-1 small"),
                    ], className="mb-2"),
                    _bulk_row(group_i, "migration-bulk-cgc", "migration-bulk-cgs",
                              "migration-bulk-cg-apply",
                              bulk_ctx_default, bulk_sub_opts, bulk_sub_default),
                    header_row,
                    html.Div(node_rows, style=scroll_style),
                ])
            ], className="mb-2"))

    # --- Subcontext changes ---
    sub_orphans = orphans_by_field.get('subcontext', {})
    if sub_orphans:
        children.append(html.H5("Subcontext Changes", className="mt-3 mb-2"))
        for group_i, (old_val, nodes) in enumerate(sub_orphans.items()):
            # Smart default: if old label is "ctx > sub" and `sub` now lives
            # under exactly one new parent, pre-pick that (parent, sub).
            default_ctx = "__keep__"
            default_sub = "__keep__"
            if " > " in old_val:
                _, sub_name = old_val.split(" > ", 1)
                candidates = [c for c, ss in subcontexts_map.items() if sub_name in ss]
                if len(candidates) == 1:
                    default_ctx = candidates[0]
                    default_sub = sub_name
            sub_opts, _ = _sub_options_for(default_ctx)

            node_rows = []
            for n in nodes:
                node_idx = len(sub_node_entries)
                node_rows.append(_per_node_row(
                    node_idx, _orphan_name_label(n), "migration-sgc-node", "migration-sgs-node",
                    default_ctx, sub_opts, default_sub,
                ))
                sub_node_entries.append({
                    "field": "subcontext",
                    "old_value": old_val,
                    "node_name": n.name,
                    "group_idx": group_i,
                })

            scroll_style = {"maxHeight": "40vh", "overflowY": "auto"} if len(nodes) > 12 else {}
            children.append(dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(old_val),
                        html.Span(f" — {len(nodes)} node{'s' if len(nodes) != 1 else ''}",
                                  className="text-muted ms-1 small"),
                    ], className="mb-2"),
                    _bulk_row(group_i, "migration-bulk-sgc", "migration-bulk-sgs",
                              "migration-bulk-sg-apply",
                              default_ctx, sub_opts, default_sub),
                    header_row,
                    html.Div(node_rows, style=scroll_style),
                ])
            ], className="mb-2"))

    return children, {
        "type": type_mapping,
        "ctx_nodes": ctx_node_entries,
        "sub_nodes": sub_node_entries,
    }


def build_migration_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Migration Required")),
        dbc.ModalBody(id="migration-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-migration-cancel", color="secondary", className="me-auto"),
            # A refused Apply or Skip says why here. The choices above stay put
            # for another try, and nothing has been saved.
            html.Span(id="migration-error", className="text-danger me-2"),
            dbc.Button("Skip (keep old values)", id="btn-migration-skip", color="secondary", className="me-2"),
            dbc.Button("Apply Migrations", id="btn-migration-apply", color="primary"),
        ])
    ], id="modal-migration", size="xl", is_open=False, centered=True, backdrop="static")


def _apply_per_node_migrations(manager, entries: list, ctx_vals: list, sub_vals: list,
                                new_subcontexts: dict) -> None:
    """Apply per-node ctx/sub remaps via `manager.apply_node_migration`.

    Each `entries[i]` carries a 'node_name' field; ctx_vals[i] and sub_vals[i]
    are the chosen new values from the modal's per-node dropdowns.
    `__keep__` is a no-op; `__clear__` clears the field (handled inside
    `apply_node_migration` via the sentinel).
    """
    for i, entry in enumerate(entries):
        ctx_val = ctx_vals[i] if i < len(ctx_vals) else None
        sub_val = sub_vals[i] if i < len(sub_vals) else None
        if ctx_val and ctx_val != '__keep__':
            manager.apply_node_migration(entry['node_name'], 'context',
                                         ctx_val, new_subcontexts)
        if sub_val and sub_val != '__keep__':
            manager.apply_node_migration(entry['node_name'], 'subcontext',
                                         sub_val, new_subcontexts)


def register_migration_callbacks(app, services):
    manager = services.graph

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Output('context-editor-store', 'data', allow_duplicate=True),
        Output('migration-error', 'children'),
        Output('pending-settings-store', 'data', allow_duplicate=True),
        Output('settings-save-status', 'children', allow_duplicate=True),
        Output('settings-modal', 'is_open', allow_duplicate=True),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        Input('btn-migration-cancel', 'n_clicks'),
        State({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
        running=[(Output(button, 'disabled'), True, False)
                 for button in ('btn-migration-apply', 'btn-migration-skip', 'btn-migration-cancel')],
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks, cancel_clicks,
                         cgc_node_values, cgs_node_values,
                         sgc_node_values, sgs_node_values,
                         mapping_data, pending_state):
        from types import SimpleNamespace

        trigger_id = get_trigger_id()

        if trigger_id == 'pending-settings-store' and pending_data:
            orphans = pending_data.get('orphans', {})
            new_values = pending_data.get('new_values', {})
            subcontexts_by_context = pending_data.get('subcontexts', {})
            rename_map = pending_data.get('rename_map', {})

            orphans_for_ui = {}
            for field, val_map in orphans.items():
                orphans_for_ui[field] = {}
                for old_val, node_dicts in val_map.items():
                    orphans_for_ui[field][old_val] = [SimpleNamespace(**d) for d in node_dicts]

            children, mapping = build_migration_content(
                orphans_for_ui, new_values, subcontexts_by_context,
                rename_map=rename_map,
            )
            return (True, children, mapping, dash.no_update, "",
                    dash.no_update, dash.no_update, dash.no_update)

        if trigger_id == 'btn-migration-cancel':
            # Declining migration returns to the complete draft, including the
            # context removals, so the user can correct it without losing edits.
            return False, [], None, dash.no_update, "", None, "", dash.no_update

        if trigger_id in ('btn-migration-apply', 'btn-migration-skip') and pending_state:
            try:
                # One transaction: the renames, the settings and any rehoming
                # are saved together or not at all.
                with database.transaction():
                    # The renames and moves the editor already resolved go on
                    # first, on Skip as well as Apply: skipping declines to rehome
                    # the stranded nodes, not to make the rename that was asked
                    # for. Doing it here rather than at Save is what makes Cancel
                    # leave the graph untouched.
                    manager.apply_taxonomy_migration(
                        pending_state.get('ctx_renames', {}),
                        pending_state.get('pair_moves', []),
                    )

                    apply_settings(pending_state)

                    if trigger_id == 'btn-migration-apply' and mapping_data:
                        new_subcontexts = pending_state.get('subcontexts', {})

                        ctx_nodes = mapping_data.get('ctx_nodes', []) if isinstance(mapping_data, dict) else []
                        _apply_per_node_migrations(manager, ctx_nodes, cgc_node_values,
                                                    cgs_node_values, new_subcontexts)

                        sub_nodes = mapping_data.get('sub_nodes', []) if isinstance(mapping_data, dict) else []
                        _apply_per_node_migrations(manager, sub_nodes, sgc_node_values,
                                                    sgs_node_values, new_subcontexts)
                    editor = editor_state(manager)
            except Exception:
                logger.exception("Failed to apply the settings migration")
                return (dash.no_update,) * 4 + (
                    "Couldn't apply the changes, so nothing was saved. The log "
                    "has the details.",) + (dash.no_update,) * 3

            # Re-seed the rows from what was just saved, so the next edit
            # diffs against it and the node counts reflect the rehoming.
            return False, [], None, editor, "", None, "Settings saved", False

        return (dash.no_update,) * 8

    def _filtered_sub_options(ctx_val, subcontexts_map):
        mode = ConfigManager.get_subcontext_sort_mode()
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = sort_subcontexts(subcontexts_map.get(ctx_val, []), mode)
        else:
            subs = sort_subcontexts(
                [s for ss in subcontexts_map.values() for s in ss], mode
            )
        opts = [{"label": s, "value": s} for s in subs]
        opts += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]
        default = subs[0] if subs else "__keep__"
        return opts, default

    def _per_row_filter(ctx_vals, sub_vals, pending_data):
        """Shared body for per-node ctx→sub cascading callbacks.

        Updates only the triggered row's options. Preserves the row's current
        sub value when it remains valid under the new ctx — this is what
        keeps bulk-apply from being clobbered when its programmatic ctx writes
        re-trigger this callback.
        """
        if not ctx_vals:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return [dash.no_update] * len(ctx_vals), [dash.no_update] * len(ctx_vals)
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(ctx_vals)
        new_vals = [dash.no_update] * len(ctx_vals)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(ctx_vals[pos], subcontexts_map)
                new_opts[pos] = opts
                current_sub = sub_vals[pos] if pos < len(sub_vals) else None
                valid_subs = {o['value'] for o in opts}
                new_vals[pos] = dash.no_update if current_sub in valid_subs else default
                break
        return new_opts, new_vals

    # --- Migration: per-node cascading filter for context-orphan section ---
    @app.callback(
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "options"),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        Input({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_cgs_node_options(cgc_vals, cgs_vals, pending_data):
        return _per_row_filter(cgc_vals, cgs_vals, pending_data)

    # --- Migration: per-node cascading filter for subcontext-orphan section ---
    @app.callback(
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "options"),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        Input({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_sgs_node_options(sgc_vals, sgs_vals, pending_data):
        return _per_row_filter(sgc_vals, sgs_vals, pending_data)

    def _bulk_cascading(bulk_ctx_vals, pending_data):
        """Cascading filter for the per-group bulk-apply ctx → sub dropdown."""
        if not bulk_ctx_vals:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return ([dash.no_update] * len(bulk_ctx_vals),
                    [dash.no_update] * len(bulk_ctx_vals))
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(bulk_ctx_vals)
        new_vals = [dash.no_update] * len(bulk_ctx_vals)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(bulk_ctx_vals[pos], subcontexts_map)
                new_opts[pos] = opts
                new_vals[pos] = default
                break
        return new_opts, new_vals

    # --- Migration: cascading filter for ctx-orphan bulk row ---
    @app.callback(
        Output({"type": "migration-bulk-cgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-bulk-cgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-bulk-cgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_bulk_cgs_options(bulk_ctx_vals, pending_data):
        return _bulk_cascading(bulk_ctx_vals, pending_data)

    # --- Migration: cascading filter for sub-orphan bulk row ---
    @app.callback(
        Output({"type": "migration-bulk-sgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-bulk-sgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-bulk-sgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_bulk_sgs_options(bulk_ctx_vals, pending_data):
        return _bulk_cascading(bulk_ctx_vals, pending_data)

    def _bulk_apply(entries_key, ctx_dd_type, sub_dd_type,
                    bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                    n_ctx_outputs):
        """Push a single (ctx, sub) pair to every per-node row in the
        triggered group. Returns (ctx_values, sub_values, sub_options) lists
        sized to the per-node dropdowns; rows outside the group get no_update.
        """
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or n_ctx_outputs == 0:
            return ([dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs)
        group_i = triggered.get('index')
        entries = (mapping_data or {}).get(entries_key, [])
        # Bulk dropdowns are indexed per group; pick the values for THIS group.
        new_ctx = bulk_ctx_vals[group_i] if group_i < len(bulk_ctx_vals) else None
        new_sub = bulk_sub_vals[group_i] if group_i < len(bulk_sub_vals) else None
        if not new_ctx:
            return ([dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs)
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        sub_opts, _ = _filtered_sub_options(new_ctx, subcontexts_map)
        ctx_out = [dash.no_update] * n_ctx_outputs
        sub_out = [dash.no_update] * n_ctx_outputs
        opts_out = [dash.no_update] * n_ctx_outputs
        for i, entry in enumerate(entries):
            if i >= n_ctx_outputs:
                break
            if entry.get('group_idx') == group_i:
                ctx_out[i] = new_ctx
                sub_out[i] = new_sub
                opts_out[i] = sub_opts
        return ctx_out, sub_out, opts_out

    # --- Migration: bulk apply for ctx-orphan group ---
    @app.callback(
        Output({"type": "migration-cgc-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "options", allow_duplicate=True),
        Input({"type": "migration-bulk-cg-apply", "index": dash.ALL}, "n_clicks"),
        State({"type": "migration-bulk-cgc", "index": dash.ALL}, "value"),
        State({"type": "migration-bulk-cgs", "index": dash.ALL}, "value"),
        State({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def bulk_apply_cg(n_clicks_list, bulk_ctx_vals, bulk_sub_vals,
                      cgc_node_vals, mapping_data, pending_data):
        if not any(n_clicks_list):
            return (dash.no_update, dash.no_update, dash.no_update)
        return _bulk_apply('ctx_nodes', 'migration-cgc-node', 'migration-cgs-node',
                           bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                           len(cgc_node_vals))

    # --- Migration: bulk apply for sub-orphan group ---
    @app.callback(
        Output({"type": "migration-sgc-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "options", allow_duplicate=True),
        Input({"type": "migration-bulk-sg-apply", "index": dash.ALL}, "n_clicks"),
        State({"type": "migration-bulk-sgc", "index": dash.ALL}, "value"),
        State({"type": "migration-bulk-sgs", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def bulk_apply_sg(n_clicks_list, bulk_ctx_vals, bulk_sub_vals,
                      sgc_node_vals, mapping_data, pending_data):
        if not any(n_clicks_list):
            return (dash.no_update, dash.no_update, dash.no_update)
        return _bulk_apply('sub_nodes', 'migration-sgc-node', 'migration-sgs-node',
                           bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                           len(sgc_node_vals))
