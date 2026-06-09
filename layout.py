"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from config import (
    ConfigManager,
    CANVAS_HEIGHT,
    TOOLTIP_SHOW_DELAY_MS,
    TOOLTIP_HIDE_DELAY_MS,
    TOOLTIP_NODE_HIDE_DELAY_MS,
    TOAST_CLEAR_INTERVAL_MS,
    DEFAULT_GRAPH_LAYOUT,
    sort_subcontexts,
)
from events_layout import build_events_tab_content
from details_layout import build_details_tab_content, _freeze_indicator, build_graph_settings_panel
from settings_layout import build_settings_modal
from review_hub_layout import build_review_hub_modal
from analyze_layout import build_analyze_tab_content
from sidebars_layout import build_all_sidebars
from styles import stylesheet
from models import STATUS_DONE



# --- Graph View (Canvas only) ---

def create_graph_view(initial_elements):
    """Create the Cytoscape graph canvas with fullscreen toggle button."""
    gl = ConfigManager.get_graph_layout_defaults()
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={
                    'name': 'fcose', 'quality': 'proof',
                    'fit': True, 'animate': False,
                    'padding': 30, 'numIter': 2500, 'randomize': True,
                    'idealEdgeLength': gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
                    'nodeRepulsion': gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
                    'gravity': gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
                },
                style={'width': '100%', 'height': '100%',
                       'backgroundColor': '#1a1d21', 'borderRadius': '8px'},
                elements=initial_elements,
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                boxSelectionEnabled=True,
                userPanningEnabled=False,
                autoungrabify=False
            ),
            dbc.Button(html.I(className="bi bi-gear"),
                       id="btn-graph-settings",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right"),
            dbc.Tooltip("Graph settings", target="btn-graph-settings", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            _freeze_indicator("freeze-indicator"),
            build_graph_settings_panel(
                "graph-settings",
                defaults_getter=ConfigManager.get_graph_layout_defaults,
            ),
            dbc.Button(html.I(className="bi bi-arrows-fullscreen"),
                       id="btn-fullscreen",
                       color="secondary", size="sm",
                       className="btn-canvas-overlay btn-canvas-bottom-right-mid"),
            dbc.Tooltip("Toggle fullscreen", target="btn-fullscreen", placement="left",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            html.Div(id="canvas-node-count", className="canvas-stats-overlay"),
        ], id="canvas-container", className="canvas-container h-100", style={"overflow": "hidden", "borderRadius": "8px"}),
    ], className="h-100", style={"overflow": "hidden"})





_section_title_style = {"fontSize": "1.3rem", "fontWeight": "600"}
_formula_hint_style = {"fontSize": "0.8rem", "fontFamily": "monospace", "color": "#6c757d", "marginBottom": "0.25rem"}

# --- Info Panels ---

