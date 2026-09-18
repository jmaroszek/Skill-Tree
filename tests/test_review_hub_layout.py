"""Structure contracts for the Reflection review-history table."""

from pathlib import Path

from models import Node
from review_hub_callbacks import _build_history_table


THEME_CSS = Path(__file__).resolve().parents[1] / "assets" / "theme.css"


def _reviewed_node(name="Reflected node"):
    node = Node(
        name=name,
        type="Learn",
        description="",
        value=5,
        time_o=1,
        time_m=2,
        time_p=4,
        interest=5,
        difficulty=5,
        status="Done",
    )
    node.actual_time_point = 3
    node.reflect_value = 6
    node.reflect_interest = 7
    node.reflect_difficulty = 4
    return node


def test_review_history_uses_the_shared_pencil_treatment():
    table = _build_history_table([_reviewed_node()])
    row = table.children[1].children[0]
    action_group = row.children[-1].children
    edit_button, tooltip = action_group.children

    assert "review-history-table" in table.className
    assert row.className == "review-history-row"
    assert action_group.className == "review-history-actions"
    assert edit_button.className == "review-history-edit-btn"
    assert edit_button.children[0].className == "bi bi-pencil"
    assert edit_button.children[1].children == "Edit reflection for Reflected node"
    assert tooltip.children == "Edit reflection"


def test_review_history_edit_actions_reveal_on_row_intent_and_touch():
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".review-history-table .review-history-actions" in css
    assert ".review-history-row:hover .review-history-actions" in css
    assert ".review-history-actions:focus-within" in css
    assert "@media (hover: none), (pointer: coarse)" in css
