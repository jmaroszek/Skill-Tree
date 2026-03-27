"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from dash import html, dcc
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from config import ConfigManager, CANVAS_HEIGHT
from events_layout import build_events_tab_content
from goals_layout import build_goals_tab_content
from simulate_layout import build_simulate_tab_content
from settings_layout import build_settings_tab_content
from styles import stylesheet

# Read initial config values (lightweight DB reads, no GraphManager needed).
# These are only used for the initial render; core_engine refreshes them dynamically.
NODE_TYPES = ConfigManager.get_node_types()
CONTEXTS = ConfigManager.get_contexts()

# Cytoscape stylesheet is imported from styles.py

# --- Sidebar (Node Editor) ---

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
                options=[],  # Populated dynamically by core_engine callback
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
                dbc.Select(id="node-context", options=[{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in CONTEXTS], value="", style={'flex': 1}),
                dbc.Button("▾", id="btn-subcontext-toggle", color="light", className="ms-1 px-2")
            ], className="d-flex"),
            dbc.Collapse(dbc.Select(id="node-subcontext", options=[], className="mt-1"), id="collapse-subcontext", is_open=False),

            dbc.Label("Description", className="mt-2"),
            dbc.Textarea(id="node-desc"),
            
            html.Div(id="auto-status-display", className="d-none"),

            # --- Section: Done toggle + Time Estimates (Learn, Goal, Resource) ---
            html.Div(id="section-done-time", children=[
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Done", "value": "Done"}],
                        value=[],
                        id="node-status-done",
                        switch=True,
                        className="mt-3",
                    ),
                    dbc.Badge(id="node-priority-badge", children="", color="warning",
                              className="ms-2 mt-3 align-self-start",
                              style={"display": "none", "fontSize": "0.75rem"}),
                ], className="d-flex align-items-start"),
            ]),

            # --- Section: Resource-specific (progress slider) ---
            html.Div(id="section-resource", style={"display": "none"}, children=[
                dbc.Label("Progress", className="mt-2"),
                dcc.Slider(min=0, max=100, step=1, value=0, id="node-progress",
                           marks={0: "0%", 25: "25%", 50: "50%", 75: "75%", 100: "100%"}),
            ]),

            # --- Section: Habit-specific (status, frequency, session duration) ---
            html.Div(id="section-habit", style={"display": "none"}, children=[
                dbc.Label("Status", className="mt-3"),
                dbc.Select(id="habit-status", options=[
                    {"label": "Active", "value": "Active"},
                    {"label": "Paused", "value": "Paused"},
                    {"label": "Retired", "value": "Retired"},
                ], value="Active"),

                html.Hr(className="my-2"),
                html.H5("Habit Schedule", className="mt-2 mb-1"),
                dbc.Label("Frequency", className="mt-2"),
                dbc.Select(id="habit-frequency", options=[
                    {"label": "Daily", "value": "Daily"},
                    {"label": "Weekly", "value": "Weekly"},
                    {"label": "Monthly", "value": "Monthly"},
                    {"label": "Yearly", "value": "Yearly"},
                ], value="Daily"),

                dbc.Label("Session Duration in Minutes", className="mt-3"),
                dbc.Row([
                    dbc.Col([dbc.Label("Lower Bound", className="small text-muted mb-0"), dbc.Input(id="session-lower", type="number", min=0)]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="session-expected", type="number", min=0)]),
                    dbc.Col([dbc.Label("Upper Bound", className="small text-muted mb-0"), dbc.Input(id="session-upper", type="number", min=0)]),
                ]),
            ]),

            html.Hr(className="my-2"),

            # Numeric inputs (shared by all types)
            html.H5("Ratings", className="mt-2 mb-1"),
            dbc.Label("Value", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),

            dbc.Label("Interest", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),

            dbc.Label("Effort", className="mt-2"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-difficulty"),

            # --- Section: Time Estimates (Learn, Goal, Resource — hidden for Habit) ---
            html.Div(id="section-time-estimates", children=[
                html.Hr(),
                html.H5("Time Estimates in Hours", className="mt-2 mb-1"),
                dbc.Row([
                    dbc.Col([dbc.Label("Optimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-o", type="number", min=0)]),
                    dbc.Col([dbc.Label("Expected", className="small text-muted mb-0"), dbc.Input(id="node-time-m", type="number", min=0)]),
                    dbc.Col([dbc.Label("Pessimistic", className="small text-muted mb-0"), dbc.Input(id="node-time-p", type="number", min=0)]),
                ]),
            ]),
            
            html.Hr(),
            html.H5("Relationships", className="mt-2 mb-1"),
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
            html.Div(dcc.Dropdown(id="edge-helps", multi=True, placeholder="Synergistic Nodes..."), className="text-dark"),

            dbc.Label("Resources", className="mt-2"),
            html.Div(dcc.Dropdown(id="edge-resources", multi=True, placeholder="Resource Nodes..."), className="text-dark"),

            html.Hr(),
            html.H5("External Resources", className="mt-2 mb-1"),

            # Stores hold JSON arrays of links for each resource type
            dcc.Store(id='obsidian-links-store', data=['']),
            dcc.Store(id='drive-links-store', data=['']),
            dcc.Store(id='website-links-store', data=['']),

            dbc.Label("Obsidian", className="mt-0"),
            html.Div(id='obsidian-links-container'),

            dbc.Label("Google Drive", className="mt-2"),
            html.Div(id='drive-links-container'),

            dbc.Label("Website", className="mt-2"),
            html.Div(id='website-links-container'),
            
            html.Hr(),
            html.Div([
                html.Div(id="save-output", className="text-success fw-bold flex-grow-1 align-self-center pe-2"),
                dbc.Button("Clear", id="btn-clear", color="secondary", className="me-2"),
                dbc.Button("Delete", id="btn-delete", color="danger", className="me-2", style={"backgroundColor": ConfigManager.get_danger_color(), "borderColor": ConfigManager.get_danger_color()}),
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
    """Create the Cytoscape graph canvas with fullscreen toggle button."""
    return html.Div([
        html.Div([
            cyto.Cytoscape(
                id='cytoscape-graph',
                layout={'name': 'cose', 'fit': True},
                style={'width': '100%', 'height': '100%',
                       'backgroundColor': '#1a1d21', 'borderRadius': '8px'},
                elements=initial_elements,
                stylesheet=stylesheet,
                userZoomingEnabled=False,
                boxSelectionEnabled=True,
                userPanningEnabled=False,
                autoungrabify=False
            ),
            html.Button(
                "⛶", id="btn-fullscreen",
                className="btn btn-secondary btn-sm btn-fullscreen-toggle",
                title="Toggle fullscreen"
            ),
        ], id="canvas-container", className="canvas-container h-100", style={"overflow": "hidden", "borderRadius": "8px"}),
    ], className="h-100", style={"overflow": "hidden"})



# --- Filters Section ---

filters_content = html.Div([
    html.Div([
        html.H4("Filters"),
        html.Span("×", id="btn-close-filters", className="fs-3 text-white float-end", style={"cursor": "pointer"})
    ], className="d-flex justify-content-between align-items-center mb-3 mt-2"),

    html.H5("General", className="mt-2 mb-1"),
    dbc.Label("Node Type", className="mt-2"),
    dbc.Select(
        id="filter-node-type",
        options=[{"label": "All", "value": "All"}] + [{"label": t, "value": t} for t in NODE_TYPES],
        value="All",
    ),

    dbc.Label("Context", className="mt-2"),
    dbc.Select(
        id="filter-context",
        options=["All"] + CONTEXTS,
        value="All"
    ),

    dbc.Label("Subcontext", className="mt-2"),
    dbc.Select(id="filter-subcontext", options=[{"label": "All", "value": "All"}], value="All"),

    dbc.Label("Goal", className="mt-2"),
    dbc.Select(
        id="filter-goal",
        options=[{"label": "All", "value": "All"}],
        value="All",
    ),

    html.Hr(className="my-3"),

    html.H5("Communities", className="mt-2 mb-1"),
    dbc.Label("Detection Method", className="mt-2"),
    dbc.Select(id="community-method", options=[
        {"label": "Islands", "value": "components"},
        {"label": "Clusters", "value": "louvain"}
    ], value="components"),

    dbc.Label("Community", className="mt-3"),
    dbc.Select(id="filter-community", options=[{"label": "All", "value": "All"}], value="All"),

    html.Hr(className="my-3"),

    html.H5("Ratings", className="mt-2 mb-1"),
    dbc.Label("Min Value", className="mt-2"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-value",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Min Interest", className="mt-2"),
    dcc.Slider(min=1, max=10, step=1, value=1, id="filter-interest",
               marks={i: str(i) for i in range(1, 11)}),

    dbc.Label("Max Effort", className="mt-3"),
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


_section_title_style = {"fontSize": "1.3rem", "fontWeight": "600"}
_formula_hint_style = {"fontSize": "0.8rem", "fontFamily": "monospace", "color": "#6c757d", "marginBottom": "0.25rem"}

# --- Info Panels ---

relationships_view = html.Div([
    html.H6("Relationships", className="text-muted mb-2", style=_section_title_style),
    html.Div([
        html.Div([
            html.H6("Dependencies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="traversal-chains")
        ], style={"marginRight": "2rem"}),
        html.Div([
            html.H6("Synergies", className="text-muted mb-2", style={"fontSize": "0.95rem"}),
            html.Div(id="synergies-list")
        ]),
    ], style={"display": "flex", "alignItems": "flex-start"})
])

suggestions_view = html.Div([
    dcc.Store(id='suggestion-count-store', data=5),
    html.Div([
        html.H6("Suggestions", className="text-muted mb-0", style=_section_title_style),
        dbc.ButtonGroup([
            dbc.Button("−", id="btn-sugg-minus", color="secondary", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
            html.Span(id="suggestion-count-display", children="5",
                       className="align-self-center mx-2",
                       style={"fontSize": "0.95rem", "fontWeight": "bold", "minWidth": "18px",
                              "textAlign": "center"}),
            dbc.Button("+", id="btn-sugg-plus", color="secondary", size="sm",
                       style={"fontSize": "1rem", "lineHeight": "1", "padding": "2px 8px"}),
        ], className="align-middle"),
        html.Div([
            dbc.Button("Filters", id="btn-suggestions-filters-toggle", color="secondary", size="sm"),
        ], className="ms-auto d-flex align-items-center"),
    ], className="d-flex align-items-center mb-2", style={"gap": "12px"}),
    dcc.Store(id='selected-suggestion-store', data=None),
    html.Div(id="suggestions-table", style={"maxHeight": "750px", "overflowY": "auto"}),
])






# --- Migration Modal ---

def build_migration_content(orphans_by_field, new_values_by_field):
    """Build dynamic migration modal body from orphan data.

    Args:
        orphans_by_field: {'context': {'OldCtx': [Node, ...]}, 'type': {...}, 'subcontext': {...}}
        new_values_by_field: {'context': [...], 'type': [...], 'subcontext': [...]}

    Returns:
        Tuple of (children list for modal body, mapping list for interpreting dropdown indices)
    """
    children = []
    mapping = []  # List of (field, old_value) tuples, indexed to match dropdowns
    idx = 0

    for field in ('type', 'context', 'subcontext'):
        orphans = orphans_by_field.get(field, {})
        if not orphans:
            continue

        new_vals = new_values_by_field.get(field, [])
        field_label = field.replace('_', ' ').title()
        children.append(html.H5(f"{field_label} Changes", className="mt-3 mb-2"))

        for old_val, nodes in orphans.items():
            node_names = [n.name for n in nodes]
            display_names = ", ".join(node_names[:8])
            if len(node_names) > 8:
                display_names += f" (+{len(node_names) - 8} more)"

            options = [{"label": v, "value": v} for v in new_vals]
            if field != 'type':
                options.append({"label": "Clear (set to none)", "value": "__clear__"})

            children.append(dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(f'"{old_val}"'),
                        html.Span(f" — {len(node_names)} node{'s' if len(node_names) != 1 else ''} affected",
                                  className="text-muted ms-1"),
                    ]),
                    html.Small(display_names, className="text-muted d-block mb-2"),
                    dbc.Select(
                        id={"type": "migration-dropdown", "index": idx},
                        options=options,
                        value=new_vals[0] if new_vals else None,
                        placeholder=f"Reassign to..."
                    ),
                ])
            ], className="mb-2"))

            mapping.append({"field": field, "old_value": old_val})
            idx += 1

    return children, mapping


migration_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Migration Required")),
    dbc.ModalBody(id="migration-modal-body"),
    dbc.ModalFooter([
        dbc.Button("Skip (keep old values)", id="btn-migration-skip", color="secondary", className="me-2"),
        dbc.Button("Apply Migrations", id="btn-migration-apply", color="primary"),
    ])
], id="modal-migration", size="lg", is_open=False, centered=True, backdrop="static")


