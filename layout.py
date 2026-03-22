"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from config import ConfigManager
from graph_manager import GraphManager

_manager = GraphManager()

# Default configurations read from DB
NODE_TYPES = ConfigManager.get_node_types()
CONTEXTS = ConfigManager.get_contexts()

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
        'selector': '[type = "Needs_Hard"]',
        'style': {
            'target-arrow-color': '#f8f9fa',
            'line-color': '#adb5bd',
            'line-style': 'solid'
        }
    },
    {
        'selector': '[type = "Needs_Soft"]',
        'style': {
            'target-arrow-color': '#6c757d',
            'line-color': '#6c757d',
            'line-style': 'dashed'
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

all_nodes = _manager.get_all_nodes()
_initial_search_options = [{"label": n.name, "value": n.name} for n in all_nodes]

sidebar_content = html.Div(
    [
        html.Div([
            html.H4("Node Editor"),
            html.Span("×", id="btn-close-editor", className="fs-3 text-white float-end", style={"cursor": "pointer"})
        ], className="d-flex justify-content-between align-items-center mb-3 mt-2"),
        dbc.Form([
            html.H5("Search", className="mt-2 mb-1"),
            html.Div(dcc.Dropdown(
                id="search-node",
                options=_initial_search_options,
                value=None,
                searchable=True,
                clearable=True,
            ), className="text-dark"),
            
            html.H5("General", className="mt-3 mb-1"),
            dbc.Label("Name", className="mt-2"),
            dbc.Input(id="node-name", type="text"),

            dbc.Label("Type", className="mt-2"),
            dbc.Select(id="node-type", options=[{"label": t, "value": t} for t in NODE_TYPES]),

            dbc.Label("Context", className="mt-2"),
            html.Div([
                dbc.Select(id="node-context", options=[{"label": c, "value": c} for c in CONTEXTS], style={'flex': 1}),
                dbc.Button("▾", id="btn-subcontext-toggle", color="light", className="ms-1 px-2")
            ], className="d-flex"),
            dbc.Collapse(dbc.Select(id="node-subcontext", options=[], className="mt-1"), id="collapse-subcontext", is_open=False),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="node-desc"),
            
            html.Div(id="auto-status-display", className="d-none"),
            dbc.Checklist(
                options=[{"label": "Done", "value": "Done"}],
                value=[],
                id="node-status-done",
                switch=True,
                className="mt-3",
            ),

            html.Hr(className="my-2"),

            # Numeric inputs
            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),

            dbc.Label("Difficulty", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-difficulty"),

            html.Hr(),
            html.H5("Time Estimates in Hours"),
            dbc.Row([
                dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-o", type="number", min=0)]),
                dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="node-time-m", type="number", min=0)]),
                dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-p", type="number", min=0)]),
            ]),
            
            html.Hr(),
            html.H5("Relationships"),
            dbc.Label("Needs", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="edge-needs-hard", multi=True, placeholder="Hard Prerequisites..."),
                dcc.Dropdown(id="edge-needs-soft", multi=True, placeholder="Soft Prerequisites...", className="mt-1"),
            ], className="text-dark"),

            dbc.Label("Supports", className="mt-2"),
            html.Div([
                dcc.Dropdown(id="edge-supports-hard", multi=True, placeholder="Hard Dependents..."),
                dcc.Dropdown(id="edge-supports-soft", multi=True, placeholder="Soft Dependents...", className="mt-1"),
            ], className="text-dark"),

            dbc.Label("Helps", className="mt-2"),
            html.Div(dcc.Dropdown(id="edge-helps", multi=True, placeholder="Select Synergistic Nodes..."), className="text-dark"),

            dbc.Label("Resources", className="mt-2"),
            html.Div(dcc.Dropdown(id="edge-resources", multi=True, placeholder="Select Resource Nodes..."), className="text-dark"),

            html.Hr(),
            html.H5("External Resources"),
            dbc.Label("Obsidian", className="mt-0"),
            html.Div([
                dbc.Input(id="node-obsidian-path", type="text", placeholder="Link to Obsidian file", className="me-1", style={"flex": "1"}),
                dbc.Button("📁", id="btn-obsidian-browse", color="secondary", size="sm", title="Browse vault", className="me-1"),
                dbc.Button("🔗", id="btn-obsidian-open", color="outline-info", size="sm", title="Open in Obsidian"),
            ], className="d-flex"),
            
            dbc.Label("Google Drive", className="mt-2"),
            html.Div([
                dbc.Input(id="node-google-drive-path", type="text", placeholder="Link to Drive file", className="me-1", style={"flex": "1"}),
                dbc.Button("🔗", id="btn-drive-open", color="outline-info", size="sm", title="Open in Drive"),
            ], className="d-flex"),

            dbc.Label("Website", className="mt-2"),
            html.Div([
                dbc.Input(id="node-website-path", type="text", placeholder="Link to Website", className="me-1", style={"flex": "1"}),
                dbc.Button("🔗", id="btn-website-open", color="outline-info", size="sm", title="Open Website"),
            ], className="d-flex"),
            
            html.Hr(),
            html.Div([
                html.Div(id="save-output", className="text-success fw-bold flex-grow-1 align-self-center pe-2"),
                dbc.Button("Clear", id="btn-clear", color="secondary", className="me-2"),
                dbc.Button("Delete", id="btn-delete", color="danger", className="me-2"),
                dbc.Button("Save", id="btn-save", color="primary")
            ], className="d-flex justify-content-end mt-4 mb-5"),
            dcc.Interval(id='clear-interval', interval=3000, n_intervals=0, disabled=True)
        ])
    ],
    className="ps-3 pe-4 pb-2 pt-0",
    style={"width": "380px", "minWidth": "380px"}
)


