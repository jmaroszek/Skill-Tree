"""
Callback definitions for the Next tab (priority suggestions).
"""

import database
from copy import deepcopy

from dash import Input, Output, State, ALL, ClientsideFunction
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import get_trigger_id, format_now_nodes_section, format_suggestions_table, build_filters
from callback_helpers import assemble_suggestions
from models import STATUS_DONE

manager = GraphManager()


def _components_by_id(children):
    """Index a component tree without modifying shared layout templates."""
    found = {}
    def visit(component):
        if isinstance(component, (list, tuple)):
            for child in component:
                visit(child)
        elif hasattr(component, 'to_plotly_json'):
            identity = getattr(component, 'id', None)
            if isinstance(identity, str):
                found[identity] = component
            visit(getattr(component, 'children', None))
    visit(children)
    return found


@database.snapshot_read
def _initial_next_view(template, sidebars):
    """Ship usable Next content in the first layout, with the actual UI filters."""
    view = deepcopy(template)
    controls = _components_by_id(sidebars)
    def value(identity):
        return controls[identity].value
    filters = build_filters(
        value('filter-context'), value('filter-subcontext'), value('filter-done'),
        value('filter-value'), value('filter-interest'), value('filter-time'),
        value('filter-difficulty'), value('filter-node-type'),
        f_time_unit=value('filter-time-unit'), f_show_dormant=value('filter-dormant'))
    parts = _components_by_id(view)
    count = ConfigManager.get_next_table_rows()
    parts['suggestion-count-store'].data = count
    parts['suggestion-count-display'].children = str(count)
    parts['suggestions-table'].children = format_suggestions_table(
        get_suggestions(filters, count=count), manager, override_set=get_override_set())
    parts['now-nodes-table'].children = format_now_nodes_section(
        manager.get_now_nodes(), ConfigManager.get_now_node_cap(), manager)
    return view


@database.snapshot_read
def get_suggestions(filters=None, count=5, exclude_override=False):
    """Assemble top-N suggestions using ROI merit and hierarchical variety.

    When a manual override is active, uses two-tier sorting:
    Tier 1 (top): overridden nodes, scored among themselves.
    Tier 2 (bottom): filtered candidates, diversified after counting Tier 1.

    If ``exclude_override`` is True, skip the override tier entirely and
    return only non-override recommendations (useful for the Details tab
    top-recommendations list, which shouldn't duplicate the override row).
    """
    if filters is None:
        filters = {}
    nodes = manager.get_all_nodes()
    # Now nodes live exclusively in the "Now" section on the Next tab —
    # exclude them here so they don't duplicate in the Suggestions/Next
    # table below. Filtering at the top covers both override and normal
    # tiers without special-casing.
    nodes = [n for n in nodes if not n.now]
    filtered_nodes = manager.filter_nodes(nodes, filters)
    priority_goals = ConfigManager.get_priority_goals()

    override_set = ConfigManager.get_override_node_set(manager)
    hp = ConfigManager.get_hyperparams()

    if exclude_override and override_set:
        filtered_nodes = [n for n in filtered_nodes if n.name not in override_set]
        scored = manager.calculate_priority_scores(filtered_nodes, priority_goals=priority_goals)
        valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
        return assemble_suggestions(valid, count, hp)

    if override_set:
        # Tier 1 (override) bypasses the user filter: a pin is an explicit
        # user intent that supersedes passive scope narrowing. Without this,
        # toggling a context filter can silently drop a pinned node from Next.
        # Tier 2 still respects the filter — unpinned nodes are scoped normally.
        tier1_nodes = [n for n in nodes if n.name in override_set]
        tier2_nodes = [n for n in filtered_nodes if n.name not in override_set]

        scored_t1 = manager.calculate_priority_scores(tier1_nodes, priority_goals=priority_goals)
        scored_t2 = manager.calculate_priority_scores(tier2_nodes, priority_goals=priority_goals)

        valid_t1 = [n for n in scored_t1 if getattr(n, 'priority_score', -1) >= 0]
        valid_t2 = [n for n in scored_t2 if getattr(n, 'priority_score', -1) >= 0]

        return valid_t1 + assemble_suggestions(valid_t2, count - len(valid_t1), hp, valid_t1)
    else:
        scored = manager.calculate_priority_scores(filtered_nodes, priority_goals=priority_goals)
        valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
        return assemble_suggestions(valid, count, hp)


