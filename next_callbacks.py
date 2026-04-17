"""
Callback definitions for the Next tab (priority suggestions).
"""

import dash
from dash import Input, Output, State, ALL, ctx
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import get_trigger_id

manager = GraphManager()


def get_suggestions(filters=None, count=5, exclude_override=False):
    """Retrieve top-N prioritized nodes based on ROI scoring.

    When a manual override is active, uses two-tier sorting:
    Tier 1 (top): overridden nodes, scored among themselves.
    Tier 2 (bottom): normal nodes, scored among themselves.

    If ``exclude_override`` is True, skip the override tier entirely and
    return only non-override recommendations (useful for the Details tab
    top-recommendations list, which shouldn't duplicate the override row).
    """
    if filters is None:
        filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    priority_goals = ConfigManager.get_priority_goals()

    override_set = ConfigManager.get_override_node_set(manager)

    if exclude_override and override_set:
        filtered_nodes = [n for n in filtered_nodes if n.name not in override_set]
        scored = manager.calculate_priority_scores(filtered_nodes, priority_goals=priority_goals)
        valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
        return valid[:count]

    if override_set:
        tier1_nodes = [n for n in filtered_nodes if n.name in override_set]
        tier2_nodes = [n for n in filtered_nodes if n.name not in override_set]

        scored_t1 = manager.calculate_priority_scores(tier1_nodes, priority_goals=priority_goals)
        scored_t2 = manager.calculate_priority_scores(tier2_nodes, priority_goals=priority_goals)

        valid_t1 = [n for n in scored_t1 if getattr(n, 'priority_score', -1) >= 0]
        valid_t2 = [n for n in scored_t2 if getattr(n, 'priority_score', -1) >= 0]

        return valid_t1 + valid_t2[:max(0, count - len(valid_t1))]
    else:
        scored = manager.calculate_priority_scores(filtered_nodes, priority_goals=priority_goals)
        valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
        return valid[:count]


def get_override_set():
    """Return the current set of overridden node names."""
    return ConfigManager.get_override_node_set(manager)


def register_next_callbacks(app):

    # --- Suggestion Count +/- ---
    @app.callback(
        Output('suggestion-count-store', 'data'),
        Output('suggestion-count-display', 'children'),
        Input('btn-sugg-plus', 'n_clicks'),
        Input('btn-sugg-minus', 'n_clicks'),
        State('suggestion-count-store', 'data'),
        prevent_initial_call=True
    )
    def update_suggestion_count(plus, minus, current_count):
        trigger_id = get_trigger_id()
        count = current_count or 10
        if trigger_id == 'btn-sugg-plus':
            count = count + 1
        elif trigger_id == 'btn-sugg-minus':
            count = max(1, count - 1)
        return count, str(count)

    # --- Suggestion Row Selection ---
    @app.callback(
        Output('selected-suggestion-store', 'data'),
        Input({'type': 'suggestion-row', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def update_selected_suggestion(n_clicks_list):
        if not any(n_clicks_list):
            return dash.no_update
        trigger_id = ctx.triggered_id
        if trigger_id and isinstance(trigger_id, dict) and 'index' in trigger_id:
            return trigger_id['index']
        return dash.no_update

    # --- Suggestion Name Click -> Navigate to Details Tab ---
    @app.callback(
        Output('main-tabs', 'active_tab', allow_duplicate=True),
        Output('details-node-select', 'value', allow_duplicate=True),
        Input({'type': 'suggestion-name-link', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def navigate_to_suggestion_node(n_clicks_list):
        if not any(n_clicks_list):
            return dash.no_update, dash.no_update
        trigger = ctx.triggered_id
        if trigger and isinstance(trigger, dict) and 'index' in trigger:
            return 'tab-details', trigger['index']
        return dash.no_update, dash.no_update
