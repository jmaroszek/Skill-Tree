"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from constants import NODE_TYPES, NODE_STATUSES, CONTEXTS, EFFORT_OPTIONS, DEFAULT_WN, DEFAULT_WH
from graph_manager import GraphManager

_manager = GraphManager()


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
            'target-arrow-color': '#666',
            'line-color': '#666',
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
            dbc.Label("Name", className="mt-2"),
            dbc.Input(id="node-name", type="text"),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES]),

            dbc.Label("Description", className="mt-2"),
            dbc.Input(id="node-desc", type="text"),

            dbc.Label("Context", className="mt-2"),
            dbc.Select(id="node-context", options=[{"label": c, "value": c} for c in CONTEXTS]),

            dbc.Label("Status", className="mt-2"),
            dbc.Select(id="node-status", options=[{"label": s, "value": s} for s in ["Open", "Blocked", "Done"]]),

            # Numeric inputs
            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),

            dbc.Label("Time Estimate (Hours)", className="mt-2"),
            dbc.Input(id="node-time", type="number", min=0.1, value=1.0),

            dbc.Label("Effort", className="mt-2"),
            dbc.Select(id="node-effort", options=EFFORT_OPTIONS),

            html.Hr(),
            html.H5("Relationships"),
            dbc.Label("Needs", className="mt-2"),
            dcc.Dropdown(id="edge-needs", multi=True, placeholder="Select Prerequisite Nodes..."),

            dbc.Label("Supports", className="mt-2"),
            dcc.Dropdown(id="edge-supports", multi=True, placeholder="Select Dependent Nodes..."),

            dbc.Label("Helps", className="mt-2"),
            dcc.Dropdown(id="edge-helps", multi=True, placeholder="Select Synergistic Nodes..."),

            dbc.Label("Resources", className="mt-2"),
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


# --- Graph View (Canvas only, filters moved below) ---

def create_graph_view(initial_elements):
    """Creates the graph view component with initial elements (no filters)."""
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={'name': 'cose'},
                style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'},
                elements=initial_elements,
                stylesheet=stylesheet,
                userZoomingEnabled=False
            ),
            html.Button(
                "⛶", id="btn-fullscreen",
                className="btn btn-dark btn-sm btn-fullscreen-toggle",
                title="Toggle fullscreen"
            ),
        ], id="canvas-container", className="canvas-container"),
    ])


# --- Filters Section (placed above Dependencies & Synergies) ---

all_nodes = _manager.get_all_nodes()
_initial_search_options = [{"label": n.name, "value": n.name} for n in all_nodes]

