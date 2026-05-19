"""
Callback definitions for the Details tab.
"""

import os
from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from graph_manager import GraphManager
from event_manager import EventManager
from config import ConfigManager, badge_style, sort_subcontexts, sort_contexts
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from details_layout import (build_details_subtasks_table,
                             _build_suggestion_row, build_details_suggestions,
                             build_milestone_tile)
from simulation import simulate_task_chain
from callback_helpers import (render_link_rows, strip_gdrive_prefix,
                              spawn_local_file_picker, build_filters,
                              is_filters_active,
                              build_explain_summary, build_explain_chart,
                              habit_to_hours, compute_habit_time_omp,
                              resolve_time_mode, get_trigger_id)
from scoring import explain_score, shortest_paths_focus_data

graph_manager = GraphManager()
event_manager = EventManager()


def _apply_max_depth(subtree, selected_node, max_depth, edge_types):
    """Filter a subtree set to only include nodes within max_depth hops."""
    if not max_depth or max_depth <= 0:
        return subtree
    edges = graph_manager.get_edges()
    full_set = subtree | {selected_node}
    adj = {}
    for e in edges:
        s, t = e['source'], e['target']
        if s in full_set and t in full_set and e['type'] in edge_types:
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)
    visited = {selected_node}
    frontier = {selected_node}
    for _ in range(max_depth):
        next_frontier = set()
        for n in frontier:
            for nb in adj.get(n, set()):
                if nb not in visited:
                    visited.add(nb)
                    next_frontier.add(nb)
        frontier = next_frontier
        if not frontier:
            break
    return subtree & visited


def _build_milestones_section(subtask_nodes, parent_name, edges, include_transitive):
    """Compute the (section_style, bottom_toggles_style, tiles) tuple for
    the milestones strip and the canonical bottom toggle wrapper.

    Mirrors the Subtasks table exactly: takes the same filtered subtree,
    applies the same direct-children narrowing when Transitive is OFF
    (matching the post-filter logic at the top of
    ``build_details_subtasks_table``), then picks out Milestones and renders
    them as tiles.

    The bottom toggle wrapper visibility is the *inverse* of the milestones
    section visibility: when milestones are shown, the toggles live up next
    to the Milestones header (their -top counterparts), so the canonical
    bottom set is hidden to avoid duplication. Otherwise the canonical set
    sits with the Subtasks header as before.

    Returns (section: display:none, bottom_toggles: visible, tiles: []) when
    no Milestone survives filtering.
    """
    # Direct-children narrowing (same shape as build_details_subtasks_table).
    if not include_transitive and parent_name:
        direct_children = set()
        for e in edges or []:
            if e['target'] == parent_name:
                direct_children.add(e['source'])
            elif e['source'] == parent_name:
                direct_children.add(e['target'])
        subtask_nodes = [n for n in subtask_nodes if n.name in direct_children]

    milestones = [n for n in subtask_nodes if n.type == "Milestone"]
    # Sort Open first, Blocked next, Done last — within each group alphabetical.
    # Mirrors the existing subtasks-table convention (Done at the bottom) but
    # additionally promotes Open above Blocked since Open milestones are the
    # ones the user can act on right now.
    _STATUS_ORDER = {STATUS_OPEN: 0, STATUS_BLOCKED: 1, STATUS_DONE: 2}
    milestones.sort(key=lambda n: (_STATUS_ORDER.get(n.status, 99), n.name))
    if not milestones:
        # Milestones hidden → canonical bottom toggles visible (default).
        return {"display": "none"}, {}, []
    tiles = [
        build_milestone_tile(
            ms,
            graph_manager.get_goal_completion(ms.name, include_soft=False),
        )
        for ms in milestones
    ]
    # Milestones shown → bottom toggles hidden (top toggles take over).
    return {"display": "block"}, {"display": "none"}, tiles


def _run_simulation(node_name, include_soft_val, include_synergies_val,
                    include_transitive_val=None, global_filters=None, max_depth=0):
    """Shared helper: run the Monte Carlo simulation and return (figure, style, style)."""
    all_nodes = graph_manager.get_all_nodes()
    if global_filters:
        # Filter nodes but always keep the target node itself
        filtered = graph_manager.filter_nodes(all_nodes, global_filters)
        filtered_names = {n.name for n in filtered} | {node_name}
        all_nodes = [n for n in all_nodes if n.name in filtered_names]
    nodes_dict = {n.name: n for n in all_nodes}
    edges = graph_manager.get_edges()

    if node_name not in nodes_dict:
        return no_update, no_update, no_update

    include_soft = bool(include_soft_val and "include" in include_soft_val)
    include_helps = bool(include_synergies_val and "include" in include_synergies_val)
    include_transitive = bool(include_transitive_val and "include" in include_transitive_val)

    # When Transitive is off, restrict simulation to direct children only by
    # filtering edges to those that directly reference the selected node.
    sim_edges = edges
    if not include_transitive:
        direct_sources = set()
        for e in edges:
            if e['target'] == node_name and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                direct_sources.add(e['source'])
            if e['type'] == EDGE_HELPS:
                if e['target'] == node_name:
                    direct_sources.add(e['source'])
                elif e['source'] == node_name:
                    direct_sources.add(e['target'])
        allowed = direct_sources | {node_name}
        sim_edges = [e for e in edges if e['source'] in allowed and e['target'] in allowed]

    # Apply max depth filter to simulation
    if max_depth and max_depth > 0:
        sim_edge_types = [EDGE_NEEDS_HARD]
        if include_soft:
            sim_edge_types.append(EDGE_NEEDS_SOFT)
        if include_helps:
            sim_edge_types.append(EDGE_HELPS)
        full_subtree = {n for n in nodes_dict if n != node_name}
        depth_limited = _apply_max_depth(full_subtree, node_name, max_depth, sim_edge_types)
        allowed_depth = depth_limited | {node_name}
        sim_edges = [e for e in sim_edges if e['source'] in allowed_depth and e['target'] in allowed_depth]
        nodes_dict = {k: v for k, v in nodes_dict.items() if k in allowed_depth}

    result = simulate_task_chain(
        target_name=node_name,
        nodes_dict=nodes_dict,
        edges=sim_edges,
        include_soft=include_soft,
        include_helps=include_helps,
        n_simulations=10000,
    )

    samples = result['samples']
    stats = result['stats']

    # Pre-bin server-side: shipping 50 bars is ~50x smaller than shipping
    # 10,000 raw samples for Plotly to bin in the browser.
    counts, edges = np.histogram(samples, bins=50)
    centers = (edges[:-1] + edges[1:]) / 2
    width = edges[1] - edges[0]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=centers, y=counts, width=width,
        marker_color='#0d6efd', opacity=0.85,
        hoverinfo='skip',
    ))

    for label, val, color in [
        ('P10', stats['p10'], '#198754'),
        ('P50', stats['p50'], '#ffc107'),
        ('P90', stats['p90'], '#dc3545'),
    ]:
        fig.add_vline(
            x=val, line_dash="dash", line_color=color, line_width=2,
            annotation_text=f"{label}: {ConfigManager.format_time_friendly(val)}",
            annotation_position="top",
            annotation_font_color=color,
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#1a1d21',
        plot_bgcolor='#1a1d21',
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title="Hours",
        yaxis_title="Frequency",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
        showlegend=False,
        hovermode=False,
        bargap=0,
    )

    return (
        fig,
        {"display": "flex", "flexDirection": "column", "flex": "1", "minHeight": "0"},
        {"display": "none"},
    )


