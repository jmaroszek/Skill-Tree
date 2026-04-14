"""
Callback definitions for the Details tab.
"""

import os
import json as _json
import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from details_layout import build_details_subtasks_table, build_goal_card
from simulation import simulate_task_chain
from callback_helpers import render_link_rows, strip_gdrive_prefix, spawn_local_file_picker, build_filters

graph_manager = GraphManager()


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

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=samples, nbinsx=50,
        marker_color='#0d6efd', opacity=0.85,
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
        showlegend=False,
    )

    return (
        fig,
        {"display": "flex", "flexDirection": "column", "flex": "1"},
        {"display": "none"},
    )


def register_details_callbacks(app):

    # --- Populate node dropdown when tab becomes active ---
    @app.callback(
        Output("details-node-select", "options"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
    )
    def populate_details_dropdown(active_tab, _refresh):
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
        # Simulation — auto-run on node selection
        Output("details-sim-chart", "figure", allow_duplicate=True),
        Output("details-sim-results", "style", allow_duplicate=True),
        Output("details-sim-empty", "style", allow_duplicate=True),
        # Inputs
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
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
        State("details-graph-settings-max-depth", "value"),
        prevent_initial_call=True,
    )
    def select_detail_node(node_name, _refresh,
                           include_soft_val, include_transitive_val,
                           include_synergies_val,
                           f_context, f_subcontext, f_done,
                           f_value, f_interest, f_time, f_difficulty,
                           f_node_types, gs_max_depth):
        if not node_name:
            empty_fig = go.Figure()
            empty_fig.update_layout(template="plotly_dark",
                                    paper_bgcolor='#1a1d21',
                                    plot_bgcolor='#1a1d21')
            return (
                {"display": "block"},
                {"display": "none"},
                None,
                "", [], "", "", "", "", "", "", "", "",
                {"display": "none"}, 0, "",
                {"display": "none"}, "",
                html.Div("Select a node to see subtasks.",
                         className="text-muted text-center py-3"),
                empty_fig, {"display": "none"}, {"display": "block"},
            )

        node = graph_manager.get_node(node_name)
        if not node:
            return (no_update,) * 22

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_transitive = bool(include_transitive_val and "include" in include_transitive_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)

        # Build badges
        badges = []
        if node.type:
            type_colors = {"Learn": "primary", "Action": "warning",
                          "Goal": "warning", "Resource": "info"}
            badges.append(dbc.Badge(node.type,
                                    color=type_colors.get(node.type, "secondary"),
                                    style={"fontSize": "0.75rem"}))
        status_colors = {"Done": "success", "Blocked": "danger", "Open": "primary"}
        badges.append(dbc.Badge(node.status,
                                color=status_colors.get(node.status, "secondary"),
                                style={"fontSize": "0.75rem"}))

        priority_goals = ConfigManager.get_priority_goals()
        if node_name in priority_goals:
            rank = priority_goals.index(node_name) + 1
            badges.append(dbc.Badge(f"#{rank} Priority", color="warning",
                                    style={"fontSize": "0.75rem"}))
        else:
            for rank_idx, goal_name in enumerate(priority_goals[:3]):
                subtree = graph_manager.get_goal_subtree(goal_name)
                if node_name in subtree:
                    hard_subtree = graph_manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                    rel_type = "Hard" if node_name in hard_subtree else "Soft"
                    rel_color = "primary" if rel_type == "Hard" else "info"
                    badges.append(dbc.Badge(f"{rel_type} #{rank_idx+1}",
                                            color=rel_color,
                                            style={"fontSize": "0.75rem"}))
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
                node_name, include_soft=include_soft,
                include_transitive=include_transitive)
            if completion["total"] > 0:
                show_progress = {"display": "block", "marginBottom": "8px"}
                progress_val = completion["pct"]
                remaining = ConfigManager.format_time_friendly(
                    completion["remaining_time"])
                progress_text = (f"{completion['done']}/{completion['total']} "
                                f"subtasks · {remaining} remaining")

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
                                       f_node_types)
        subtask_nodes = graph_manager.filter_nodes(subtask_nodes, global_filters)

        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        subtasks_table = build_details_subtasks_table(
            subtask_nodes, graph_manager=graph_manager, edges=edges,
            parent_name=node_name, include_soft=include_soft,
            include_transitive=include_transitive,
            include_synergies=include_synergies)

        # Auto-run simulation
        sim_fig, sim_show, sim_hide = _run_simulation(
            node_name, include_soft_val, include_synergies_val,
            include_transitive_val=include_transitive_val,
            global_filters=global_filters, max_depth=depth_val)

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
            sim_fig, sim_show, sim_hide,
        )

    # --- Toggle subtask filters ---
    @app.callback(
        Output("details-subtasks-table-container", "children", allow_duplicate=True),
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
        Input("details-graph-settings-max-depth", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_details_subtask_filters(include_soft_val, include_transitive_val,
                                        include_synergies_val,
                                        f_context, f_subcontext, f_done,
                                        f_value, f_interest, f_time, f_difficulty,
                                        f_node_types, gs_max_depth, selected_node):
        if not selected_node:
            return no_update

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
                                       f_node_types)
        subtask_nodes = graph_manager.filter_nodes(subtask_nodes, global_filters)

        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        return build_details_subtasks_table(
            subtask_nodes, graph_manager=graph_manager, edges=edges,
            parent_name=selected_node, include_soft=include_soft,
            include_transitive=include_transitive,
            include_synergies=include_synergies)

    # --- Dependency Graph ---
    @app.callback(
        Output("details-mini-graph", "elements"),
        Input("details-selected-node-store", "data"),
        Input("details-refresh-trigger", "data"),
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
        Input("details-graph-settings-max-depth", "value"),
        Input("details-graph-settings-neighbor-links", "value"),
    )
    def update_details_graph(selected_node, _refresh,
                             include_soft_val, include_transitive_val,
                             include_synergies_val,
                             f_node_types, f_done, f_context, f_subcontext,
                             f_value, f_interest, f_time, f_difficulty,
                             gs_max_depth, gs_neighbor_links):
        if not selected_node:
            return []
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types)
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

    # --- Goal Sidebar Toggle ---
    @app.callback(
        Output("details-goal-sidebar", "style"),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Input("btn-goals-toggle", "n_clicks"),
        Input("btn-details-goals-close", "n_clicks"),
        Input("btn-add", "n_clicks"),
        State("details-goal-sidebar", "style"),
        State("details-refresh-trigger", "data"),
        State("sidebar-editor-container", "style"),
        prevent_initial_call=True,
    )
    def toggle_goal_sidebar(open_clicks, close_clicks, add_clicks, current_style, refresh_data, editor_style):
        trigger = ctx.triggered_id
        style = dict(current_style) if current_style else {}
        refresh = no_update
        next_editor_style = no_update
        if trigger == "btn-goals-toggle":
            opening = style.get("left", "-380px") == "-380px"
            style["left"] = "0px" if opening else "-380px"
            if opening:
                refresh = (refresh_data or 0) + 1
                # Sidebar mutex: close editor when opening goal sidebar
                if editor_style and editor_style.get("transform", "") == "translateX(0px)":
                    next_editor_style = dict(editor_style)
                    next_editor_style["transform"] = "translateX(-380px)"
        elif trigger in ("btn-details-goals-close", "btn-add"):
            style["left"] = "-380px"
        return style, refresh, next_editor_style