# --- Bottom Panel (Relationships only) ---

bottom_panel = html.Div([relationships_view], className="p-3")


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

    context_menu = html.Div(
        id="node-context-menu",
        children=[
            html.Div("Edit", id="ctx-menu-edit", className="ctx-menu-item"),
            html.Div("Toggle Done", id="ctx-menu-toggle-done", className="ctx-menu-item"),
            html.Div("Simulate", id="ctx-menu-simulate", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Open in Obsidian", id="ctx-menu-obsidian", className="ctx-menu-item"),
            html.Div("Open in Drive", id="ctx-menu-drive", className="ctx-menu-item"),
            html.Hr(style={"margin": "2px"}),
            html.Div("Delete", id="ctx-menu-delete", className="ctx-menu-item", style={"color": ConfigManager.get_danger_color()}),
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

    # --- Tab Navigation ---
    main_tabs = dbc.Tabs(
        id="main-tabs",
        active_tab="tab-canvas",
        children=[
            dbc.Tab(label="Nodes", tab_id="tab-canvas"),
            dbc.Tab(label="Goals", tab_id="tab-goals"),
            dbc.Tab(label="Suggestions", tab_id="tab-suggestions"),
            dbc.Tab(label="Simulation", tab_id="tab-simulate"),
            dbc.Tab(label="Events", tab_id="tab-events"),
            dbc.Tab(label="Settings", tab_id="tab-settings"),
        ],
        className="px-3 pt-1",
        style={"borderBottom": "1px solid #495057", "backgroundColor": "#1a1d21"}
    )

    # --- Canvas Tab Content (existing layout, unchanged) ---
    canvas_tab_content = html.Div(
        id="canvas-tab-content",
        children=[
            # --- LEFT SIDEBAR (EDITOR) ---
            html.Div(
                id="sidebar-editor-container",
                children=[sidebar_content],
                style={
                    "width": "380px",
                    "minWidth": "380px",
                    "marginLeft": "-380px",
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderRight": "1px solid #495057",
                    "transition": "margin-left 0.3s ease",
                    "backgroundColor": "#212529"
                }
            ),

            # --- MAIN CENTER CONTENT ---
            html.Div(
                style={
                    "flexGrow": 1,
                    "display": "flex",
                    "flexDirection": "column",
                    "minWidth": "0",
                    "transition": "flex-grow 0.3s ease-in-out"
                },
                children=[
                    # Top Toolbar
                    dbc.Row([
                        dbc.Col(
                            html.Div([
                                dbc.Button("New Node", id="btn-add", color="success", size="sm", className="me-2"),
                                dbc.Button("Clear Focus", id="btn-clear-focus", color="warning", size="sm", className="me-2",
                                           style={"display": "none"})
                            ], className="d-flex"),
                            width="auto"
                        ),
                        dbc.Col(
                            html.H4("Skill Tree (Sandbox)" if env == "sandbox" else "Skill Tree", className="text-center mb-0",
                                     style={"color": "#dee2e6", "fontWeight": "300", "letterSpacing": "2px"}),
                            className="d-flex align-items-center justify-content-center"
                        ),
                        dbc.Col(
                            dbc.Button("Filters", id="btn-filters-toggle", color="secondary", size="sm"),
                            width="auto",
                            className="text-end"
                        ),
                    ], className="py-3 px-3 mb-2 align-items-center m-0", style={"borderBottom": "1px solid #495057", "width": "100%"}),

                    # Canvas Container
                    html.Div(
                        [create_graph_view(initial_elements)], 
                        className="flex-grow-1 px-3 mt-2", 
                        style={
                            "flexBasis": "760px",
                            "minHeight": "200px",
                            "position": "relative", 
                            "overflow": "hidden" 
                        }
                    ),

                    # Resize Handle
                    html.Div(id="resize-handle"),

                    # Bottom panel
                    html.Div(
                        [bottom_panel], 
                        id="bottom-panel-container", 
                        className="px-3 pb-2", 
                        style={
                            "height": "35vh", 
                            "minHeight": "150px", 
                            "overflowY": "auto",
                            "flexShrink": 0  # Forces the panel to perfectly match the mouse pixel height
                        }
                    )
                ]
            ),

        ],
        className="d-flex",
        style={"width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Events Tab Content (hidden by default) ---
    events_tab_content = html.Div(
        id="events-tab-content",
        children=[build_events_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Goals Tab Content (hidden by default) ---
    goals_tab_content = html.Div(
        id="goals-tab-content",
        children=[build_goals_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Suggestions Tab Content (hidden by default) ---
    suggestions_tab_content = html.Div(
        id="suggestions-tab-content",
        children=[
            html.Div([
                html.Div([suggestions_view], className="px-4 pt-3 pb-4", style={"maxWidth": "900px"}),
            ], style={"flex": "1", "overflowY": "auto"}),
        ],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0", "flexDirection": "column"}
    )

    # --- Simulate Tab Content (hidden by default) ---
    simulate_tab_content = html.Div(
        id="simulate-tab-content",
        children=[build_simulate_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Settings Tab Content (hidden by default) ---
    settings_tab_content = html.Div(
        id="settings-tab-content",
        children=[build_settings_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0"}
    )

    return html.Div([
        hover_tooltip,
        edit_trigger,
        toggle_trigger,
        context_menu,
        dcc.Store(id='ctx-obsidian-path-store', data=None),
        dcc.Store(id='ctx-drive-path-store', data=None),
        dcc.Input(id='group-delete-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='simulate-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='edit-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='toggle-done-trigger-input', type='text', value='', style={'display': 'none'}),
        html.Div(id='canvas-height-config', style={'display': 'none'}, **{'data-height': str(CANVAS_HEIGHT)}),
        migration_modal,
        dcc.Store(id='pending-settings-store', data=None),
        dcc.Store(id='migration-mapping-store', data=None),

        main_tabs,
        # Tab content wrapper — only one tab visible at a time
        html.Div([
            canvas_tab_content,
            suggestions_tab_content,
            goals_tab_content,
            simulate_tab_content,
            settings_tab_content,
            events_tab_content,
            # --- SHARED FILTERS SIDEBAR (overlay, accessible from Canvas + Suggestions) ---
            html.Div(
                id="sidebar-filters-container",
                children=[filters_content],
                style={
                    "position": "absolute",
                    "top": "0",
                    "right": "-320px",
                    "width": "320px",
                    "height": "100%",
                    "zIndex": 100,
                    "overflowX": "hidden",
                    "overflowY": "auto",
                    "borderLeft": "1px solid #495057",
                    "transition": "right 0.3s ease",
                    "backgroundColor": "#212529"
                }
            )
        ], style={"flex": "1", "overflow": "hidden", "position": "relative"}),
    ], style={"width": "100vw", "height": "100vh", "overflow": "hidden",
              "display": "flex", "flexDirection": "column"})