@database.snapshot_read
def get_container_suggestions(count=5, exclude_names=None):
    """Retrieve top-N container nodes ranked by total_value.

    A "container" here is ``Node.is_container`` — any node with at least
    one inherited mode (ratings or time). The intent is "structurally rich
    nodes worth examining in the Details tab," not "what to do next."

    Milestones are excluded: per the framework they are single-event
    checkpoints, not capacity containers — the work happens upstream
    in their prereq Goals, and Milestones offer no internal structure
    worth examining.

    Also excludes Done and dormant nodes, plus any names in
    ``exclude_names`` (used by the Details empty state to dedupe
    against the override and priority-goal sections).
    """
    exclude_names = set(exclude_names or [])
    nodes = manager.get_all_nodes()
    scored = manager.calculate_priority_scores(nodes)

    containers = [
        n for n in scored
        if n.is_container
        and n.type != 'Milestone'
        and n.status != STATUS_DONE
        and not getattr(n, 'dormant', False)
        and n.name not in exclude_names
    ]
    containers.sort(key=lambda n: getattr(n, 'total_value', 0.0), reverse=True)
    return containers[:count]


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

    # Selection uses descriptions already shipped with the visible rows.
    # No Python request or graph/table refresh is needed for a click.
    app.clientside_callback(
        ClientsideFunction(namespace='skillTreeNext', function_name='select'),
        Output('selected-suggestion-store', 'data'),
        Output('next-description-text', 'children'),
        Output({'type': 'suggestion-row', 'index': ALL}, 'style'),
        Output({'type': 'now-row', 'index': ALL}, 'style'),
        Output('next-description-text', 'style'),
        Input({'type': 'suggestion-row', 'index': ALL}, 'n_clicks'),
        Input({'type': 'now-row', 'index': ALL}, 'n_clicks'),
        Input('suggestions-table', 'children'),
        Input('now-nodes-table', 'children'),
        State('selected-suggestion-store', 'data'),
    )

    @app.callback(
        Output('suggestions-table', 'children'),
        Input('graph-version-store', 'data'),
        Input('suggestion-count-store', 'data'),
        Input('filter-context', 'value'), Input('filter-subcontext', 'value'),
        Input('filter-done', 'value'), Input('filter-value', 'value'),
        Input('filter-interest', 'value'), Input('filter-time', 'value'),
        Input('filter-time-unit', 'value'), Input('filter-difficulty', 'value'),
        Input('filter-node-type', 'value'), Input('filter-dormant', 'value'),
        Input('settings-save-status', 'children'),
    )
    @database.snapshot_read
    def populate_suggestions(_version, count, context, subcontext, done, value,
                             interest, time, time_unit, difficulty, types, dormant, _settings):
        filters = build_filters(context, subcontext, done, value, interest, time,
                                difficulty, types, f_time_unit=time_unit,
                                f_show_dormant=dormant)
        return format_suggestions_table(get_suggestions(filters, count=count or 10),
                                        manager, override_set=get_override_set())

    # --- Now Section: populate now-nodes-table ---
    # Listens to graph-version-store so the section refreshes whenever any
    # node mutates (including a flip of the Now flag, which goes through
    # update_node and bumps graph_version).
    @app.callback(
        Output('now-nodes-table', 'children'),
        Input('graph-version-store', 'data'),
        State('selected-suggestion-store', 'data'),
    )
    def populate_now_section(_version, selected_node_id):
        now_nodes = manager.get_now_nodes()
        return format_now_nodes_section(
            now_nodes,
            cap=ConfigManager.get_now_node_cap(),
            manager=manager,
            selected_node_id=selected_node_id,
        )
