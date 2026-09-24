"""Structure contracts for the Events-tab layout."""

from datetime import date
from pathlib import Path

from events_layout import (
    DORMANT_COL_WIDTHS,
    build_dormant_nodes_table,
    build_event_card,
    dormant_delete_confirmation_body,
)
from models import Node
from config import BADGE_PALETTE
from models import STATUS_DONE


THEME_CSS = Path(__file__).resolve().parents[1] / "assets" / "theme.css"


def _node(name="Audio Engineering", dormant=1):
    """A dormant node by default -- every row in this table has one.

    The Node dataclass defaults `dormant` to 0, and the table now reads that
    flag to decide what a row says, so a test row that forgets it renders as
    Awake and quietly loses its actions.
    """
    return Node(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", dormant=dormant,
    )


def _row(name="Audio Engineering", *, delay_days=0, activated=False,
         dormant=1, **extra):
    row = {"node": _node(name, dormant=dormant), "delay_days": delay_days,
           "activated": activated}
    row.update(extra)
    return row


class _Event:
    """Just enough of an Event for the wake-date projection."""

    def __init__(self, trigger_date=None, trigger_nodes=None):
        self.trigger_date = trigger_date
        self.trigger_nodes = trigger_nodes or []


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
    table = build_dormant_nodes_table([_row()])

    row = table.children[1].children[0]
    actions = row.children[-1].children
    (edit_button, _edit_tip, move_button, _move_tip,
     delete_button, _delete_tip) = actions.children

    assert table.className.startswith("dormant-nodes-table")
    assert _header_labels(table) == ["Name", "Type", "Delay", "Wakes", "Actions"]
    assert table.children[0].children.children[-1].children.className == "visually-hidden"
    assert row.className == "dormant-node-row"
    assert "dormant-node-actions" in actions.className
    assert edit_button.className == "dormant-node-action-btn"
    assert move_button.className == "dormant-node-action-btn"
    assert "dormant-node-action-btn-danger" in delete_button.className
    assert edit_button.children[0].className == "bi bi-pencil"
    assert move_button.children[0].className == "bi bi-box-arrow-right"
    assert delete_button.children[0].className == "bi bi-trash3"
    assert edit_button.children[1].children == "Edit dormant node Audio Engineering"
    assert move_button.children[1].children == (
        "Move dormant node Audio Engineering to another event")
    assert delete_button.children[1].children == "Delete dormant node Audio Engineering"
    assert delete_button.id == {"type": "btn-delete-dormant-node",
                                "index": "Audio Engineering"}
    assert _delete_tip.children == "Delete node"
    assert not hasattr(edit_button, "title")
    assert not hasattr(delete_button, "title")


def _text(component):
    """Flattened visible text of a component tree."""
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return "".join(_text(c) for c in component)
    return _text(getattr(component, "children", None))


def test_delete_confirmation_names_the_node_and_says_it_is_permanent():
    body = _text(dormant_delete_confirmation_body("Audio Engineering"))

    assert "Audio Engineering" in body
    assert "permanently deleted from the graph" in body
    assert "cannot be undone" in body
    assert "move it to another event instead" in body


def test_an_awake_row_has_no_actions():
    """Gated per row, not per event."""
    table = build_dormant_nodes_table([_row(activated=True, dormant=0)])

    assert table.children[1].children[0].children[-1].children is None


def test_a_dormant_row_on_a_fired_event_keeps_its_actions():
    """The mirror case: a fired event still holds scheduled nodes, and the
    old per-event gate left them read-only."""
    table = build_dormant_nodes_table(
        [_row(delay_days=14, activation_date="2026-10-01")])

    assert table.children[1].children[0].children[-1].children is not None


def test_dormant_node_table_grid_does_not_move_between_events():
    """Two events with nothing in common still line their columns up.

    Column positions used to depend on the longest node name in whichever
    event was selected, and on whether that event happened to carry a delay
    or a mix of awake and dormant nodes.
    """
    plain = build_dormant_nodes_table([_row("A")])
    varied = build_dormant_nodes_table([
        _row("A rather long dormant node name indeed", delay_days=14),
        _row("Awake", activated=True, dormant=0),
    ])

    assert _header_labels(plain) == _header_labels(varied)
    assert _header_widths(plain) == _header_widths(varied)
    for table in (plain, varied):
        assert table.style["tableLayout"] == "fixed"
        assert _header_widths(table)[0] is None, "Name absorbs the leftover width"


def test_dormant_node_table_balances_metadata_spacing_and_action_room():
    assert set(DORMANT_COL_WIDTHS) == {"type", "delay", "wakes", "actions"}
    # Wakes holds a date, so it is the widest of the three metadata columns.
    widths = {k: int(v.removesuffix("px")) for k, v in DORMANT_COL_WIDTHS.items()}
    assert widths["wakes"] > widths["type"] > widths["delay"]
    # Three icons now, where there used to be two.
    assert widths["actions"] >= 84


def test_dormant_node_name_cell_truncates_but_keeps_the_full_name():
    long_name = "A rather long dormant node name indeed"
    table = build_dormant_nodes_table([_row(long_name)])

    name_cell = table.children[1].children[0].children[0]
    assert name_cell.className == "dormant-node-name-cell"
    assert name_cell.title == long_name
    assert name_cell.children == long_name


