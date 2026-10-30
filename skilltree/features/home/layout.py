"""The Home tab's layout."""
from dash import dcc
from dash import html
from skilltree.store import settings
from skilltree.ui import tokens
from skilltree.ui.kit import filter_chip
from skilltree.ui.kit import step_button
import dash_bootstrap_components as dbc


# The Next table fills the room beside the Description panel up to this width.
# Its basis is the narrowest it reads well, which is also where the panel drops
# below it.
NEXT_TABLE_MAX_WIDTH = 1500


NEXT_TABLE_BASIS = 780


def build_next_view():
    return html.Div([
        dcc.Store(id='suggestion-count-store', data=settings.NEXT_TABLE_ROWS.get()),
    
        # A new user's checklist (onboarding_callbacks.py); empty once done.
        html.Div(id="getting-started"),

        # "Now" section — currently-Now nodes (cap = settings.NOW_NODE_CAP.get()).
        # Heading + rows are emitted together by populate_now_section. The
        # section collapses to zero height when there are no Now nodes, so
        # the Next heading floats to the top of the tab.
        html.Div(id="now-nodes-table"),
    
        html.Div([
            html.H6("Next", className="text-muted mb-0", style=tokens.SECTION_TITLE_STYLE),
            dbc.ButtonGroup([
                step_button("btn-sugg-minus", "dash-lg", "Show fewer suggestions"),
                html.Span(id="suggestion-count-display", children=str(settings.NEXT_TABLE_ROWS.get()),
                           className="align-self-center mx-1",
                           style={"fontSize": tokens.FS_LG, "fontWeight": "bold", "minWidth": "18px",
                                  "textAlign": "center"}),
                step_button("btn-sugg-plus", "plus-lg", "Show more suggestions"),
            ], className="align-middle"),
            filter_chip("next-filter-chip"),
        ], className="d-flex align-items-center mb-2", style={"gap": tokens.SPACE_BLOCK}),
    
        dcc.Store(id='selected-suggestion-store', data=None),
        dcc.Store(id='focus-goal-store', data=None),
    
        # Next Table and Description side-by-side
        html.Div([
            html.Div(id="suggestions-table", children=[
                html.P("Loading suggestions...", className="text-muted mt-3")
            ], style={"flex": f"1 1 {NEXT_TABLE_BASIS}px", "minWidth": 0,
                      "maxWidth": f"{NEXT_TABLE_MAX_WIDTH}px"}),
        
            # Description area — populated when clicking a Now card or Next row.
            html.Div(id="next-description-area", children=[
                html.H6("Description", className="text-muted mb-2", style=tokens.SECTION_TITLE_STYLE),
                html.Div("Click a card or row to see its description", id="next-description-text", className="selectable",
                         style={"color": tokens.TEXT_DIM, "whiteSpace": "pre-wrap", "fontSize": tokens.FS_LG}),
                html.Div(id="next-relations"),
            ], style={"flex": "0 1 420px", "minWidth": "280px",
                      "paddingRight": "2.5rem", "boxSizing": "content-box"}),
        # Wraps under the table when the window is too narrow for both.
        ], style={"display": "flex", "flexWrap": "wrap", "alignItems": "flex-start",
                  "columnGap": "3rem", "rowGap": "2rem"}),
    ])
