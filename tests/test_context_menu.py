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


def test_shared_menu_groups_actions_by_intent():
    from layout import build_app_layout

    menu = _find(build_app_layout([], env="sandbox"), "node-context-menu")
    item_ids = [
        getattr(child, "id", None)
        for child in menu.children
        if getattr(child, "id", None)
    ]
    assert item_ids == [
        "ctx-menu-edit",
        "ctx-menu-details",
        "ctx-menu-explain",
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
    assert getattr(now_row, "data-website") == '["https://example.com"]'
    assert getattr(now_row, "data-status") == "Open"
    assert getattr(now_row, "data-now") == "1"


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