relationships_view = html.Div([
    html.H6("Relationships", className="text-muted mb-2", style=_section_title_style),
    html.Div([
        html.Div([
            html.H6("Hard Dependencies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="traversal-chains-hard")
        ], style={"marginRight": "2rem", "flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
        html.Div([
            html.H6("Soft Dependencies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="traversal-chains-soft")
        ], style={"marginRight": "2rem", "flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
        html.Div([
            html.H6("Synergies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="synergies-list")
        ], style={"flex": "0 1 auto", "minWidth": 0, "overflow": "hidden"}),
    ], style={"display": "flex", "alignItems": "flex-start"})
], style={"flex": "0 0 auto", "maxWidth": "80%", "minWidth": 0})

description_view = html.Div([
    html.H6("Description", className="text-muted mb-2", style=_section_title_style),
    html.Div(id="node-info-description", style={"color": "#dee2e6", "whiteSpace": "pre-wrap", "fontSize": "0.95rem"})
], style={"flex": "1", "marginLeft": "3rem", "minWidth": 0})

# --- Next View ---

next_view = html.Div([
    dcc.Store(id='suggestion-count-store', data=ConfigManager.get_next_table_rows()),
    
    # "Now" section — currently-Now nodes (cap = ConfigManager.get_now_node_cap()).
    # Heading + rows are emitted together by populate_now_section. The
    # section collapses to zero height when there are no Now nodes, so
    # the Next heading floats to the top of the tab.
    html.Div(id="now-nodes-table"),
    
    html.Div([
        html.H6("Next", className="text-muted mb-0", style=_section_title_style),
        dbc.ButtonGroup([
            dbc.Button("−", id="btn-sugg-minus", color="link", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 2px",
                              "color": "#6c757d", "textDecoration": "none", "boxShadow": "none"}),
            html.Span(id="suggestion-count-display", children=str(ConfigManager.get_next_table_rows()),
                       className="align-self-center mx-1",
                       style={"fontSize": "0.95rem", "fontWeight": "bold", "minWidth": "18px",
                              "textAlign": "center"}),
            dbc.Button("+", id="btn-sugg-plus", color="link", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 2px",
                              "color": "#6c757d", "textDecoration": "none", "boxShadow": "none"}),
        ], className="align-middle"),
    ], className="d-flex align-items-center mb-2", style={"gap": "12px"}),
    
    dcc.Store(id='selected-suggestion-store', data=None),
    dcc.Store(id='focus-goal-store', data=None),
    
    # Next Table and Description side-by-side
    html.Div([
        html.Div(id="suggestions-table", children=[
            html.P("Loading suggestions...", className="text-muted mt-3")
        ], style={"flex": "4 1 0", "minWidth": 0}),
        
        # Description area — populated when clicking a Now card or Next row.
        html.Div(id="next-description-area", children=[
            html.H6("Description", className="text-muted mb-2", style=_section_title_style),
            html.Div("Click a card or row to see its description",
                     style={"color": "#6c757d", "whiteSpace": "pre-wrap", "fontSize": "0.95rem"})
        ], style={"flex": "1 1 0", "maxWidth": "800px"}),
    ], style={"display": "flex", "alignItems": "flex-start", "gap": "4rem"}),
])


# --- Migration Modal ---

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

    `rename_map` (from `detect_context_renames`) pre-fills per-node defaults
    to (new_ctx, original_subcontext) when a 1:1 context rename preserves
    subcontexts — making "rename Social → People" a one-click apply.

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
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = sort_subcontexts(subcontexts_map.get(ctx_val, []))
        else:
            subs = sort_subcontexts(
                [s for ss in subcontexts_map.values() for s in ss]
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
            # Smart default: if old label is "ctx › sub" and `sub` now lives
            # under exactly one new parent, pre-pick that (parent, sub).
            default_ctx = "__keep__"
            default_sub = "__keep__"
            if " › " in old_val:
                _, sub_name = old_val.split(" › ", 1)
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


migration_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Migration Required")),
    dbc.ModalBody(id="migration-modal-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-migration-cancel", color="secondary", className="me-auto"),
        dbc.Button("Skip (keep old values)", id="btn-migration-skip", color="secondary", className="me-2"),
        dbc.Button("Apply Migrations", id="btn-migration-apply", color="primary"),
    ])
], id="modal-migration", size="xl", is_open=False, centered=True, backdrop="static")


error_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Validation Error", className="text-danger")),
    dbc.ModalBody(id="error-modal-body", style={"color": "#dee2e6"}),
    dbc.ModalFooter(dbc.Button("Close", id="btn-close-error", color="secondary"))
], id="modal-error", size="sm", is_open=False, centered=True)


unsaved_changes_modal = dbc.Modal([
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


delete_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
    dbc.ModalBody("Are you sure you want to delete this node? This action cannot be undone."),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-node-delete-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Delete", id="btn-node-delete-confirm", color="danger", className="flex-fill",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
    ], className="d-flex"),
], id="modal-node-delete-confirm", size="sm", is_open=False, centered=True)


# Confirmation modal for un-marking a Done node when downstream Done nodes
# would be re-blocked by the cascade. Lists the affected nodes and waits for
# explicit confirmation so the user knows their previously-Done dependents
# will flip to Blocked.
undo_done_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Un-mark as Done?")),
    dbc.ModalBody(id="undo-done-confirm-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-undo-done-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Un-mark", id="btn-undo-done-confirm", color="warning", className="flex-fill"),
    ], className="d-flex"),
], id="modal-undo-done-confirm", size="md", is_open=False, centered=True)


# Confirms detaching a dormant node from its event(s) and waking it back into
# the live graph. Triggered by toggling the editor's Dormant switch off.
# Distinct from the events-tab "Delete event" flow — this preserves the node,
# only severs the event association and clears dormant=1.
dormant_deactivate_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Wake node?")),
    dbc.ModalBody(id="dormant-deactivate-confirm-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-dormant-deactivate-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Wake", id="btn-dormant-deactivate-confirm", color="primary", className="flex-fill"),
    ], className="d-flex"),
], id="modal-dormant-deactivate-confirm", size="md", is_open=False, centered=True)


# Suggestion modal that fires when the last hard prerequisite of a Goal or
# Milestone becomes Done. Offers a one-click "Mark Done" without forcing it —
# matches the user's preference that container completion remain explicit.
auto_done_suggestion_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Mark Done?")),
    dbc.ModalBody(id="auto-done-suggestion-body"),
    dbc.ModalFooter([
        dbc.Button("Dismiss", id="btn-auto-done-dismiss", color="secondary", className="flex-fill me-2"),
        dbc.Button("Mark Done", id="btn-auto-done-confirm", color="primary", className="flex-fill"),
    ], className="d-flex"),
], id="modal-auto-done-suggestion", size="sm", is_open=False, centered=True)


