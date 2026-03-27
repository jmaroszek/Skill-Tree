"""
Layout definitions for the Simulate tab.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


def build_simulate_tab_content():
    """Builds the Simulate tab UI with node selector and Monte Carlo results."""

    # --- Left Panel: Controls ---
    controls_panel = html.Div([
        html.H4("Simulate", className="mb-3 mt-3"),

        # Node selector
        dbc.Label("Select Node", className="mb-1"),
        dcc.Dropdown(
            id="sim-node-select",
            placeholder="Search for a node...",
            className="mb-3",
        ),

        # Dependency options
        html.H6("Dependency Options", className="mb-2 mt-2"),
        dbc.Checklist(
            id="sim-include-soft",
            options=[{"label": "Include soft dependents", "value": "yes"}],
            value=[],
            switch=True,
            className="mb-2",
        ),
        dbc.Checklist(
            id="sim-include-helps",
            options=[{"label": "Include synergies", "value": "yes"}],
            value=[],
            switch=True,
            className="mb-3",
        ),

        # Run button
        dbc.Button("Run Simulation", id="btn-run-sim", color="primary",
                   className="w-100 mb-4", size="lg"),

        # Chain summary
        html.Div(id="sim-chain-list"),

    ], style={
        "width": "380px",
        "minWidth": "340px",
        "borderRight": "1px solid #495057",
        "display": "flex",
        "flexDirection": "column",
        "padding": "0 20px",
        "overflow": "visible",
    })

    # --- Right Panel: Results ---
    results_panel = html.Div([
        # Empty state
        html.Div(
            id="sim-empty",
            children=[
                html.Div([
                    html.H5("No Simulation Run", className="text-muted mb-2"),
                    html.P("Select a node and click Run Simulation to see the time distribution.",
                           className="text-muted"),
                ], style={"textAlign": "center", "marginTop": "20vh"})
            ],
        ),

        # Results container (hidden until simulation runs)
        html.Div(id="sim-results-container", style={"display": "none"}, children=[
            html.H5(id="sim-title", className="mb-3 mt-3"),

            # Chart
            dcc.Graph(
                id="sim-chart",
                config={"displayModeBar": False},
                style={"height": "400px"},
            ),

            # Stats row
            html.Div(id="sim-stats", className="mt-2"),
        ]),
    ], style={
        "flex": "1",
        "padding": "0 24px",
        "overflowY": "auto",
    })

    return html.Div([
        controls_panel,
        results_panel,
    ], style={
        "display": "flex",
        "height": "100%",
        "width": "100%",
    })
