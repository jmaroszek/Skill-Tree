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
            'text-outline-color': '#1a1d21',
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


# --- Sidebar (Node Editor — inside Offcanvas) ---

all_nodes = _manager.get_all_nodes()
_initial_search_options = [{"label": n.name, "value": n.name} for n in all_nodes]

sidebar_content = html.Div(
    [
        dbc.Form([
            html.H5("Search", className="mt-0 mb-1"),
            dcc.Dropdown(
                id="search-node",
                options=_initial_search_options,
                value=None,
                searchable=True,
                clearable=True,
                placeholder="Search for an existing node..."
            ),
            html.H5("Attributes", className="mt-3 mb-1"),
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

            html.Hr(className="my-2"),

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

            html.Hr(),
            dbc.Label("Obsidian", className="mt-0"),
            html.Div([
                dbc.Input(id="node-obsidian-path", type="text",
                          placeholder="Link to Obsidian file",
                          className="me-1", style={"flex": "1"}),
                dbc.Button("📁", id="btn-obsidian-browse", color="secondary",
                           size="sm", title="Browse vault", className="me-1"),
                dbc.Button("🔗", id="btn-obsidian-open", color="outline-info",
                           size="sm", title="Open in Obsidian"),
            ], className="d-flex"),
            html.Hr(),
            html.Div([
                html.Div(id="save-output", className="text-success fw-bold flex-grow-1 align-self-center pe-2"),
                dbc.Button("Clear", id="btn-clear", color="secondary", className="me-2"),
                dbc.Button("Delete", id="btn-delete", color="danger", className="me-2"),
                dbc.Button("Save", id="btn-save", color="primary")
            ], className="d-flex justify-content-end mt-4"),
            dcc.Interval(id='clear-interval', interval=3000, n_intervals=0, disabled=True)
        ])
    ],
    className="px-2 pb-2 pt-0"
)

editor_offcanvas = dbc.Offcanvas(
    sidebar_content,
    id="offcanvas-editor",
    title=html.Span("Node Editor", style={"fontSize": "1.4rem", "fontWeight": "600"}),
    is_open=False,
    placement="start",
    backdrop=False,
    close_button=True,
    style={"width": "380px"},
    className="offcanvas-editor-partial"
)


# --- Graph View (Canvas only) ---

def create_graph_view(initial_elements):
    """Creates the graph view component with initial elements."""
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={'name': 'cose'},
                style={'width': '100%', 'height': 'calc(100vh - 310px)',
                       'backgroundColor': '#1a1d21', 'borderRadius': '8px'},
                elements=initial_elements,
                stylesheet=stylesheet,
                userZoomingEnabled=False
            ),
            html.Button(
                "⛶", id="btn-fullscreen",
                className="btn btn-outline-light btn-sm btn-fullscreen-toggle",
                title="Toggle fullscreen"
            ),
        ], id="canvas-container", className="canvas-container"),
    ])


# --- Filters Section (inside right-side Offcanvas) ---

filters_content = html.Div([
    dbc.Label("Context", className="mt-0"),
    dbc.Select(
        id="filter-context",
        options=[{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in CONTEXTS],
        value="All"
    ),

    html.Hr(className="my-3"),

    dbc.Label("Community Detection Method", className="mt-0"),
    dbc.Select(id="community-method", options=[
        {"label": "Islands", "value": "components"},
        {"label": "Clusters", "value": "louvain"}
    ], value="components"),

    dbc.Label("Community", className="mt-3"),
    dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),

    html.Hr(className="my-3"),

    dbc.Label("Min Value", className="mt-0"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-value",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Min Interest", className="mt-2"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-interest",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Max Time (Hrs)", className="mt-2"),
    dbc.Input(id="filter-time", type="number", min=0.1, placeholder="No limit"),

    dbc.Label("Effort", className="mt-3"),
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

    html.Hr(className="my-3"),

    dbc.Checklist(
        options=[{"label": "Hide 'Done'", "value": "hide_done"}],
        value=[],
        id="filter-done",
        switch=True,
    ),
], className="px-2 pb-2 pt-0")

