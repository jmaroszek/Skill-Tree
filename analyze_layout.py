"""
Layout definition for the Analyze tab.
Provides a static shell; content is dynamically populated by analyze_callbacks.py.
"""

from dash import html


def build_analyze_tab_content():
    """Builds the static shell for the Analyze tab. Content is injected by callback."""
    return html.Div(
        id="analyze-content-container",
        children=[
            html.Div([
                html.H5("Analyze", className="text-muted"),
                html.P("Switch to this tab to load analytics.",
                       className="text-muted small"),
            ], style={"textAlign": "center", "marginTop": "20%"}),
        ],
        className="px-4 pt-3 pb-4",
    )
