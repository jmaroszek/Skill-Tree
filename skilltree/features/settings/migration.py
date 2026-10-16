"""The dialog that asks where nodes go when Settings removes their context."""
from dash import html
from skilltree.domain.contexts import sort_subcontexts
from skilltree.store.settings import ConfigManager
import dash_bootstrap_components as dbc


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
