"""Shared node context-menu structure and state-action behavior."""

import json

import dash
from dash.development.base_component import Component

import callbacks
from callback_helpers import format_now_nodes_section, format_suggestions_table
from config import ConfigManager
from graph_manager import GraphManager
from models import Node


def _node(name, **overrides):
    fields = dict(
        name=name,
        type="Learn",
        description="",
        value=5,
        time_o=1,
        time_m=1,
        time_p=1,
        interest=5,
        difficulty=5,
        status="Open",
        context="Mind",
        priority_score=10,
    )
    fields.update(overrides)
    return Node(**fields)


def _find(component, component_id):
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        if not isinstance(node, Component):
            continue
        if getattr(node, "id", None) == component_id:
            return node
        children = getattr(node, "children", None)
        if children is not None:
            stack.append(children)
    raise AssertionError(f"Missing component {component_id}")


def _app():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    return app


def _callback(app, name):
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None and fn.__name__ == name:
            return fn
    raise LookupError(name)


def _layout():
    from layout import build_app_layout
    return build_app_layout([], env="sandbox")


def _child_ids(menu):
    return [getattr(child, "id", None) for child in menu.children
            if getattr(child, "id", None)]


def _labels(component):
    """Every item label in a menu, submenus included, in document order."""
    labels = []
    stack = [component]
    while stack:
        node = stack.pop(0)
        if isinstance(node, (list, tuple)):
            stack[:0] = list(node)
            continue
        if not isinstance(node, Component):
            continue
        if "ctx-menu-item" in (getattr(node, "className", None) or "").split()                 and isinstance(node.children, str):
            labels.append(node.children)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple, Component)):
            stack.insert(0, children)
    return labels


def test_shared_menu_groups_actions_by_intent():
    menu = _find(_layout(), "node-context-menu")
    assert _child_ids(menu) == [
        "ctx-menu-edit",
        "ctx-menu-details",
        "ctx-menu-explain",
        "ctx-menu-priority-divider",
        "ctx-menu-priority",
        "ctx-menu-toggle-now",
        "ctx-menu-add-to-event",
        "ctx-menu-toggle-done",
        "ctx-menu-links-divider",
        "ctx-menu-website",
        "ctx-menu-obsidian",
        "ctx-menu-drive",
        "ctx-menu-delete",
    ]
    assert _find(menu, "ctx-menu-details").children == "View Details"
    assert _find(menu, "ctx-menu-explain").children == "Explain Priority"
    assert _find(menu, "ctx-menu-delete").children == "Delete…"
    assert "ctx-menu-item-danger" in _find(menu, "ctx-menu-delete").className


def test_goals_get_set_priority_in_the_shared_menu():
    """The Goals sidebar used to keep its own menu, which fell behind the
    shared one. Its one extra command now lives in the shared menu."""
    menu = _find(_layout(), "node-context-menu")
    priority = _find(menu, "ctx-menu-priority")
    assert "ctx-menu-submenu-parent" in priority.className
    for item_id, label in (("ctx-menu-priority-1", "Priority 1"),
                           ("ctx-menu-priority-2", "Priority 2"),
                           ("ctx-menu-priority-3", "Priority 3"),
                           ("ctx-menu-priority-clear", "Clear Priority")):
        assert _find(priority, item_id).children == label


def test_no_separate_goal_menu_remains():
    layout = _layout()
    for gone in ("goal-context-menu", "goal-details-trigger-input"):
        try:
            _find(layout, gone)
        except AssertionError:
            continue
        raise AssertionError(f"{gone} is still in the layout")


def test_rank_popover_offers_the_same_priority_commands():
    layout = _layout()
    popover = _find(layout, "goal-rank-popover")
    submenu = _find(_find(layout, "node-context-menu"), "ctx-menu-priority")
    assert _labels(popover) == _labels(submenu)


def test_event_menu_follows_the_shared_conventions():
    menu = _find(_layout(), "event-context-menu")
    assert _child_ids(menu) == [
        "event-ctx-edit",
        "event-ctx-trigger-divider",
        "event-ctx-trigger",
        "event-ctx-delete",
    ]
    assert _labels(menu) == ["Edit", "Trigger Now…", "Delete…"]
    assert "ctx-menu-item-danger" in _find(menu, "event-ctx-delete").className


def test_every_floating_menu_shares_one_panel_class():
    layout = _layout()
    for menu_id in ("node-context-menu", "event-context-menu", "goal-rank-popover"):
        assert _find(layout, menu_id).className == "ctx-menu"


def test_event_cards_say_whether_they_can_still_trigger():
    from events_layout import build_event_card

    card = build_event_card("Trip", "", "Triggered", {"total": 1, "activated": 0})
    assert getattr(card, "data-event-status") == "Triggered"


def test_next_rows_carry_context_menu_state_and_all_link_types():
    manager = GraphManager()
    suggestion = _node(
        "Suggestion",
        obsidian_path='["note.md"]',
        google_drive_path='["https://drive.example/file"]',
        website='["https://example.com"]',
    )
    manager.add_node(suggestion)

    suggestion_row = _find(
        format_suggestions_table([suggestion], manager)[0],
        {"type": "suggestion-row", "index": "Suggestion"},
    )
    assert getattr(suggestion_row, "data-node-menu") == "Suggestion"
    assert getattr(suggestion_row, "data-type") == "Learn"
    assert getattr(suggestion_row, "data-website") == '["https://example.com"]'
    assert getattr(suggestion_row, "data-status") == "Open"
    assert getattr(suggestion_row, "data-now") == "0"

    suggestion.now = 1
    manager.update_node(suggestion)
    now_section = format_now_nodes_section([suggestion], 5, manager)
    now_row = _find(
        now_section,
        {"type": "now-row", "index": "Suggestion"},
    )
    assert getattr(now_row, "data-node-menu") == "Suggestion"
    assert getattr(now_row, "data-website") == '["https://example.com"]'
    assert getattr(now_row, "data-status") == "Open"
    assert getattr(now_row, "data-now") == "1"


def test_goal_cards_open_the_shared_node_menu():
    import sidebars_callbacks

    manager = GraphManager()
    manager.add_node(_node("Fitness", type="Goal", website='["https://example.com"]'))
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_sidebars_callbacks(app)
    render = _callback(app, "render_goal_list")

    cards = render("tab-next", None, None, None, None, "manual", None, None,
                   {"left": "0px"})
    card = _find(cards, {"type": "goal-card", "index": "Fitness"})
    assert getattr(card, "data-node-menu") == "Fitness"
    assert getattr(card, "data-type") == "Goal"
    assert getattr(card, "data-website") == '["https://example.com"]'
    assert getattr(card, "data-goal-name") == "Fitness"


def test_view_details_leaves_the_tab_alone_when_already_there():
    import details_callbacks

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    details_callbacks.register_details_callbacks(app)
    navigate = _callback(app, "context_menu_details_navigate")

    assert navigate("Fitness|1", "tab-next") == ("tab-details", "Fitness")
    assert navigate("Fitness|1", "tab-details") == (dash.no_update, "Fitness")


def test_bulk_now_action_sets_mixed_selection_then_clears_all():
    manager = GraphManager()
    manager.add_node(_node("Already Now", now=1))
    manager.add_node(_node("Not Now"))
    callback = _callback(_app(), "handle_now_trigger")
    payload = json.dumps(["Already Now", "Not Now"]) + "|1"

    callback(payload)
    assert manager.get_node("Already Now").now > 0
    assert manager.get_node("Not Now").now > 0

    callback(payload)
    assert manager.get_node("Already Now").now == 0
    assert manager.get_node("Not Now").now == 0