# --- Graph View (Canvas only) ---

def create_graph_view(initial_elements):
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={'name': 'cose', 'fit': True},
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
        ], id="canvas-container", className="canvas-container h-100"),
    ], className="h-100")



# --- Filters Section ---

filters_content = html.Div([
    html.Div([
        html.H4("Filters"),
        html.Span("×", id="btn-close-filters", className="fs-3 text-white float-end", style={"cursor": "pointer"})
    ], className="d-flex justify-content-between align-items-center mb-3 mt-2"),

    dbc.Label("Context", className="mt-0"),
    dbc.Select(
        id="filter-context",
        options=["All"] + CONTEXTS, 
        value="All"
    ),

    dbc.Label("Subcontext", className="mt-2"),
    dbc.Select(id="filter-subcontext", options=[{"label": "All", "value": "All"}], value="All"),

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

    dbc.Label("Max Difficulty", className="mt-3"),
    dcc.Slider(min=1, max=10, step=1, value=10, id="filter-difficulty",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Max Time in Hours", className="mt-2"),
    dbc.Input(id="filter-time", type="number", min=0.1, placeholder="No limit"),

    html.Hr(className="my-3"),

    dbc.Checklist(
        options=[{"label": "Hide Completed Tasks", "value": "hide_done"}],
        value=["hide_done"],  # Default ON
        id="filter-done",
        switch=True,
    ),
], className="px-3 pb-2 pt-0", style={"width": "320px", "minWidth": "320px"})


# --- Info Panels (inside tabs) ---

traversal_view = html.Div([
    html.Div(id="traversal-chains")
], className="p-3")

synergies_view = html.Div([
    html.Div(id="synergies-list")
], className="p-3")

suggestions_view = html.Div([
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
    ], className="mb-2"),
    html.Div(id="suggestions-table", style={"maxHeight": "750px", "overflowY": "auto"}),
], className="p-3")


