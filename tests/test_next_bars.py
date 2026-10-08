"""The Next priority bar: tinted fill, solid edge, capped length."""

import pytest

from callback_helpers import (BAR_FILL_PERCENT, BAR_MIN_WIDTH, BAR_ROW_GAP, META_GAP,
                              NAME_MAX_WIDTH, NAME_MIN_WIDTH, RANK_TRACK_WIDTH,
                              format_suggestions_table)
from config import BADGE_PALETTE
from graph_manager import GraphManager
from models import Node


@pytest.fixture
def mgr():
    return GraphManager()


def _table(mgr, *specs):
    nodes = []
    for name, type_, score in specs:
        fields = dict(name=name, type=type_, description="", value=5, time_o=1,
                      time_m=2, time_p=4, interest=5, difficulty=5, status="Open",
                      context="Mind")
        mgr.add_node(Node(**fields))
        nodes.append(Node(**fields, priority_score=score))
    return format_suggestions_table(nodes, mgr)[0]


def _rows(mgr, *specs):
    return _table(mgr, *specs).children


def _bar_fill(row):
    return row.children[2].children


def test_a_bar_is_tinted_with_a_solid_edge_in_its_type_colour(mgr):
    learn, action = _rows(mgr, ("Study", "Learn", 10), ("Practise", "Action", 8))

    for row, type_ in ((learn, "Learn"), (action, "Action")):
        color = BADGE_PALETTE[type_][0]
        style = _bar_fill(row).style
        assert style["background"] == f"color-mix(in srgb, {color} {BAR_FILL_PERCENT}%, transparent)"
        assert style["boxShadow"] == f"inset -3px 0 0 {color}"


def test_the_rows_share_one_grid_whose_name_column_fits_its_names(mgr):
    table = _table(mgr, ("Study", "Learn", 10), ("Practise", "Action", 8))

    assert table.style["display"] == "grid"
    assert table.style["gridTemplateColumns"] == (
        f"{RANK_TRACK_WIDTH}px fit-content({NAME_MAX_WIDTH}px) "
        f"minmax({BAR_MIN_WIDTH}px, 1fr) auto")
    for row in table.children:
        assert row.style["gridTemplateColumns"] == "subgrid"
        assert row.children[1].style["minWidth"] == f"{NAME_MIN_WIDTH}px"


def test_the_row_spaces_its_columns_and_its_meta_items(mgr):
    (row,) = _rows(mgr, ("Study", "Learn", 10))

    assert row.style["gap"] == f"{BAR_ROW_GAP}px"
    assert row.children[3].style["gap"] == f"{META_GAP}px"
