"""
Callback definitions for the Goals tab.
"""

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
from goals_layout import build_goal_card, build_subtasks_table

graph_manager = GraphManager()


def register_goal_callbacks(app):

    # --- Goals List Rendering ---
    @app.callback(
        Output("goals-list-container", "children"),
        Input("goals-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
        Input("goal-order-store", "data"),
        State("selected-goal-store", "data"),
    )
    def render_goals_list(refresh_trigger, active_tab, goal_order, selected_goal):
        all_nodes = graph_manager.get_all_nodes()
        goals = [n for n in all_nodes if n.type == "Goal"]

        if not goals:
            return html.Div(
                html.P("No goals yet.", className="text-muted"),
                className="text-center py-5"
            )

        priority_goals = ConfigManager.get_priority_goals()
        goal_map = {g.name: g for g in goals}
        priority_set = set(priority_goals[:3])

        # --- Priority section: top 3 in rank order ---
        cards = []
        for i, pg_name in enumerate(priority_goals[:3]):
            goal = goal_map.get(pg_name)
            if not goal:
                continue
            completion = graph_manager.get_goal_completion(goal.name)
            cards.append(build_goal_card(
                goal.name, goal.status, completion,
                completion.get("total", 0),
                is_selected=(goal.name == selected_goal),
                priority_rank=i + 1,
                show_order_buttons=False,
            ))

        # --- Non-priority section: sorted by goal-order-store ---
        non_priority = [g for g in goals if g.name not in priority_set]
        stored_order = goal_order or []
        stored_set = set(stored_order)
        # Goals in stored order first, then any new goals appended at end
        ordered_names = [n for n in stored_order if n in {g.name for g in non_priority}]
        remaining = [g.name for g in non_priority if g.name not in stored_set]
        ordered_non_priority = [goal_map[n] for n in (ordered_names + remaining) if n in goal_map]

        for i, goal in enumerate(ordered_non_priority):
            completion = graph_manager.get_goal_completion(goal.name)
            cards.append(build_goal_card(
                goal.name, goal.status, completion,
                completion.get("total", 0),
                is_selected=(goal.name == selected_goal),
                priority_rank=None,
                show_order_buttons=True,
                is_first=(i == 0),
                is_last=(i == len(ordered_non_priority) - 1),
            ))
        return cards

    # --- Goal Reordering ---
    @app.callback(
        Output("goal-order-store", "data"),
        Input({"type": "goal-up", "index": ALL}, "n_clicks"),
        Input({"type": "goal-down", "index": ALL}, "n_clicks"),
        State("goal-order-store", "data"),
        prevent_initial_call=True,
    )
    def reorder_goal(up_clicks, down_clicks, current_order):
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            return no_update
        if not any((v or 0) for v in ((up_clicks or []) + (down_clicks or []))):
            return no_update

        direction = triggered.get("type")  # "goal-up" or "goal-down"
        name = triggered.get("index")

        # Seed order from all currently rendered non-priority goals if goal not in store
        priority_goals = ConfigManager.get_priority_goals()
        priority_set = set(priority_goals[:3])
        all_nodes = graph_manager.get_all_nodes()
        non_priority_names = [n.name for n in all_nodes if n.type == "Goal" and n.name not in priority_set]

        order = list(current_order or [])
        # Ensure all non-priority goals are represented
        stored_set = set(order)
        for n in non_priority_names:
            if n not in stored_set:
                order.append(n)

        if name not in order:
            return order  # goal not found (edge case); return normalized order

        idx = order.index(name)
        if direction == "goal-up" and idx > 0:
            order[idx], order[idx - 1] = order[idx - 1], order[idx]
        elif direction == "goal-down" and idx < len(order) - 1:
            order[idx], order[idx + 1] = order[idx + 1], order[idx]

        return order

    # --- New Goal ---
    @app.callback(
        Output("selected-goal-store", "data", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-detail-empty", "style", allow_duplicate=True),
        Output("goal-detail-content", "style", allow_duplicate=True),
        Output("goal-name", "value", allow_duplicate=True),
        Output("goal-description", "value", allow_duplicate=True),
        Output("goal-value", "value", allow_duplicate=True),
        Output("goal-interest", "value", allow_duplicate=True),
        Output("goal-difficulty", "value", allow_duplicate=True),
        Output("goal-context", "options", allow_duplicate=True),
        Output("goal-context", "value", allow_duplicate=True),
        Output("goal-subcontext", "options", allow_duplicate=True),
        Output("goal-subcontext", "value", allow_duplicate=True),
        Output("goal-done-toggle", "value", allow_duplicate=True),
        Output("goal-priority-rank", "value", allow_duplicate=True),
        Output("goal-stats-section", "style", allow_duplicate=True),
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Output("goal-save-status", "children", allow_duplicate=True),
        Input("btn-new-goal", "n_clicks"),
        prevent_initial_call=True,
    )
    def create_new_goal(n_clicks):
        if not n_clicks:
            return (no_update,) * 18

        contexts = ConfigManager.get_contexts()
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]

        return (
            None,  # selected_goal_store — clear (new unsaved goal)
            dash.callback_context.triggered_id,  # refresh trigger
            {"display": "none"},  # hide empty state
            {"display": "flex", "flexDirection": "column", "height": "100%"},  # show detail
            "",  # name
            "",  # description
            5, 5, 5,  # value, interest, difficulty
            ctx_opts, "",  # context opts + value (None)
            [{"label": "None", "value": ""}], "",  # subcontext opts + value (None)
            [],  # done toggle
            "none",  # priority rank
            {"display": "none"},  # hide stats for new goal
            html.Div(
                html.P("Save the goal first, then add subtask nodes via the canvas.", className="text-muted"),
                className="text-center py-3"
            ),
            "",  # save status
        )

    # --- Goal Selection ---
    @app.callback(
        Output("selected-goal-store", "data", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-detail-empty", "style", allow_duplicate=True),
        Output("goal-detail-content", "style", allow_duplicate=True),
        Output("goal-name", "value", allow_duplicate=True),
        Output("goal-description", "value", allow_duplicate=True),
        Output("goal-value", "value", allow_duplicate=True),
        Output("goal-interest", "value", allow_duplicate=True),
        Output("goal-difficulty", "value", allow_duplicate=True),
        Output("goal-context", "options", allow_duplicate=True),
        Output("goal-context", "value", allow_duplicate=True),
        Output("goal-subcontext", "options", allow_duplicate=True),
        Output("goal-subcontext", "value", allow_duplicate=True),
        Output("goal-done-toggle", "value", allow_duplicate=True),
        Output("goal-priority-rank", "value", allow_duplicate=True),
        Output("goal-stats-section", "style", allow_duplicate=True),
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Output("goal-save-status", "children", allow_duplicate=True),
        Output("goal-progress-bar", "value", allow_duplicate=True),
        Output("goal-stats-text", "children", allow_duplicate=True),
        Input({"type": "goal-card", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_goal(n_clicks_list):
        if not any(n_clicks_list):
            return (no_update,) * 20

        triggered = ctx.triggered_id
        if not triggered:
            return (no_update,) * 20

        goal_name = triggered["index"]
        goal = graph_manager.get_node(goal_name)
        if not goal:
            return (no_update,) * 20

        contexts = ConfigManager.get_contexts()
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]
        subcontexts = ConfigManager.get_subcontexts().get(goal.context, []) if goal.context else []
        sub_opts = [{"label": "None", "value": ""}] + [{"label": s, "value": s} for s in subcontexts]

        priority_goals = ConfigManager.get_priority_goals()
        rank_value = "none"
        if goal_name in priority_goals:
            rank_value = str(priority_goals.index(goal_name) + 1)

        completion = graph_manager.get_goal_completion(goal_name)
        subtree = graph_manager.get_goal_subtree(goal_name)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))

        edges = graph_manager.get_edges()

        return (
            goal_name,  # selected_goal_store
            f"select-{goal_name}",  # refresh trigger
            {"display": "none"},  # hide empty state
            {"display": "flex", "flexDirection": "column", "height": "100%"},  # show detail
            goal.name,
            goal.description or "",
            goal.value, goal.interest, goal.difficulty,
            ctx_opts, goal.context or "",
            sub_opts, goal.subcontext or "",
            ["done"] if goal.status == "Done" else [],
            rank_value,  # priority rank dropdown
            {"display": "block"},  # show stats
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges),
            "",  # save status
            completion["pct"],  # progress bar
            f"{completion['done']}/{completion['total']} subtasks complete \u00b7 {round(completion['remaining_time'])}h remaining",
        )

    # --- Update Subcontext Options ---
    @app.callback(
        Output("goal-subcontext", "options"),
        Input("goal-context", "value"),
    )
    def update_goal_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = ConfigManager.get_subcontexts().get(context, [])
        return base + [{"label": s, "value": s} for s in subs]

    # --- Save Goal ---
    @app.callback(
        Output("selected-goal-store", "data", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-save-status", "children", allow_duplicate=True),
        Input("btn-goal-save", "n_clicks"),
        State("selected-goal-store", "data"),
        State("goal-name", "value"),
        State("goal-description", "value"),
        State("goal-value", "value"),
        State("goal-interest", "value"),
        State("goal-difficulty", "value"),
        State("goal-context", "value"),
        State("goal-subcontext", "value"),
        State("goal-done-toggle", "value"),
        prevent_initial_call=True,
    )
    def save_goal(n_clicks, selected_goal, name, description, value, interest, difficulty,
                  context, subcontext, done_toggle):
        if not n_clicks or not name or not name.strip():
            return no_update, no_update, "Goal name is required."

        name = name.strip()
        description = (description or "").strip()
        status = "Done" if done_toggle and "done" in done_toggle else "Open"

        node = graph_manager.get_node(selected_goal) if selected_goal else None

        goal_node = Node(
            name=name,
            type="Goal",
            description=description,
            value=value or 5,
            time_o=node.time_o if node else 0.0,
            time_m=node.time_m if node else 0.0,
            time_p=node.time_p if node else 0.0,
            interest=interest or 5,
            difficulty=difficulty or 5,
            status=status,
            context=context or None,
            subcontext=(subcontext or "").strip() or None,
        )

        try:
            if selected_goal is None:
                graph_manager.add_node(goal_node)
            else:
                goal_node.name = selected_goal
                if name != selected_goal:
                    graph_manager.delete_node(selected_goal)
                    graph_manager.add_node(goal_node)
                    priority_goals = ConfigManager.get_priority_goals()
                    if selected_goal in priority_goals:
                        priority_goals = [name if g == selected_goal else g for g in priority_goals]
                        ConfigManager.set_priority_goals(priority_goals)
                    goal_node.name = name
                else:
                    graph_manager.update_node(goal_node)
        except ValueError as e:
            return no_update, no_update, str(e)

        return name, f"save-{name}", "Saved."

    # --- Priority Rank Change ---
    @app.callback(
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-save-status", "children", allow_duplicate=True),
        Input("goal-priority-rank", "value"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def set_priority_rank(rank_value, selected_goal):
        if not selected_goal:
            return no_update, no_update

        priority_goals = ConfigManager.get_priority_goals()

        if selected_goal in priority_goals:
            priority_goals.remove(selected_goal)

        if rank_value and rank_value != "none":
            rank_idx = int(rank_value) - 1
            rank_idx = min(rank_idx, len(priority_goals))
            priority_goals.insert(rank_idx, selected_goal)

        ConfigManager.set_priority_goals(priority_goals)
        return f"rank-{selected_goal}-{rank_value}", ""

    # --- Subtask Name Click → Navigate to Canvas ---
    @app.callback(
        Output("search-node", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input({"type": "subtask-name", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def navigate_to_subtask(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
        return triggered["index"], "tab-canvas"

    # --- Delete Goal ---
    @app.callback(
        Output("modal-goal-confirm-delete", "is_open", allow_duplicate=True),
        Input("btn-goal-delete", "n_clicks"),
        Input("btn-goal-delete-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_goal_delete_modal(delete_clicks, cancel_clicks):
        trigger = ctx.triggered_id
        if trigger == "btn-goal-delete" and delete_clicks:
            return True
        return False

    @app.callback(
        Output("selected-goal-store", "data", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-detail-empty", "style", allow_duplicate=True),
        Output("goal-detail-content", "style", allow_duplicate=True),
        Output("modal-goal-confirm-delete", "is_open", allow_duplicate=True),
        Input("btn-goal-delete-confirm", "n_clicks"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def delete_goal(confirm_clicks, selected_goal):
        if not confirm_clicks or not selected_goal:
            return (no_update,) * 5

        priority_goals = ConfigManager.get_priority_goals()
        if selected_goal in priority_goals:
            priority_goals.remove(selected_goal)
            ConfigManager.set_priority_goals(priority_goals)

        graph_manager.delete_node(selected_goal)
        return (
            None,
            f"delete-{selected_goal}",
            {"display": "block"},
            {"display": "none"},
            False,
        )

    # --- Focus Button ---
    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input("btn-goal-focus", "n_clicks"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def focus_on_canvas(n_clicks, selected_goal):
        if not n_clicks or not selected_goal:
            return no_update, no_update
        return selected_goal, "tab-canvas"

    # --- Clear Focus ---
    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Input("btn-clear-focus", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_focus(n_clicks):
        if n_clicks:
            return None
        return no_update

    # --- Mini Dependency Graph ---
    @app.callback(
        Output("goal-mini-graph", "elements"),
        Input("selected-goal-store", "data"),
        Input("goals-refresh-trigger", "data"),
    )
    def update_goal_mini_graph(selected_goal, _refresh):
        if not selected_goal:
            return []

        subtree = graph_manager.get_goal_subtree(selected_goal)
        node_names = subtree | {selected_goal}

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
                    'color': colors.get(node.status, '#6c757d'),
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

    # --- Add Node Modal: Open ---
    @app.callback(
        Output("modal-goal-add-node", "is_open", allow_duplicate=True),
        Output("goal-add-type", "options"),
        Output("goal-add-context", "options", allow_duplicate=True),
        Output("goal-add-subcontext", "options", allow_duplicate=True),
        Output("goal-add-existing-dropdown", "options"),
        Output("goal-add-name", "value"),
        Output("goal-add-desc", "value"),
        Output("goal-add-save-status", "children", allow_duplicate=True),
        Input("btn-goal-add-node", "n_clicks"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_goal):
        if not n_clicks:
            return (no_update,) * 8

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]

        # Build existing node options (exclude goal itself and its subtree)
        all_nodes = graph_manager.get_all_nodes()
        subtree = graph_manager.get_goal_subtree(selected_goal) if selected_goal else set()
        exclude = subtree | {selected_goal} if selected_goal else set()
        existing_opts = [{"label": n.name, "value": n.name}
                        for n in sorted(all_nodes, key=lambda n: n.name)
                        if n.name not in exclude]

        return True, type_opts, ctx_opts, [{"label": "None", "value": ""}], existing_opts, "", "", ""

    # --- Add Node Modal: Toggle mode (create vs link) ---
    @app.callback(
        Output("goal-add-create-section", "style"),
        Output("goal-add-link-section", "style"),
        Input("goal-add-mode", "value"),
    )
    def toggle_add_mode(mode):
        if mode == "link":
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Add Node Modal: Update subcontexts ---
    @app.callback(
        Output("goal-add-subcontext", "options"),
        Input("goal-add-context", "value"),
    )
    def update_add_node_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = ConfigManager.get_subcontexts().get(context, [])
        return base + [{"label": s, "value": s} for s in subs]

    # --- Add Node Modal: Cancel ---
    @app.callback(
        Output("modal-goal-add-node", "is_open", allow_duplicate=True),
        Input("btn-goal-add-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_add_node_modal(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Add Node Modal: Save ---
    @app.callback(
        Output("modal-goal-add-node", "is_open", allow_duplicate=True),
        Output("goal-add-save-status", "children", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Input("btn-goal-add-save", "n_clicks"),
        State("selected-goal-store", "data"),
        State("goal-add-mode", "value"),
        State("goal-add-existing-dropdown", "value"),
        State("goal-add-name", "value"),
        State("goal-add-type", "value"),
        State("goal-add-context", "value"),
        State("goal-add-subcontext", "value"),
        State("goal-add-desc", "value"),
        State("goal-add-value", "value"),
        State("goal-add-interest", "value"),
        State("goal-add-difficulty", "value"),
        State("goal-add-time-o", "value"),
        State("goal-add-time-m", "value"),
        State("goal-add-time-p", "value"),
        State("goal-add-edge-type", "value"),
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_goal, mode, existing_node,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty, time_o, time_m, time_p,
                      edge_type):
        if not n_clicks or not selected_goal:
            return (no_update,) * 4

        edge_type = edge_type or EDGE_NEEDS_HARD

        if mode == "link":
            # Link existing node
            if not existing_node:
                return no_update, "Select a node to link.", no_update, no_update
            node_name = existing_node
        else:
            # Create new node
            if not name or not name.strip():
                return no_update, "Node name is required.", no_update, no_update
            node_name = name.strip()

            new_node = Node(
                name=node_name,
                type=node_type or "Learn",
                description=(desc or "").strip(),
                value=value or 5,
                time_o=float(time_o or 0),
                time_m=float(time_m or 0),
                time_p=float(time_p or 0),
                interest=interest or 5,
                difficulty=difficulty or 5,
                status="Open",
                context=context or None,
                subcontext=(subcontext or "").strip() or None,
            )

            try:
                graph_manager.add_node(new_node)
            except ValueError as e:
                return no_update, str(e), no_update, no_update

        # Add edge: node_name → selected_goal (node_name is a dependency of the goal)
        try:
            graph_manager.add_edge(node_name, selected_goal, edge_type)
        except (ValueError, Exception) as e:
            return no_update, str(e), no_update, no_update

        # Rebuild subtasks table
        subtree = graph_manager.get_goal_subtree(selected_goal)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        return (
            False,  # close modal
            "",  # clear status
            f"add-node-{node_name}",  # refresh trigger
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges),
        )
