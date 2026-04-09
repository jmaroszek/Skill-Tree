"""
Callback definitions for the Goals tab.
"""

import os
import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, EDGE_RESOURCE
from goals_layout import build_goal_card, build_subtasks_table
from callback_helpers import serialize_links, parse_links, render_link_rows, spawn_local_file_picker, strip_gdrive_prefix, expand_gdrive_prefix

graph_manager = GraphManager()


def register_goal_callbacks(app):

    # --- Goals List Rendering ---
    @app.callback(
        Output("goals-list-container", "children"),
        Input("goals-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
        Input("goal-order-store", "data"),
        Input("goal-include-soft-needs", "value"),
        Input("goal-include-transitive", "value"),
        Input("goal-search-input", "value"),
        Input("goal-filter-context", "value"),
        Input("goal-filter-subcontext", "value"),
        Input("goal-filter-value", "value"),
        Input("goal-filter-interest", "value"),
        Input("goal-filter-difficulty", "value"),
        Input("goal-sort-mode", "value"),
        State("selected-goal-store", "data"),
    )
    def render_goals_list(refresh_trigger, active_tab, goal_order, include_soft_value, include_transitive_value,
                          search_val, f_context, f_subcontext, f_min_value, f_min_interest, f_max_difficulty,
                          sort_mode, selected_goal):
        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)

        all_nodes = graph_manager.get_all_nodes()
        goals = [n for n in all_nodes if n.type == "Goal"]

        if not goals:
            return html.Div(
                html.P("No goals yet.", className="text-muted"),
                className="text-center py-5"
            )

        # Apply search filter
        if search_val and search_val.strip():
            search_lower = search_val.strip().lower()
            goals = [g for g in goals if search_lower in g.name.lower()]

        # Apply context/subcontext filters
        if f_context and f_context != "All":
            goals = [g for g in goals if g.context == f_context]
        if f_subcontext and f_subcontext != "All":
            goals = [g for g in goals if g.subcontext == f_subcontext]

        # Apply rating filters
        if f_min_value and f_min_value > 1:
            goals = [g for g in goals if g.value >= f_min_value]
        if f_min_interest and f_min_interest > 1:
            goals = [g for g in goals if g.interest >= f_min_interest]
        if f_max_difficulty and f_max_difficulty < 10:
            goals = [g for g in goals if g.difficulty <= f_max_difficulty]

        if not goals:
            return html.Div(
                html.P("No goals match the current filters.", className="text-muted"),
                className="text-center py-5"
            )

        priority_goals = ConfigManager.get_priority_goals()
        goal_map = {g.name: g for g in goals}
        priority_set = set(priority_goals[:3])

        # Pre-compute completion for sorting
        completion_cache = {}
        for g in goals:
            completion_cache[g.name] = graph_manager.get_goal_completion(g.name, include_soft=include_soft, include_transitive=include_transitive)

        # --- Priority section: top 3 in rank order (always shown first) ---
        cards = []
        for i, pg_name in enumerate(priority_goals[:3]):
            goal = goal_map.get(pg_name)
            if not goal:
                continue
            completion = completion_cache[goal.name]
            cards.append(build_goal_card(
                goal.name, goal.status, completion,
                completion.get("total", 0),
                is_selected=(goal.name == selected_goal),
                priority_rank=i + 1,
                show_order_buttons=False,
            ))

        # --- Non-priority section ---
        non_priority = [g for g in goals if g.name not in priority_set]

        sort_mode = sort_mode or "manual"
        if sort_mode == "alpha-asc":
            non_priority.sort(key=lambda g: g.name.lower())
        elif sort_mode == "alpha-desc":
            non_priority.sort(key=lambda g: g.name.lower(), reverse=True)
        elif sort_mode == "time-asc":
            non_priority.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0))
        elif sort_mode == "time-desc":
            non_priority.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0), reverse=True)
        else:
            # Manual order from goal-order-store
            stored_order = goal_order or []
            stored_set = set(stored_order)
            ordered_names = [n for n in stored_order if n in {g.name for g in non_priority}]
            remaining = [g.name for g in non_priority if g.name not in stored_set]
            non_priority = [goal_map[n] for n in (ordered_names + remaining) if n in goal_map]

        show_order_buttons = (sort_mode or "manual") == "manual"
        for i, goal in enumerate(non_priority):
            completion = completion_cache[goal.name]
            cards.append(build_goal_card(
                goal.name, goal.status, completion,
                completion.get("total", 0),
                is_selected=(goal.name == selected_goal),
                priority_rank=None,
                show_order_buttons=show_order_buttons,
                is_first=(i == 0),
                is_last=(i == len(non_priority) - 1),
            ))
        return cards

    # --- Goal Reordering (up/down buttons + drag-and-drop) ---
    @app.callback(
        Output("goal-order-store", "data"),
        Input({"type": "goal-up", "index": ALL}, "n_clicks"),
        Input({"type": "goal-down", "index": ALL}, "n_clicks"),
        Input("goal-drag-order-input", "value"),
        State("goal-order-store", "data"),
        prevent_initial_call=True,
    )
    def reorder_goal(up_clicks, down_clicks, drag_order_json, current_order):
        import json as _json
        trigger_id = ctx.triggered_id

        # --- Drag-and-drop reorder ---
        if trigger_id == "goal-drag-order-input" and drag_order_json:
            try:
                new_order = _json.loads(drag_order_json)
                if isinstance(new_order, list) and new_order:
                    # Filter to non-priority goals only
                    priority_goals = ConfigManager.get_priority_goals()
                    priority_set = set(priority_goals[:3])
                    return [n for n in new_order if n not in priority_set]
            except (ValueError, TypeError):
                pass
            return no_update

        # --- Up/down button reorder (fallback) ---
        triggered = trigger_id
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

    # --- Autocomplete datalist for goals search ---
    @app.callback(
        Output("goal-search-datalist", "children"),
        Input("goals-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
    )
    def populate_goal_search_datalist(refresh_trigger, active_tab):
        from dash import html as _html
        all_nodes = graph_manager.get_all_nodes()
        return [_html.Option(value=n.name) for n in all_nodes if n.type == "Goal"]

    # --- Goal Filters Toggle ---
    @app.callback(
        Output("goal-filters-collapse", "is_open"),
        Output("goal-filter-context", "options"),
        Input("btn-goal-filters-toggle", "n_clicks"),
        State("goal-filters-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_goal_filters(n_clicks, is_open):
        if not n_clicks:
            return no_update, no_update
        contexts = ConfigManager.get_contexts()
        ctx_opts = [{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in contexts]
        return not is_open, ctx_opts

    # --- Goal Filter: Update subcontexts when context changes ---
    @app.callback(
        Output("goal-filter-subcontext", "options"),
        Output("goal-filter-subcontext", "value"),
        Input("goal-filter-context", "value"),
    )
    def update_goal_filter_subcontexts(context):
        base = [{"label": "All", "value": "All"}]
        if not context or context == "All":
            return base, "All"
        subs = ConfigManager.get_subcontexts().get(context, [])
        return base + [{"label": s, "value": s} for s in subs], "All"

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
        # Relationship dropdowns
        Output("goal-edge-needs-hard", "options", allow_duplicate=True),
        Output("goal-edge-needs-hard", "value", allow_duplicate=True),
        Output("goal-edge-needs-soft", "options", allow_duplicate=True),
        Output("goal-edge-needs-soft", "value", allow_duplicate=True),
        Output("goal-edge-supports-hard", "options", allow_duplicate=True),
        Output("goal-edge-supports-hard", "value", allow_duplicate=True),
        Output("goal-edge-supports-soft", "options", allow_duplicate=True),
        Output("goal-edge-supports-soft", "value", allow_duplicate=True),
        Output("goal-edge-helps", "options", allow_duplicate=True),
        Output("goal-edge-helps", "value", allow_duplicate=True),
        # External resource stores
        Output("goal-obsidian-links-store", "data", allow_duplicate=True),
        Output("goal-drive-links-store", "data", allow_duplicate=True),
        Output("goal-website-links-store", "data", allow_duplicate=True),
        Input("btn-new-goal", "n_clicks"),
        prevent_initial_call=True,
    )
    def create_new_goal(n_clicks):
        if not n_clicks:
            return (no_update,) * 31

        contexts = ConfigManager.get_contexts()
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]

        all_nodes = graph_manager.get_all_nodes()
        all_node_opts = [{"label": n.name, "value": n.name} for n in sorted(all_nodes, key=lambda n: n.name)]

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
            # Relationships (empty)
            all_node_opts, [], all_node_opts, [], all_node_opts, [],
            all_node_opts, [], all_node_opts, [],
            # External resources (empty)
            [''], [''], [''],
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
        # Relationship dropdowns
        Output("goal-edge-needs-hard", "options", allow_duplicate=True),
        Output("goal-edge-needs-hard", "value", allow_duplicate=True),
        Output("goal-edge-needs-soft", "options", allow_duplicate=True),
        Output("goal-edge-needs-soft", "value", allow_duplicate=True),
        Output("goal-edge-supports-hard", "options", allow_duplicate=True),
        Output("goal-edge-supports-hard", "value", allow_duplicate=True),
        Output("goal-edge-supports-soft", "options", allow_duplicate=True),
        Output("goal-edge-supports-soft", "value", allow_duplicate=True),
        Output("goal-edge-helps", "options", allow_duplicate=True),
        Output("goal-edge-helps", "value", allow_duplicate=True),
        # External resource stores
        Output("goal-obsidian-links-store", "data", allow_duplicate=True),
        Output("goal-drive-links-store", "data", allow_duplicate=True),
        Output("goal-website-links-store", "data", allow_duplicate=True),
        Input({"type": "goal-card", "index": ALL}, "n_clicks"),
        State("goal-include-soft-needs", "value"),
        State("goal-include-transitive", "value"),
        prevent_initial_call=True,
    )
    def select_goal(n_clicks_list, include_soft_value, include_transitive_value):
        if not any(n_clicks_list):
            return (no_update,) * 33

        triggered = ctx.triggered_id
        if not triggered:
            return (no_update,) * 33

        goal_name = triggered["index"]
        goal = graph_manager.get_node(goal_name)
        if not goal:
            return (no_update,) * 33

        contexts = ConfigManager.get_contexts()
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]
        subcontexts = ConfigManager.get_subcontexts().get(goal.context, []) if goal.context else []
        sub_opts = [{"label": "None", "value": ""}] + [{"label": s, "value": s} for s in subcontexts]

        priority_goals = ConfigManager.get_priority_goals()
        rank_value = "none"
        if goal_name in priority_goals:
            rank_value = str(priority_goals.index(goal_name) + 1)

        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)

        completion = graph_manager.get_goal_completion(goal_name, include_soft=include_soft, include_transitive=include_transitive)
        edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) if include_soft else (EDGE_NEEDS_HARD,)
        subtree = graph_manager.get_goal_subtree(goal_name, edge_types=edge_types)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))

        edges = graph_manager.get_edges()

        # Build relationship dropdown options and current values
        all_nodes = graph_manager.get_all_nodes()
        all_node_opts = [{"label": n.name, "value": n.name} for n in sorted(all_nodes, key=lambda n: n.name) if n.name != goal_name]

        needs_hard_val = [e['source'] for e in edges if e['target'] == goal_name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_val = [e['source'] for e in edges if e['target'] == goal_name and e['type'] == EDGE_NEEDS_SOFT]
        supports_hard_val = [e['target'] for e in edges if e['source'] == goal_name and e['type'] == EDGE_NEEDS_HARD]
        supports_soft_val = [e['target'] for e in edges if e['source'] == goal_name and e['type'] == EDGE_NEEDS_SOFT]
        helps_val = [e['target'] for e in edges if e['source'] == goal_name and e['type'] == EDGE_HELPS] + \
                    [e['source'] for e in edges if e['target'] == goal_name and e['type'] == EDGE_HELPS]

        # Parse external resource links
        obs_links = parse_links(goal.obsidian_path) or ['']
        drive_links = parse_links(goal.google_drive_path) or ['']
        website_links = parse_links(goal.website) or ['']

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
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges,
                                 goal_name=goal_name, include_soft=include_soft,
                                 include_transitive=include_transitive),
            "",  # save status
            completion["pct"],  # progress bar
            f"{completion['done']}/{completion['total']} subtasks complete \u00b7 {ConfigManager.format_time_friendly(completion['remaining_time'])} remaining",
            # Relationships
            all_node_opts, needs_hard_val,
            all_node_opts, needs_soft_val,
            all_node_opts, supports_hard_val,
            all_node_opts, supports_soft_val,
            all_node_opts, helps_val,
            # External resources
            obs_links, drive_links, website_links,
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
        Output("modal-goal-confirm-rename", "is_open", allow_duplicate=True),
        Output("goal-rename-pending", "data"),
        Output("goal-rename-modal-body", "children"),
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
        State("goal-edge-needs-hard", "value"),
        State("goal-edge-needs-soft", "value"),
        State("goal-edge-supports-hard", "value"),
        State("goal-edge-supports-soft", "value"),
        State("goal-edge-helps", "value"),
        State({'type': 'goal-obsidian-link', 'index': ALL}, 'value'),
        State({'type': 'goal-drive-link', 'index': ALL}, 'value'),
        State({'type': 'goal-website-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def save_goal(n_clicks, selected_goal, name, description, value, interest, difficulty,
                  context, subcontext, done_toggle,
                  e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                  obs_link_values, drive_link_values, website_link_values):
        if not n_clicks or not name or not name.strip():
            return no_update, no_update, "Goal name is required.", no_update, no_update, no_update

        name = name.strip()
        description = (description or "").strip()
        status = "Done" if done_toggle and "done" in done_toggle else "Open"

        existing = graph_manager.get_node(selected_goal) if selected_goal else None

        obs_path = serialize_links(obs_link_values)
        drive_path = serialize_links(drive_link_values)
        website_path = serialize_links(website_link_values)

        goal_node = Node(
            name=name,
            type="Goal",
            description=description,
            value=value or 5,
            time_o=existing.time_o if existing else 0.0,
            time_m=existing.time_m if existing else 0.0,
            time_p=existing.time_p if existing else 0.0,
            interest=interest or 5,
            difficulty=difficulty or 5,
            status=status,
            context=context or None,
            subcontext=(subcontext or "").strip() or None,
            obsidian_path=obs_path,
            google_drive_path=drive_path,
            website=website_path,
        )

        try:
            if selected_goal is None:
                graph_manager.add_node(goal_node)
                # Sync edges for the new goal
                graph_manager.sync_edges(
                    name,
                    e_needs_h or [], e_needs_s or [],
                    e_supp_h or [], e_supp_s or [],
                    e_helps or [],
                )
                return name, f"save-{name}", "Saved.", False, None, ""
            elif name != selected_goal:
                # Name changed — ask for confirmation before overwriting
                pending = {
                    "old_name": selected_goal,
                    "new_name": name,
                    "description": description,
                    "value": value or 5,
                    "interest": interest or 5,
                    "difficulty": difficulty or 5,
                    "context": context or None,
                    "subcontext": (subcontext or "").strip() or None,
                    "status": status,
                    "obsidian_path": obs_path,
                    "google_drive_path": drive_path,
                    "website": website_path,
                    "e_needs_h": e_needs_h or [],
                    "e_needs_s": e_needs_s or [],
                    "e_supp_h": e_supp_h or [],
                    "e_supp_s": e_supp_s or [],
                    "e_helps": e_helps or [],
                }
                modal_body = f'Would you like to rename "{selected_goal}" to "{name}"?'
                return no_update, no_update, no_update, True, pending, modal_body
            else:
                goal_node.name = selected_goal
                graph_manager.update_node(goal_node)
                # Sync edges for the existing goal
                graph_manager.sync_edges(
                    selected_goal,
                    e_needs_h or [], e_needs_s or [],
                    e_supp_h or [], e_supp_s or [],
                    e_helps or [],
                )
                return name, f"save-{name}", "Saved.", False, None, ""
        except ValueError as e:
            return no_update, no_update, str(e), False, None, ""

    # --- Rename Goal: Confirm ---
    @app.callback(
        Output("selected-goal-store", "data", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Output("goal-save-status", "children", allow_duplicate=True),
        Output("modal-goal-confirm-rename", "is_open", allow_duplicate=True),
        Output("goal-rename-pending", "data", allow_duplicate=True),
        Input("btn-goal-rename-confirm", "n_clicks"),
        State("goal-rename-pending", "data"),
        prevent_initial_call=True,
    )
    def confirm_rename_goal(n_clicks, pending):
        if not n_clicks or not pending:
            return (no_update,) * 5

        old_name = pending["old_name"]
        new_name = pending["new_name"]
        existing = graph_manager.get_node(old_name)

        goal_node = Node(
            name=new_name,
            type="Goal",
            description=pending.get("description", ""),
            value=pending.get("value") or 5,
            time_o=existing.time_o if existing else 0.0,
            time_m=existing.time_m if existing else 0.0,
            time_p=existing.time_p if existing else 0.0,
            interest=pending.get("interest") or 5,
            difficulty=pending.get("difficulty") or 5,
            status=pending.get("status", "Open"),
            context=pending.get("context") or None,
            subcontext=pending.get("subcontext") or None,
            obsidian_path=pending.get("obsidian_path"),
            google_drive_path=pending.get("google_drive_path"),
            website=pending.get("website"),
        )

        try:
            graph_manager.rename_node(old_name, new_name)
            graph_manager.update_node(goal_node)
            # Sync edges after rename
            graph_manager.sync_edges(
                new_name,
                pending.get("e_needs_h", []), pending.get("e_needs_s", []),
                pending.get("e_supp_h", []), pending.get("e_supp_s", []),
                pending.get("e_helps", []),
            )
            priority_goals = ConfigManager.get_priority_goals()
            if old_name in priority_goals:
                priority_goals = [new_name if g == old_name else g for g in priority_goals]
                ConfigManager.set_priority_goals(priority_goals)
        except ValueError as e:
            return no_update, no_update, str(e), True, pending

        return new_name, f"save-{new_name}", "Saved.", False, None

    # --- Rename Goal: Cancel ---
    @app.callback(
        Output("modal-goal-confirm-rename", "is_open", allow_duplicate=True),
        Input("btn-goal-rename-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_rename_goal(n_clicks):
        if n_clicks:
            return False
        return no_update

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
                    'color': (
                        colors.get('Done', '#198754') if node.type == 'Goal' and node.status == 'Done'
                        else colors.get('Blocked', '#dc3545') if node.type == 'Goal' and node.status == 'Blocked'
                        else colors.get('Goal', '#ffc107') if node.type == 'Goal'
                        else colors.get('Done', '#198754') if node.type == 'Resource' and node.status == 'Done'
                        else colors.get('Blocked', '#dc3545') if node.type == 'Resource' and node.status == 'Blocked'
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

    # --- Subtask × Click: Open Confirmation Modal ---
    @app.callback(
        Output("modal-subtask-remove-confirm", "is_open", allow_duplicate=True),
        Output("subtask-remove-pending", "data"),
        Output("subtask-remove-modal-body", "children"),
        Input({"type": "subtask-remove", "index": ALL}, "n_clicks"),
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
                html.Strong(node_name),
                '?',
            ]),
            html.Ul([
                html.Li([html.Strong("Remove from Goal"), " — removes it from this goal's subtask list, but keeps the node in the database and on the canvas."]),
                html.Li([html.Strong("Delete Node"), " — permanently deletes the node and all its edges from the database."]),
            ]),
        ])
        return True, node_name, body

    # --- Cancel Modal ---
    @app.callback(
        Output("modal-subtask-remove-confirm", "is_open", allow_duplicate=True),
        Input("btn-subtask-remove-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_subtask_remove(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Confirm: Remove Edge Only ---
    @app.callback(
        Output("modal-subtask-remove-confirm", "is_open", allow_duplicate=True),
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-subtask-remove-edge", "n_clicks"),
        State("subtask-remove-pending", "data"),
        State("selected-goal-store", "data"),
        State("goal-include-soft-needs", "value"),
        State("goal-include-transitive", "value"),
        prevent_initial_call=True,
    )
    def confirm_remove_subtask_edge(n_clicks, node_name, selected_goal, include_soft_value, include_transitive_value):
        if not n_clicks or not node_name or not selected_goal:
            return no_update, no_update, no_update

        edges = graph_manager.get_edges()
        for e in edges:
            if e['source'] == node_name and e['target'] == selected_goal and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
                graph_manager.remove_edge(node_name, selected_goal, e['type'])

        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)
        subtree = graph_manager.get_goal_subtree(selected_goal)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        return (
            False,
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges,
                                 goal_name=selected_goal, include_soft=include_soft,
                                 include_transitive=include_transitive),
            f"remove-subtask-{node_name}",
        )

    # --- Confirm: Delete Node Entirely ---
    @app.callback(
        Output("modal-subtask-remove-confirm", "is_open", allow_duplicate=True),
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Output("goals-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-subtask-delete-node", "n_clicks"),
        State("subtask-remove-pending", "data"),
        State("selected-goal-store", "data"),
        State("goal-include-soft-needs", "value"),
        State("goal-include-transitive", "value"),
        prevent_initial_call=True,
    )
    def confirm_delete_subtask_node(n_clicks, node_name, selected_goal, include_soft_value, include_transitive_value):
        if not n_clicks or not node_name or not selected_goal:
            return no_update, no_update, no_update

        graph_manager.delete_node(node_name)

        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)
        subtree = graph_manager.get_goal_subtree(selected_goal)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        return (
            False,
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges,
                                 goal_name=selected_goal, include_soft=include_soft,
                                 include_transitive=include_transitive),
            f"delete-subtask-{node_name}",
        )

    # --- Subtasks Filter Toggles ---
    @app.callback(
        Output("goal-subtasks-table-container", "children", allow_duplicate=True),
        Output("goal-progress-bar", "value", allow_duplicate=True),
        Output("goal-stats-text", "children", allow_duplicate=True),
        Input("goal-include-soft-needs", "value"),
        Input("goal-include-transitive", "value"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_subtask_filters(include_soft_value, include_transitive_value, selected_goal):
        if not selected_goal:
            return no_update, no_update, no_update

        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)
        # Use the same edge types as get_goal_completion for consistency
        edge_types = (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) if include_soft else (EDGE_NEEDS_HARD,)
        subtree = graph_manager.get_goal_subtree(selected_goal, edge_types=edge_types)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()
        completion = graph_manager.get_goal_completion(selected_goal, include_soft=include_soft, include_transitive=include_transitive)

        return (
            build_subtasks_table(
                subtask_nodes, graph_manager=graph_manager, edges=edges,
                goal_name=selected_goal, include_soft=include_soft,
                include_transitive=include_transitive,
            ),
            completion["pct"],
            f"{completion['done']}/{completion['total']} subtasks complete \u00b7 {ConfigManager.format_time_friendly(completion['remaining_time'])} remaining",
        )

    # --- Add Node Modal: Open ---
    @app.callback(
        Output("modal-goal-add-node", "is_open", allow_duplicate=True),
        Output("goal-add-type", "options"),
        Output("goal-add-context", "options", allow_duplicate=True),
        Output("goal-add-subcontext", "options", allow_duplicate=True),
        Output("goal-add-existing-dropdown", "options"),
        Output("goal-add-existing-dropdown", "value"),
        Output("goal-add-name", "value"),
        Output("goal-add-desc", "value"),
        Output("goal-add-save-status", "children", allow_duplicate=True),
        Output("goal-node-time-unit", "value"),
        Output("goal-add-needs-hard", "options"),
        Output("goal-add-needs-soft", "options"),
        Output("goal-add-supports-hard", "options"),
        Output("goal-add-supports-soft", "options"),
        Output("goal-add-helps", "options"),
        Output("goal-add-edge-resources", "options"),
        Output("goal-add-needs-hard", "value"),
        Output("goal-add-needs-soft", "value"),
        Output("goal-add-supports-hard", "value"),
        Output("goal-add-supports-soft", "value"),
        Output("goal-add-helps", "value"),
        Output("goal-add-edge-resources", "value"),
        Output("goal-add-obsidian-store", "data"),
        Output("goal-add-drive-store", "data"),
        Output("goal-add-website-store", "data"),
        Output("goal-add-value", "value"),
        Output("goal-add-interest", "value"),
        Output("goal-add-difficulty", "value"),
        Output("goal-add-time-o", "value"),
        Output("goal-add-time-m", "value"),
        Output("goal-add-time-p", "value"),
        Output("goal-add-context", "value", allow_duplicate=True),
        Output("goal-add-subcontext", "value", allow_duplicate=True),
        Output("goal-add-mode", "value"),
        Input("btn-goal-add-node", "n_clicks"),
        State("selected-goal-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_goal):
        if not n_clicks:
            return (no_update,) * 34

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]

        # Build node options (all nodes, excluding goal and its subtree)
        all_nodes = graph_manager.get_all_nodes()
        subtree = graph_manager.get_goal_subtree(selected_goal) if selected_goal else set()
        exclude = subtree | {selected_goal} if selected_goal else set()
        existing_opts = [{"label": n.name, "value": n.name}
                         for n in sorted(all_nodes, key=lambda n: n.name)
                         if n.name not in exclude]
        all_node_opts = [{"label": n.name, "value": n.name}
                         for n in sorted(all_nodes, key=lambda n: n.name)]
        resource_opts = [{"label": n.name, "value": n.name}
                         for n in sorted(all_nodes, key=lambda n: n.name)
                         if n.type == 'Resource']

        return (
            True, type_opts, ctx_opts, [{"label": "None", "value": ""}],
            existing_opts, None, "", "", "", "weeks",
            all_node_opts, all_node_opts, all_node_opts, all_node_opts, all_node_opts, resource_opts,
            [], [], [], [], [], [],
            [''], [''], [''],
            5, 5, 5,          # value, interest, difficulty
            2, 4, 6,          # time-o, time-m, time-p (in weeks)
            "", "",           # context, subcontext
            "create",         # mode
        )

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

    # --- Add Node Modal: Link Row Renderers ---
    @app.callback(
        Output('goal-add-obsidian-container', 'children'),
        Input('goal-add-obsidian-store', 'data'),
    )
    def render_goal_add_obsidian(links):
        return render_link_rows(links, 'goal-add-obsidian-link', has_browse=True)

    @app.callback(
        Output('goal-add-drive-container', 'children'),
        Input('goal-add-drive-store', 'data'),
    )
    def render_goal_add_drive(links):
        return render_link_rows(strip_gdrive_prefix(links), 'goal-add-drive-link', has_browse=True)

    @app.callback(
        Output('goal-add-website-container', 'children'),
        Input('goal-add-website-store', 'data'),
    )
    def render_goal_add_website(links):
        return render_link_rows(links, 'goal-add-website-link', has_browse=False)

    # --- Add Node Modal: Link Add/Remove/Browse ---
    @app.callback(
        Output('goal-add-obsidian-store', 'data', allow_duplicate=True),
        Input('btn-goal-add-obsidian-add', 'n_clicks'),
        Input({'type': 'btn-goal-add-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-goal-add-obsidian-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-obsidian-link', 'index': ALL}, 'value'),
        State('goal-add-obsidian-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_add_obsidian(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-add-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-goal-add-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-goal-add-obsidian-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
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
                else:
                    return no_update
        return links

    @app.callback(
        Output('goal-add-drive-store', 'data', allow_duplicate=True),
        Input('btn-goal-add-drive-add', 'n_clicks'),
        Input({'type': 'btn-goal-add-drive-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-goal-add-drive-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-drive-link', 'index': ALL}, 'value'),
        State('goal-add-drive-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_add_drive(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-add-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-goal-add-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-goal-add-drive-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
                abs_path = spawn_local_file_picker(
                    initial_dir=r"G:\\My Drive",
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")],
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
                else:
                    return no_update
        return links

    @app.callback(
        Output('goal-add-website-store', 'data', allow_duplicate=True),
        Input('btn-goal-add-website-add', 'n_clicks'),
        Input({'type': 'btn-goal-add-website-link-remove', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-website-link', 'index': ALL}, 'value'),
        State('goal-add-website-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_add_website(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-add-website-add':
            links.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-goal-add-website-link-remove':
            idx = trigger['index']
            if 0 <= idx < len(links) and len(links) > 1:
                links.pop(idx)
        return links

    # --- Add Node Modal: Link Open ---
    @app.callback(
        Output('goal-add-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-add-obsidian-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-obsidian-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_add_obsidian(n_clicks_list, values):
        import subprocess, urllib.parse
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            rel_path = values[idx]
            if not rel_path or not rel_path.strip():
                return "No Obsidian file path set."
            vault = ConfigManager.get_obsidian_vault()
            abs_path = os.path.join(vault, rel_path.strip())
            encoded = urllib.parse.quote(abs_path, safe='')
            uri = f'obsidian://open?path={encoded}'
            try:
                subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
                return no_update
            except Exception as e:
                return f"Error opening Obsidian: {str(e)}"
        return no_update

    @app.callback(
        Output('goal-add-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-add-drive-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-drive-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_add_drive(n_clicks_list, values):
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            url = expand_gdrive_prefix(values[idx])
            if not url or not url.strip():
                return "No path set."
            try:
                os.startfile(url.strip())
                return no_update
            except Exception as e:
                return f"Error opening: {str(e)}"
        return no_update

    @app.callback(
        Output('goal-add-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-add-website-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-add-website-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_add_website(n_clicks_list, values):
        import webbrowser
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            url = (values[idx] or '').strip()
            if not url:
                return "No URL set."
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            try:
                webbrowser.open_new_tab(url)
                return no_update
            except Exception as e:
                return f"Error opening URL: {str(e)}"
        return no_update

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
        State("goal-add-link-edge-type", "value"),
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
        State("goal-node-time-unit", "value"),
        State("goal-add-needs-hard", "value"),
        State("goal-add-needs-soft", "value"),
        State("goal-add-supports-hard", "value"),
        State("goal-add-supports-soft", "value"),
        State("goal-add-helps", "value"),
        State({'type': 'goal-add-obsidian-link', 'index': ALL}, 'value'),
        State({'type': 'goal-add-drive-link', 'index': ALL}, 'value'),
        State({'type': 'goal-add-website-link', 'index': ALL}, 'value'),
        State("goal-include-soft-needs", "value"),
        State("goal-include-transitive", "value"),
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_goal, mode, existing_node, link_edge_type,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty, time_o, time_m, time_p,
                      time_unit,
                      needs_hard, needs_soft, supports_hard, supports_soft, helps,
                      obsidian_vals, drive_vals, website_vals,
                      include_soft_value, include_transitive_value):
        if not n_clicks or not selected_goal:
            return (no_update,) * 4

        if mode == "link":
            if not existing_node:
                return no_update, "Select a node to link.", no_update, no_update
            node_name = existing_node
        else:
            if not name or not name.strip():
                return no_update, "Node name is required.", no_update, no_update
            node_name = name.strip()

            multiplier = ConfigManager.get_time_multiplier(time_unit)

            new_node = Node(
                name=node_name,
                type=node_type or "Learn",
                description=(desc or "").strip(),
                value=value or 5,
                time_o=float(time_o or 0) * multiplier,
                time_m=float(time_m or 0) * multiplier,
                time_p=float(time_p or 0) * multiplier,
                interest=interest or 5,
                difficulty=difficulty or 5,
                status="Open",
                context=context or None,
                subcontext=(subcontext or "").strip() or None,
                obsidian_path=serialize_links(obsidian_vals),
                google_drive_path=serialize_links(drive_vals),
                website=serialize_links(website_vals),
            )

            try:
                graph_manager.add_node(new_node)
            except ValueError as e:
                return no_update, str(e), no_update, no_update

            # Apply relationships for the new node
            graph_manager.sync_edges(
                node_name,
                needs_hard or [], needs_soft or [],
                supports_hard or [], supports_soft or [],
                helps or [],
            )

        # Add edge to the goal only if the user didn't already set one
        # via supports_hard/supports_soft (which would have been applied by sync_edges above)
        existing_edges = graph_manager.get_edges()
        has_goal_edge = any(
            e['source'] == node_name and e['target'] == selected_goal
            and e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)
            for e in existing_edges
        )
        if not has_goal_edge:
            # Use selected edge type for link mode; default to hard for create mode
            goal_edge_type = EDGE_NEEDS_SOFT if (mode == "link" and link_edge_type == "soft") else EDGE_NEEDS_HARD
            try:
                graph_manager.add_edge(node_name, selected_goal, goal_edge_type)
            except (ValueError, Exception) as e:
                return no_update, str(e), no_update, no_update

        # Rebuild subtasks table
        subtree = graph_manager.get_goal_subtree(selected_goal)
        subtask_nodes = [graph_manager.get_node(n) for n in subtree]
        subtask_nodes = [n for n in subtask_nodes if n is not None]
        subtask_nodes.sort(key=lambda n: (n.status == "Done", n.name))
        edges = graph_manager.get_edges()

        include_soft = bool(include_soft_value and "include" in include_soft_value)
        include_transitive = bool(include_transitive_value and "include" in include_transitive_value)

        return (
            False,
            "",
            f"add-node-{node_name}",
            build_subtasks_table(subtask_nodes, graph_manager=graph_manager, edges=edges,
                                 goal_name=selected_goal, include_soft=include_soft,
                                 include_transitive=include_transitive),
        )

    # ================================================================
    # Goal Editor: External Resource Link Management
    # ================================================================

    # --- Render link rows ---
    @app.callback(
        Output('goal-obsidian-links-container', 'children'),
        Input('goal-obsidian-links-store', 'data'),
    )
    def render_goal_obsidian(links):
        return render_link_rows(links, 'goal-obsidian-link', has_browse=True)

    @app.callback(
        Output('goal-drive-links-container', 'children'),
        Input('goal-drive-links-store', 'data'),
    )
    def render_goal_drive(links):
        return render_link_rows(strip_gdrive_prefix(links), 'goal-drive-link', has_browse=True)

    @app.callback(
        Output('goal-website-links-container', 'children'),
        Input('goal-website-links-store', 'data'),
    )
    def render_goal_website(links):
        return render_link_rows(links, 'goal-website-link', has_browse=False)

    # --- Add/Remove/Browse links ---
    @app.callback(
        Output('goal-obsidian-links-store', 'data', allow_duplicate=True),
        Input('btn-goal-obsidian-add', 'n_clicks'),
        Input({'type': 'btn-goal-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-goal-obsidian-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-obsidian-link', 'index': ALL}, 'value'),
        State('goal-obsidian-links-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_obsidian(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-goal-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-goal-obsidian-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
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
                else:
                    return no_update
        return links

    @app.callback(
        Output('goal-drive-links-store', 'data', allow_duplicate=True),
        Input('btn-goal-drive-add', 'n_clicks'),
        Input({'type': 'btn-goal-drive-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-goal-drive-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-drive-link', 'index': ALL}, 'value'),
        State('goal-drive-links-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_drive(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-goal-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-goal-drive-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
                abs_path = spawn_local_file_picker(
                    initial_dir=r"G:\\My Drive",
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")],
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
                else:
                    return no_update
        return links

    @app.callback(
        Output('goal-website-links-store', 'data', allow_duplicate=True),
        Input('btn-goal-website-add', 'n_clicks'),
        Input({'type': 'btn-goal-website-link-remove', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-website-link', 'index': ALL}, 'value'),
        State('goal-website-links-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_goal_website(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-goal-website-add':
            links.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-goal-website-link-remove':
            idx = trigger['index']
            if 0 <= idx < len(links) and len(links) > 1:
                links.pop(idx)
        return links

    # --- Open links ---
    @app.callback(
        Output('goal-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-obsidian-link-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-obsidian-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_obsidian(n_clicks_list, values):
        import subprocess, urllib.parse
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            rel_path = values[idx]
            if not rel_path or not rel_path.strip():
                return "No Obsidian file path set."
            vault = ConfigManager.get_obsidian_vault()
            abs_path = os.path.join(vault, rel_path.strip())
            encoded = urllib.parse.quote(abs_path, safe='')
            uri = f'obsidian://open?path={encoded}'
            try:
                subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
                return no_update
            except Exception as e:
                return f"Error opening Obsidian: {str(e)}"
        return no_update

    @app.callback(
        Output('goal-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-drive-link-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-drive-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_drive(n_clicks_list, values):
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            url = expand_gdrive_prefix(values[idx])
            if not url or not url.strip():
                return "No path set."
            try:
                os.startfile(url.strip())
                return no_update
            except Exception as e:
                return f"Error opening: {str(e)}"
        return no_update

    @app.callback(
        Output('goal-save-status', 'children', allow_duplicate=True),
        Input({'type': 'btn-goal-website-link-open', 'index': ALL}, 'n_clicks'),
        State({'type': 'goal-website-link', 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def open_goal_website(n_clicks_list, values):
        import webbrowser
        if not any(n_clicks_list):
            return no_update
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        idx = trigger['index']
        if 0 <= idx < len(values):
            url = (values[idx] or '').strip()
            if not url:
                return "No URL set."
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            try:
                webbrowser.open_new_tab(url)
                return no_update
            except Exception as e:
                return f"Error opening URL: {str(e)}"
        return no_update
