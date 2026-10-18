"""Structure contracts for the Reflection review-history table."""

import json
import shutil
import subprocess
from types import SimpleNamespace

import dash
import pytest

from skilltree.domain.models import Node
from skilltree.features.review.callbacks import register_review_callbacks
from skilltree.features.review.callbacks import (
    _build_history_table,
    _rating_change_magnitude,
    _sort_history_nodes,
    _visible_excluded_count,
    _pager,
    _visible_history_count,
)
from skilltree.features.review.layout import build_review_hub_modal
from skilltree.features.review.layout import build_calibration_dismissed_view
from skilltree.features.review.layout import build_pending_preview
from skilltree.features.review.layout import excluded_summary
from skilltree.features.review.layout import pending_label
from support.clientside import clientside_source
from support.graphs import make_node
from support.paths import asset_file


THEME_CSS = asset_file("theme.css")


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


def _reflect_sections(modal):
    pending = modal.children[1].children.children[0]
    return pending.children[0].children


def test_reflection_modal_has_the_short_queue_copy_and_stable_narrow_width():
    modal = build_review_hub_modal()
    queue, empty, excluded = _reflect_sections(modal)
    head, description, preview = queue.children

    assert modal.dialog_class_name == "review-hub-dialog"
    assert modal.children[1].class_name == "review-hub-body"
    css = THEME_CSS.read_text(encoding="utf-8")
    assert ".review-hub-dialog {\n    max-width: 980px;" in css
    assert ".review-hub-dialog .modal-content {\n    height:" in css
    assert description.children == "Walk through completed nodes that haven't been reflected on yet."
    assert empty.children[0].className == "bi bi-check-circle reflect-empty-icon"
    assert empty.children[1].children == "All caught up"
    # The History list fades while more rows sit below; its pager is outside it.
    assert ".scroll-fade-bottom,\n.review-history-scroll {" in css
    tabs = modal.children[1].children.children
    assert [tab.label for tab in tabs] == ["Reflect", "History"]
    # The queue is a card led by its count, with the launch button beside it,
    # so hiding the card hides the button too.
    assert queue.id == "hub-pending-summary"
    assert queue.className == "reflect-queue-card"
    count_block, launch = head.children
    assert count_block.children[0].id == "hub-pending-count"
    assert launch.id == "btn-hub-pending-launch"
    assert preview.id == "hub-pending-list"
    # Excluded is one divider line at the bottom of the frame, its list folded
    # away, so the queue leads however long the list grows.
    assert excluded.className == "reflect-excluded"
    assert ".reflect-excluded {\n    margin-top: auto;" in css
    divider, body = excluded.children
    assert divider.className == "events-triggered-divider"
    summary, _dot, toggle = divider.children[1].children
    assert summary.id == "hub-excluded-summary"
    assert toggle.id == "hub-excluded-toggle"
    assert toggle.className == "events-triggered-toggle"
    assert body.id == "hub-excluded-body"
    assert body.style == {"display": "none"}
    assert excluded_summary(1) == "1 excluded node"
    assert excluded_summary(50) == "50 excluded nodes"