filters_offcanvas = dbc.Offcanvas(
    filters_content,
    id="offcanvas-filters",
    title=html.Span("Filters", style={"fontSize": "1.4rem", "fontWeight": "600"}),
    is_open=False,
    placement="end",
    backdrop=False,
    close_button=True,
    style={"width": "320px"},
    className="offcanvas-editor-partial"
)


# --- Info Panels (inside tabs) ---

traversal_view = html.Div([
    html.Div(id="traversal-chains")
], className="p-3")

synergies_view = html.Div([
    html.Div(id="synergies-list")
], className="p-3")

suggestions_view = html.Div([
    dcc.Store(id='hyperparams-store', data=_manager.get_hyperparams()),
    dcc.Store(id='suggestion-count-store', data=5),
    dbc.Row([
        dbc.Col(html.Div([
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
        ], className="d-flex align-items-center"), width="auto"),
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
                style={"maxWidth": "180px"}
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
        ], className="d-flex align-items-center gap-1 justify-content-end"), width="auto", className="ms-auto")
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
], className="p-3")


# --- Bottom Tabs ---

bottom_tabs = dbc.Tabs([
    dbc.Tab(suggestions_view, label="Suggestions", tab_id="tab-suggestions",
            active_tab_style={"fontWeight": "bold"}),
    dbc.Tab(traversal_view, label="Dependencies", tab_id="tab-dependencies",
            active_tab_style={"fontWeight": "bold"}),
    dbc.Tab(synergies_view, label="Synergies", tab_id="tab-synergies",
            active_tab_style={"fontWeight": "bold"}),
], id="bottom-tabs", active_tab="tab-suggestions", className="mt-2")


# --- Floating Tooltip ---

hover_tooltip = html.Div(
    id="hover-tooltip",
    className="border rounded shadow p-2",
    style={
        "position": "fixed",
        "zIndex": 9999,
        "display": "none",
        "pointerEvents": "none",
        "maxWidth": "280px",
        "fontSize": "0.85rem",
        "lineHeight": "1.5",
        "backgroundColor": "#2b3035",
        "color": "#dee2e6",
        "borderColor": "#495057"
    }
)


def build_app_layout(initial_elements):
    """Assembles the full application layout."""
    # Hidden button — clicked programmatically by JS on double-click / context menu edit
    edit_trigger = html.Button(id="btn-edit-node", style={"display": "none"})

    # Right-click context menu (positioned by JS)
    context_menu = html.Div(
        id="node-context-menu",
        children=[
            html.Div("Edit", id="ctx-menu-edit", className="ctx-menu-item"),
            html.Div("Open in Obsidian", id="ctx-menu-obsidian", className="ctx-menu-item"),
        ],
        style={
            "display": "none",
            "position": "fixed",
            "zIndex": 10000,
            "backgroundColor": "#2b3035",
            "border": "1px solid #495057",
            "borderRadius": "6px",
            "padding": "4px 0",
            "minWidth": "140px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.4)",
        }
    )

    return dbc.Container([
        hover_tooltip,
        editor_offcanvas,
        filters_offcanvas,
        edit_trigger,
        context_menu,
        # Hidden store for right-clicked node's obsidian path (written by JS)
        dcc.Store(id='ctx-obsidian-path-store', data=None),

        # Top toolbar
        dbc.Row([
            dbc.Col(
                dbc.Button("+ New Node", id="btn-add", color="success", size="sm",
                           className="me-2"),
                width="auto"
            ),
            dbc.Col(
                dbc.Button("⚙ Filters", id="btn-filters-toggle", color="outline-light",
                           size="sm"),
                width="auto"
            ),
            dbc.Col(
                html.H4("Skill Tree", className="text-center mb-0",
                         style={"color": "#dee2e6", "fontWeight": "300", "letterSpacing": "2px"}),
                className="d-flex align-items-center justify-content-center"
            ),
        ], className="py-2 px-3 mb-2 align-items-center",
           style={"borderBottom": "1px solid #495057"}),

        # Canvas (full width)
        create_graph_view(initial_elements),

        # Bottom tabbed panel
        bottom_tabs,

    ], fluid=True, className="px-3 py-2",
       style={"minHeight": "100vh"})

