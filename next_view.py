"""Next view queries and initial hydration shared by layout and callbacks."""
from collections import namedtuple
from copy import deepcopy
import database
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import format_now_nodes_section, format_suggestions_table, build_filters

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


def perf_stats_text():
    """The Home tab's scoring-time caption, or None before one is recorded.

    Timings are recorded once per process, by the first scoring pass, which
    is the one that builds the first layout. So the layout carries the
    caption, and each later table refresh reads it again.
    """
    t = GraphManager._last_perf_timings
    if not t:
        return None
    return (f"{t['n_nodes']} nodes · {t['n_edges']} edges · "
            f"{t['total_ms']:.0f}ms")


NextRows = namedtuple("NextRows", "rows pinned_steps")


@database.snapshot_read
def get_suggestions(filters=None, count=5, *, manager=manager):
    """Build the Next table: unblocking steps on top, then the ranking.

    Hierarchical variety is already baked into `priority_score` by the
    scoring module (see scoring.variety_divisors), so the lower section is a
    slice of an ordered list rather than a second selection pass. That is what
    lets the Home tab print the number it sorts on.

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
