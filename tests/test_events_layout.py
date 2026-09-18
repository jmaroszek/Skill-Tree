"""Structure contracts for the Events-tab layout."""

from pathlib import Path

from events_layout import build_dormant_nodes_table
from models import Node


THEME_CSS = Path(__file__).resolve().parents[1] / "assets" / "theme.css"


def _node(name="Audio Engineering"):
    return Node(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open",
    )


def _header_labels(table):
    labels = []
    for cell in table.children[0].children.children:
        child = cell.children
        labels.append(child.children if hasattr(child, "className") else child)
    return labels


def test_dormant_node_table_uses_progressively_disclosed_direct_actions():
    table = build_dormant_nodes_table(
        [{"node": _node(), "delay_days": 0, "activated": False}],
        "Pending",
    )

    row = table.children[1].children[0]
    actions = row.children[-1].children
    edit_button, _edit_tooltip, remove_button, _remove_tooltip = actions.children

    assert table.className.startswith("dormant-nodes-table")
    assert _header_labels(table) == ["", "Name", "Type", "Actions"]
    assert table.children[0].children.children[-1].children.className == "visually-hidden"
    assert row.className == "dormant-node-row"
    assert "dormant-node-actions" in actions.className
    assert edit_button.className == "dormant-node-action-btn"
    assert "dormant-node-action-btn-danger" in remove_button.className
    assert edit_button.children[0].className == "bi bi-pencil"
    assert remove_button.children[0].className == "bi bi-x-lg"
    assert edit_button.children[1].children == "Edit dormant node Audio Engineering"
    assert remove_button.children[1].children == "Remove dormant node Audio Engineering"
    assert not hasattr(edit_button, "title")
    assert not hasattr(remove_button, "title")


def test_triggered_dormant_node_table_has_no_row_actions():
    table = build_dormant_nodes_table(
        [{"node": _node(), "delay_days": 0, "activated": True}],
        "Triggered",
    )

    assert table.children[1].children[0].children[-1].children is None


def test_dormant_node_table_shows_a_uniform_non_default_delay():
    table = build_dormant_nodes_table(
        [
            {"node": _node("A"), "delay_days": 14, "activated": False},
            {"node": _node("B"), "delay_days": 14, "activated": False},
        ],
        "Pending",
    )

    assert _header_labels(table) == ["", "Name", "Type", "Delay", "Actions"]


def test_dormant_node_table_shows_status_for_mixed_activation():
    table = build_dormant_nodes_table(
        [
            {"node": _node("Sleeping"), "delay_days": 0, "activated": False},
            {"node": _node("Awake"), "delay_days": 0, "activated": True},
        ],
        "Triggered",
    )

    assert _header_labels(table) == ["", "Name", "Type", "Status", "Actions"]


def test_dormant_node_actions_are_visible_on_intent_and_for_touch():
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".dormant-nodes-table .dormant-node-actions {\n    opacity: 0;" in css
    assert ".dormant-node-row:hover .dormant-node-actions," in css
    assert ".dormant-node-actions:focus-within" in css
    assert ".dormant-node-row:focus-within .dormant-node-actions" not in css
    assert "@media (hover: none), (pointer: coarse)" in css
