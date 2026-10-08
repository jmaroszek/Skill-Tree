"""The Next priority bar: tinted fill, solid edge, capped length."""

import pytest

from callback_helpers import BAR_FILL_PERCENT, BAR_MAX_WIDTH, format_suggestions_table
from config import BADGE_PALETTE
from graph_manager import GraphManager
from models import Node


@pytest.fixture
def mgr():
    return GraphManager()


def _rows(mgr, *specs):
    nodes = []
    for name, type_, score in specs:
        fields = dict(name=name, type=type_, description="", value=5, time_o=1,
                      time_m=2, time_p=4, interest=5, difficulty=5, status="Open",
                      context="Mind")
        mgr.add_node(Node(**fields))
        nodes.append(Node(**fields, priority_score=score))
    return format_suggestions_table(nodes, mgr)[0].children


def _bar_fill(row):
    return row.children[2].children


def test_a_bar_is_tinted_with_a_solid_edge_in_its_type_colour(mgr):
    learn, action = _rows(mgr, ("Study", "Learn", 10), ("Practise", "Action", 8))

    for row, type_ in ((learn, "Learn"), (action, "Action")):
        color = BADGE_PALETTE[type_][0]
        style = _bar_fill(row).style
        assert style["background"] == f"color-mix(in srgb, {color} {BAR_FILL_PERCENT}%, transparent)"
        assert style["boxShadow"] == f"inset -3px 0 0 {color}"


def test_the_bar_column_is_capped_at_three_and_a_half_name_columns(mgr):
    (row,) = _rows(mgr, ("Study", "Learn", 10))

    assert BAR_MAX_WIDTH == 3.5 * 250
    assert f"minmax(240px, {BAR_MAX_WIDTH}px)" in row.style["gridTemplateColumns"]