# Time-calibration modal: pops after an explicit single-node completion to
# capture how long the work actually took. Submit persists the values onto the
# node; Skip leaves the actual_time_* fields NULL. The reference div is filled
# by core_engine with the node name and its original estimate. Input fields are
# static (the app doesn't suppress callback exceptions, so State-referenced IDs
# must exist in the initial layout); they are reset on close.
time_calibration_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Reflection", id="time-calibration-title")),
    dbc.ModalBody([
        # Progress bar — shown in review + completion (chrome callback toggles).
        html.Div(id="calibration-review-progress-wrap", style={"display": "none"},
                 className="mb-3", children=[
            dbc.Progress(id="calibration-review-progress", value=0, label="",
                         style={"height": "20px"}),
        ]),
        # Active rating form — hidden on the completion screen.
        html.Div(id="time-calibration-active", children=[
            html.Div(id="time-calibration-reference", className="text-muted small mb-3"),
            html.H6("How long did it actually take?", className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Lower Bound"),
                    dbc.Input(id="time-calibration-lower", type="number", min=0),
                ], width=4),
                dbc.Col([
                    dbc.Label("Best Estimate"),
                    dbc.Input(id="time-calibration-point", type="number", min=0),
                ], width=4),
                dbc.Col([
                    dbc.Label("Upper Bound"),
                    dbc.Input(id="time-calibration-upper", type="number", min=0),
                ], width=4),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Unit", className="mt-2"),
                    dbc.Select(id="time-calibration-unit", value="hours", options=[
                        {"label": "Hours", "value": "hours"},
                        {"label": "Weeks", "value": "weeks"},
                        {"label": "Months", "value": "months"},
                    ]),
                ], width=4),
            ], className="mt-1"),
            # V/I/E sliders — capture how the node *actually* felt now that
            # the work is done. Stored as reflect_value/interest/difficulty
            # (separate from the estimate columns value/interest/difficulty).
            html.Div(id="calibration-vie-section", children=[
                html.Hr(className="my-3"),
                html.Div([
                    html.H6("How was it actually?", className="mb-0"),
                    html.Button(
                        html.I(className="bi bi-info-circle"),
                        id="btn-reflection-ratings-info",
                        style={
                            "background": "none", "border": "none", "padding": "0 0 0 6px",
                            "color": "#6c757d", "cursor": "pointer", "fontSize": "0.95rem",
                            "lineHeight": "1", "position": "relative", "top": "0px"
                        }
                    ),
                    dbc.Tooltip("Ratings reference", target="btn-reflection-ratings-info", placement="right",
                                delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
                ], className="d-flex align-items-center mb-2"),
                dbc.Label("Actual Value", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5,
                           id="calibration-value",
                           marks={i: str(i) for i in range(1, 11)}),
                dbc.Label("Actual Interest", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5,
                           id="calibration-interest",
                           marks={i: str(i) for i in range(1, 11)}),
                dbc.Label("Actual Effort", className="mt-2"),
                dcc.Slider(min=1, max=10, step=1, value=5,
                           id="calibration-difficulty",
                           marks={i: str(i) for i in range(1, 11)}),
            ]),
        ]),
        # Completion screen — shown only after the last node of a review cycle.
        html.Div(id="time-calibration-complete", style={"display": "none"},
                 className="text-center py-3"),
    ]),
    dbc.ModalFooter([
        # Dismiss / Done are shown contextually by the chrome callback.
        dbc.Button("Don't ask again", id="btn-time-calibration-dismiss",
                   color="secondary", className="flex-fill me-2",
                   style={"display": "none"}),
        dbc.Button("Skip", id="btn-time-calibration-skip",
                   color="secondary", className="flex-fill me-2"),
        dbc.Button("Submit", id="btn-time-calibration-submit",
                   color="primary", className="flex-fill"),
        dbc.Button("Done", id="btn-time-calibration-done",
                   color="primary", className="flex-fill",
                   style={"display": "none"}),
    ], className="d-flex"),
], id="modal-time-calibration", size="lg", is_open=False, centered=True)


# Brief notification shown when calibration review is launched but every
# completed node is already rated or dismissed.
calibration_review_toast = dbc.Toast(
    id="calibration-review-toast",
    header="Reflection",
    is_open=False,
    dismissable=True,
    duration=4000,
    icon="info",
    style={"position": "fixed", "top": 66, "right": 12,
           "width": 340, "zIndex": 1100},
)


# Used by the canvas context menu and Delete-key hotkey — handles one or many
# nodes. Distinct from the node-editor delete flow above, which always targets
# the single node currently open in the editor.
group_delete_confirm_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Confirm Delete")),
    dbc.ModalBody(id="group-delete-confirm-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-group-delete-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Delete", id="btn-group-delete-confirm", color="danger", className="flex-fill",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
    ], className="d-flex"),
], id="modal-group-delete-confirm", size="sm", is_open=False, centered=True)


override_conflict_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Override Conflict")),
    dbc.ModalBody([
        html.Div(id="override-conflict-body"),
        html.Div(id="override-conflict-mode-wrapper", children=[
            html.Hr(className="my-2"),
            dbc.RadioItems(
                id="override-conflict-mode-radio",
                options=[
                    {"label": "Node Only", "value": "node_only"},
                    {"label": "Node + Hard Dependencies", "value": "hard"},
                    {"label": "Node + Soft Dependencies", "value": "soft"},
                    {"label": "Node + All Dependencies", "value": "all"},
                ],
                value="hard",
            ),
        ]),
    ]),
    dbc.ModalFooter([
        dbc.Button("Keep Current", id="btn-override-keep", color="secondary", className="flex-fill me-2"),
        dbc.Button("Apply to New", id="btn-override-replace", color="primary", className="flex-fill"),
    ], className="d-flex"),
], id="modal-override-conflict", is_open=False, centered=True)


