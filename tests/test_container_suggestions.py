"""The Details Explore list and the app's one 0-100 Goal priority.

Explore lists Goals from the Goal ranking the Goals sidebar uses, and shows the
same number. These tests cover the selection rules and that the number agrees
across the sidebar, the Explain modal and Details.
"""

from typing import Any

import dash
from dash.development.base_component import Component

from analyze_callbacks import _rank_goals, explain_goal, normalize_goal_scores
from callback_helpers import select_explore_goals
from config import ConfigManager
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, STATUS_DONE, Node


def _node(name: str, **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
        status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


def _goal(name: str, **overrides: Any) -> Node:
    return _node(name, type="Goal", **overrides)


def _edge(source: str, target: str):
    return {"source": source, "target": target, "type": EDGE_NEEDS_HARD}


def _names(goals):
    return [goal.name for goal in goals]


# ============================================================================
# select_explore_goals — which ranked Goals Explore lists
# ============================================================================

def test_keeps_rank_order_and_skips_seeds_filtered_and_finished_goals():
    seed, hidden, finished, empty, kept = (
        _goal(name) for name in ("Seed", "Hidden", "Finished", "Empty", "Kept"))
    nodes = [seed, hidden, finished, empty, kept,
             _node("Seed work"), _node("Hidden work"),
             _node("Finished work", status=STATUS_DONE), _node("Kept work")]
    edges = [_edge("Seed work", "Seed"), _edge("Hidden work", "Hidden"),
             _edge("Finished work", "Finished"), _edge("Kept work", "Kept")]

    chosen = select_explore_goals(
        [seed, hidden, finished, empty, kept], nodes, edges,
        candidate_names={"Seed", "Finished", "Empty", "Kept"},
        seed_names=["Seed"])

    assert _names(chosen) == ["Kept"]


def test_a_nested_goal_waits_for_an_unrelated_one():
    parent, child, other = _goal("Parent"), _goal("Child"), _goal("Other")
    nodes = [parent, child, other, _node("Deep"), _node("Other work")]
    edges = [_edge("Deep", "Child"), _edge("Child", "Parent"),
             _edge("Other work", "Other")]

    assert _names(select_explore_goals(
        [parent, child, other], nodes, edges, count=2)) == ["Parent", "Other"]
    # With room to spare, the nested Goal fills in, still in rank order.
    assert _names(select_explore_goals(
        [parent, child, other], nodes, edges, count=3)) == [
        "Parent", "Child", "Other"]


def test_a_priority_goal_keeps_its_children_out_of_explore():
    parent, child, other = _goal("Parent"), _goal("Child"), _goal("Other")
    nodes = [parent, child, other, _node("Deep"), _node("Other work")]
    edges = [_edge("Deep", "Child"), _edge("Child", "Parent"),
             _edge("Other work", "Other")]

    chosen = select_explore_goals(
        [parent, child, other], nodes, edges, count=1, seed_names=["Parent"])

    assert _names(chosen) == ["Other"]
    assert select_explore_goals([other], nodes, edges, count=0) == []


# ============================================================================
# One 0-100 Goal priority across the app
# ============================================================================

def _add_graph(manager, nodes, edges):
    for node in nodes:
        manager.add_node(node)
    for source, target in edges:
        manager.add_edge(source, target, EDGE_NEEDS_HARD)


def _ranked(manager):
    nodes = manager.get_all_nodes()
    edges = manager.get_edges()
    ranked = _rank_goals([n for n in nodes if n.type == "Goal"], nodes, edges,
                         ConfigManager.get_priority_goals(),
                         ConfigManager.get_hyperparams(), with_scores=True)
    return ranked, nodes, edges


def test_finished_goals_get_no_number_and_do_not_set_the_base():
    """Regression: a Done Goal owes no work, so its score dwarfed every open
    Goal and shrank the Explain modal's numbers below the sidebar's."""
    manager = GraphManager()
    _add_graph(manager, [
        _goal("Finished", status=STATUS_DONE),
        _node("F1", value=10, interest=10, status=STATUS_DONE),
        _node("F2", value=10, interest=10, status=STATUS_DONE),
        _goal("Ticked"),
        _node("T1", value=10, interest=10, status=STATUS_DONE),
        _goal("Open"),
        _node("O1", value=6, interest=6),
    ], [("F1", "Finished"), ("F2", "Finished"), ("T1", "Ticked"),
        ("O1", "Open")])
    ranked, nodes, edges = _ranked(manager)
    scores = dict((goal.name, score) for goal, score in ranked)
    assert scores["Finished"] > scores["Open"]

    priorities = normalize_goal_scores(ranked, nodes, edges)

    assert priorities == {"Open": 100}
    hp = ConfigManager.get_hyperparams()
    assert explain_goal("Open", nodes, edges, hp, [])[1] == 100
    assert explain_goal("Finished", nodes, edges, hp, [])[1] is None


def _component_ids_and_badges(component):
    """(id, corner badge text) for each goal or suggestion card in a tree."""
    found, stack = {}, [component]
    while stack:
        current = stack.pop()
        if isinstance(current, (list, tuple)):
            stack.extend(current)
            continue
        if not isinstance(current, Component):
            continue
        card_id = getattr(current, "id", None)
        if isinstance(card_id, dict) and card_id.get("type") in (
                "goal-card", "details-suggestion-item"):
            if card_id["type"] == "goal-card":
                corner = current.children[1].children[1].children[1]
            else:
                corner = current.children[1] if len(current.children) > 1 else None
            found[card_id["index"]] = corner.children if corner is not None else None
        children = getattr(current, "children", None)
        if children is not None:
            stack.append(children)
    return found


def _callback(app, name):
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None and fn.__name__ == name:
            return fn
    raise LookupError(name)


def test_sidebar_and_details_show_the_same_number_whatever_is_hidden():
    import details_callbacks
    import sidebars_callbacks

    manager = GraphManager()
    _add_graph(manager, [
        _goal("Alpha", context="Mind"),
        _node("A1", value=9, interest=9, context="Mind"),
        _goal("Beta", context="Body"),
        _node("B1", value=3, interest=3, context="Body"),
    ], [("A1", "Alpha"), ("B1", "Beta")])

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_sidebars_callbacks(app)
    details_callbacks.register_details_callbacks(app)
    render_sidebar = _callback(app, "render_goal_list")
    render_details = _callback(app, "build_empty_state_suggestions")

    def sidebar(search):
        return _component_ids_and_badges(render_sidebar(
            "tab-details", None, None, None, search, "priority", None, None,
            {"left": "0px"}))

    def details(context):
        return _component_ids_and_badges(render_details(
            0, 0, context, [], [], 1, 1, None, "hours", 10, [], [], ""))

    everything = sidebar(None)
    assert everything["Alpha"] == "100"
    beta = everything["Beta"]
    assert beta not in (None, "100")

    # A search in the sidebar and a filter in Details leave the base alone.
    assert sidebar("Beta") == {"Beta": beta}
    assert details([]) == {"Alpha": "100", "Beta": beta}
    assert details(["Body"]) == {"Beta": beta}
