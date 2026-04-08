"""
Callback definitions for the Details tab.
"""

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from details_layout import build_details_subtasks_table
from simulation import simulate_task_chain
from goals_layout import build_goal_card

graph_manager = GraphManager()


def register_details_callbacks(app):

    # --- Populate node dropdown when tab becomes active ---
    @app.callback(
        Output("details-node-select", "options"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
    )
    def populate_details_dropdown(active_tab, _refresh):
        if active_tab != "tab-details":
            return no_update
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name}
                for n in sorted(nodes, key=lambda n: n.name)]

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
        # Reset simulation
        Output("details-sim-results", "style", allow_duplicate=True),
        Output("details-sim-empty", "style", allow_duplicate=True),
        # Inputs
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
        State("details-include-soft-needs", "value"),
        State("details-include-transitive", "value"),
        State("details-include-synergies", "value"),
        prevent_initial_call=True,
    )
    def select_detail_node(node_name, _refresh,
                           include_soft_val, include_transitive_val,
                           include_synergies_val):
        if not node_name:
            return (
                {"display": "block"},                                    # empty visible
                {"display": "none"},                                     # content hidden
                None,                                                    # store
                "", [], "", "", "", "", "", "", "", "",                  # attrs
                {"display": "none"}, 0, "",                             # progress
                {"display": "none"}, "",                                # priority
                html.Div("Select a node to see subtasks.", className="text-muted text-center py-3"),
                {"display": "none"}, {"display": "block"},              # sim reset
            )

        node = graph_manager.get_node(node_name)
        if not node:
            return (no_update,) * 21

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

        # Context string
        ctx_str = node.context or "—"
        if node.subcontext:
            ctx_str += f" › {node.subcontext}"

        # Time (use effective time for inherited mode)
        effective_time = graph_manager.get_effective_time(node_name)
        time_str = ConfigManager.format_time_friendly(effective_time) if effective_time else "—"

        # Progress (for goals)
        show_progress = {"display": "none"}
        progress_val = 0
        progress_text = ""
        if node.type == "Goal":
            completion = graph_manager.get_goal_completion(
                node_name, include_soft=include_soft,
                include_transitive=include_transitive)
            if completion["total"] > 0:
                show_progress = {"display": "block"}
                progress_val = completion["pct"]
                remaining = ConfigManager.format_time_friendly(
                    completion["remaining_time"])
                progress_text = (f"{completion['done']}/{completion['total']} "
                                f"subtasks · {remaining} remaining")

        # Priority
        show_priority = {"display": "none"}
        priority_badge = ""
        priority_goals = ConfigManager.get_priority_goals()
        if node_name in priority_goals:
            rank = priority_goals.index(node_name) + 1
            show_priority = {"display": "block"}
            priority_badge = dbc.Badge(f"#{rank} Priority", color="warning",
                                       style={"fontSize": "0.8rem"})
        else:
            # Check if in any priority goal's subtree
            for rank_idx, goal_name in enumerate(priority_goals[:3]):
                subtree = graph_manager.get_goal_subtree(goal_name)
                if node_name in subtree:
                    show_priority = {"display": "block"}
                    priority_badge = html.Div([
                        dbc.Badge(f"#{rank_idx+1} Priority", color="warning",
                                  style={"fontSize": "0.8rem"}),
                        html.Small(f" (via {goal_name})", className="text-muted ms-1"),
                    ], className="d-flex align-items-center")
                    break

        # Subtasks table
        edge_types = [EDGE_NEEDS_HARD]
        if include_soft:
            edge_types.append(EDGE_NEEDS_SOFT)
        if include_synergies:
            edge_types.append(EDGE_HELPS)

        subtree = graph_manager.get_goal_subtree(node_name,
                                                  edge_types=tuple(edge_types))
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        subtasks_table = build_details_subtasks_table(
            subtask_nodes, graph_manager=graph_manager, edges=edges,
            parent_name=node_name, include_soft=include_soft,
            include_transitive=include_transitive)

        return (
            {"display": "none"},                                         # hide empty
            {"display": "flex", "flexDirection": "column", "flex": "1",
             "padding": "0 24px", "overflowY": "auto"},                 # show content
            node_name,                                                   # store
            node.name,                                                   # name
            badges,                                                      # badges
            node.description or "No description.",                       # description
            node.type or "—",                                            # type
            node.status or "—",                                          # status
            ctx_str,                                                     # context
            time_str,                                                    # time
            str(node.value),                                             # value
            str(node.interest),                                          # interest
            str(node.difficulty),                                        # effort
            show_progress, progress_val, progress_text,                  # progress
            show_priority, priority_badge,                               # priority
            subtasks_table,                                              # subtasks
            {"display": "none"}, {"display": "block"},                   # reset sim
        )

    # --- Toggle subtask filters ---
    @app.callback(
        Output("details-subtasks-table-container", "children", allow_duplicate=True),
        Input("details-include-soft-needs", "value"),
        Input("details-include-transitive", "value"),
        Input("details-include-synergies", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_details_subtask_filters(include_soft_val, include_transitive_val,
                                        include_synergies_val, selected_node):
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
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        return build_details_subtasks_table(
            subtask_nodes, graph_manager=graph_manager, edges=edges,
            parent_name=selected_node, include_soft=include_soft,
            include_transitive=include_transitive)

    # --- Dependency Graph ---
    @app.callback(
        Output("details-mini-graph", "elements"),
        Input("details-selected-node-store", "data"),
        Input("details-refresh-trigger", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-transitive", "value"),
        Input("details-include-synergies", "value"),
    )
    def update_details_graph(selected_node, _refresh,
                             include_soft_val, include_transitive_val,
                             include_synergies_val):
        if not selected_node:
            return []

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)

        edge_types = [EDGE_NEEDS_HARD]
        if include_soft:
            edge_types.append(EDGE_NEEDS_SOFT)
        if include_synergies:
            edge_types.append(EDGE_HELPS)

        subtree = graph_manager.get_goal_subtree(selected_node,
                                                  edge_types=tuple(edge_types))
        node_names = subtree | {selected_node}

        colors = ConfigManager.get_node_colors()
        shapes = ConfigManager.get_node_shapes()

        elements = []
        for name in node_names:
            node = graph_manager.get_node(name)
            if not node:
                continue
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
                    'difficulty': node.difficulty,
                    'context': node.context or '',
                    'time': round(node.time, 1) if node.time else 0,
                    'time_o': node.time_o,
                    'time_m': node.time_m,
                    'time_p': node.time_p,
                },
            })

        edges = graph_manager.get_edges()
        for e in edges:
            if e['source'] in node_names and e['target'] in node_names:
                elements.append({
                    'data': {
                        'id': f"{e['source']}_{e['target']}_{e['type']}",
                        'source': e['source'],
                        'target': e['target'],
                        'type': e['type'],
                    },
                })

        return elements

    # --- Goal Sidebar Toggle ---
    @app.callback(
        Output("details-goal-sidebar", "style"),
        Input("btn-details-goals-toggle", "n_clicks"),
        Input("btn-details-goals-close", "n_clicks"),
        State("details-goal-sidebar", "style"),
        prevent_initial_call=True,
    )
    def toggle_goal_sidebar(open_clicks, close_clicks, current_style):
        trigger = ctx.triggered_id
        style = dict(current_style) if current_style else {}
        if trigger == "btn-details-goals-toggle":
            style["left"] = "0px" if style.get("left", "-320px") == "-320px" else "-320px"
        elif trigger == "btn-details-goals-close":
            style["left"] = "-320px"
        return style

    # --- Populate Goal Sidebar ---
    @app.callback(
        Output("details-goal-list-container", "children"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
        Input("details-goal-search", "value"),
        Input("details-goal-sort", "value"),
        State("details-selected-node-store", "data"),
    )
    def render_goal_list(active_tab, _refresh, search_val, sort_mode, selected_node):
        if active_tab != "tab-details":
            return no_update

        all_nodes = graph_manager.get_all_nodes()
        goals = [n for n in all_nodes if n.type == "Goal"]

        if not goals:
            return html.Div(
                html.P("No goals yet.", className="text-muted"),
                className="text-center py-5"
            )

        # Search filter
        if search_val and search_val.strip():
            search_lower = search_val.strip().lower()
            goals = [g for g in goals if search_lower in g.name.lower()]

        # Compute completions
        priority_goals = ConfigManager.get_priority_goals()
        completion_cache = {}
        for g in goals:
            completion_cache[g.name] = graph_manager.get_goal_completion(g.name)

        # Sort
        sort_mode = sort_mode or "alpha-asc"
        if sort_mode == "alpha-asc":
            goals.sort(key=lambda g: g.name.lower())
        elif sort_mode == "alpha-desc":
            goals.sort(key=lambda g: g.name.lower(), reverse=True)
        elif sort_mode == "time-asc":
            goals.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0))
        elif sort_mode == "time-desc":
            goals.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0),
                       reverse=True)

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
                show_order_buttons=False,
            ))
        return cards

    # --- Goal Card Click → Select in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "goal-card", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def goal_card_to_details(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Run Simulation ---
    @app.callback(
        Output("details-sim-chart", "figure"),
        Output("details-sim-stats", "children"),
        Output("details-sim-results", "style"),
        Output("details-sim-empty", "style"),
        Output("details-sim-title", "children"),
        Input("btn-details-simulate", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-include-soft-needs", "value"),
        State("details-include-synergies", "value"),
        prevent_initial_call=True,
    )
    def run_details_simulation(n_clicks, node_name, include_soft_val,
                                include_synergies_val):
        if not n_clicks or not node_name:
            return no_update, no_update, no_update, no_update, no_update

        all_nodes = graph_manager.get_all_nodes()
        nodes_dict = {n.name: n for n in all_nodes}
        edges = graph_manager.get_edges()

        if node_name not in nodes_dict:
            return no_update, no_update, no_update, no_update, no_update

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_helps = bool(include_synergies_val and "include" in include_synergies_val)

        result = simulate_task_chain(
            target_name=node_name,
            nodes_dict=nodes_dict,
            edges=edges,
            include_soft=include_soft,
            include_helps=include_helps,
            n_simulations=10000,
        )

        samples = result['samples']
        stats = result['stats']

        # Build histogram
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
            margin=dict(l=40, r=20, t=30, b=40),
            xaxis_title="Hours",
            yaxis_title="Frequency",
            showlegend=False,
        )

        # Stats row
        stats_children = html.Div([
            _stat_card("P10", ConfigManager.format_time_friendly(stats['p10']), "success"),
            _stat_card("P50", ConfigManager.format_time_friendly(stats['p50']), "warning"),
            _stat_card("P90", ConfigManager.format_time_friendly(stats['p90']), "danger"),
            _stat_card("Mean", ConfigManager.format_time_friendly(stats['mean']), "info"),
            _stat_card("Std", ConfigManager.format_time_friendly(stats['std']), "secondary"),
        ], className="d-flex gap-2 flex-wrap")

        title = f"Time Distribution — {node_name}"

        return (
            fig,
            stats_children,
            {"display": "block"},    # show results
            {"display": "none"},     # hide empty
            title,
        )

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

    # --- Edit Node → Navigate to Nodes Tab ---
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

    # --- Subtask Name Click → Navigate to Canvas ---
    @app.callback(
        Output("search-node", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input({"type": "details-subtask-name", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def navigate_to_subtask(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
        return triggered["index"], "tab-canvas"

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
        Input("btn-details-add-node", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_node):
        if not n_clicks:
            return (no_update,) * 19

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": "None", "value": ""}] + \
                   [{"label": c, "value": c} for c in contexts]

        all_nodes = graph_manager.get_all_nodes()
        subtree = graph_manager.get_goal_subtree(selected_node) if selected_node else set()
        exclude = subtree | {selected_node} if selected_node else set()
        existing_opts = [{"label": n.name, "value": n.name}
                         for n in sorted(all_nodes, key=lambda n: n.name)
                         if n.name not in exclude]

        _ted = ConfigManager.get_time_estimate_defaults()

        return (
            True, type_opts, ctx_opts, [{"label": "None", "value": ""}],
            existing_opts, None, "", "", "", _ted.get('unit', 'weeks'),
            5, 5, 5,                        # value, interest, difficulty
            _ted.get('optimistic', 2),       # time-o
            _ted.get('expected', 4),         # time-m
            _ted.get('pessimistic', 6),      # time-p
            "", "",                          # context, subcontext
            "create",                        # mode
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
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_node, mode,
                      link_node, link_edge_type,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty,
                      time_o, time_m, time_p, time_unit):
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
            # Create mode
            if not name or not name.strip():
                return no_update, no_update, "Node name is required."
            if not node_type:
                return no_update, no_update, "Node type is required."

            multiplier = ConfigManager.get_time_multiplier(time_unit or "weeks")
            t_o = float(time_o or 0) * multiplier
            t_m = float(time_m or 0) * multiplier
            t_p = float(time_p or 0) * multiplier

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
            )

            try:
                graph_manager.add_node(new_node)
                graph_manager.add_edge(name.strip(), selected_node, EDGE_NEEDS_HARD)
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

    # --- Tooltip for details mini graph ---
    @app.callback(
        Output('hover-tooltip', 'children', allow_duplicate=True),
        Input('details-mini-graph', 'mouseoverNodeData'),
        prevent_initial_call=True,
    )
    def details_graph_tooltip(data):
        if not data:
            return ""
        node_id = data.get('id', data.get('label', ''))
        time_str = ConfigManager.format_time_friendly(data.get('time', 0))
        return [
            html.Div(html.Strong(data.get('label', node_id)),
                     style={"fontSize": "0.95rem", "marginBottom": "4px",
                            "borderBottom": "1px solid #495057", "paddingBottom": "4px"}),
            html.Div([html.Strong("Type: "), data.get('type', '')]),
            html.Div([html.Strong("Status: "), data.get('status', '')]),
            html.Div([html.Strong("Time: "), time_str]),
        ]


def _stat_card(label: str, value: str, color: str):
    """Build a small stat display card."""
    return html.Div([
        html.Small(label, className=f"text-{color}",
                   style={"fontSize": "0.7rem"}),
        html.Br(),
        html.Strong(value, style={"fontSize": "0.85rem"}),
    ], className="text-center", style={
        "backgroundColor": "#2b3035",
        "borderRadius": "6px",
        "padding": "6px 10px",
        "minWidth": "60px",
    })
