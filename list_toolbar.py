"""Search-and-sort toolbar shared by the Goals and Events sidebars.

Each sidebar list gets a search field and, beside it, a sort button that opens
a floating menu. The chosen sort lives in a local-storage ``dcc.Store`` so it
survives a reload. The button's tooltip names the current sort, and the menu
marks it with a check.

``assets/sort_menu.js`` opens the menu under the button and writes the chosen
value to a hidden input. The clientside callbacks here copy that value into the
store and keep the tooltip and check marks in step with it. The menus
themselves are built in ``layout.py`` with the shared floating-menu helpers.
"""

from __future__ import annotations

import json
from typing import NamedTuple

from dash import Input, Output, dcc, html
import dash_bootstrap_components as dbc

from config import TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS


class SortMenu(NamedTuple):
    prefix: str
    store_id: str
    default: str
    options: tuple[tuple[str, str], ...]  # (value, label)

    @property
    def button_id(self) -> str:
        return f"{self.prefix}-sort-button"

    @property
    def menu_id(self) -> str:
        return f"{self.prefix}-sort-menu"

    @property
    def input_id(self) -> str:
        return f"{self.prefix}-sort-input"

    @property
    def tooltip_id(self) -> str:
        return f"{self.prefix}-sort-tooltip"

    def item_id(self, value: str) -> str:
        return f"{self.menu_id}-{value}"

    def label(self, value: str) -> str:
        return dict(self.options).get(value, dict(self.options)[self.default])


GOALS_SORT = SortMenu(
    prefix="goals",
    store_id="details-goal-sort",
    default="priority",
    options=(
        ("priority", "Priority"),
        ("time-desc", "Time"),
        ("manual", "Manual"),
        ("alpha-asc", "Alphabetical"),
    ),
)

EVENTS_SORT = SortMenu(
    prefix="events",
    store_id="events-sort-mode",
    default="type",
    options=(
        ("manual", "Manual"),
        ("az", "Alphabetical"),
        ("type", "Trigger Type"),
        ("impact", "Node Count"),
    ),
)

SORT_MENUS = (GOALS_SORT, EVENTS_SORT)

SEARCH_STYLE = {
    "backgroundColor": "#2b3035",
    "border": "1px solid #495057",
    "color": "#dee2e6",
    "borderRadius": "6px",
    "flex": "1",
    "minWidth": "0",
}

MENU_ITEM_CLASS = "ctx-menu-item"
MENU_ITEM_CHECKED_CLASS = "ctx-menu-item ctx-menu-item-checked"


def build_list_toolbar(search_input, sort: SortMenu):
    """The search field with the sort button beside it, plus the sort store."""
    return html.Div([
        search_input,
        html.Button(
            html.I(className="bi bi-arrow-down-up"),
            id=sort.button_id,
            type="button",
            className="btn btn-secondary btn-sm details-header-btn sort-menu-button",
            **{
                "aria-label": "Sort",
                "aria-haspopup": "menu",
                "data-sort-menu": sort.menu_id,
                "data-sort-input": sort.input_id,
            },
        ),
        dbc.Tooltip(
            f"Sort: {sort.label(sort.default)}",
            id=sort.tooltip_id,
            target=sort.button_id,
            placement="top",
            delay={"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS},
        ),
        dcc.Store(id=sort.store_id, storage_type="local", data=sort.default),
    ], className="d-flex align-items-center",
       style={"gap": "4px", "padding": "0 12px", "marginBottom": "12px"})


def sort_menu_items(sort: SortMenu):
    """(label children, item id) pairs for ``layout._menu_item``.

    Every row carries a check glyph so labels stay aligned; only the current
    sort's check is visible.
    """
    return [
        ([html.I(className="bi bi-check2 ctx-menu-check"), html.Span(label)],
         sort.item_id(value))
        for value, label in sort.options
    ]


def register_list_toolbar_callbacks(app) -> None:
    for sort in SORT_MENUS:
        values = [value for value, _ in sort.options]

        # A menu choice lands in the hidden input; copy it into the store.
        app.clientside_callback(
            f"""function(value) {{
                if ({json.dumps(values)}.indexOf(value) === -1) {{
                    return window.dash_clientside.no_update;
                }}
                return value;
            }}""",
            Output(sort.store_id, "data"),
            Input(sort.input_id, "value"),
            prevent_initial_call=True,
        )

        # The tooltip names the current sort and the menu checks it. A stored
        # value that is no longer an option reads as the default.
        app.clientside_callback(
            f"""function(current) {{
                var values = {json.dumps(values)};
                var labels = {json.dumps(dict(sort.options))};
                var active = values.indexOf(current) === -1 ? {json.dumps(sort.default)} : current;
                var classes = values.map(function(v) {{
                    return v === active ? {json.dumps(MENU_ITEM_CHECKED_CLASS)} : {json.dumps(MENU_ITEM_CLASS)};
                }});
                return ['Sort: ' + labels[active]].concat(classes);
            }}""",
            Output(sort.tooltip_id, "children"),
            *[Output(sort.item_id(value), "className") for value in values],
            Input(sort.store_id, "data"),
        )