# --- New Goal from Sidebar "+" Button ---
    @app.callback(
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Output("node-type", "value", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Input("btn-goals-sidebar-new", "n_clicks"),
        State("details-goal-sidebar", "style"),
        State("sidebar-editor-container", "style"),
        prevent_initial_call=True,
    )
    def new_goal_from_sidebar(n_clicks, goal_sidebar_style, editor_style):
        if not n_clicks:
            return no_update, no_update, no_update
        goal_style = dict(goal_sidebar_style) if goal_sidebar_style else {}
        goal_style["left"] = "-380px"
        ed_style = dict(editor_style) if editor_style else {}
        ed_style["transform"] = "translateX(0px)"
        return goal_style, "Goal", ed_style

# --- Populate Goal Sidebar ---
    @app.callback(
        Output("details-goal-list-container", "children"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
        Input("details-goal-search", "value"),
        Input("details-goal-sort", "value"),
        Input("details-goal-order-store", "data"),
        State("details-selected-node-store", "data"),
    )
    def render_goal_list(active_tab, _refresh, search_val, sort_mode, manual_order, selected_node):

        all_nodes = graph_manager.get_all_nodes()
        goals = [n for n in all_nodes if n.type == "Goal"]

        if not goals:
            return html.Div(
                html.P("No goals yet.", className="text-muted"),
                className="text-center py-5"
            )

        if search_val and search_val.strip():
            search_lower = search_val.strip().lower()
            goals = [g for g in goals if search_lower in g.name.lower()]

        priority_goals = ConfigManager.get_priority_goals()
        completion_cache = {}
        for g in goals:
            completion_cache[g.name] = graph_manager.get_goal_completion(g.name)

        sort_mode = sort_mode or "manual"
        is_manual = sort_mode == "manual"

        if sort_mode == "alpha-asc":
            goals.sort(key=lambda g: g.name.lower())
        elif sort_mode == "alpha-desc":
            goals.sort(key=lambda g: g.name.lower(), reverse=True)
        elif sort_mode == "time-asc":
            goals.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0))
        elif sort_mode == "time-desc":
            goals.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0),
                       reverse=True)
        elif is_manual and manual_order:
            order_map = {name: idx for idx, name in enumerate(manual_order)}
            goals.sort(key=lambda g: order_map.get(g.name, 999))

        # Pin priority 1-3 at the top
        pinned = []
        unpinned = []
        for g in goals:
            if g.name in priority_goals[:3]:
                pinned.append(g)
            else:
                unpinned.append(g)
        pinned.sort(key=lambda g: priority_goals.index(g.name))
        goals = pinned + unpinned

        cards = []
        for goal in goals:
            completion = completion_cache[goal.name]
            rank = None
            if goal.name in priority_goals:
                rank = priority_goals.index(goal.name) + 1
            cards.append(build_goal_card(
                goal.name, goal.status, completion,
                completion.get("total", 0),
                is_selected=(goal.name == selected_node),
                priority_rank=rank,
                show_order_buttons=is_manual,
            ))
        return cards

    # --- Goal Card Click → Select in Details + switch tab ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input({"type": "goal-card", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def goal_card_to_details(n_clicks_list, active_tab):
        if not any(n_clicks_list):
            return no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
        node_name = triggered["index"]
        # Switch to details tab if not already there
        next_tab = "tab-details" if active_tab != "tab-details" else no_update
        return node_name, next_tab

    # --- Goal Drag Reorder ---
    @app.callback(
        Output("details-goal-order-store", "data"),
        Input("details-goal-drag-order-input", "value"),
        prevent_initial_call=True,
    )
    def reorder_details_goals(drag_order_json):
        if drag_order_json:
            try:
                new_order = _json.loads(drag_order_json)
                if isinstance(new_order, list) and new_order:
                    ConfigManager.set_goal_order(new_order)
                    return new_order
            except (ValueError, TypeError):
                pass
        return no_update

    # --- Re-run simulation when any toggle changes ---
    # (Node selection auto-run is handled inside select_detail_node)
    @app.callback(
        Output("details-sim-chart", "figure", allow_duplicate=True),
        Output("details-sim-results", "style", allow_duplicate=True),
        Output("details-sim-empty", "style", allow_duplicate=True),
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
        Input("details-graph-settings-max-depth", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def run_details_simulation(include_soft_val, include_transitive_val,
                                include_synergies_val,
                                f_context, f_subcontext, f_done,
                                f_value, f_interest, f_time, f_difficulty,
                                f_node_types, gs_max_depth, node_name):
        if not node_name:
            return no_update, no_update, no_update
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types)
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
        prevent_initial_call=True,
    )
    def details_focus_canvas(n_clicks, selected_node):
        if not n_clicks or not selected_node:
            return no_update, no_update
        return selected_node, "tab-canvas"

    # --- Edit Node → Navigate to Nodes Tab + open editor ---
    @app.callback(
        Output("search-node", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input("btn-details-edit", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def details_edit_node(n_clicks, selected_node):
        if not n_clicks or not selected_node:
            return no_update, no_update
        return selected_node, "tab-canvas"

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
        # External resource stores reset
        Output("details-add-obsidian-store", "data"),
        Output("details-add-drive-store", "data"),
        Output("details-add-website-store", "data"),
        Input("btn-details-add-node", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_node):
        if not n_clicks:
            return (no_update,) * 32

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": "None", "value": ""}] + \
                   [{"label": c, "value": c} for c in contexts]

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
            # Reset external resource stores
            [''], [''], [''],
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
        subs = ConfigManager.get_subcontexts().get(context, [])
        return base + [{"label": s, "value": s} for s in subs]

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
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_node, mode,
                      link_node, link_edge_type,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty,
                      time_o, time_m, time_p, time_unit,
                      needs_hard, needs_soft, supports_hard, supports_soft, helps,
                      obsidian_vals, drive_vals, website_vals):
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

            new_node = Node(
                name=name.strip(),
                type=node_type,
                description=(desc or "").strip(),
                value=value or 5,
                time_o=t_o, time_m=t_m, time_p=t_p,
                interest=interest or 5,
                difficulty=difficulty or 5,
                status="Open",
                context=context or None,
                subcontext=(subcontext or "").strip() or None,
                obsidian_path=obs_path,
                google_drive_path=drive_path,
                website=web_path,
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
            return False, f"add-{name}", ""

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
        State('details-graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_details_graph_settings(_n, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Details Tab: Node Count in Sidebar ---
    @app.callback(
        Output('filter-node-count', 'children', allow_duplicate=True),
        Input('details-mini-graph', 'elements'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def update_details_node_count(elements, active_tab):
        if active_tab != 'tab-details':
            return no_update
        if not elements:
            return "0 nodes displayed"
        count = sum(1 for el in elements if 'source' not in el.get('data', {}))
        return f"{count} node{'s' if count != 1 else ''} displayed"

    # --- Details Graph Settings: Apply Layout Parameters ---
    @app.callback(
        Output('details-mini-graph', 'layout'),
        Input('details-graph-settings-edge-length', 'value'),
        Input('details-graph-settings-gravity', 'value'),
        Input('details-graph-settings-repulsion', 'value'),
    )
    def update_details_graph_layout(edge_length, gravity, repulsion):
        return {
            'name': 'cose-bilkent',
            'animate': False,
            'fit': True,
            'padding': 20,
            'idealEdgeLength': edge_length or 100,
            'nodeRepulsion': repulsion or 4500,
            'gravity': gravity if gravity is not None else 0.25,
            'numIter': 2500,
        }


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
        node_names = node_names & visited

    colors = ConfigManager.get_node_colors()
    shapes = ConfigManager.get_node_shapes()

    # Apply global filters to subtree nodes (always include the selected node itself)
    all_subtree_nodes = [graph_manager.get_node(n) for n in node_names if n != selected_node]
    all_subtree_nodes = [n for n in all_subtree_nodes if n is not None]
    filtered_subtree = {n.name for n in graph_manager.filter_nodes(all_subtree_nodes, global_filters)}
    filtered_subtree.add(selected_node)

    elements = []
    filtered_names = set()
    for name in node_names:
        node = graph_manager.get_node(name)
        if not node:
            continue
        if name not in filtered_subtree:
            continue
        filtered_names.add(name)
        elements.append({
            'data': {
                'id': node.name,
                'label': node.name,
                'color': (
                    colors.get('Done', '#198754') if node.status == 'Done'
                    else colors.get('Blocked', '#dc3545') if node.status == 'Blocked'
                    else colors.get('Goal', '#ffc107') if node.type == 'Goal'
                    else colors.get('Resource', '#9b59b6') if node.type == 'Resource'
                    else colors.get(node.status, '#6c757d')
                ),
                'shape': shapes.get(node.type, 'ellipse'),
                'type': node.type,
                'status': node.status,
                'value': node.value,
                'interest': node.interest,
                'difficulty': node.difficulty,
                'context': node.context or '',
                'subcontext': node.subcontext or '',
                'time': round(node.time, 1) if node.time else 0,
                'time_o': node.time_o,
                'time_m': node.time_m,
                'time_p': node.time_p,
            },
        })

    edges = graph_manager.get_edges()
    for e in edges:
        if e['source'] in filtered_names and e['target'] in filtered_names:
            # Neighbor links filter: when off, only show edges touching selected node
            if not neighbor_links:
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
