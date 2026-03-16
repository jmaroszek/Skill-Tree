"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from constants import NODE_TYPES, NODE_STATUSES, CONTEXTS, EFFORT_OPTIONS


# --- Cytoscape Stylesheet ---

stylesheet = [
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'background-color': 'data(color)',
            'shape': 'data(shape)',
            'color': '#fff',
            'text-outline-width': 2,
            'text-outline-color': '#555',
            'width': 60,
            'height': 60,
        }
    },
    {
        'selector': 'node:selected',
        'style': {
            'background-color': '#0dcaf0',
            'border-width': 4,
            'border-color': '#055160'
        }
    },
    {
        'selector': 'edge',
        'style': {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#888',
            'line-color': '#888',
            'width': 2
        }
    },
    {
        'selector': '[type = "Helps"]',
        'style': {
            'source-arrow-shape': 'triangle',
            'source-arrow-color': '#0d6efd',
            'target-arrow-color': '#0d6efd',
            'line-color': '#0d6efd',
            'line-style': 'solid'
        }
    },
    {
        'selector': '[type = "Resource"]',
        'style': {
            'line-style': 'dotted'
        }
    }
]


# --- Sidebar (Node Editor) ---

sidebar = html.Div(
    [
        html.H2("Node Editor", className="display-6"),
        dbc.Button("New Node", id="btn-add", color="success", className="w-100 mb-3", size="lg"),

        dbc.Form([
            html.H5("Attributes"),
            dbc.Label("Name"),
            dbc.Input(id="node-name", type="text", placeholder="Node Name"),

            dbc.Label("Type"),
            dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES]),

            dbc.Label("Description"),
            dbc.Input(id="node-desc", type="text"),

            dbc.Label("Context"),
            dbc.Select(id="node-context", options=[{"label": c, "value": c} for c in CONTEXTS]),

            dbc.Label("Status"),
            dbc.Select(id="node-status", options=[{"label": s, "value": s} for s in ["Open", "Blocked", "Done"]]),

            # Numeric inputs
            dbc.Label("Value (1-10)"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

            dbc.Label("Interest (1-10)"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),

            dbc.Label("Time Estimate (Hours)"),
            dbc.Input(id="node-time", type="number", min=0.1, value=1.0),

            dbc.Label("Effort"),
            dbc.Select(id="node-effort", options=EFFORT_OPTIONS),

            html.Hr(),
            html.H5("Relationships"),
            dbc.Label("Needs"),
            dcc.Dropdown(id="edge-needs", multi=True, placeholder="Select Prerequisite Nodes..."),

            dbc.Label("Supports"),
            dcc.Dropdown(id="edge-supports", multi=True, placeholder="Select Dependent Nodes..."),

            dbc.Label("Helps"),
            dcc.Dropdown(id="edge-helps", multi=True, placeholder="Select Synergistic Nodes..."),

            dbc.Label("Resources"),
            dcc.Dropdown(id="edge-resources", multi=True, placeholder="Select Resources..."),

            html.Br(),
            html.Div([
                html.Div(id="save-output", className="text-success fw-bold flex-grow-1 align-self-center pe-2"),
                dbc.Button("Clear", id="btn-clear", color="secondary", className="me-2"),
                dbc.Button("Delete", id="btn-delete", color="danger", className="me-2"),
                dbc.Button("Save", id="btn-save", color="primary")
            ], className="d-flex justify-content-end mt-2"),
            dcc.Interval(id='clear-interval', interval=3000, n_intervals=0, disabled=True)
        ])
    ],
    className="bg-light p-3",
    style={"height": "100vh", "overflowY": "scroll"}
)


# --- Graph View (Canvas + Filters) ---

def create_graph_view(initial_elements):
    """Creates the graph view component with initial elements."""
    return html.Div([
        html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Search Task"),
                    dbc.Input(id="search-node", type="text", placeholder="Search by name..."),
                ], width=2),
                dbc.Col([
                    dbc.Label("Filter Context"),
                    dbc.Select(
                        id="filter-context",
                        options=[{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in CONTEXTS],
                        value="All"
                    ),
                ], width=2),
                dbc.Col([
                    dbc.Label("Community Method"),
                    dbc.Select(id="community-method", options=[
                        {"label": "Islands (Connected)", "value": "components"},
                        {"label": "Clusters (Louvain)", "value": "louvain"}
                    ], value="components"),
                ], width=2),
                dbc.Col([
                    dbc.Label("Community"),
                    dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),
                ], width=2),
                dbc.Col([
                    dbc.Checklist(
                        options=[{"label": "Hide 'Done' nodes", "value": "hide_done"}],
                        value=[],
                        id="filter-done",
                        switch=True,
                    )
                ], width=2, className="d-flex align-items-center mt-4"),
            ], className="mb-3")
        ]),

        cyto.Cytoscape(
            id='cytoscape-graph',
            layout={'name': 'cose'},
            style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'},
            elements=initial_elements,
            stylesheet=stylesheet
        )
    ])


# --- Info Panels ---

traversal_view = html.Div([
    html.H4("Dependencies"),
    html.Div(id="traversal-chains")
], className="mt-4 p-3 bg-light border rounded")

synergies_view = html.Div([
    html.H4("Synergies"),
    html.Div(id="synergies-list")
], className="mt-4 p-3 bg-light border rounded")

suggestions_view = html.Div([
    dbc.Row([
        dbc.Col(html.H4("Suggestions"), width=8),
        dbc.Col(dbc.Select(
            id="suggestion-algo",
            options=[{"label": "Priority Score", "value": "priority"}],
            value="priority", size="sm"
        ), width=4)
    ], className="mb-2"),
    html.Div(id="suggestions-table")
], className="mt-4 p-3 bg-light border rounded")


# --- Floating Tooltip ---

hover_tooltip = html.Div(
    id="hover-tooltip",
    className="bg-white border rounded shadow p-2",
    style={
        "position": "fixed",
        "zIndex": 9999,
        "display": "none",
        "pointerEvents": "none",
        "maxWidth": "280px",
        "fontSize": "0.85rem",
        "lineHeight": "1.5"
    }
)


def build_app_layout(initial_elements):
    """Assembles the full application layout."""
    return dbc.Container([
        hover_tooltip,
        dbc.Row([
            dbc.Col(sidebar, width=3),
            dbc.Col([
                create_graph_view(initial_elements),
                dbc.Row([
                    dbc.Col(suggestions_view, width=6),
                    dbc.Col([traversal_view, synergies_view], width=6)
                ])
            ], width=9)
        ])
    ], fluid=True)