def register_details_callbacks(app):

    # --- Populate node dropdown when tab becomes active ---
    @app.callback(
        Output("details-node-select", "options"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
    )
    def populate_details_dropdown(active_tab, _refresh, _version):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name}
                for n in sorted(nodes, key=lambda n: n.name)]

    # --- Navigation History: push new entries, handle back/forward ---
    @app.callback(
        Output("details-nav-history", "data"),
        Output("details-nav-index", "data"),
        Output("btn-details-nav-back", "disabled"),
        Output("btn-details-nav-forward", "disabled"),
        Input("details-selected-node-store", "data"),
        Input("btn-details-nav-back", "n_clicks"),
        Input("btn-details-nav-forward", "n_clicks"),
        State("details-nav-history", "data"),
        State("details-nav-index", "data"),
        prevent_initial_call=True,
    )
    def manage_nav_history(selected_node, back_clicks, fwd_clicks,
                           history, nav_index):
        trigger = ctx.triggered_id
        history = list(history or [])
        nav_index = int(nav_index) if nav_index is not None else -1

        if trigger == "btn-details-nav-back":
            if nav_index > 0:
                nav_index -= 1
        elif trigger == "btn-details-nav-forward":
            if nav_index < len(history) - 1:
                nav_index += 1
        elif trigger == "details-selected-node-store":
            if selected_node:
                # Only push if it's a new node (not a back/forward replay)
                if nav_index < 0 or (nav_index < len(history) and
                                     history[nav_index] != selected_node):
                    # Truncate forward history and push
                    history = history[:nav_index + 1]
                    history.append(selected_node)
                    nav_index = len(history) - 1
                elif not history:
                    history.append(selected_node)
                    nav_index = 0

        back_disabled = nav_index <= 0
        fwd_disabled = nav_index >= len(history) - 1

        return history, nav_index, back_disabled, fwd_disabled

    # --- Back/Forward button clicks → update dropdown selection ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("btn-details-nav-back", "n_clicks"),
        Input("btn-details-nav-forward", "n_clicks"),
        State("details-nav-history", "data"),
        State("details-nav-index", "data"),
        prevent_initial_call=True,
    )
    def nav_button_select(back_clicks, fwd_clicks, history, nav_index):
        trigger = ctx.triggered_id
        history = list(history or [])
        nav_index = int(nav_index) if nav_index is not None else -1

        if trigger == "btn-details-nav-back":
            target_idx = nav_index - 1
        elif trigger == "btn-details-nav-forward":
            target_idx = nav_index + 1
        else:
            return no_update

        if 0 <= target_idx < len(history):
            return history[target_idx]
        return no_update

    # --- Node Selection: populate detail view ---
    @app.callback(
        # Visibility
        Output("details-empty", "style"),
        Output("details-content", "style"),
        # Store
        Output("details-selected-node-store", "data"),
        # Node attributes
        Output("details-node-name", "children"),
        Output("details-node-badges", "children"),
        Output("details-node-description", "children"),
        Output("details-attr-type", "children"),
        Output("details-attr-status", "children"),
        Output("details-attr-context", "children"),
        Output("details-attr-time", "children"),
        Output("details-attr-value", "children"),
        Output("details-attr-interest", "children"),
        Output("details-attr-effort", "children"),
        # Progress
        Output("details-progress-section", "style"),
        Output("details-progress-bar", "value"),
        Output("details-progress-text", "children"),
        # Priority
        Output("details-priority-section", "style"),
        Output("details-priority-badge", "children"),
        # Subtasks
        Output("details-subtasks-table-container", "children"),
        # Milestones roster (above the subtasks table, filter-aware) +
        # canonical bottom toggle visibility (hidden when milestones show).
        Output("details-milestones-section", "style"),
        Output("details-subtask-toggles-bottom", "style"),
        Output("details-milestones-tiles", "children"),
        # Inputs
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("override-store", "data"),
        State("details-include-soft-needs", "value"),
        State("details-include-transitive", "value"),
        State("details-include-synergies", "value"),
        State("filter-context", "value"),
        State("filter-subcontext", "value"),
        State("filter-done", "value"),
        State("filter-value", "value"),
        State("filter-interest", "value"),
        State("filter-time", "value"),
        State("filter-difficulty", "value"),
        State("filter-node-type", "value"),
        State("filter-dormant", "value"),
        State("details-graph-settings-max-depth", "value"),
        State("details-hide-blocked", "value"),
        prevent_initial_call=True,
    )
    def select_detail_node(node_name, _refresh, _version, _override_data,
                           include_soft_val, include_transitive_val,
                           include_synergies_val,
                           f_context, f_subcontext, f_done,
                           f_value, f_interest, f_time, f_difficulty,
                           f_node_types, f_show_dormant, gs_max_depth, hide_blocked_val):
        if not node_name:
            return (
                {"display": "block"},
                {"display": "none"},
                None,
                "", [], "", "", "", "", "", "", "", "",
                {"display": "none"}, 0, "",
                {"display": "none"}, "",
                html.Div("Select a node to see subtasks.",
                         className="text-muted text-center py-3"),
                {"display": "none"}, {}, [],
            )

        node = graph_manager.get_node(node_name)
        if not node:
            return (no_update,) * 22

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_transitive = bool(include_transitive_val and "include" in include_transitive_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)

        # Build badges. Order: Override → Status → Priority → Type → RelPriority.
        # Goal type tile is suppressed when a Priority N tile is shown
        # (the Priority tile already implies "this is a Goal").
        badges = []
        priority_goals = ConfigManager.get_priority_goals()
        is_priority_goal = node_name in priority_goals

        # 1. Override (always first if active)
        override = ConfigManager.get_override()
        if override.get("parent"):
            override_set = ConfigManager.get_override_node_set(graph_manager)
            if node_name in override_set:
                is_parent = (node_name == override["parent"])
                override_label = "Override" if is_parent else "Override (Dependent)"
                badges.append(html.Span(override_label, className="badge",
                                        style=badge_style('Override')))

        # 2. Status (always)
        badges.append(html.Span(node.status, className="badge",
                                style=badge_style(node.status)))

        # 3. Priority (Priority N for priority Goals)
        if is_priority_goal:
            rank = priority_goals.index(node_name) + 1
            badges.append(html.Span(f"Priority {rank}", className="badge",
                                    style=badge_style('Priority')))

        # 4. Type (skip Goal when Priority N already rendered above)
        if node.type and not is_priority_goal:
            badges.append(html.Span(node.type, className="badge",
                                    style=badge_style(node.type)))

        # 5. Relationship Priority (Hard/Soft N for non-priority nodes in a priority Goal's subtree)
        if not is_priority_goal:
            for rank_idx, goal_name in enumerate(priority_goals[:3]):
                subtree = graph_manager.get_goal_subtree(goal_name)
                if node_name in subtree:
                    hard_subtree = graph_manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                    rel_type = "Hard" if node_name in hard_subtree else "Soft"
                    palette_name = "HardRelPri" if rel_type == "Hard" else "SoftRelPri"
                    badges.append(html.Span(f"{rel_type} {rank_idx+1}",
                                            className="badge",
                                            style=badge_style(palette_name)))
                    break

        ctx_str = node.context or "—"
        if node.subcontext:
            ctx_str += f" › {node.subcontext}"

        effective_time = graph_manager.get_effective_time(node_name)
        time_str = ConfigManager.format_time_friendly(effective_time) if effective_time else "—"

        show_progress = {"display": "none"}
        progress_val = 0
        progress_text = ""
        if node.type == "Goal":
            completion = graph_manager.get_goal_completion(
                node_name, include_soft=False,
                include_transitive=True)
            if completion["total"] > 0:
                show_progress = {"display": "block", "marginBottom": "8px"}
                progress_val = completion["pct"]
                remaining = ConfigManager.format_time_friendly(
                    completion["remaining_time"])
                # Milestone count: walk the same hard-subtree the completion
                # walked, count Milestones in it. Filter-independent (matches
                # the existing "X/Y hard subtasks" stat which is also total).
                hard_subtree = graph_manager.get_goal_subtree(
                    node_name, edge_types=(EDGE_NEEDS_HARD,))
                ms_total = 0
                ms_done = 0
                for child_name in hard_subtree:
                    child = graph_manager.get_node(child_name)
                    if child is not None and child.type == "Milestone":
                        ms_total += 1
                        if child.status == STATUS_DONE:
                            ms_done += 1
                ms_label = "milestone" if ms_total == 1 else "milestones"
                parts = []
                if ms_total > 0:
                    parts.append(f"{ms_done}/{ms_total} {ms_label}")
                parts.append(f"{completion['done']}/{completion['total']} hard subtasks")
                parts.append(f"{remaining} remaining")
                #   (nbsp) sits next to the regular space so it doesn't
                # collapse — gives a visibly wider gap on each side of the
                # middle dot than a plain " · " would.
                progress_text = "  ·  ".join(parts)

        show_priority = {"display": "none"}
        priority_badge = ""

        # Subtasks
        edge_types = [EDGE_NEEDS_HARD]
        if include_soft:
            edge_types.append(EDGE_NEEDS_SOFT)
        if include_synergies:
            edge_types.append(EDGE_HELPS)

        subtree = graph_manager.get_goal_subtree(node_name,
                                                  edge_types=tuple(edge_types))
        # Apply max depth filter
        depth_val = gs_max_depth or 0
        subtree = _apply_max_depth(subtree, node_name, depth_val, edge_types)

        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]

        # Apply global filters to subtask nodes
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes = graph_manager.filter_nodes(subtask_nodes, global_filters)

        subtask_nodes.sort(key=lambda n: (n.status == STATUS_DONE, n.name))
        edges = graph_manager.get_edges()

        # Milestones get their own dedicated strip above the table, so the
        # table itself excludes them — avoids redundant rendering.
        non_milestone_subtasks = [n for n in subtask_nodes if n.type != "Milestone"]
        subtasks_table = build_details_subtasks_table(
            non_milestone_subtasks, graph_manager=graph_manager, edges=edges,
            parent_name=node_name, include_soft=include_soft,
            include_transitive=include_transitive,
            include_synergies=include_synergies)

        # Milestones roster — derived from the same filtered subtask_nodes the
        # Subtasks table uses, with the same Transitive narrowing, so the strip
        # stays in lockstep with the table.
        ms_section_style, bottom_toggles_style, ms_tiles = _build_milestones_section(
            subtask_nodes, node_name, edges, include_transitive)

        return (
            {"display": "none"},
            {"display": "flex", "flexDirection": "column", "flex": "1",
             "padding": "0 24px", "overflowY": "auto"},
            node_name,
            node.name,
            badges,
            node.description or "No description.",
            node.type or "—",
            node.status or "—",
            ctx_str,
            time_str,
            str(node.value),
            str(node.interest),
            str(node.difficulty),
            show_progress, progress_val, progress_text,
            show_priority, priority_badge,
            subtasks_table,
            ms_section_style, bottom_toggles_style, ms_tiles,
        )

    # --- Toggle subtask filters ---
    @app.callback(
        Output("details-subtasks-table-container", "children", allow_duplicate=True),
        Output("details-milestones-section", "style", allow_duplicate=True),
        Output("details-subtask-toggles-bottom", "style", allow_duplicate=True),
        Output("details-milestones-tiles", "children", allow_duplicate=True),
        Input("details-include-soft-needs", "value"),
        Input("details-include-transitive", "value"),
        Input("details-include-synergies", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-done", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-node-type", "value"),
        Input("filter-dormant", "value"),
        Input("details-graph-settings-max-depth", "value"),
        Input("details-hide-blocked", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_details_subtask_filters(include_soft_val, include_transitive_val,
                                        include_synergies_val,
                                        f_context, f_subcontext, f_done,
                                        f_value, f_interest, f_time, f_difficulty,
                                        f_node_types, f_show_dormant, gs_max_depth,
                                        hide_blocked_val, selected_node):
        if not selected_node:
            return no_update, no_update, no_update, no_update

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_transitive = bool(include_transitive_val and "include" in include_transitive_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)

        edge_types = [EDGE_NEEDS_HARD]
        if include_soft:
            edge_types.append(EDGE_NEEDS_SOFT)
        if include_synergies:
            edge_types.append(EDGE_HELPS)

        subtree = graph_manager.get_goal_subtree(selected_node,
                                                  edge_types=tuple(edge_types))
        # Apply max depth filter
        subtree = _apply_max_depth(subtree, selected_node, gs_max_depth or 0, edge_types)

        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]

        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes = graph_manager.filter_nodes(subtask_nodes, global_filters)

        subtask_nodes.sort(key=lambda n: (n.status == STATUS_DONE, n.name))
        edges = graph_manager.get_edges()

        # Milestones get their own dedicated strip — exclude them from the table.
        non_milestone_subtasks = [n for n in subtask_nodes if n.type != "Milestone"]
        subtasks_table = build_details_subtasks_table(
            non_milestone_subtasks, graph_manager=graph_manager, edges=edges,
            parent_name=selected_node, include_soft=include_soft,
            include_transitive=include_transitive,
            include_synergies=include_synergies)

        # Milestones roster shares the same filtered subtree + Transitive
        # narrowing the table uses, so both surfaces stay in lockstep.
        ms_section_style, bottom_toggles_style, ms_tiles = _build_milestones_section(
            subtask_nodes, selected_node, edges, include_transitive)

        return subtasks_table, ms_section_style, bottom_toggles_style, ms_tiles

    # --- Sync "Hide Done" toggle with sidebar filter ---
    @app.callback(
        Output("details-hide-done", "value"),
        Output("filter-done", "value", allow_duplicate=True),
        Input("details-hide-done", "value"),
        Input("filter-done", "value"),
        prevent_initial_call=True,
    )
    def sync_hide_done(details_val, filter_val):
        if (details_val or []) == (filter_val or []):
            return no_update, no_update
        if ctx.triggered_id == "details-hide-done":
            return no_update, details_val
        return filter_val, no_update

    # --- Sync Milestones-row toggles with the canonical Subtasks-row toggles ---
    # The five filter switches render twice (top: with the Milestones header;
    # bottom: with the Subtasks header). Only one set is visible at a time;
    # the user's interaction with whichever set is showing must propagate to
    # the other so the canonical (no-suffix) IDs always reflect the current
    # value — every existing scoring/filter callback listens to those.
    #
    # Each pair gets its own two-way sync callback that no_updates when the
    # other side already matches, keeping the dispatch from looping.
    def _register_toggle_sync(canonical_id):
        top_id = f"{canonical_id}-top"

        @app.callback(
            Output(canonical_id, "value", allow_duplicate=True),
            Output(top_id, "value", allow_duplicate=True),
            Input(canonical_id, "value"),
            Input(top_id, "value"),
            prevent_initial_call=True,
        )
        def _sync(canonical_val, top_val):
            trig = get_trigger_id()
            canonical_val = canonical_val or []
            top_val = top_val or []
            if list(canonical_val) == list(top_val):
                return no_update, no_update
            if trig == canonical_id:
                return no_update, canonical_val
            return top_val, no_update
        # Give Dash a unique function name per registration so logs/errors
        # are easier to attribute to the right toggle pair.
        _sync.__name__ = f"sync_toggle_{canonical_id.replace('-', '_')}"
        return _sync

    for _toggle_id in ("details-include-soft-needs",
                       "details-include-transitive",
                       "details-include-synergies",
                       "details-hide-done",
                       "details-hide-blocked"):
        _register_toggle_sync(_toggle_id)

    # --- Dependency Graph ---
    # Outputs to details-elements-pending-store; a clientside callback in
    # callbacks.py applies freeze bypass (direct cy mutation during freeze)
    # or forwards to details-mini-graph.elements normally.
    @app.callback(
        Output("details-elements-pending-store", "data"),
        Input("details-selected-node-store", "data"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-transitive", "value"),
        Input("details-include-synergies", "value"),
        Input("filter-node-type", "value"),
        Input("filter-done", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-dormant", "value"),
        Input("details-graph-settings-max-depth", "value"),
        Input("details-graph-settings-neighbor-links", "value"),
        Input("details-hide-blocked", "value"),
    )
    def update_details_graph(selected_node, _refresh, _version,
                             include_soft_val, include_transitive_val,
                             include_synergies_val,
                             f_node_types, f_done, f_context, f_subcontext,
                             f_value, f_interest, f_time, f_difficulty,
                             f_show_dormant,
                             gs_max_depth, gs_neighbor_links, hide_blocked_val):
        if not selected_node:
            return []
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        return _build_graph_elements(selected_node, include_soft_val,
                                     include_synergies_val, global_filters,
                                     include_transitive_val=include_transitive_val,
                                     max_depth=gs_max_depth or 0,
                                     neighbor_links=gs_neighbor_links if gs_neighbor_links is not None else True)

    # --- Clicking a node in the dep graph → select it ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-mini-graph", "tapNodeData"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def dep_graph_node_click(tap_data, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not tap_data:
            return no_update
        return tap_data.get("id", no_update)

    # --- Run simulation on node selection or when any toggle changes ---
    # Triggered by details-selected-node-store so it runs in parallel with the
    # graph callback after select_detail_node writes the store — instead of
    # blocking inside select_detail_node's 19-output batch.
    @app.callback(
        Output("details-sim-chart", "figure", allow_duplicate=True),
        Output("details-sim-results", "style", allow_duplicate=True),
        Output("details-sim-empty", "style", allow_duplicate=True),
        Input("details-selected-node-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-transitive", "value"),
        Input("details-include-synergies", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-done", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-node-type", "value"),
        Input("filter-dormant", "value"),
        Input("details-graph-settings-max-depth", "value"),
        Input("details-hide-blocked", "value"),
        prevent_initial_call=True,
    )
    def run_details_simulation(node_name, include_soft_val, include_transitive_val,
                                include_synergies_val,
                                f_context, f_subcontext, f_done,
                                f_value, f_interest, f_time, f_difficulty,
                                f_node_types, f_show_dormant, gs_max_depth, hide_blocked_val):
        if not node_name:
            empty_fig = go.Figure()
            empty_fig.update_layout(template="plotly_dark",
                                    paper_bgcolor='#1a1d21',
                                    plot_bgcolor='#1a1d21')
            return empty_fig, {"display": "none"}, {"display": "block"}
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        return _run_simulation(node_name, include_soft_val, include_synergies_val,
                               include_transitive_val=include_transitive_val,
                               global_filters=global_filters,
                               max_depth=gs_max_depth or 0)

    # --- Run Simulation from context menu trigger ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-simulate-trigger-input", "value"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def context_menu_simulate_trigger(trigger_val, active_tab):
        if not trigger_val:
            return no_update
        # Parse "nodeName|timestamp"
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update
        # Select the node — which will auto-run simulation
        return node_name

    # --- Focus on Canvas ---
    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input("btn-details-focus", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-mini-graph", "elements"),
        prevent_initial_call=True,
    )
    def details_focus_canvas(n_clicks, selected_node, mini_graph_elements):
        if not n_clicks or not selected_node:
            return no_update, no_update
        # Extract node IDs from the mini-graph elements (exclude edges)
        subtree = [el["data"]["id"] for el in (mini_graph_elements or [])
                   if "source" not in el.get("data", {})]
        return {"node": selected_node, "subtree": subtree}, "tab-canvas"

    # --- Edit Node → Open editor overlay (no tab switch) ---
    @app.callback(
        Output("details-edit-trigger-input", "value", allow_duplicate=True),
        Input("btn-details-edit", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def details_edit_node(n_clicks, selected_node):
        if not n_clicks or not selected_node:
            return no_update
        import time
        return f"{selected_node}|{int(time.time())}"

    # --- Locate on Details mini-graph: pulse the selected node in place ---
    # Reuses window.locateNodeOnGraph (assets/locate_node.js), passing the
    # mini-graph's DOM id so the pulse runs on the Details tab's embedded
    # subgraph rather than the main canvas. No tab switch.
    app.clientside_callback(
        """function(n_clicks, selected) {
            if (!n_clicks || !selected) {
                return window.dash_clientside.no_update;
            }
            if (typeof window.locateNodeOnGraph === 'function') {
                window.locateNodeOnGraph(selected, 'details-mini-graph');
            }
            return '';
        }""",
        Output('details-locate-dummy', 'children'),
        Input('btn-details-locate', 'n_clicks'),
        State('details-selected-node-store', 'data'),
        prevent_initial_call=True,
    )

    # --- Context Menu "Details" → Navigate to Details tab with node selected ---
    @app.callback(
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-navigate-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def context_menu_details_navigate(trigger_val):
        if not trigger_val:
            return no_update, no_update
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update, no_update
        return "tab-details", node_name

    # --- Context Menu "Explain" → select node + open modal (stay on current tab) ---
    # The modal renders via React Portal (dbc.Modal uses createPortal), so it is
    # visible from any tab even though it lives inside details-tab-content.
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Output("modal-details-explain", "is_open", allow_duplicate=True),
        Input("details-explain-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def context_menu_explain_open(trigger_val):
        if not trigger_val:
            return no_update, no_update
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update, no_update
        return node_name, True

    # --- Subtask Name Click → Select that node in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-subtask-name", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def navigate_to_subtask(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Milestone Tile Click → Select that Milestone in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-milestone-tile", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def navigate_to_milestone_tile(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Empty-state suggestions: override + priority goals + top recs ---
    @app.callback(
        Output("details-suggestions-container", "children"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("override-store", "data"),
        Input("details-selected-node-store", "data"),
    )
    def build_empty_state_suggestions(_refresh, _version, _override_data, _selected):
        from next_callbacks import get_container_suggestions

        seen = set()

        override_row = None
        override_name = ConfigManager.get_override().get("parent")
        if override_name:
            override_node = graph_manager.get_node(override_name)
            if override_node and not override_node.dormant:
                override_row = _build_suggestion_row(override_name, "Override", "pink")
                seen.add(override_name)

        goal_rows = []
        for i, goal_name in enumerate(ConfigManager.get_priority_goals()[:3]):
            if goal_name in seen:
                continue
            goal_node = graph_manager.get_node(goal_name)
            if not goal_node or goal_node.dormant:
                continue
            goal_rows.append(_build_suggestion_row(
                goal_name, str(i + 1), "warning"))
            seen.add(goal_name)

        rec_nodes = get_container_suggestions(count=5, exclude_names=seen)
        for n in rec_nodes:
            seen.add(n.name)

        max_tv = max((getattr(n, "total_value", 0) for n in rec_nodes),
                     default=0)
        rec_rows = []
        tooltip_text = ("Normalized total value (0–100) from the priority "
                        "scoring algorithm — cascade-driven score for this "
                        "container.")
        for i, n in enumerate(rec_nodes):
            raw = getattr(n, "total_value", 0)
            normalized = round((raw / max_tv) * 100) if max_tv else 0
            rec_rows.append(_build_suggestion_row(
                n.name, str(normalized),
                badge_style(STATUS_OPEN)["backgroundColor"],
                badge_id=f"details-sugg-rec-badge-{i}",
                tooltip_text=tooltip_text,
            ))

        return build_details_suggestions(override_row, goal_rows, rec_rows)

    # --- Suggestion Click → Select that node in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-suggestion-item", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def select_suggested_node(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Add Node Modal: Open ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Output("details-add-type", "options"),
        Output("details-add-context", "options", allow_duplicate=True),
        Output("details-add-subcontext", "options", allow_duplicate=True),
        Output("details-add-existing-dropdown", "options"),
        Output("details-add-existing-dropdown", "value"),
        Output("details-add-name", "value"),
        Output("details-add-desc", "value"),
        Output("details-add-save-status", "children", allow_duplicate=True),
        Output("details-add-time-unit", "value"),
        Output("details-add-value", "value"),
        Output("details-add-interest", "value"),
        Output("details-add-difficulty", "value"),
        Output("details-add-time-o", "value"),
        Output("details-add-time-m", "value"),
        Output("details-add-time-p", "value"),
        Output("details-add-context", "value", allow_duplicate=True),
        Output("details-add-subcontext", "value", allow_duplicate=True),
        Output("details-add-mode", "value"),
        # Relationship dropdowns
        Output("details-add-needs-hard", "options"),
        Output("details-add-needs-soft", "options"),
        Output("details-add-supports-hard", "options"),
        Output("details-add-supports-soft", "options"),
        Output("details-add-helps", "options"),
        Output("details-add-needs-hard", "value"),
        Output("details-add-needs-soft", "value"),
        Output("details-add-supports-hard", "value"),
        Output("details-add-supports-soft", "value"),
        Output("details-add-helps", "value"),
        # Time mode + subcontext collapse reset
        Output("details-add-time-mode", "value"),
        Output("collapse-details-add-subcontext", "is_open"),
        # External resource stores reset
        Output("details-add-obsidian-store", "data"),
        Output("details-add-drive-store", "data"),
        Output("details-add-website-store", "data"),
        # Override reset
        Output("details-add-override-toggle", "value"),
        # Value mode reset
        Output("details-add-value-mode", "value"),
        # Habit-mode reset (7 new outputs)
        Output("details-add-time-habit-mode", "value"),
        Output("details-add-habit-duration", "value"),
        Output("details-add-habit-duration-unit", "value"),
        Output("details-add-habit-intensity-o", "value"),
        Output("details-add-habit-intensity-m", "value"),
        Output("details-add-habit-intensity-p", "value"),
        Output("details-add-habit-intensity-unit", "value"),
        Input("btn-details-add-node", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_node):
        if not n_clicks:
            return (no_update,) * 43

        types = ConfigManager.get_node_types()
        contexts = sort_contexts(ConfigManager.get_contexts())
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": c, "value": c} for c in contexts]

        all_nodes = graph_manager.get_all_nodes()
        subtree = graph_manager.get_goal_subtree(selected_node) if selected_node else set()
        exclude = subtree | {selected_node} if selected_node else set()
        node_opts = [{"label": n.name, "value": n.name}
                     for n in sorted(all_nodes, key=lambda n: n.name)]
        existing_opts = [opt for opt in node_opts if opt["value"] not in exclude]

        _ted = ConfigManager.get_time_estimate_defaults()

        return (
            True, type_opts, ctx_opts, [{"label": "None", "value": ""}],
            existing_opts, None, "", "", "", _ted.get('unit', 'weeks'),
            5, 5, 5,
            _ted.get('optimistic', 2),
            _ted.get('expected', 4),
            _ted.get('pessimistic', 6),
            "", "",
            "create",
            # Relationship dropdown options + values (cleared)
            node_opts, node_opts, node_opts, node_opts, node_opts,
            [], [], [], [], [],
            # Time mode + subcontext collapse reset
            [], False,
            # Reset external resource stores
            [''], [''], [''],
            # Override reset
            [],
            # Value mode reset
            [],
            # Habit reset
            [],            # details-add-time-habit-mode
            0,             # details-add-habit-duration
            'weeks',       # details-add-habit-duration-unit
            0, 0, 0,       # details-add-habit-intensity o/m/p
            'min_per_day', # details-add-habit-intensity-unit
        )

    # --- Add Node Modal: Toggle mode ---
    @app.callback(
        Output("details-add-create-section", "style"),
        Output("details-add-link-section", "style"),
        Input("details-add-mode", "value"),
    )
    def toggle_add_mode(mode):
        if mode == "link":
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Add Node Modal: Update subcontexts ---
    @app.callback(
        Output("details-add-subcontext", "options"),
        Input("details-add-context", "value"),
    )
    def update_add_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = sort_subcontexts(ConfigManager.get_subcontexts().get(context, []))
        return base + [{"label": s, "value": s} for s in subs]

    # --- Add Node Modal: Subcontext Toggle ---
    @app.callback(
        Output("collapse-details-add-subcontext", "is_open", allow_duplicate=True),
        Input("btn-details-add-subcontext-toggle", "n_clicks"),
        State("collapse-details-add-subcontext", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_details_add_subcontext(n, is_open):
        if n:
            return not is_open
        return no_update

    # --- Add Node Modal: Mode toggles control OMP / Habit visibility ---
    @app.callback(
        Output("details-add-time-omp", "style"),
        Output("section-details-add-time-habit", "style"),
        Input("details-add-time-mode", "value"),
        Input("details-add-time-habit-mode", "value"),
        prevent_initial_call=True,
    )
    def toggle_details_add_time_mode(inherit_val, habit_val):
        inherit_on = bool(inherit_val and "inherited" in inherit_val)
        habit_on = bool(habit_val and "habit" in habit_val)
        if inherit_on:
            return {"display": "none"}, {"display": "none"}
        if habit_on:
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Add Node Modal: Habit / Inherit mutual exclusivity ---
    @app.callback(
        Output("details-add-time-mode", "value", allow_duplicate=True),
        Output("details-add-time-habit-mode", "value", allow_duplicate=True),
        Input("details-add-time-mode", "value"),
        Input("details-add-time-habit-mode", "value"),
        prevent_initial_call=True,
    )
    def enforce_details_add_exclusivity(inherit_val, habit_val):
        trig = ctx.triggered_id
        if trig == "details-add-time-mode" and inherit_val and "inherited" in inherit_val:
            return inherit_val, []
        if trig == "details-add-time-habit-mode" and habit_val and "habit" in habit_val:
            return [], habit_val
        return inherit_val, habit_val

    # --- Add Node Modal: Live total-hours preview for habit ---
    @app.callback(
        Output("details-add-habit-total-preview", "children"),
        Input("details-add-habit-duration", "value"),
        Input("details-add-habit-duration-unit", "value"),
        Input("details-add-habit-intensity-m", "value"),
        Input("details-add-habit-intensity-unit", "value"),
    )
    def update_details_add_habit_preview(duration, dur_unit, intensity_m, int_unit):
        total = habit_to_hours(duration or 0, dur_unit or 'weeks',
                               intensity_m or 0, int_unit or 'min_per_day')
        if total <= 0:
            return ""
        return f"Computes to ~{round(total, 1)} h total"

    # --- Add Node Modal: Inherit-ratings toggle hides/shows V/I/E sliders ---
    @app.callback(
        Output("details-add-ratings", "style"),
        Input("details-add-value-mode", "value"),
        prevent_initial_call=True,
    )
    def toggle_details_add_value_mode(mode_val):
        if mode_val and "inherited" in mode_val:
            return {"display": "none"}
        return {"display": "block"}

    # --- Add Node Modal: External Resources Link Renderers ---
    @app.callback(
        Output('details-add-obsidian-container', 'children'),
        Input('details-add-obsidian-store', 'data'),
    )
    def render_details_add_obsidian(links):
        return render_link_rows(links, 'details-add-obsidian-link', has_browse=True)

    @app.callback(
        Output('details-add-drive-container', 'children'),
        Input('details-add-drive-store', 'data'),
    )
    def render_details_add_drive(links):
        return render_link_rows(strip_gdrive_prefix(links), 'details-add-drive-link', has_browse=True)

    @app.callback(
        Output('details-add-website-container', 'children'),
        Input('details-add-website-store', 'data'),
    )
    def render_details_add_website(links):
        return render_link_rows(links, 'details-add-website-link', has_browse=False)

    # --- Add Node Modal: Link Add/Remove/Browse for Obsidian ---
    @app.callback(
        Output('details-add-obsidian-store', 'data', allow_duplicate=True),
        Input('btn-details-add-obsidian-add', 'n_clicks'),
        Input({'type': 'btn-details-add-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-details-add-obsidian-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-obsidian-link', 'index': ALL}, 'value'),
        State('details-add-obsidian-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_obsidian(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-details-add-obsidian-browse':
                if not any(browse_clicks):
                    return no_update
                idx = trigger['index']
                vault = ConfigManager.get_obsidian_vault()
                abs_path = spawn_local_file_picker(
                    initial_dir=vault,
                    title="Select Obsidian File",
                    filetypes_list=[("Markdown files", "*.md"), ("All files", "*.*")],
                )
                if abs_path:
                    vault_norm = os.path.normpath(vault)
                    rel = abs_path[len(vault_norm):].lstrip(os.sep) if abs_path.startswith(vault_norm) else abs_path
                    if 0 <= idx < len(links):
                        links[idx] = rel
        return links

    # --- Add Node Modal: Link Add/Remove/Browse for Drive ---
    @app.callback(
        Output('details-add-drive-store', 'data', allow_duplicate=True),
        Input('btn-details-add-drive-add', 'n_clicks'),
        Input({'type': 'btn-details-add-drive-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-details-add-drive-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-drive-link', 'index': ALL}, 'value'),
        State('details-add-drive-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_drive(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        from callback_helpers import expand_gdrive_prefix
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-details-add-drive-browse':
                if not any(browse_clicks):
                    return no_update
                idx = trigger['index']
                gdrive = ConfigManager.get_gdrive_path() or ''
                abs_path = spawn_local_file_picker(
                    initial_dir=gdrive,
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")],
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
        # Store with full prefix for DB; UI shows stripped
        return [expand_gdrive_prefix(p) if p else p for p in links]

    # --- Add Node Modal: Link Add/Remove for Website ---
    @app.callback(
        Output('details-add-website-store', 'data', allow_duplicate=True),
        Input('btn-details-add-website-add', 'n_clicks'),
        Input({'type': 'btn-details-add-website-link-remove', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-website-link', 'index': ALL}, 'value'),
        State('details-add-website-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_website(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-website-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-website-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
        return links

    # --- Add Node Modal: Cancel ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Input("btn-details-add-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_add_node(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Add Node Modal: Save ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("details-add-save-status", "children"),
        Input("btn-details-add-save", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-add-mode", "value"),
        # Link mode
        State("details-add-existing-dropdown", "value"),
        State("details-add-link-edge-type", "value"),
        # Create mode
        State("details-add-name", "value"),
        State("details-add-type", "value"),
        State("details-add-context", "value"),
        State("details-add-subcontext", "value"),
        State("details-add-desc", "value"),
        State("details-add-value", "value"),
        State("details-add-interest", "value"),
        State("details-add-difficulty", "value"),
        State("details-add-time-o", "value"),
        State("details-add-time-m", "value"),
        State("details-add-time-p", "value"),
        State("details-add-time-unit", "value"),
        State("details-add-time-mode", "value"),
        State("details-add-value-mode", "value"),
        # Habit-mode states
        State("details-add-time-habit-mode", "value"),
        State("details-add-habit-duration", "value"),
        State("details-add-habit-duration-unit", "value"),
        State("details-add-habit-intensity-o", "value"),
        State("details-add-habit-intensity-m", "value"),
        State("details-add-habit-intensity-p", "value"),
        State("details-add-habit-intensity-unit", "value"),
        # Relationships
        State("details-add-needs-hard", "value"),
        State("details-add-needs-soft", "value"),
        State("details-add-supports-hard", "value"),
        State("details-add-supports-soft", "value"),
        State("details-add-helps", "value"),
        # External resources
        State({'type': 'details-add-obsidian-link', 'index': ALL}, 'value'),
        State({'type': 'details-add-drive-link', 'index': ALL}, 'value'),
        State({'type': 'details-add-website-link', 'index': ALL}, 'value'),
        # Override
        State("details-add-override-toggle", "value"),
        State("details-add-override-mode", "value"),
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_node, mode,
                      link_node, link_edge_type,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty,
                      time_o, time_m, time_p, time_unit, time_mode_val,
                      value_mode_val,
                      time_habit_mode_val,
                      habit_duration, habit_duration_unit,
                      habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                      needs_hard, needs_soft, supports_hard, supports_soft, helps,
                      obsidian_vals, drive_vals, website_vals,
                      override_toggle, override_mode):
        from callback_helpers import serialize_links
        if not n_clicks or not selected_node:
            return no_update, no_update, no_update

        if mode == "link":
            if not link_node:
                return no_update, no_update, "Please select a node to link."
            edge_type = EDGE_NEEDS_HARD if link_edge_type == "hard" else EDGE_NEEDS_SOFT
            try:
                graph_manager.add_edge(link_node, selected_node, edge_type)
            except ValueError as e:
                return no_update, no_update, str(e)
            return False, f"link-{link_node}", ""
        else:
            if not name or not name.strip():
                return no_update, no_update, "Node name is required."
            if not node_type:
                return no_update, no_update, "Node type is required."

            multiplier = ConfigManager.get_time_multiplier(time_unit or "weeks")
            t_o = float(time_o or 0) * multiplier
            t_m = float(time_m or 0) * multiplier
            t_p = float(time_p or 0) * multiplier

            obs_path = serialize_links(obsidian_vals)
            drive_path = serialize_links(drive_vals)
            web_path = serialize_links(website_vals)

            # Resolve time_mode via the shared helper — Goal/Milestone always
            # inherit; otherwise habit > inherited > manual.
            t_mode = resolve_time_mode(node_type, time_mode_val, time_habit_mode_val)
            if t_mode == 'habit':
                t_o, t_m, t_p = compute_habit_time_omp(
                    habit_duration or 0, habit_duration_unit or 'weeks',
                    habit_int_o or 0, habit_int_m or 0, habit_int_p or 0,
                    habit_int_unit or 'min_per_day',
                )
            v_mode = 'inherited' if (value_mode_val and 'inherited' in value_mode_val) else 'manual'

            new_node = Node(
                name=name.strip(),
                type=node_type,
                description=(desc or "").strip(),
                value=value or 5,
                time_o=t_o, time_m=t_m, time_p=t_p,
                interest=interest or 5,
                difficulty=difficulty or 5,
                status=STATUS_OPEN,
                context=context or None,
                subcontext=(subcontext or "").strip() or None,
                obsidian_path=obs_path,
                google_drive_path=drive_path,
                website=web_path,
                time_mode=t_mode,
                value_mode=v_mode,
                habit_duration=habit_duration or 0,
                habit_duration_unit=habit_duration_unit or 'weeks',
                habit_intensity_o=habit_int_o or 0,
                habit_intensity_m=habit_int_m or 0,
                habit_intensity_p=habit_int_p or 0,
                habit_intensity_unit=habit_int_unit or 'min_per_day',
            )

            try:
                graph_manager.add_node(new_node)
                graph_manager.add_edge(name.strip(), selected_node, EDGE_NEEDS_HARD)

                node_name_clean = name.strip()
                for target in (needs_hard or []):
                    try:
                        graph_manager.add_edge(target, node_name_clean, EDGE_NEEDS_HARD)
                    except ValueError:
                        pass
                for target in (needs_soft or []):
                    try:
                        graph_manager.add_edge(target, node_name_clean, EDGE_NEEDS_SOFT)
                    except ValueError:
                        pass
                for target in (supports_hard or []):
                    try:
                        graph_manager.add_edge(node_name_clean, target, EDGE_NEEDS_HARD)
                    except ValueError:
                        pass
                for target in (supports_soft or []):
                    try:
                        graph_manager.add_edge(node_name_clean, target, EDGE_NEEDS_SOFT)
                    except ValueError:
                        pass
                for target in (helps or []):
                    try:
                        graph_manager.add_edge(node_name_clean, target, EDGE_HELPS)
                    except ValueError:
                        pass
            except ValueError as e:
                return no_update, no_update, str(e)

            # Apply override if requested
            if override_toggle and "on" in override_toggle:
                ConfigManager.set_override({
                    "parent": name.strip(),
                    "mode": override_mode or "hard"
                })

            return False, f"add-{name}", ""

    # --- Add Node Modal: Override toggle visibility ---
    @app.callback(
        Output("details-add-override-options", "style"),
        Input("details-add-override-toggle", "value"),
        prevent_initial_call=True,
    )
    def toggle_add_override_options(on):
        return {"display": "block"} if on and "on" in on else {"display": "none"}

    # --- Subtask Remove: Open Modal ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-subtask-remove-pending", "data"),
        Output("details-subtask-remove-modal-body", "children"),
        Input({"type": "details-subtask-remove", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_subtask_remove_modal(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update, no_update
        node_name = triggered["index"]
        body = html.Div([
            html.P([
                'What would you like to do with node ',
                html.Strong(node_name), '?',
            ]),
            html.Ul([
                html.Li([html.Strong("Remove Edge"),
                         " — removes it from this node's dependency list."]),
                html.Li([html.Strong("Delete Node"),
                         " — permanently deletes the node."]),
            ]),
        ])
        return True, node_name, body

    # --- Subtask Remove: Cancel ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Input("btn-details-subtask-remove-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_subtask_remove(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Subtask Remove: Remove Edge ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-details-subtask-remove-edge", "n_clicks"),
        State("details-subtask-remove-pending", "data"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_remove_edge(n_clicks, node_name, selected_node):
        if not n_clicks or not node_name or not selected_node:
            return no_update, no_update
        edges = graph_manager.get_edges()
        for e in edges:
            if (e['source'] == node_name and e['target'] == selected_node and
                    e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)):
                graph_manager.remove_edge(node_name, selected_node, e['type'])
        return False, f"remove-edge-{node_name}"

    # --- Subtask Remove: Delete Node ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-details-subtask-delete-node", "n_clicks"),
        State("details-subtask-remove-pending", "data"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_delete_node(n_clicks, node_name, selected_node):
        if not n_clicks or not node_name:
            return no_update, no_update
        graph_manager.delete_node(node_name)
        return False, f"delete-{node_name}"

    # --- Details Graph Settings: Toggle Panel ---
    @app.callback(
        Output('details-graph-settings-panel', 'style'),
        Input('btn-details-graph-settings', 'n_clicks'),
        Input('btn-close-details-graph-settings', 'n_clicks'),
        State('details-graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_details_graph_settings(_n_open, _n_close, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Details Graph Settings: Reset to Stored Defaults ---
    @app.callback(
        Output('details-graph-settings-max-depth', 'value', allow_duplicate=True),
        Output('details-graph-settings-neighbor-links', 'value', allow_duplicate=True),
        Output('details-graph-settings-animate', 'value', allow_duplicate=True),
        Output('details-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('details-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('details-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('details-graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-details-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_details_graph_settings(n_clicks):
        if not n_clicks:
            return (no_update,) * 7
        gl = ConfigManager.get_details_graph_layout_defaults()
        return (
            0, True, True,
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Details Tab: Node Count Canvas Overlay ---
    # The Details canvas honors the global Context/Subcontext/Type/Done/
    # ratings/time filters but ignores Goal and Community (those only narrow
    # the main canvas), so the indicator only checks the filters that
    # actually affect the subtree being rendered here.
    @app.callback(
        Output('details-canvas-node-count', 'children'),
        Input('details-mini-graph', 'elements'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-done', 'value'),
        Input('details-graph-settings-max-depth', 'value'),
    )
    def update_details_node_count(elements, f_type, f_ctx, f_sub, f_val,
                                  f_int, f_diff, f_time, f_done, max_depth):
        n = sum(1 for el in (elements or []) if 'source' not in el.get('data', {}))
        text = f"{n} node{'s' if n != 1 else ''}"
        # Non-default max-depth (anything other than 0 = "All") narrows the
        # rendered subtree just like a filter does — surface it the same way.
        depth_active = bool(max_depth)
        if depth_active or is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                value=f_val, interest=f_int, difficulty=f_diff,
                time=f_time, done=f_done):
            return f"{text} · filtered"
        return text

    # --- Details Graph Settings: Apply Layout Parameters ---
    # Clientside so allowOneLayout('details') is set in the same synchronous
    # function that returns the layout dict — see callbacks.py for the rationale.
    app.clientside_callback(
        """
        function(edge_length, gravity, repulsion, animate, relayout_n, elements, freeze_on) {
            var ctx = window.dash_clientside.callback_context;
            var trig = ctx.triggered_id
                || (ctx.triggered && ctx.triggered.length
                    ? ctx.triggered[0].prop_id.split('.')[0]
                    : null);
            // While frozen, suppress layout prop updates (sliders/element changes)
            // EXCEPT explicit re-layout clicks — those bypass the JS guard.
            if (freeze_on && trig !== 'details-graph-settings-relayout') {
                return window.dash_clientside.no_update;
            }
            var is_relayout = (trig === 'details-graph-settings-relayout');
            // Randomize on re-layout click or when elements change (new node selected).
            var randomize = is_relayout || (trig === 'details-mini-graph');
            if (is_relayout && window.SkillTree && window.SkillTree.allowOneLayout) {
                window.SkillTree.allowOneLayout('details');
            }
            // Scale fcose iterations with graph size. Small subtrees converge
            // fast and don't need 2500 iters; large ones still do.
            var node_count = 0;
            if (Array.isArray(elements)) {
                for (var i = 0; i < elements.length; i++) {
                    var e = elements[i];
                    if (e && e.data && e.data.source === undefined) node_count++;
                }
            }
            var num_iter = Math.max(500, Math.min(2500, node_count * 25));
            return {
                name: 'fcose',
                quality: 'proof',
                animate: !!animate,
                fit: true,
                randomize: randomize,
                padding: 20,
                idealEdgeLength: edge_length || 100,
                nodeRepulsion: repulsion || 4500,
                gravity: (gravity !== null && gravity !== undefined) ? gravity : 0.25,
                numIter: num_iter,
            };
        }
        """,
        Output('details-mini-graph', 'layout'),
        Input('details-graph-settings-edge-length', 'value'),
        Input('details-graph-settings-gravity', 'value'),
        Input('details-graph-settings-repulsion', 'value'),
        Input('details-graph-settings-animate', 'value'),
        Input('details-graph-settings-relayout', 'n_clicks'),
        Input('details-mini-graph', 'elements'),
        State('details-freeze-rerender-store', 'data'),
    )

    # --- Explain Score modal ---------------------------------------------
    @app.callback(
        Output("modal-details-explain", "is_open"),
        [Input("btn-details-explain", "n_clicks"),
         Input("btn-details-explain-close", "n_clicks")],
        State("modal-details-explain", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_explain_modal(_open_clicks, _close_clicks, is_open):
        return not is_open

    @app.callback(
        [Output("details-explain-title", "children"),
         Output("details-explain-summary", "children"),
         Output("details-explain-contrib-store", "data"),
         Output("details-explain-count", "value")],
        [Input("modal-details-explain", "is_open"),
         Input("details-node-select", "value")],
        prevent_initial_call=True,
    )
    def populate_explain_modal(is_open, node_name):
        if not is_open or not node_name:
            return no_update, no_update, no_update, no_update
        all_nodes = graph_manager.get_all_nodes()
        priority_goals = ConfigManager.get_priority_goals()
        hypers = ConfigManager.get_hyperparams()
        hypers['context_weights'] = ConfigManager.get_context_weights()
        node = next((n for n in all_nodes if n.name == node_name), None)
        is_goal = node is not None and node.type == 'Goal'

        normalized = None
        if is_goal:
            # Goals are sinks in the prereq DAG: explain_score's forward
            # cascade collapses to ~nothing and would mark them ineligible.
            # explain_goal recomputes the breakdown on the inverted prereq
            # graph and pulls the headline score from _rank_goals, so the
            # modal matches the Goals-sidebar ranking exactly.
            from analyze_callbacks import explain_goal
            result = explain_goal(node_name, all_nodes,
                                  graph_manager.get_edges(),
                                  hypers, priority_goals)
            breakdown, normalized = result if result else (None, None)
        else:
            breakdown = explain_score(
                node_name,
                all_nodes,
                graph_manager.get_edges(),
                hypers,
                priority_goals=priority_goals,
            )
            # Match the Next-tab suggestion table: normalize this node's
            # priority_score against the max across all eligible active
            # nodes (see callback_helpers.format_suggestions_table).
            if breakdown and breakdown['eligible'] and breakdown['score'] > 0:
                scored = graph_manager.calculate_priority_scores(
                    all_nodes, priority_goals=priority_goals,
                )
                valid_scores = [n.priority_score for n in scored
                                if getattr(n, 'priority_score', -1) > 0]
                if valid_scores:
                    top = max(valid_scores)
                    if top > 0:
                        normalized = round((breakdown['score'] / top) * 100)
        title = node_name if breakdown else "Node not found"
        contributors = breakdown['contributors'] if breakdown else []
        # Reset count to default only when the modal opens — not when the
        # user selects a different node while it's already open.
        count_out = 10 if ctx.triggered_id == "modal-details-explain" else no_update
        return (title, build_explain_summary(breakdown, normalized),
                contributors, count_out)

    @app.callback(
        Output("details-explain-chart", "figure"),
        [Input("details-explain-count", "value"),
         Input("details-explain-contrib-store", "data")],
        prevent_initial_call=True,
    )
    def update_explain_chart(count, contributors):
        try:
            n = max(1, int(count)) if count else 10
        except (TypeError, ValueError):
            n = 10
        return build_explain_chart(contributors or [], top_n=n)

    @app.callback(
        [Output("details-explain-focus-feedback", "children"),
         Output("btn-details-explain-focus", "disabled")],
        Input("details-explain-focus-count", "value"),
        prevent_initial_call=True,
    )
    def validate_focus_count(val):
        if val is None:
            return "", False
        try:
            n = int(val)
        except (TypeError, ValueError):
            return "", False
        if n > 5:
            return "Max is 5", True
        if n < 1:
            return "Min is 1", True
        return "", False

    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("modal-details-explain", "is_open", allow_duplicate=True),
        Input("btn-details-explain-focus", "n_clicks"),
        [State("details-selected-node-store", "data"),
         State("details-explain-contrib-store", "data"),
         State("details-explain-focus-count", "value")],
        prevent_initial_call=True,
    )
    def focus_top_contributor_paths(n_clicks, selected_node, contributors, k):
        if not n_clicks or not selected_node or not contributors:
            return no_update, no_update, no_update
        try:
            k_int = max(1, min(5, int(k))) if k else 3
        except (TypeError, ValueError):
            k_int = 3
        # Top-K contributors excluding Self; rank by list position.
        ranked_targets = []
        for c in contributors:
            name = c.get('name')
            if not name or name == selected_node:
                continue
            ranked_targets.append((len(ranked_targets) + 1, name))
            if len(ranked_targets) >= k_int:
                break
        all_nodes_fc = graph_manager.get_all_nodes()
        node_fc = next((n for n in all_nodes_fc if n.name == selected_node), None)
        is_goal_fc = node_fc is not None and node_fc.type == 'Goal'
        edges_fc = graph_manager.get_edges()
        if is_goal_fc:
            # A Goal's contributors are its prerequisites (upstream), so the
            # paths to them run against the arrows — walk the inverted
            # Hard/Soft graph. Helps is symmetric and left alone.
            edges_fc = [
                {'source': e['target'], 'target': e['source'], 'type': e['type']}
                if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) else e
                for e in edges_fc
            ]
        pi = shortest_paths_focus_data(
            selected_node, ranked_targets, all_nodes_fc, edges_fc,
        )
        edge_rank_items = list(pi['edge_rank'].items())
        if is_goal_fc:
            # Flip keys back to real edge orientation so the canvas matches
            # them against actual prereq -> dependent edges.
            edge_rank_items = [((t, s, etype), r)
                               for (s, t, etype), r in edge_rank_items]
        # Serialize edge_rank keys for JSON compatibility in dcc.Store.
        edge_rank_str = {
            f"{s}|{t}|{etype}": r
            for (s, t, etype), r in edge_rank_items
        }
        return (
            {"node": selected_node,
             "subtree": pi['subtree'],
             "path_info": {
                 "node_rank": pi['node_rank'],
                 "edge_rank": edge_rank_str,
                 "target_labels": pi['target_labels'],
             }},
            "tab-canvas", False,
        )


def _build_graph_elements(selected_node, include_soft_val, include_synergies_val,
                          global_filters=None, include_transitive_val=None,
                          max_depth=0, neighbor_links=True):
    """Shared helper to build Cytoscape elements for the dependency graph."""
    include_soft = bool(include_soft_val and "include" in include_soft_val)
    include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
    include_transitive = bool(include_transitive_val and "include" in include_transitive_val)
    global_filters = global_filters or {}

    edge_types = [EDGE_NEEDS_HARD]
    if include_soft:
        edge_types.append(EDGE_NEEDS_SOFT)
    if include_synergies:
        edge_types.append(EDGE_HELPS)

    subtree = graph_manager.get_goal_subtree(selected_node,
                                              edge_types=tuple(edge_types))

    # When Transitive is off, restrict to direct children only
    if not include_transitive:
        all_edges = graph_manager.get_edges()
        direct = set()
        for e in all_edges:
            if e['target'] == selected_node and e['type'] in edge_types:
                direct.add(e['source'])
            if EDGE_HELPS in edge_types and e['type'] == EDGE_HELPS:
                if e['target'] == selected_node:
                    direct.add(e['source'])
                elif e['source'] == selected_node:
                    direct.add(e['target'])
        subtree = subtree & direct

    node_names = subtree | {selected_node}
    depth_by_name = {}

    # --- Max Depth filtering (BFS from selected node) ---
    if max_depth and max_depth > 0:
        all_edges = graph_manager.get_edges()
        adj = {}
        for e in all_edges:
            s, t = e['source'], e['target']
            if s in node_names and t in node_names:
                adj.setdefault(s, set()).add(t)
                adj.setdefault(t, set()).add(s)
        visited = {selected_node}
        depth_by_name = {selected_node: 0}
        frontier = {selected_node}
        for d in range(max_depth):
            next_frontier = set()
            for n in frontier:
                for nb in adj.get(n, set()):
                    if nb not in visited:
                        visited.add(nb)
                        depth_by_name[nb] = d + 1
                        next_frontier.add(nb)
            frontier = next_frontier
            if not frontier:
                break
        node_names = node_names & visited

    colors = ConfigManager.get_node_colors()
    shapes = ConfigManager.get_node_shapes()
    trigger_names = event_manager.get_trigger_node_names()

    # Apply global filters to subtree nodes (always include the selected node itself)
    all_subtree_nodes = [graph_manager.get_node(n) for n in node_names if n != selected_node]
    all_subtree_nodes = [n for n in all_subtree_nodes if n is not None]
    filtered_subtree = {n.name for n in graph_manager.filter_nodes(all_subtree_nodes, global_filters)}
    filtered_subtree.add(selected_node)

    # Post-filter reachability: drop nodes that are only reachable through a
    # filtered-out bridge (e.g. a Done node that the Done filter hid). Without
    # this, such nodes appear as orphaned clusters disconnected from the
    # selected node in the rendered mini-graph.
    all_edges_for_reach = graph_manager.get_edges()
    reach_adj = {}
    for e in all_edges_for_reach:
        if e['source'] not in filtered_subtree or e['target'] not in filtered_subtree:
            continue
        if e['type'] not in edge_types:
            continue
        reach_adj.setdefault(e['source'], set()).add(e['target'])
        reach_adj.setdefault(e['target'], set()).add(e['source'])
    reachable = {selected_node}
    stack = [selected_node]
    while stack:
        n = stack.pop()
        for nb in reach_adj.get(n, ()):
            if nb not in reachable:
                reachable.add(nb)
                stack.append(nb)
    filtered_subtree = filtered_subtree & reachable

    elements = []
    filtered_names = set()
    for name in node_names:
        node = graph_manager.get_node(name)
        if not node:
            continue
        if name not in filtered_subtree:
            continue
        filtered_names.add(name)
        element = {
            'data': {
                'id': node.name,
                'label': node.name,
                'color': (
                    colors.get(STATUS_DONE, '#198754') if node.status == STATUS_DONE
                    else colors.get(STATUS_BLOCKED, '#dc3545') if node.status == STATUS_BLOCKED
                    else colors.get(node.type, colors.get(STATUS_OPEN, '#0d6efd'))
                ),
                'shape': shapes.get(node.type, 'ellipse'),
                'type': node.type,
                'status': node.status,
                'value': node.value,
                'interest': node.interest,
                'difficulty': node.difficulty,
                'context': node.context or '',
                'subcontext': node.subcontext or '',
                'time': round(graph_manager.get_effective_time(node.name), 1),
                'time_o': node.time_o,
                'time_m': node.time_m,
                'time_p': node.time_p,
            },
        }
        if name in trigger_names:
            element['classes'] = 'trigger'
        elements.append(element)

    edges = graph_manager.get_edges()
    for e in edges:
        if e['source'] in filtered_names and e['target'] in filtered_names:
            # Neighbor links filter: when off, hide peer edges between same-BFS-depth
            # nodes so the local subtree stays legible (Obsidian local-graph style).
            # When no BFS ran (max_depth == 0), fall back to "edges touching selected node".
            if not neighbor_links:
                if depth_by_name:
                    if depth_by_name.get(e['source']) == depth_by_name.get(e['target']):
                        continue
                else:
                    if e['source'] != selected_node and e['target'] != selected_node:
                        continue
            elements.append({
                'data': {
                    'id': f"{e['source']}_{e['target']}_{e['type']}",
                    'source': e['source'],
                    'target': e['target'],
                    'type': e['type'],
                },
            })

    return elements
