"""Callbacks for the four cross-tab sidebars.

Goals-sidebar logic, the filters-sidebar toggle, and the editor-sidebar
fast-path live here so they don't have to ride along inside the Details or
Canvas tab modules. The cross-sidebar style coordinator (`_compute_sidebar_styles`
and friends) stays in callbacks.py because it's woven into core_engine's output
tuple — see the IDX constants there.
"""

import json as _json
import time as _time

from dash import html, Input, Output, State, no_update, ClientsideFunction

from graph_manager import GraphManager
from config import ConfigManager, SIDEBAR_WIDTH_NEG_PX
from models import STATUS_DONE
from details_layout import build_goal_card

graph_manager = GraphManager()


def register_sidebars_callbacks(app):
    """Register the cross-tab sidebar callbacks: goals (toggle, new, render,
    priority, context-menu, drag-reorder), filters toggle, editor fast-path."""

    # --- Goal Sidebar Toggle (CLIENTSIDE) ---
    # Handled in the browser via assets/goals_sidebar.js to eliminate the
    # server round-trip on open/close. On open it bumps goals-ui-refresh-trigger
    # (NOT details-refresh-trigger) so only render_goal_list re-runs — core_engine
    # stays idle, keeping the animation smooth.
    app.clientside_callback(
        ClientsideFunction(namespace='goals', function_name='toggle_sidebar'),
        Output("details-goal-sidebar", "style"),
        Output("goals-ui-refresh-trigger", "data", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("events-sidebar-container", "style", allow_duplicate=True),
        Input("btn-goals-toggle", "n_clicks"),
        Input("btn-details-goals-close", "n_clicks"),
        State("details-goal-sidebar", "style"),
        State("sidebar-editor-container", "style"),
        State("events-sidebar-container", "style"),
        State("goals-ui-refresh-trigger", "data"),
        prevent_initial_call=True,
    )

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
        goal_style["left"] = SIDEBAR_WIDTH_NEG_PX
        ed_style = dict(editor_style) if editor_style else {}
        ed_style["transform"] = "translateX(0px)"
        return goal_style, "Goal", ed_style

    # --- Populate Goal Sidebar ---
    @app.callback(
        Output("details-goal-list-container", "children"),
        Input("main-tabs", "active_tab"),
        Input("details-refresh-trigger", "data"),
        Input("goals-ui-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-goal-search", "value"),
        Input("details-goal-sort", "value"),
        Input("details-goal-order-store", "data"),
        State("details-selected-node-store", "data"),
    )
    def render_goal_list(active_tab, _refresh, _ui_refresh, _version, search_val, sort_mode, manual_order, selected_node):

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
            completion_cache[g.name] = graph_manager.get_goal_completion(g.name, include_soft=False)

        def _is_done(g):
            c = completion_cache[g.name]
            return g.status == STATUS_DONE or (c.get("pct", 0) == 100 and c.get("total", 0) > 0)

        # Done goals are hidden from the sidebar.
        goals = [g for g in goals if not _is_done(g)]

        if not goals:
            return html.Div(
                html.P("No goals to show.", className="text-muted"),
                className="text-center py-5"
            )

        sort_mode = sort_mode or "manual"
        is_manual = sort_mode == "manual"

        score_map = {}
        if sort_mode == "priority":
            # Goals are sinks, so the forward priority_score collapses to
            # ~nothing. _rank_goals ranks them by ROI on the inverted prereq
            # graph — subtree value per unit of remaining time, boosted by
            # priority rank and context weight.
            from analyze_callbacks import _rank_goals
            ranked = _rank_goals(goals, all_nodes, graph_manager.get_edges(),
                                 priority_goals, ConfigManager.get_hyperparams(),
                                 with_scores=True)
            goals = [g for g, _ in ranked]
            score_map = {g.name: sc for g, sc in ranked}
        elif sort_mode == "alpha-asc":
            goals.sort(key=lambda g: g.name.lower())
        elif sort_mode == "time-desc":
            goals.sort(key=lambda g: completion_cache[g.name].get("remaining_time", 0),
                       reverse=True)
        elif is_manual and manual_order:
            order_map = {name: idx for idx, name in enumerate(manual_order)}
            goals.sort(key=lambda g: order_map.get(g.name, 999))

        # Pin priority 1-3 at the top; Done goals always sink to the bottom so
        # they don't compete with active goals for the top slots.
        pinned, unpinned, done = [], [], []
        for g in goals:
            if _is_done(g):
                done.append(g)
            elif g.name in priority_goals[:3]:
                pinned.append(g)
            else:
                unpinned.append(g)
        pinned.sort(key=lambda g: priority_goals.index(g.name))
        goals = pinned + unpinned + done

        # Sort-dependent top-right corner indicator (open goals only).
        # Priority -> normalized score 0-100; Manual -> displayed rank.
        # Time/Alphabetical -> nothing (time is already on the stats line,
        # alphabetical order carries no rank meaning).
        corner_map = {}
        active = pinned + unpinned
        if sort_mode == "priority":
            scores = [score_map[g.name] for g in active if score_map.get(g.name, -1) >= 0]
            max_score = max(scores) if scores else 0
            if max_score > 0:
                for g in active:
                    s = score_map.get(g.name, -1)
                    if s >= 0:
                        corner_map[g.name] = str(round(s / max_score * 100))
        elif is_manual:
            for idx, g in enumerate(active):
                corner_map[g.name] = str(idx + 1)

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
                corner_text=corner_map.get(goal.name),
            ))
        return cards

    # --- Goal Sidebar: Priority Change (from rank popover or context menu) ---
    @app.callback(
        Output('details-refresh-trigger', 'data', allow_duplicate=True),
        Input('goal-priority-trigger-input', 'value'),
        prevent_initial_call=True,
    )
    def handle_goal_priority_change(payload):
        if not payload:
            return no_update
        parts = payload.split('|')
        if len(parts) < 2:
            return no_update
        goal_name, action = parts[0], parts[1]
        if not goal_name:
            return no_update
        priority_goals = ConfigManager.get_priority_goals()
        if goal_name in priority_goals:
            priority_goals.remove(goal_name)
        if action in ('1', '2', '3'):
            rank_idx = min(int(action) - 1, len(priority_goals))
            priority_goals.insert(rank_idx, goal_name)
        ConfigManager.set_priority_goals(priority_goals)
        return f'goal-priority-{_time.time()}'

    # --- Goal Sidebar: Context Menu → Open in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input("goal-details-trigger-input", "value"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def goal_ctx_to_details(payload, active_tab):
        if not payload:
            return no_update, no_update
        goal_name = payload.split('|')[0]
        if not goal_name:
            return no_update, no_update
        next_tab = "tab-details" if active_tab != "tab-details" else no_update
        return goal_name, next_tab

    # --- Goal Drag Reorder ---
    @app.callback(
        Output("details-goal-order-store", "data"),
        Input("details-goal-drag-order-input", "value"),
        prevent_initial_call=True,
    )
    def reorder_goals(drag_order_json):
        if drag_order_json:
            try:
                new_order = _json.loads(drag_order_json)
                if isinstance(new_order, list) and new_order:
                    ConfigManager.set_goal_order(new_order)
                    return new_order
            except (ValueError, TypeError):
                pass
        return no_update

    # --- Filters Sidebar Toggle (CLIENTSIDE) ---
    # Handled entirely in the browser via assets/filters_sidebar.js. Previously
    # this toggle went through core_engine, whose expensive graph-regen branch
    # delayed the CSS transition by 500ms-2s on each click.
    app.clientside_callback(
        ClientsideFunction(namespace='filters', function_name='toggle_sidebar'),
        Output('sidebar-filters-container', 'style'),
        Input('btn-filters-toggle', 'n_clicks'),
        Input('btn-close-filters', 'n_clicks'),
        State('sidebar-filters-container', 'style'),
        prevent_initial_call=True,
    )

    # --- Editor Sidebar Fast-Path (CLIENTSIDE) ---
    # Starts the open-editor CSS transition immediately on btn-add, in parallel
    # with core_engine's form-population work. core_engine still sets the same
    # open-transform value server-side as a safety net. Close/save/new-node
    # stay server-side because they depend on form state.
    app.clientside_callback(
        ClientsideFunction(namespace='editor', function_name='open_on_add'),
        Output('sidebar-editor-container', 'style', allow_duplicate=True),
        Output('details-goal-sidebar', 'style', allow_duplicate=True),
        Output('events-sidebar-container', 'style', allow_duplicate=True),
        Input('btn-add', 'n_clicks'),
        State('sidebar-editor-container', 'style'),
        State('details-goal-sidebar', 'style'),
        State('events-sidebar-container', 'style'),
        prevent_initial_call=True,
    )