override_untoggle_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Override Active")),
    dbc.ModalBody(id="override-untoggle-body"),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-override-untoggle-cancel", color="secondary", className="flex-fill me-2"),
        dbc.Button("Untoggle All", id="btn-override-untoggle-all", color="danger", className="flex-fill me-2",
                   style={"backgroundColor": ConfigManager.get_danger_color(),
                          "borderColor": ConfigManager.get_danger_color()}),
        dbc.Button("Hard Only", id="btn-override-untoggle-hard", color="primary", className="flex-fill me-2"),
        dbc.Button("Soft Only", id="btn-override-untoggle-soft", color="info", className="flex-fill"),
    ], className="d-flex"),
], id="modal-override-untoggle", size="md", is_open=False, centered=True)


# --- Bottom Panel (Relationships + Description) ---

bottom_panel = html.Div([
    html.Div([
        relationships_view,
        description_view
    ], className="d-flex")
], className="p-3")


# --- Floating Tooltip ---

hover_tooltip = html.Div(
    id="hover-tooltip",
    className="border rounded shadow p-2",
    style={
        "position": "fixed",
        "zIndex": 9999,
        "display": "none",
        "pointerEvents": "none",
        "maxWidth": "280px",
        "fontSize": "0.85rem",
        "lineHeight": "1.5",
        "backgroundColor": "#2b3035",
        "color": "#dee2e6",
        "borderColor": "#495057"
    }
)


_cell_style = {
    "padding": "6px 8px",
    "verticalAlign": "top",
    "borderBottom": "1px solid #343a40",
    "lineHeight": "1.4",
}
_header_cell_style = {
    **_cell_style,
    "fontWeight": "700",
    "backgroundColor": "#2b3035",
    "borderBottom": "2px solid #495057",
    "position": "sticky",
    "top": "0",
}


def _ratings_cell_children(text):
    """Render a definition string with its leading keyword (up to the first
    colon) bolded for quick scanning."""
    head, sep, tail = text.partition(':')
    if not sep:
        return text
    return [html.Strong(head + sep), tail]


def build_popup_table_rows(defs):
    """Build the ratings popup table rows from a list of definition dicts."""
    return [
        html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['value']), style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['interest']), style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
            html.Td(_ratings_cell_children(d['effort']), style={
                **_cell_style, "backgroundColor": "#1a1d21" if i % 2 == 0 else "transparent",
            }),
        ])
        for i, d in enumerate(defs)
    ]


def build_editor_table(defs, id_prefix="ratings-edit"):
    """Build the full editor table (with header) for a ratings editor modal.

    `id_prefix` namespaces the textarea pattern-matching ids so the estimation
    and reflection editors don't collide (e.g. "ratings-edit" vs
    "reflection-ratings-edit")."""
    return html.Table([
        html.Thead(html.Tr([
            html.Th("#", style={**_header_cell_style, "width": "36px"}),
            html.Th("Value", style=_header_cell_style),
            html.Th("Interest", style=_header_cell_style),
            html.Th("Effort", style=_header_cell_style),
        ])),
        html.Tbody(build_editor_rows(defs, id_prefix)),
    ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"})


def build_editor_rows(defs, id_prefix="ratings-edit"):
    """Build the editor modal rows (textareas) from a list of definition dicts."""
    from dash import dcc
    rows = []
    for d in defs:
        i = d['rating'] - 1
        rows.append(html.Tr([
            html.Td(str(d['rating']), style={
                **_cell_style, "fontWeight": "700", "color": "#adb5bd",
                "width": "36px", "textAlign": "center",
            }),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-value", "index": i},
                value=d['value'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-interest", "index": i},
                value=d['interest'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
            html.Td(dcc.Textarea(
                id={"type": f"{id_prefix}-effort", "index": i},
                value=d['effort'],
                style={"width": "100%", "height": "72px", "resize": "vertical",
                       "backgroundColor": "#2b3035", "color": "#dee2e6",
                       "border": "1px solid #495057", "borderRadius": "4px",
                       "padding": "4px", "fontSize": "0.8rem"},
            ), style=_cell_style),
        ]))
    return rows


ratings_popup = html.Div([
    # Draggable header
    html.Div([
        html.Span("Ratings Reference", style={"fontWeight": "600", "fontSize": "0.9rem"}),
        html.Button(html.I(className="bi bi-pencil"), id="btn-ratings-edit", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "0.85rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0 6px", "marginLeft": "8px",
        }, title="Edit definitions"),
        html.Button("×", id="btn-ratings-close", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "1.2rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0", "marginLeft": "auto",
        }),
    ], id="ratings-popup-header", className="d-flex align-items-center", style={
        "cursor": "move",
        "padding": "8px 10px",
        "backgroundColor": "#2b3035",
        "borderBottom": "1px solid #495057",
        "borderRadius": "6px 6px 0 0",
        "flexShrink": "0",
        "userSelect": "none",
    }),
    # Scrollable body
    html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("#", style={**_header_cell_style, "width": "36px"}),
                html.Th("Value", style=_header_cell_style),
                html.Th("Interest", style=_header_cell_style),
                html.Th("Effort", style=_header_cell_style),
            ])),
            html.Tbody(
                id="ratings-popup-table-body",
                children=build_popup_table_rows(ConfigManager.get_ratings_definitions()),
            ),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"}),
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
    "backgroundColor": "#212529",
    "border": "1px solid #495057",
    "borderRadius": "6px",
    "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
    "resize": "both",
    "overflow": "hidden",
})