filters_section = html.Div([
    html.H4("Filters"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Search Task"),
            dcc.Dropdown(
                id="search-node",
                options=_initial_search_options,
                value=None,
                searchable=True,
                clearable=True,
                placeholder="Search by name..."
            ),
        ], width=3),
        dbc.Col([
            dbc.Label("Filter Context"),
            dbc.Select(
                id="filter-context",
                options=[{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in CONTEXTS],
                value="All"
            ),
        ], width=2),
        dbc.Col([
            dbc.Label("Method"),
            dbc.Select(id="community-method", options=[
                {"label": "Islands", "value": "components"},
                {"label": "Clusters", "value": "louvain"}
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
        ], width=3, className="d-flex align-items-center mt-4"),
    ], className="mb-2"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Min Value"),
            dcc.Slider(min=1, max=10, step=1, value=1, id="filter-value",
                       marks={i: str(i) for i in range(1, 11)}),
        ], width=3),
        dbc.Col([
            dbc.Label("Min Interest"),
            dcc.Slider(min=1, max=10, step=1, value=1, id="filter-interest",
                       marks={i: str(i) for i in range(1, 11)}),
        ], width=3),
        dbc.Col([
            dbc.Label("Max Time (Hours)"),
            dbc.Input(id="filter-time", type="number", min=0.1, placeholder="No limit"),
        ], width=3),
        dbc.Col([
            dbc.Label("Effort"),
            dbc.Select(
                id="filter-effort",
                options=[
                    {"label": "All", "value": "All"},
                    {"label": "Easy", "value": "1"},
                    {"label": "Medium", "value": "2"},
                    {"label": "Hard", "value": "3"},
                ],
                value="All"
            ),
        ], width=3),
    ], className="mb-2"),
], className="mt-4 p-3 bg-light border rounded")


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
    dcc.Store(id='hyperparams-store', data=_manager.get_hyperparams()),
    dcc.Store(id='suggestion-count-store', data=5),
    dbc.Row([
        dbc.Col(html.Div([
            html.H4("Suggestions", className="d-inline me-3 mb-0"),
            dbc.ButtonGroup([
                dbc.Button("−", id="btn-sugg-minus", color="outline-secondary", size="sm",
                           style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
                html.Span(id="suggestion-count-display", children="5",
                           className="align-self-center mx-2",
                           style={"fontSize": "0.95rem", "fontWeight": "bold", "minWidth": "18px",
                                  "textAlign": "center"}),
                dbc.Button("+", id="btn-sugg-plus", color="outline-secondary", size="sm",
                           style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
            ], className="align-middle"),
        ], className="d-flex align-items-center"), width=7),
        dbc.Col(html.Div([
            dbc.Button(
                "⚙", id="btn-algo-settings", color="link", size="sm",
                className="flex-shrink-0",
                style={"fontSize": "1.1rem", "padding": "2px 2px", "textDecoration": "none"}
            ), 
            dbc.Button(
                "ℹ", id="btn-algo-info", color="link", size="sm",
                className="flex-shrink-0",
                style={"fontSize": "1.1rem", "padding": "2px 0px", "textDecoration": "none"}
            ),
            dbc.Select(
                id="suggestion-algo",
                options=[{"label": "Priority Score", "value": "priority"}],
                value="priority", size="sm",
                className="flex-grow-1"
            ),
            dbc.Popover(
                dbc.PopoverBody(
                    dcc.Markdown(
                        r"""
$$\text{Priority} = \frac{\text{Value} \times \text{Interest}}{\text{Time} \times \text{Effort}} + W_n \cdot N + W_h \cdot H$$

| Variable | Meaning |
|---|---|
| **N** | Blocked nodes this task unlocks |
| **H** | Active synergistic (Helps) connections |
| **W_n** | Unlock weight  |
| **W_h** | Synergy weight  |
                        """,
                        mathjax=True,
                        style={"fontSize": "0.85rem"}
                    )
                ),
                target="btn-algo-info",
                trigger="click",
                placement="left",
                style={"minWidth": "420px"}
            )
        ], className="d-flex align-items-center gap-1"), width=5)
    ], className="mb-2"),
    html.Div(id="suggestions-table", style={"maxHeight": "750px", "overflowY": "auto"}),

    # Hyperparameters Modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Algorithm Hyperparameters")),
        dbc.ModalBody([
            dbc.Label("Unlock Weight", className="fw-bold"),
            html.P("How much to prioritize tasks that unblock other tasks.",
                   className="text-muted small mb-1"),
            dbc.Input(id="input-wn", type="number", value=DEFAULT_WN, step=0.5, min=0,
                      className="mb-2"),
            html.Div(id="input-wn-feedback", className="text-danger small mb-3"),

            dbc.Label("Synergy Weight", className="fw-bold"),
            html.P("How much to prioritize tasks with active synergistic connections.",
                   className="text-muted small mb-1"),
            dbc.Input(id="input-wh", type="number", value=DEFAULT_WH, step=0.5, min=0,
                      className="mb-2"),
            html.Div(id="input-wh-feedback", className="text-danger small mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-hp-cancel", color="secondary", className="me-2"),
            dbc.Button("Apply", id="btn-hp-apply", color="primary"),
        ])
    ], id="modal-hyperparams", is_open=False, centered=True)
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
                    dbc.Col([filters_section, traversal_view, synergies_view], width=6)
                ])
            ], width=9)
        ])
    ], fluid=True)
