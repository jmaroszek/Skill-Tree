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


def _css_rule(css, selector):
    """Returns the declaration block of the rule with exactly this selector."""
    marker = selector + " {"
    assert marker in css, selector
    start = css.index(marker) + len(marker)
    return css[start:css.index("}", start)]


def _header_widths(table):
    return [
        (cell.style or {}).get("width") if hasattr(cell, "style") else None
        for cell in table.children[0].children.children
    ]


def test_dormant_node_table_uses_progressively_disclosed_direct_actions():
    table = build_dormant_nodes_table(
        [{"node": _node(), "delay_days": 0, "activated": False}],
        "Pending",
    )

    row = table.children[1].children[0]
    actions = row.children[-1].children
    edit_button, _edit_tooltip, remove_button, _remove_tooltip = actions.children

    assert table.className.startswith("dormant-nodes-table")
    assert _header_labels(table) == ["", "Name", "Type", "Delay", "Status", "Actions"]
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


def test_dormant_node_table_grid_does_not_move_between_events():
    """Two events with nothing in common still line their columns up.

    Column positions used to depend on the longest node name in whichever
    event was selected, and on whether that event happened to carry a delay
    or a mix of awake and dormant nodes.
    """
    plain = build_dormant_nodes_table(
        [{"node": _node("A"), "delay_days": 0, "activated": False}],
        "Pending",
    )
    varied = build_dormant_nodes_table(
        [
            {"node": _node("A rather long dormant node name indeed"),
             "delay_days": 14, "activated": False},
            {"node": _node("Awake"), "delay_days": 0, "activated": True},
        ],
        "Pending",
    )

    assert _header_labels(plain) == _header_labels(varied)
    assert _header_widths(plain) == _header_widths(varied)
    for table in (plain, varied):
        assert table.style["tableLayout"] == "fixed"
        assert _header_widths(table)[1] is None, "Name absorbs the leftover width"


def test_dormant_node_name_cell_truncates_but_keeps_the_full_name():
    long_name = "A rather long dormant node name indeed"
    table = build_dormant_nodes_table(
        [{"node": _node(long_name), "delay_days": 0, "activated": False}],
        "Pending",
    )

    name_cell = table.children[1].children[0].children[1]
    assert name_cell.className == "dormant-node-name-cell"
    assert name_cell.title == long_name
    assert name_cell.children == long_name


def test_dormant_node_table_mutes_default_delay_and_status():
    table = build_dormant_nodes_table(
        [{"node": _node(), "delay_days": 0, "activated": False}],
        "Pending",
    )

    _select, _name, _type, delay, status, _actions = table.children[1].children[0].children
    assert delay.children.children == "None"
    assert delay.children.className == "text-muted"
    assert status.children.children == "Dormant"
    assert status.children.className == "text-muted"


def test_dormant_node_table_gives_non_default_delay_and_status_full_contrast():
    table = build_dormant_nodes_table(
        [
            {"node": _node("Delayed"), "delay_days": 14, "activated": False,
             "activation_date": "2026-10-01"},
            {"node": _node("Awake"), "delay_days": 0, "activated": True},
        ],
        "Pending",
    )

    delayed_row, awake_row = table.children[1].children
    delay_text, scheduled = delayed_row.children[3].children
    assert delay_text.children == "2 weeks"
    assert scheduled.children == "Scheduled: 2026-10-01"
    assert awake_row.children[4].children.children == "Awake"
    assert awake_row.children[4].children.color == "success"


def test_dormant_node_actions_are_visible_on_intent_and_for_touch():
    css = THEME_CSS.read_text(encoding="utf-8")

    assert "opacity: 0;" in _css_rule(css, ".dormant-nodes-table .dormant-node-actions")
    assert ".dormant-node-row:hover .dormant-node-actions," in css
    assert ".dormant-node-actions:focus-within" in css
    assert ".dormant-node-row:focus-within .dormant-node-actions" not in css
    assert "@media (hover: none), (pointer: coarse)" in css


def test_dormant_select_checkbox_takes_the_whole_cell_as_its_hit_target():
    """The box stays 14px; the cell around it becomes clickable.

    dbc renders an empty label already carrying `for`, so stretching it over
    the cell is a native click target. The pointer cursor has to move with it:
    it used to sit on the .form-check wrapper, showing a pointer over the dead
    space beside the box while the box itself showed the default arrow.
    """
    css = THEME_CSS.read_text(encoding="utf-8")
    cell = ".dormant-nodes-table .dormant-node-select-cell"

    assert "position: relative;" in _css_rule(css, cell)

    label = _css_rule(css, cell + " .form-check-label")
    assert "position: absolute;" in label
    assert "inset: 0;" in label
    assert "cursor: pointer;" in label

    assert "cursor: pointer;" in _css_rule(css, cell + " .form-check-input")
    assert "cursor: default;" in _css_rule(css, cell + " .form-check")


def test_dormant_node_name_cell_clips_with_an_ellipsis():
    css = THEME_CSS.read_text(encoding="utf-8")
    rule = _css_rule(css, ".dormant-nodes-table .dormant-node-name-cell")

    assert "overflow: hidden;" in rule
    assert "text-overflow: ellipsis;" in rule
    assert "white-space: nowrap;" in rule