# --- Global Settings Modal ---
settings_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Settings")),
    dbc.ModalBody([
        dbc.Tabs([
            dbc.Tab(label="Nodes", children=[
                html.Div([
                    dbc.Label("Node Types", className="fw-bold mt-2"),
                    dbc.Textarea(id="setting-node-types", rows=4, placeholder="Enter node types separated by commas or new lines..."),
                    html.P("These dynamically populate your node type drop-downs. Defined order is preserved.", className="text-muted small"),
                    
                    html.Hr(),
                    dbc.Label("Contexts", className="fw-bold mt-2"),
                    dbc.Textarea(id="setting-contexts", rows=4, placeholder="Enter contexts separated by commas or new lines..."),
                    html.P("These dynamically populate your context drop-downs. Defined order is preserved.", className="text-muted small"),
                    
                    html.Hr(),
                    dbc.Label("Subcontexts", className="fw-bold mt-2"),
                    dbc.Textarea(id="setting-subcontexts", rows=4, placeholder="Enter subcontexts in the format Context: Subcontext1, Subcontext2..."),
                    html.P("These dynamically populate your subcontext drop-downs per context. Defined order is preserved.", className="text-muted small"),
                ], className="p-2")
            ]),
            dbc.Tab(label="Algorithms", children=[
                html.Div([
                    dbc.Label("Algorithm Profile", className="fw-bold mt-2"),
                    dbc.Select(id="setting-hp-profile", options=[
                        {"label": "Default", "value": "Default"},
                        {"label": "Curious", "value": "Curious"},
                        {"label": "Industrious", "value": "Industrious"},
                        {"label": "Custom", "value": "Custom"}
                    ], value="Default"),
                    
                    dbc.Row([
                        dbc.Col([dbc.Label("Value Weight"), dbc.Input(id="hp-wv", type="number", step=0.1), html.Small("Multiplier for 'Value' attribute.", className="text-muted")]),
                        dbc.Col([dbc.Label("Interest Weight"), dbc.Input(id="hp-wi", type="number", step=0.1), html.Small("Multiplier for 'Interest' attribute.", className="text-muted")]),
                    ], className="mt-2"),
                    dbc.Row([
                        dbc.Col([dbc.Label("Hard Prereq Factor"), dbc.Input(id="hp-dh", type="number", step=0.01), html.Small("Penalty for unmet hard prerequisites.", className="text-muted")]),
                        dbc.Col([dbc.Label("Soft Prereq Factor"), dbc.Input(id="hp-ds", type="number", step=0.01), html.Small("Penalty for unmet soft prerequisites.", className="text-muted")]),
                        dbc.Col([dbc.Label("Synergy Factor"), dbc.Input(id="hp-dsyn", type="number", step=0.01), html.Small("Bonus for having synergistic neighbors.", className="text-muted")]),
                    ], className="mt-2"),
                    dbc.Row([
                        dbc.Col([dbc.Label("Difficulty Penalty"), dbc.Input(id="hp-we", type="number", step=0.1), html.Small("Penalty based on difficulty score.", className="text-muted")]),
                        dbc.Col([dbc.Label("Time Penalty"), dbc.Input(id="hp-wt", type="number", step=0.1), html.Small("Penalty based on time estimates.", className="text-muted")]),
                        dbc.Col([dbc.Label("Sublinear Dampener"), dbc.Input(id="hp-beta", type="number", step=0.05), html.Small("Modulates the scaling of penalties.", className="text-muted")]),
                    ], className="mt-2"),
                ], className="p-2")
            ]),
            dbc.Tab(label="Paths", children=[
                html.Div([
                    dbc.Label("Obsidian Vault Root Path", className="fw-bold mt-2"),
                    dbc.Input(id="setting-obsidian-path", type="text"),
        
                    
                    html.Hr(),
                    html.P("Node types and custom visuals implementation in future phase.", className="text-muted")
                ], className="p-2")
            ])
        ])
    ]),
    dbc.ModalFooter([
        dbc.Button("Cancel", id="btn-settings-cancel", color="secondary", className="me-2"),
        dbc.Button("Save Settings", id="btn-settings-save", color="primary"),
    ])
], id="modal-settings", size="lg", is_open=False, centered=True)

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