def test_excluded_toggle_opens_on_click_and_folds_when_the_modal_opens():
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required to run the clientside callback")
    app = dash.Dash(__name__)
    register_review_callbacks(app, SimpleNamespace(graph=None, events=None))
    source, namespace, name = clientside_source(app, "hub-excluded-body.style")

    def run(trigger, display):
        script = (
            "global.window = {dash_clientside: {}};\n" + source + "\n"
            f"window.dash_clientside.callback_context = {{triggered_id: {json.dumps(trigger)}}};\n"
            f"const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];\n"
            f"console.log(JSON.stringify(fn(1, true, {{display: {json.dumps(display)}}})));"
        )
        result = subprocess.run([node_binary, "-e", script], capture_output=True,
                                text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert run("hub-excluded-toggle", "none") == [{"display": "block"}, "hide", "true"]
    assert run("hub-excluded-toggle", "block") == [{"display": "none"}, "show", "false"]
    assert run("modal-review-hub", "block") == [{"display": "none"}, "show", "false"]


def test_queue_preview_names_the_first_few_with_their_type():
    nodes = [make_node(f"Node {index}", type="Action") for index in range(10)]
    rows = build_pending_preview(nodes, limit=8)

    assert len(rows) == 9
    dot, name = rows[0].children
    assert dot.className == "reflect-type-dot"
    assert dot.title == "Action"
    assert dot.style["backgroundColor"].startswith("#")
    assert name.children == "Node 0"
    assert rows[-1].children == "+2 more"
    assert len(build_pending_preview(nodes[:3], limit=8)) == 3
    assert pending_label(1) == "completed node waiting"
    assert pending_label(3) == "completed nodes waiting"


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
    assert cells[0].children[0].children[0].children == node.name
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


def test_a_bracket_without_a_best_estimate_has_an_actual_time():
    # History showed a dash for it, while Analyze plotted it.
    from skilltree.features.analyze.data import compute_estimation_accuracy
    from skilltree.features.review.callbacks import _fmt_delta_hours, _fmt_hours
    bracket = _reviewed_node("Bracket")
    bracket.time_o = bracket.time_m = bracket.time_p = 80
    bracket.actual_time_point = None
    bracket.actual_time_lower, bracket.actual_time_upper = 207.8, 552.5
    point = _reviewed_node("Point")
    point.time_o = point.time_m = point.time_p = 80
    point.actual_time_point = 100

    analyzed = {row["name"]: row["actual"]
                for row in compute_estimation_accuracy([bracket, point])}
    actual = bracket.actual_time
    assert actual == analyzed["Bracket"] > 300

    cells = _build_history_table([bracket]).children[1].children[0].children
    assert cells[2].children == _fmt_hours(actual)
    assert cells[3].children == _fmt_delta_hours(actual, 80)
    assert [n.name for n in _sort_history_nodes(
        [point, bracket], {"key": "actual", "direction": "desc"})] == ["Bracket", "Point"]
    assert [n.name for n in _sort_history_nodes(
        [point, bracket], {"key": "delta_time", "direction": "asc"})] == ["Point", "Bracket"]


def test_a_node_with_no_captured_time_has_no_actual_time():
    node = _reviewed_node()
    node.actual_time_point = None
    assert node.actual_time is None


def test_history_show_more_batches_and_filter_resets():
    assert _visible_history_count('modal-review-hub', 60, 73) == 20
    assert _visible_history_count('hub-history-show-more', 20, 73) == 40
    assert _visible_history_count('hub-history-show-more', 60, 73) == 73
    assert _visible_history_count('hub-history-search', 60, 7) == 7
    assert _visible_history_count('hub-history-sort', 40, 73) == 40


def test_excluded_rows_reveal_twenty_at_a_time_and_clamp_after_restore():
    nodes = [make_node(f'Node {index:02d}') for index in range(47)]
    first, total = build_calibration_dismissed_view(nodes, limit=20)
    assert total == 47
    assert len(first.children) == 20
    _dot, name, restore = first.children[0].children
    assert name.children == 'Node 00'
    assert restore.children == 'Restore'
    assert restore.id == {'type': 'calibration-restore', 'index': 'Node 00'}
    assert _visible_excluded_count('modal-review-hub', 40, total) == 20
    assert _visible_excluded_count('hub-excluded-show-more', 20, total) == 40
    assert _visible_excluded_count('hub-excluded-show-more', 40, total) == 47
    assert _visible_excluded_count({'type': 'calibration-restore', 'index': 'Node 00'},
                                   40, 39) == 39


def test_history_pager_matches_the_events_triggered_divider():
    modal = build_review_hub_modal()
    history = modal.children[1].children.children[1]
    pager = history.children[0].children[-1]
    assert "events-triggered-divider" in pager.className
    rule, sentence, _ = pager.children
    assert rule.className == "events-triggered-rule"
    status, more = sentence.children
    assert status.id == "hub-history-page-status"
    assert more.children[0] == " · "
    assert more.children[1].children == "show more"
    assert more.children[1].className == "events-triggered-toggle"


def test_the_pager_only_appears_when_there_is_more_to_show():
    shown = {'display': 'flex'}, {'display': 'inline'}
    hidden = {'display': 'none'}, {'display': 'none'}

    assert _pager(20, 73, 'reflections') == ('Showing 20 of 73 reflections', *shown)
    # Nothing left to reveal, so nothing to say: no "Showing 1 of 1".
    assert _pager(1, 1, 'nodes') == ('', *hidden)
    assert _pager(20, 20, 'nodes') == ('', *hidden)
    assert _pager(73, 73, 'reflections') == ('', *hidden)


def test_the_pager_stops_counting_past_a_hundred():
    assert _pager(20, 100, 'reflections')[0] == 'Showing 20 of 100 reflections'
    assert _pager(20, 101, 'reflections')[0] == 'Showing 20 of many'
    assert _pager(100, 165, 'nodes')[0] == 'Showing 100 of many'


def test_notes_preview_is_capped_at_a_word_boundary():
    from skilltree.features.review.callbacks import NOTES_PREVIEW_CHARS, _notes_preview

    assert _notes_preview("Short\nnote") == "Short note"
    long = "word " * 100
    preview = _notes_preview(long)
    assert preview.endswith("…") and len(preview) <= NOTES_PREVIEW_CHARS + 1
    assert preview[:-1].split(" ")[-1] == "word"