def test_dormant_node_table_mutes_a_default_delay_and_an_unknowable_date():
    table = build_dormant_nodes_table([_row()])

    _name, _type, delay, wakes, _actions = table.children[1].children[0].children
    assert delay.children.children == "None"
    assert delay.children.className == "text-muted"
    # A manual event cannot say when it will fire, so the answer is the
    # condition rather than a date -- and it recedes like any default.
    assert wakes.children.children == "On trigger"
    assert wakes.children.className == "text-muted"


def test_a_projected_wake_date_is_muted_and_a_committed_one_is_not():
    """Before an event fires its dates can still move, so they read as
    projections. A date written at firing is committed."""
    projected = build_dormant_nodes_table(
        [_row(delay_days=14)], _Event(trigger_date="2027-06-01"))
    committed = build_dormant_nodes_table(
        [_row(delay_days=14, activation_date="2027-10-01")])

    projected_cell = projected.children[1].children[0].children[3].children
    committed_cell = committed.children[1].children[0].children[3].children

    assert projected_cell.children == "Jun 15, 2027"
    assert projected_cell.className == "text-muted"
    assert committed_cell.children == "Oct 1, 2027"
    assert getattr(committed_cell, "className", None) is None
    assert committed_cell.title == "2027-10-01", "the full date stays reachable"


def test_a_wake_date_carries_its_year_after_a_comma():
    """This year needs no year at all; another year gets one, punctuated the
    way a date is normally written."""
    from events_layout import _format_wake_date

    this_year = date.today().replace(month=10, day=1)
    assert _format_wake_date(this_year.isoformat()) == "Oct 1"
    assert _format_wake_date(f"{date.today().year + 1}-10-01") == (
        f"Oct 1, {date.today().year + 1}")


def test_a_delay_without_a_knowable_date_reads_as_an_offset():
    table = build_dormant_nodes_table([_row(delay_days=30)])

    _name, _type, delay, wakes, _actions = table.children[1].children[0].children
    assert delay.children.children == "1 month"
    assert wakes.children.children == "1 month after"


def test_a_completion_event_cannot_project_a_date():
    """It fires on a node being Done, and nothing knows when that is."""
    table = build_dormant_nodes_table(
        [_row(delay_days=7)], _Event(trigger_nodes=["5k in 25 min"]))

    assert table.children[1].children[0].children[3].children.children == "1 week after"


def test_an_awake_row_takes_the_badge():
    table = build_dormant_nodes_table([_row("Awake", activated=True, dormant=0)])

    badge = table.children[1].children[0].children[3].children
    assert badge.children == "Awake"
    # Was color="success" (stock Bootstrap #198754), which read as a different
    # green from the Done badge one table over. The palette's EventTriggered
    # is the shared "this fired" value.
    assert badge.className == "badge"
    assert badge.style["backgroundColor"] == BADGE_PALETTE['EventTriggered'][0]
    assert badge.style["backgroundColor"] == BADGE_PALETTE[STATUS_DONE][0]


def test_an_awake_row_reads_awake():
    table = build_dormant_nodes_table(
        [_row("Find a Piano Teacher", activated=False, dormant=0)])

    badge = table.children[1].children[0].children[3].children
    assert badge.children == "Awake"


def test_a_one_year_delay_reads_as_one_year():
    """365 % 30 == 5 and 365 % 7 == 1, so the table's own formatter used to
    fall through to days while the edit form said "1 year"."""
    table = build_dormant_nodes_table([_row(delay_days=365)])

    assert table.children[1].children[0].children[2].children.children == "1 year"


def test_dormant_node_actions_are_visible_on_intent_and_for_touch():
    css = THEME_CSS.read_text(encoding="utf-8")

    assert "opacity: 0;" in _css_rule(css, ".dormant-nodes-table .dormant-node-actions")
    assert ".dormant-node-row:hover .dormant-node-actions," in css
    assert ".dormant-node-actions:has(.dormant-node-action-btn:focus-visible)" in css
    assert ".dormant-node-row:focus-within .dormant-node-actions" not in css
    assert "@media (hover: none), (pointer: coarse)" in css


def test_dormant_node_name_cell_clips_with_an_ellipsis():
    css = THEME_CSS.read_text(encoding="utf-8")
    rule = _css_rule(css, ".dormant-nodes-table .dormant-node-name-cell")

    assert "overflow: hidden;" in rule
    assert "text-overflow: ellipsis;" in rule
    assert "white-space: nowrap;" in rule


def test_event_card_description_keeps_full_text_and_clamps_to_three_lines():
    description = "A deliberately long description " * 12
    card = build_event_card(
        "Trip", description, "Pending", {"total": 1, "activated": 0}
    )
    description_node = card.children[1]

    assert description_node.children == description
    assert "event-card-description" in description_node.className
    assert "d-block" not in description_node.className

    css = THEME_CSS.read_text(encoding="utf-8")
    rule = _css_rule(css, ".event-card-description")
    assert "display: -webkit-box;" in rule
    assert "-webkit-box-orient: vertical;" in rule
    assert "-webkit-line-clamp: 3;" in rule
    assert "overflow: hidden;" in rule