def build_app_layout(initial_elements, env="production"):
    """Assembles the full application layout with pure Flexbox (Push behavior)."""
    
    edit_trigger = html.Button(id="btn-edit-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    toggle_trigger = html.Button(id="btn-toggle-done-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    btn_show_deps = html.Button(id="btn-show-deps", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    btn_show_syns = html.Button(id="btn-show-syns", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})

    context_menu = html.Div(
        id="node-context-menu",
        children=[
            html.Div("Edit", id="ctx-menu-edit", className="ctx-menu-item"),
            html.Div("Toggle Done", id="ctx-menu-toggle-done", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Show Dependencies", id="ctx-menu-deps", className="ctx-menu-item"),
            html.Div("Show Synergies", id="ctx-menu-syns", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Open in Obsidian", id="ctx-menu-obsidian", className="ctx-menu-item"),
            html.Div("Open in Drive", id="ctx-menu-drive", className="ctx-menu-item"),
        ],
        style={
            "display": "none",
            "position": "fixed",
            "zIndex": 10000,
            "backgroundColor": "#2b3035",
            "border": "1px solid #495057",
            "borderRadius": "6px",
            "padding": "4px 0",
            "minWidth": "160px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.4)",
        }
    )

    return html.Div([
        hover_tooltip,
        edit_trigger,
        toggle_trigger,
        btn_show_deps,
        btn_show_syns,
        context_menu,
        dcc.Store(id='ctx-obsidian-path-store', data=None),
        dcc.Store(id='ctx-drive-path-store', data=None),
        settings_modal,

        html.Div([
            # --- LEFT SIDEBAR (EDITOR) ---
            html.Div(
                id="sidebar-editor-container",
                children=[sidebar_content],
                style={
                    "width": "0px",
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderRight": "1px solid #495057",
                    "transition": "width 0.3s ease-in-out",
                    "backgroundColor": "#212529"
                }
            ),

            # --- MAIN CENTER CONTENT ---
            html.Div(
                style={
                    "flexGrow": 1,
                    "display": "flex",
                    "flexDirection": "column",
                    "minWidth": "0",  # Prevents flex clipping
                    "transition": "flex-grow 0.3s ease-in-out"
                },
                children=[
                    # Top Toolbar
                    dbc.Row([
                        dbc.Col(
                            # Group left actions
                            html.Div([
                                dbc.Button("+ New Node", id="btn-add", color="success", size="sm", className="me-2"),
                                dbc.Button("⚙ Settings", id="btn-settings-toggle", color="outline-info", size="sm", className="me-2")
                            ], className="d-flex"),
                            width="auto"
                        ),
                        dbc.Col(
                            html.H4("Skill Tree (Sandbox)" if env == "sandbox" else "Skill Tree", className="text-center mb-0",
                                     style={"color": "#dee2e6", "fontWeight": "300", "letterSpacing": "2px"}),
                            className="d-flex align-items-center justify-content-center"
                        ),
                        dbc.Col(
                            dbc.Button("⧨ Filters", id="btn-filters-toggle", color="outline-light", size="sm"),
                            width="auto",
                            className="text-end"
                        ),
                    ], className="py-2 px-3 mb-2 align-items-center m-0", style={"borderBottom": "1px solid #495057", "width": "100%"}),

                    # Canvas Container
                    html.Div([create_graph_view(initial_elements)], className="flex-grow-1 px-3 mt-2", style={"position": "relative"}),

                    # Bottom tabbed panel
                    html.Div([bottom_tabs], id="bottom-panel-container", className="px-3 pb-2", style={"height": "35vh", "minHeight": "250px", "overflowY": "auto"})
                ]
            ),

            # --- RIGHT SIDEBAR (FILTERS) ---
            html.Div(
                id="sidebar-filters-container",
                children=[filters_content],
                style={
                    "width": "0px",
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderLeft": "1px solid #495057",
                    "transition": "width 0.3s ease-in-out",
                    "backgroundColor": "#212529"
                }
            )
        ], className="d-flex", style={"width": "100vw", "height": "100vh", "overflow": "hidden"})
    ])
