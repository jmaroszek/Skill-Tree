"""Showing the open tab's content and hiding the rest.

Every tab's layout stays mounted. A hidden tab keeps visibility: hidden as
well as display: none, so nothing in it takes focus or paints.
"""
from dash import Input, Output

from skilltree.ui.prerender import prerendered


def register_tab_callbacks(app, services=None):
    @app.callback(
        Output("next-tab-content", "style"),
        Output("canvas-tab-content", "style"),
        Output("details-tab-content", "style"),
        Output("events-tab-content", "style"),
        Output("analyze-tab-content", "style"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    @prerendered
    def toggle_tab_content(active_tab):
        base = {"width": "100%", "height": "100%", "overflow": "hidden", "position": "absolute", "top": "0", "left": "0"}
        next_style = {**base,
                      "display": "flex" if active_tab == "tab-next" else "none",
                      "flexDirection": "column",
                      "visibility": "visible" if active_tab == "tab-next" else "hidden"}
        canvas_style = {**base,
                        "display": "flex" if active_tab == "tab-canvas" else "none",
                        "visibility": "visible" if active_tab == "tab-canvas" else "hidden"}
        details_style = {**base,
                         "display": "flex" if active_tab == "tab-details" else "none",
                         "visibility": "visible" if active_tab == "tab-details" else "hidden"}
        events_style = {**base,
                        "display": "flex" if active_tab == "tab-events" else "none",
                        "visibility": "visible" if active_tab == "tab-events" else "hidden"}
        analyze_style = {**base, "overflow": "auto",
                         "display": "block" if active_tab == "tab-analyze" else "none",
                         "visibility": "visible" if active_tab == "tab-analyze" else "hidden"}
        return next_style, canvas_style, details_style, events_style, analyze_style