ratings_editor_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Edit Ratings Definitions")),
    dbc.ModalBody(
        html.Div(id="ratings-editor-body"),
        style={"maxHeight": "70vh", "overflowY": "auto"},
    ),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-ratings-editor-cancel", color="secondary", className="me-auto"),
        dbc.Button("Save", id="btn-ratings-editor-save", color="primary"),
    ]),
], id="modal-ratings-editor", size="xl", is_open=False, scrollable=True)


# Retrospective sibling of `ratings_popup`, opened only from the Reflection
# modal's info icon. It reads its own REFLECTION_RATINGS_DEFINITIONS so the
# wording can stay decoupled from the estimation rubric. The JS in
# assets/ratings_popup.js wires btn-reflection-ratings-info to this popup.
reflection_ratings_popup = html.Div([
    html.Div([
        html.Span("Reflection Ratings Reference", style={"fontWeight": "600", "fontSize": "0.9rem"}),
        html.Button(html.I(className="bi bi-pencil"), id="btn-reflection-ratings-edit", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "0.85rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0 6px", "marginLeft": "8px",
        }, title="Edit definitions"),
        html.Button("×", id="btn-reflection-ratings-close", style={
            "background": "none", "border": "none", "color": "#adb5bd",
            "fontSize": "1.2rem", "lineHeight": "1", "cursor": "pointer",
            "padding": "0", "marginLeft": "auto",
        }),
    ], id="reflection-ratings-popup-header", className="d-flex align-items-center", style={
        "cursor": "move",
        "padding": "8px 10px",
        "backgroundColor": "#2b3035",
        "borderBottom": "1px solid #495057",
        "borderRadius": "6px 6px 0 0",
        "flexShrink": "0",
        "userSelect": "none",
    }),
    html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("#", style={**_header_cell_style, "width": "36px"}),
                html.Th("Value", style=_header_cell_style),
                html.Th("Interest", style=_header_cell_style),
                html.Th("Effort", style=_header_cell_style),
            ])),
            html.Tbody(
                id="reflection-ratings-popup-table-body",
                children=build_popup_table_rows(ConfigManager.get_reflection_ratings_definitions()),
            ),
        ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "0.8rem", "color": "#dee2e6"}),
    ], style={"overflow": "auto", "flex": "1", "padding": "4px"}),
], id="reflection-ratings-popup", style={
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
    "backgroundColor": "#212529",
    "border": "1px solid #495057",
    "borderRadius": "6px",
    "boxShadow": "0 4px 16px rgba(0,0,0,0.5)",
    "resize": "both",
    "overflow": "hidden",
})


reflection_ratings_editor_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Edit Reflection Ratings Definitions")),
    dbc.ModalBody(
        html.Div(id="reflection-ratings-editor-body"),
        style={"maxHeight": "70vh", "overflowY": "auto"},
    ),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-reflection-ratings-editor-cancel", color="secondary", className="me-auto"),
        dbc.Button("Save", id="btn-reflection-ratings-editor-save", color="primary"),
    ]),
], id="modal-reflection-ratings-editor", size="xl", is_open=False, scrollable=True)


