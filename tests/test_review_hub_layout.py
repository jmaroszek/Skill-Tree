"""Structure contracts for the Reflection review-history table."""

from pathlib import Path

from models import Node
from review_hub_callbacks import (
    _build_history_table,
    _rating_change_magnitude,
    _sort_history_nodes,
    _visible_history_count,
)
from review_hub_layout import build_review_hub_modal


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


def test_reflection_modal_has_the_short_queue_copy_and_stable_narrow_width():
    modal = build_review_hub_modal()
    pending = modal.children[1].children.children[0]
    description = pending.children[0].children[0]
    empty = pending.children[0].children[2]

    assert modal.dialog_style == {"maxWidth": "940px"}
    assert description.children == "Walk through completed nodes that haven't been reflected on yet"
    assert empty.children == "All caught up"


def test_review_history_summary_keeps_full_names_and_rating_comparison_accessible():
    node = _reviewed_node("A very long reflection node name")
    table = _build_history_table([node],
                                 {"key": "delta_ratings", "direction": "desc"})
    headings = table.children[0].children.children
    cells = table.children[1].children[0].children

    assert len(headings) == len(cells) == 6
    assert [heading.children[0].children[0] if isinstance(heading.children, list)
            else heading.children.children[0] for heading in headings[:-1]] == [
        "Name", "Est Time", "Actual", "Δ Time", "Δ Ratings"]
    assert headings[4].to_plotly_json()["props"]["aria-sort"] == "descending"
    assert cells[0].children[0].children == node.name
    assert cells[0].children[0].tabIndex == 0
    assert cells[0].children[1].children == node.name
    assert cells[4].children[0].children == "+1/+2/−1"
    assert "Estimated V/I/E: 5/5/5" in cells[4].children[1].children
    assert "Actual V/I/E: 6/7/4" in cells[4].children[1].children


def test_history_sorts_numeric_time_and_rating_change_with_missing_last():
    short = _reviewed_node("Short")
    short.time_o = short.time_m = short.time_p = 8
    short.actual_time_point = 4
    short.reflect_value = 5
    short.reflect_interest = 5
    short.reflect_difficulty = 5

    long = _reviewed_node("Long")
    long.time_o = long.time_m = long.time_p = 80
    long.actual_time_point = 100
    long.reflect_value = 9
    long.reflect_interest = 2
    long.reflect_difficulty = 1

    missing = _reviewed_node("Missing")
    missing.time_mode = "inherited"
    missing.actual_time_point = None
    missing.reflect_value = None

    nodes = [missing, long, short]
    assert [n.name for n in _sort_history_nodes(
        nodes, {"key": "estimated", "direction": "asc"})] == [
            "Short", "Long", "Missing"]
    assert [n.name for n in _sort_history_nodes(
        nodes, {"key": "delta_time", "direction": "desc"})] == [
            "Long", "Short", "Missing"]
    assert _rating_change_magnitude(long) == 11
    assert [n.name for n in _sort_history_nodes(
        nodes, {"key": "delta_ratings", "direction": "desc"})] == [
            "Long", "Short", "Missing"]
    assert [n.name for n in _sort_history_nodes(
        nodes, {"key": "delta_ratings", "direction": "asc"})] == [
            "Short", "Long", "Missing"]


def test_history_show_more_batches_and_filter_resets():
    assert _visible_history_count('modal-review-hub', 60, 73) == 20
    assert _visible_history_count('hub-history-show-more', 20, 73) == 40
    assert _visible_history_count('hub-history-show-more', 60, 73) == 73
    assert _visible_history_count('hub-history-search', 60, 7) == 7
    assert _visible_history_count('hub-history-sort', 40, 73) == 40
