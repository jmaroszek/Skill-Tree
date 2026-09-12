"""
Callback definitions for the Next tab (priority suggestions).
"""

import database
from collections import namedtuple
from copy import deepcopy

from dash import Input, Output, State, ALL, ClientsideFunction
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import get_trigger_id, format_now_nodes_section, format_suggestions_table, build_filters
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
    next_rows = get_suggestions(filters, count=count)
    parts['suggestions-table'].children = format_suggestions_table(
        next_rows.rows, manager, pinned_steps=next_rows.pinned_steps)
    parts['now-nodes-table'].children = format_now_nodes_section(
        manager.get_now_nodes(), ConfigManager.get_now_node_cap(), manager)
    return view


#: What the Next table renders: the ordered rows, plus a map from a pinned
#: step's name to the Now target it unblocks (empty for an ordinary row).
NextRows = namedtuple("NextRows", "rows pinned_steps")


@database.snapshot_read
def get_suggestions(filters=None, count=5):
    """Build the Next table: unblocking steps on top, then the ranking.

    Hierarchical variety is already baked into `priority_score` by the
    scoring module (see scoring.variety_divisors), so the lower section is a
    slice of an ordered list rather than a second selection pass. That is what
    lets the Next tab print the number it sorts on.

    A Now node you cannot start yet — Blocked, or a Goal, or anything else
    scoring below zero — pins its best actionable prerequisites above that
    ranking, so the tab answers "what do I do toward this" instead of going
    quiet. Those steps are **additive**: they do not eat into the row count the
    user asked for, and they bypass the filter sidebar, because pinning is an
    explicit intent that supersedes passive scope narrowing. Everything below
    them is scoped normally, and never repeats a step.

    Now nodes themselves live exclusively in the "Now" section, so they are
    dropped here and can never come back as one of their own steps.
    """
    if filters is None:
        filters = {}
    nodes = [n for n in manager.get_all_nodes() if not n.now]
    filtered_nodes = manager.filter_nodes(nodes, filters)
    priority_goals = ConfigManager.get_priority_goals()

    steps = manager.get_unblocking_steps(
        [n.name for n in manager.get_now_nodes()],
        limit=ConfigManager.get_unblocking_steps_per_now(),
        priority_goals=priority_goals,
    )
    pinned_steps = {node.name: target for node, target in steps}

    scored = manager.calculate_priority_scores(
        [n for n in filtered_nodes if n.name not in pinned_steps],
        priority_goals=priority_goals,
    )
    ranked = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]

    return NextRows([node for node, _ in steps] + ranked[:max(0, count)],
                    pinned_steps)


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
    against the priority-goal section).
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
        next_rows = get_suggestions(filters, count=count or 10)
        return format_suggestions_table(next_rows.rows, manager,
                                        pinned_steps=next_rows.pinned_steps)

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