def build_app_layout(initial_elements, env="production"):
    """Assembles the full application layout with pure Flexbox (Push behavior)."""
    
    edit_trigger = html.Button(id="btn-edit-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    toggle_trigger = html.Button(id="btn-toggle-done-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})

    context_menu = html.Div(
        id="node-context-menu",
        children=[
            html.Div("Edit", id="ctx-menu-edit", className="ctx-menu-item"),
            html.Div("Explain", id="ctx-menu-explain", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Details", id="ctx-menu-details", className="ctx-menu-item"),
            html.Div("Event", id="ctx-menu-add-to-event", className="ctx-menu-item"),
            html.Hr(id="ctx-menu-links-divider", style={"margin": "2px"}),
            html.Div("Obsidian", id="ctx-menu-obsidian", className="ctx-menu-item"),
            html.Div("Drive", id="ctx-menu-drive", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Now", id="ctx-menu-toggle-now", className="ctx-menu-item"),
            html.Div(STATUS_DONE, id="ctx-menu-toggle-done", className="ctx-menu-item"),
            html.Div("Delete", id="ctx-menu-delete", className="ctx-menu-item ctx-menu-item-danger"),
        ],
        style={
            "display": "none",
            "position": "fixed",
            "zIndex": 10000,
            "backgroundColor": "#2b3035",
            "border": "1px solid #495057",
            "borderRadius": "6px",
            "padding": "4px 0",
            "minWidth": "160px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.4)",
        }
    )

    # --- Goal sidebar: rank popover (click rank badge / hover star) ---
    _floating_menu_style = {
        "display": "none",
        "position": "fixed",
        "zIndex": 10001,
        "backgroundColor": "#2b3035",
        "border": "1px solid #495057",
        "borderRadius": "6px",
        "padding": "4px 0",
        "minWidth": "140px",
        "boxShadow": "0 4px 16px rgba(0,0,0,0.4)",
    }

    goal_rank_popover = html.Div(
        id="goal-rank-popover",
        children=[
            html.Div("Priority 1", id="goal-rank-set-1", className="ctx-menu-item"),
            html.Div("Priority 2", id="goal-rank-set-2", className="ctx-menu-item"),
            html.Div("Priority 3", id="goal-rank-set-3", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Clear", id="goal-rank-clear", className="ctx-menu-item"),
        ],
        style=_floating_menu_style,
    )

    # --- Events sidebar: right-click context menu ---
    event_context_menu = html.Div(
        id="event-context-menu",
        children=[
            html.Div("Edit", id="event-ctx-edit", className="ctx-menu-item"),
            html.Div("Trigger", id="event-ctx-trigger", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Delete", id="event-ctx-delete", className="ctx-menu-item"),
        ],
        style=_floating_menu_style,
    )

    # --- Goal sidebar: right-click context menu ---
    # Section layout mirrors the canvas context menu so right-click feels
    # consistent app-wide: edit/explain → navigation → priority → state/delete.
    # The Priority section is a single parent row with a hover-out submenu;
    # CSS handles the flyout and goal_context_menu.js handles off-screen flip.
    goal_context_menu = html.Div(
        id="goal-context-menu",
        children=[
            html.Div("Edit", id="goal-ctx-edit", className="ctx-menu-item"),
            html.Div("Explain", id="goal-ctx-explain", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Details", id="goal-ctx-details", className="ctx-menu-item"),
            html.Div("Event", id="goal-ctx-event", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div(
                id="goal-ctx-priority-parent",
                className="ctx-menu-item ctx-menu-submenu-parent",
                children=[
                    html.Span("Set Priority"),
                    html.Span("▸", className="ctx-menu-caret"),
                    html.Div(
                        id="goal-ctx-priority-submenu",
                        className="ctx-menu-submenu",
                        children=[
                            html.Div("Set Priority 1", id="goal-ctx-set-1", className="ctx-menu-item"),
                            html.Div("Set Priority 2", id="goal-ctx-set-2", className="ctx-menu-item"),
                            html.Div("Set Priority 3", id="goal-ctx-set-3", className="ctx-menu-item"),
                            html.Div("Clear Priority", id="goal-ctx-clear", className="ctx-menu-item"),
                        ],
                    ),
                ],
            ),
            html.Hr(style={"margin": "2px"}),
            html.Div("Now", id="goal-ctx-toggle-now", className="ctx-menu-item"),
            html.Div(STATUS_DONE, id="goal-ctx-toggle-done", className="ctx-menu-item"),
            html.Div("Delete", id="goal-ctx-delete", className="ctx-menu-item ctx-menu-item-danger"),
        ],
        style={**_floating_menu_style, "minWidth": "180px"},
    )

    # --- Tab Navigation (toolbar: left buttons | centered tabs | right buttons) ---
    main_tabs = html.Div([
        # LEFT: Node Editor + Goals + Events (open left-side sidebars)
        html.Div([
            dbc.Button(html.I(className="bi bi-node-plus"), id="btn-add", color="secondary", size="sm", className="me-2"),
            dbc.Tooltip("Node editor", target="btn-add", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-star"), id="btn-goals-toggle", color="secondary", size="sm", className="me-2"),
            dbc.Tooltip("Goals", target="btn-goals-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-calendar-event"), id="btn-events-sidebar-toggle", color="secondary", size="sm"),
            dbc.Tooltip("Events", target="btn-events-sidebar-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center ps-3",
           style={"flex": "0 0 auto"}),

        # CENTER: Tabs
        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-next",
            children=[
                dbc.Tab(label="Next", tab_id="tab-next"),
                dbc.Tab(label="Nodes", tab_id="tab-canvas"),
                dbc.Tab(label="Details", tab_id="tab-details"),
                dbc.Tab(label="Events", tab_id="tab-events"),
                dbc.Tab(label="Analyze", tab_id="tab-analyze"),
            ],
            className="px-3 pt-1 justify-content-center",
            style={"flex": "1", "backgroundColor": "#1a1d21", "borderBottom": "none"}
        ),

        # RIGHT: Clear Focus + Filters (open right-side sidebar)
        html.Div([
            dbc.Button("Clear Focus", id="btn-clear-focus", color="warning", size="sm",
                       className="me-2", style={"display": "none"}),
            dbc.Button(html.I(className="bi bi-funnel"), id="btn-filters-toggle", color="secondary", size="sm"),
            dbc.Tooltip("Filters", target="btn-filters-toggle", placement="bottom",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-journal-text"), id="btn-calibration-review",
                       color="secondary", size="sm", className="ms-2",
                       style={"display": "none"}),
            dbc.Tooltip("Reflection", target="btn-calibration-review", placement="bottom",
                        trigger="hover",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
            dbc.Button(html.I(className="bi bi-gear"), id="btn-settings-toggle", color="secondary", size="sm", className="ms-2"),
            dbc.Tooltip("Settings", target="btn-settings-toggle", placement="bottom",
                        trigger="hover",
                        delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}),
        ], className="d-flex align-items-center pe-3",
           style={"flex": "0 0 auto"}),
    ], id="main-toolbar", className="d-flex align-items-center",
       style={"borderBottom": "1px solid #495057", "backgroundColor": "#1a1d21"})

    # --- Canvas Tab Content (existing layout, unchanged) ---
    canvas_tab_content = html.Div(
        id="canvas-tab-content",
        children=[
            # --- MAIN CENTER CONTENT ---
            html.Div(
                style={
                    "flex": "1",
                    "display": "flex",
                    "flexDirection": "column",
                    "minWidth": "0",
                },
                children=[
                    # Canvas Container
                    html.Div(
                        [create_graph_view(initial_elements)],
                        className="flex-grow-1",
                        style={
                            "minHeight": "200px",
                            "position": "relative",
                            "overflow": "hidden"
                        }
                    ),

                    # Hidden outputs for bottom-panel callbacks (IDs must remain in DOM)
                    html.Div([
                        html.Div(id="traversal-chains-hard"),
                        html.Div(id="traversal-chains-soft"),
                        html.Div(id="synergies-list"),
                        html.Div(id="node-info-description"),
                    ], style={"display": "none"})
                ]
            ),

        ],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Events Tab Content (hidden by default) ---
    events_tab_content = html.Div(
        id="events-tab-content",
        children=[build_events_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Next Tab Content (hidden by default) ---
    next_tab_content = html.Div(
        id="next-tab-content",
        children=[
            html.Div([
                html.Div([next_view], className="px-4 pt-3 pb-4"),
            ], style={"flex": "1", "overflowY": "auto"}),
            html.Div(id="next-filter-indicator", className="canvas-stats-overlay"),
            html.Div(id="next-perf-stats", className="next-perf-overlay"),
        ],
        style={"display": "block", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0", "flexDirection": "column",
               "visibility": "visible"}
    )

    # --- Details Tab Content (hidden by default) ---
    details_tab_content = html.Div(
        id="details-tab-content",
        children=[build_details_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Analyze Tab Content (hidden by default) ---
    analyze_tab_content = html.Div(
        id="analyze-tab-content",
        children=[build_analyze_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0"}
    )

    return html.Div([
        hover_tooltip,
        ratings_popup,
        reflection_ratings_popup,
        edit_trigger,
        toggle_trigger,
        context_menu,
        goal_rank_popover,
        goal_context_menu,
        event_context_menu,
        dcc.Input(id='event-ctx-action-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='ctx-obsidian-path-store', data=None),
        dcc.Store(id='ctx-drive-path-store', data=None),
        dcc.Input(id='group-delete-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='group-delete-request-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='group-delete-pending-store', data=None),
        dcc.Input(id='edit-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='toggle-done-trigger-input', type='text', value='', style={'display': 'none'}),
        # Written by dispatch_now_toggle after a direct DB flip of the
        # `now` flag — feeds core_engine so the canvas re-renders to show
        # the new amber border.
        dcc.Input(id='node-now-trigger-input', type='text', value='', style={'display': 'none'}),
        # Written by context-menu "Now" items (canvas + goal sidebar)
        # carrying a JSON list of node names + timestamp. A dedicated callback
        # flips Now for each named node and re-bumps node-now-trigger-
        # input to refresh the canvas.
        dcc.Input(id='toggle-now-trigger-input', type='text', value='', style={'display': 'none'}),
        # Bumped by both the editor dispatcher and the context-menu handler
        # whenever setting Now is refused for hitting the Now cap.
        # show_now_cap_toast listens and pops a transient warning toast.
        dcc.Input(id='now-cap-refused-trigger', type='text', value='', style={'display': 'none'}),
        # Transient "Now cap reached" toast — auto-dismisses after 5s.
        # Fixed top-right, anchored just below the tab bar (the row holding
        # the Filters / Calibration / Settings icons sits at ~48px tall, so
        # top:60px clears it with a touch of breathing room). zIndex above
        # context menus (10000–10002).
        dbc.Toast(
            f"{ConfigManager.get_now_node_cap()} Now nodes is the cap. Clear one to make room.",
            id="now-cap-toast",
            header="Now Cap Reached",
            is_open=False,
            duration=5000,
            dismissable=True,
            icon="warning",
            style={
                "position": "fixed",
                "top": "60px",
                "right": "20px",
                "minWidth": "320px",
                "zIndex": 10010,
            },
        ),
        dcc.Input(id='background-click-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='pending-navigation-store', data=None),
        dcc.Input(id='details-navigate-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='details-explain-trigger-input', type='text', value='', style={'display': 'none'}),
        # Set by context_menu.js when "Add to event…" is clicked. Carries a
        # JSON-encoded list of selected node IDs plus a "|<timestamp>" suffix.
        dcc.Input(id='dormant-existing-trigger-input', type='text', value='', style={'display': 'none'}),
        # Holds the node name whose dormant state is being toggled while the
        # confirm/Add-to-Event modal is open, so the post-modal sync can revert
        # the switch on cancel and the confirm callback knows what to detach.
        dcc.Store(id='pending-dormant-toggle-store', data=None),
        html.Div(id='canvas-height-config', style={'display': 'none'}, **{'data-height': str(CANVAS_HEIGHT)}),  # type: ignore[reportArgumentType]
        html.Div(id='tooltip-config', style={'display': 'none'}, **{  # type: ignore[reportArgumentType]
            'data-show': str(TOOLTIP_SHOW_DELAY_MS),
            'data-hide': str(TOOLTIP_HIDE_DELAY_MS),
            'data-node-hide': str(TOOLTIP_NODE_HIDE_DELAY_MS),
        }),
        migration_modal,
        error_modal,
        unsaved_changes_modal,
        delete_confirm_modal,
        undo_done_confirm_modal,
        dormant_deactivate_confirm_modal,
        auto_done_suggestion_modal,
        time_calibration_modal,
        calibration_review_toast,
        build_review_hub_modal(),
        group_delete_confirm_modal,
        override_conflict_modal,
        override_untoggle_modal,
        ratings_editor_modal,
        reflection_ratings_editor_modal,
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Events Triggered Since Last Launch")),
            dbc.ModalBody(id="event-announcements-body"),
            dbc.ModalFooter(dbc.Button("Dismiss", id="btn-event-announcements-dismiss",
                                       color="primary")),
        ], id="modal-event-announcements", is_open=False, centered=True, size="lg"),
        build_settings_modal(),
        dcc.Interval(id='app-load-interval', interval=500, n_intervals=0, max_intervals=1),

        dcc.Store(id='override-store', data={"parent": None, "mode": "hard"}),
        dcc.Store(id='pending-event-override-store', data=None),
        dcc.Store(id='pending-settings-store', data=None),
        dcc.Store(id='migration-mapping-store', data=None),
        dcc.Store(id='freeze-rerender-store', data=False),
        # Intermediate hop for cytoscape elements — core_engine writes here,
        # a clientside callback either applies the delta directly to the cy
        # instance (during freeze) or forwards it to cytoscape-graph.elements
        # (normal operation). See assets/freeze_positions.js. Details and
        # Events tabs each have their own pending store + freeze store.
        dcc.Store(id='elements-pending-store', data=None),
        dcc.Store(id='details-elements-pending-store', data=None),
        dcc.Store(id='events-elements-pending-store', data=None),
        dcc.Store(id='details-freeze-rerender-store', data=False),
        dcc.Store(id='events-freeze-rerender-store', data=False),
        # Bumped by the bridge callback only when GraphManager._graph_version
        # advances (i.e. a real node/edge mutation, not a cosmetic filter change).
        # Downstream listeners use this instead of cytoscape-graph.elements to
        # avoid re-firing on cosmetic updates (filter, depth, highlight).
        dcc.Store(id='graph-version-store', data=0),
        # Holds the names the user is about to un-Done while the confirmation
        # modal is open. Read by the modal-confirm callback to perform the
        # actual toggle once the user has acknowledged the downstream impact.
        dcc.Store(id='pending-undo-done-store', data=None),
        # Holds the name of the node awaiting time-calibration input while the
        # modal is open. Read by handle_time_calibration on Submit.
        dcc.Store(id='time-calibration-pending-store', data=None),
        # Queue of Goal/Milestone names whose hard prereqs just became all
        # Done. Drained from GraphManager._auto_done_candidates whenever the
        # graph version bumps, then surfaced one at a time by the auto-Done
        # suggestion modal. Persists across modal interactions so chained
        # candidates (parent container becoming ready after the child Goal
        # is marked Done) are queued naturally.
        dcc.Store(id='auto-done-candidates-store', data=[]),
        # Sink for the filter-persistence callback. Filters get written to
        # ConfigManager whenever any sidebar control changes; this Store
        # exists only to give that callback a valid Output target.
        dcc.Store(id='filter-persist-sink', data=None),
        dcc.Interval(id='settings-clear-interval', interval=TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),

        main_tabs,
        # Tab content wrapper — only one tab visible at a time
        html.Div([
            next_tab_content,
            canvas_tab_content,
            details_tab_content,
            events_tab_content,
            analyze_tab_content,
            # --- Cross-tab sidebar overlays (editor / goals / events / filters) ---
            *build_all_sidebars()
        ], style={"flex": "1", "overflow": "hidden", "position": "relative"}),
    ], style={"width": "100vw", "height": "100vh", "overflow": "hidden",
              "display": "flex", "flexDirection": "column"})
