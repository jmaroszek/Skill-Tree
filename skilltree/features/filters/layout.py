"""The Filters sidebar's layout."""
from dash import dcc
from dash import html
from skilltree.store.settings import SUPPORTED_NODE_TYPES
from skilltree.ui import tokens
from skilltree.ui.components.context_picker import build_multi_context_picker
from skilltree.ui.components.duration import unit_select
from skilltree.ui.kit import Tooltip
from skilltree.ui.kit import bullet_hint
from skilltree.ui.kit import hover_label
from skilltree.ui.kit import panel_close_button
from skilltree.ui.styles import SIDEBAR_WIDTH_PX
import dash_bootstrap_components as dbc


# Hover copy for the Filters sidebar's labels.
_FILTER_HINTS = {
    "filter_status": bullet_hint(
        "Which nodes the canvas shows:",
        "Show Done: include finished nodes.",
        "Show Dormant: include sleeping nodes."),
    "community": bullet_hint(
        "How nodes are grouped:",
        "Clusters: densely connected groups.",
        "Islands: groups with no edges to the rest.",
        "Orphans: nodes with no edges at all."),
}


# --- Filters sidebar (right) ---
def build_filters_content():
    # Filters are session state, never saved state. Every control below opens
    # at the value "Clear Filters" resets it to, so a restart always shows the
    # whole graph. A narrowing the user set weeks ago and forgot would quietly
    # scope every ranking the app produces, which is the one answer it exists
    # to give. Values here must stay in step with the clear_filters() callback.
    return html.Div([
        html.Div([
            html.H4("Filters", className="mb-0"),
            panel_close_button("btn-close-filters", "Close filters", large=True,
                               className_extra="float-end")
        ], className="d-flex justify-content-between align-items-center mb-1 mt-2"),

        html.H5("Search", className="mt-3", style={"marginBottom": "0.75rem"}),
        # The query applies on Enter or when the field loses focus, not per
        # keystroke: each change to a filter lays the canvas out again, and on
        # a large graph a layout per letter is the sluggishness to avoid. The
        # suggestions that open as you type are drawn by
        # assets/sidebars/filter_suggest.js; the glyphs inside the field by CSS.
        html.Div([
            dbc.Input(id="filter-text", type="text", value="", debounce=True,
                      placeholder="Filter by names and aliases...", autoComplete="off",
                      className="filter-search-input"),
            html.I(className="bi bi-arrow-return-left filter-search-enter",
                   title="Press Enter to apply"),
            html.Button(html.I(className="bi bi-x-lg"), id="btn-clear-filter-text",
                        type="button", className="filter-search-clear",
                        **{"aria-label": "Clear search"}),
        ], id="filter-search", className="editor-field-group filter-search"),
        # The field and the switch, as the one query every canvas filters by.
        # Derived clientside; see the callback beside clear_filters.
        dcc.Store(id="filter-search-query", data=None),
        # Off by default: a search matches names and aliases. The switch is
        # the same one the Status section uses.
        dbc.Checklist(
            options=[{"label": "Include descriptions", "value": "descriptions"}],
            value=[],
            id="filter-text-scope",
            switch=True,
            style={"marginTop": "0.75rem"},
        ),

        html.Hr(className="my-3"),

        html.H5("General", className="mt-2 mb-1"),
        dbc.Label("Context", className="mt-2"),
        build_multi_context_picker(
            "filter-context-picker",
            "filter-context",
            "filter-subcontext",
            context_value=[],
            subcontext_value=[],
        ),

        dbc.Label("Node Type", className="mt-2"),
        dcc.Dropdown(
            id="filter-node-type",
            options=[{"label": t, "value": t} for t in SUPPORTED_NODE_TYPES],
            value=[],
            multi=True,
            placeholder="All",
            className="text-dark",
        ),

        html.Hr(className="my-3"),

        html.H5("Ratings", className="mt-2 mb-1"),
        # Each rating is a two-handle range, [low, high]. Both ends at the
        # rails (1 and 10) means no filter.
        dbc.Label("Value", className="mt-2"),
        dcc.RangeSlider(min=1, max=10, step=1, value=[1, 10], id="filter-value",
                        marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Interest", className="mt-2"),
        dcc.RangeSlider(min=1, max=10, step=1, value=[1, 10], id="filter-interest",
                        marks={i: str(i) for i in range(1, 11)}),

        dbc.Label("Effort", className="mt-3"),
        dcc.RangeSlider(min=1, max=10, step=1, value=[1, 10], id="filter-difficulty",
                        marks={i: str(i) for i in range(1, 11)}),

        # A time range in one unit. Either end may be left empty; a minimum
        # above the maximum is flagged and filters nothing (see the
        # clientside callback beside clear_filters).
        dbc.Label("Time", className="mt-2"),
        html.Div([
            dbc.Input(id="filter-time-min", type="number", min=0,
                      value=None, placeholder="No min", size="sm",
                      className="flex-grow-1", style={"minWidth": 0}),
            html.Span("–", className="text-muted align-self-center"),
            dbc.Input(id="filter-time", type="number", min=0.1,
                      value=None, placeholder="No max", size="sm",
                      className="flex-grow-1", style={"minWidth": 0}),
            unit_select("filter-time-unit", value="hours", compact=True),
        ], className="d-flex gap-2"),

        html.Hr(className="my-3"),

        hover_label("Status", "filter-status-heading", _FILTER_HINTS["filter_status"],
                    component=html.H5, placement="left", className="mt-2 mb-1"),
        html.Div([
            dbc.Checklist(
                options=[{"label": "Show Done", "value": "show_done"}],
                value=[],
                id="filter-done",
                switch=True,
            ),
            dbc.Checklist(
                options=[{"label": "Show Dormant", "value": "show_dormant"}],
                value=[],
                id="filter-dormant",
                switch=True,
            ),
        ], className="d-flex gap-3 flex-wrap"),

        html.Hr(className="my-3"),

        html.H5("Communities", className="mt-2 mb-1"),
        hover_label("Detection Method", "community-method-label",
                    _FILTER_HINTS["community"], className="mt-2"),
        dbc.Select(id="community-method", options=[
            {"label": "Clusters", "value": "louvain"},
            {"label": "Islands", "value": "components"},
            {"label": "Orphans", "value": "orphans"},
        ], value="louvain"),

        dbc.Label("Community", className="mt-3"),
        dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),
        # The selected row's label and members, so a selection can follow its
        # cluster when the label changes (canvas_view.resolve_community).
        dcc.Store(id="community-memory-store", data=None),

        html.Hr(className="my-3"),
        # A filter change often leaves a layout worth re-running. This Settle
        # carries no layout of its own: assets/sidebars/filters_sidebar.js clicks the
        # Settle in the graph-settings panel of the canvas on screen, so it
        # behaves exactly like that one, Freeze included.
        html.Div([
            dbc.Button("Settle", id="btn-sidebar-relayout", color="secondary", size="sm", className="flex-fill"),
            Tooltip("Re-run layout physics on the graph on screen",
                    target="btn-sidebar-relayout", placement="top"),
            dbc.Button("Clear Filters", id="btn-clear-filters", color="secondary", size="sm", className="flex-fill"),
        ], className="d-flex gap-2 mb-3"),
    ], className="px-3 pb-2 pt-0", style={"width": SIDEBAR_WIDTH_PX, "minWidth": SIDEBAR_WIDTH_PX})


def build_filters_sidebar():
    """Container Div for the filters overlay (right, closed initially)."""
    return html.Div(
        id="sidebar-filters-container",
        children=[build_filters_content()],
        style={
            "position": "absolute",
            "top": "0",
            "right": "0px",
            "transform": "translateX(100%)",
            "width": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderLeft": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL
        }
    )
