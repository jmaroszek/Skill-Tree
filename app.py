import dash
from dash import html, dcc, Input, Output, State, ALL
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from models import Node

# Initialize App & Manager
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Skill Tree"
manager = GraphManager()

# Stylings
NODE_COLORS = {
    'Blocked': '#dc3545',     # Red
    'Open': '#0d6efd',        # Blue
    'In Progress': '#ffc107', # Yellow
    'Done': '#198754'         # Green
}

NODE_SHAPES = {
    'Goal': 'star',
    'Topic': 'ellipse',
    'Skill': 'triangle',
    'Habit': 'diamond',
    'Resource': 'pentagon'
}

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

def generate_elements(filters=None, active_node_id=None, community_names=None):
    if filters is None:
        filters = {}
        
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    
    # Apply community filter if a specific community is selected
    if community_names is not None:
        filtered_nodes = [n for n in filtered_nodes if n.name in community_names]
    
    valid_names = {n.name for n in filtered_nodes}
    edges = manager.get_edges()
    
    elements = []
    
    for n in filtered_nodes:
        node_data = {
            'data': {
                'id': n.name,
                'label': n.name,
                'color': NODE_COLORS.get(n.status, '#888'),
                'shape': NODE_SHAPES.get(n.type, 'rectangle'),
                **n.to_dict() # attach full data for tooltips
            },
            'selected': False  # Explicitly reset selection state on render
        }
        if active_node_id and n.name == active_node_id:
            node_data['selected'] = True
            
        elements.append(node_data)
        
    for e in edges:
        if e['source'] in valid_names and e['target'] in valid_names:
            elements.append({
                'data': {
                    'id': f"{e['source']}_{e['target']}_{e['type']}",
                    'source': e['source'],
                    'target': e['target'],
                    'type': e['type']
                }
            })
            
    return elements

def get_suggestions(filters=None):
    if filters is None:
        filters = {}
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    scored = manager.calculate_priority_scores(filtered_nodes)
    # top 5 that are not done or blocked (-1 score means blocked/done here)
    valid = [n for n in scored if getattr(n, 'priority_score', -1) >= 0]
    return valid[:5]


# --- Layout ---

sidebar = html.Div(
    [
        html.H2("Node Editor", className="display-6"),
        dbc.Button("New Node", id="btn-add", color="success", className="w-100 mb-3", size="lg"),
        
        dbc.Form([
            html.H5("Attributes"),
            dbc.Label("Name"),
            dbc.Input(id="node-name", type="text", placeholder="Node Name"),
            
            dbc.Label("Type"),
            dbc.Select(id="node-type", options=[{"label": i, "value": i} for i in ["Goal", "Topic", "Skill", "Habit", "Resource"]]),
            
            dbc.Label("Description"),
            dbc.Input(id="node-desc", type="text"),
            
            dbc.Label("Context"),
            dbc.Select(id="node-context", options=[{"label": i, "value": i} for i in ["None", "Mind", "Body", "Social", "Action"]]),
            
            dbc.Label("Status"),
            dbc.Select(id="node-status", options=[{"label": i, "value": i} for i in ["Open", "Blocked", "Done"]]),
            
            # Numeric inputs
            dbc.Label("Value (1-10)"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-value"),
            
            dbc.Label("Interest (1-10)"),
            dcc.Slider(min=1, max=10, step=1, value=5, id="node-interest"),
            
            dbc.Label("Time Estimate (Hours)"),
            dbc.Input(id="node-time", type="number", min=0.1, value=1.0),
            
            dbc.Label("Effort"),
            dbc.Select(id="node-effort", options=[{"label": "Easy", "value": 1}, {"label": "Medium", "value": 2}, {"label": "Hard", "value": 3}]),

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

graph_view = html.Div([
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Search Task"),
                dbc.Input(id="search-node", type="text", placeholder="Search by name..."),
            ], width=2),
            dbc.Col([
                dbc.Label("Filter Context"),
                dbc.Select(id="filter-context", options=[{"label": "All", "value": "All"}, {"label": "None", "value": "None"}, {"label": "Mind", "value": "Mind"}, {"label": "Body", "value": "Body"}, {"label": "Social", "value": "Social"}], value="All"),
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
        layout={'name': 'cose'}, # Force-directed physics view
        style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'},
        elements=generate_elements(),
        stylesheet=stylesheet
    )
])

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
        dbc.Col(dbc.Select(id="suggestion-algo", options=[{"label": "Priority Score", "value": "priority"}], value="priority", size="sm"), width=4)
    ], className="mb-2"),
    html.Div(id="suggestions-table")
], className="mt-4 p-3 bg-light border rounded")

app.layout = dbc.Container([
    # Floating mouse tooltip
    html.Div(
        id="hover-tooltip",
        className="bg-white border rounded shadow p-2",
        style={
            "position": "fixed",
            "zIndex": 9999,
            "display": "none",
            "pointerEvents": "none",  # Don't block mouse events
            "maxWidth": "280px",
            "fontSize": "0.85rem",
            "lineHeight": "1.5"
        }
    ),
    dbc.Row([
        dbc.Col(sidebar, width=3),
        dbc.Col([
            graph_view,
            dbc.Row([
                dbc.Col(suggestions_view, width=6),
                dbc.Col([traversal_view, synergies_view], width=6)
            ])
        ], width=9)
    ])
], fluid=True)


# --- Callbacks ---


@app.callback(
    Output('hover-tooltip', 'children'),
    Input('cytoscape-graph', 'mouseoverNodeData')
)
def display_hover_data(data):
    if not data:
        return ""
        
    desc_ui = []
    if data.get('description'):
        desc_ui = [html.Br(), html.Span(data.get('description'), style={'display': 'inline-block', 'whiteSpace': 'normal'})]
        
    return [
        html.Strong(data['label']), " - ", data.get('type', ''), html.Br(),
        f"Status: {data.get('status', '')} | Context: {data.get('context', '')}", html.Br(),
        f"Value: {data.get('value', '')} | Effort: {data.get('effort', '')} | Time: {data.get('time', '')}h",
        *desc_ui
    ]

@app.callback(
    [Output('node-name', 'value'), Output('node-type', 'value'), Output('node-desc', 'value'),
     Output('node-context', 'value'), Output('node-status', 'value'),
     Output('node-value', 'value'), Output('node-interest', 'value'), 
     Output('node-time', 'value'), Output('node-effort', 'value'),
     Output('edge-needs', 'value'), Output('edge-supports', 'value'), Output('edge-helps', 'value'), Output('edge-resources', 'value'),
     Output('edge-needs', 'options'), Output('edge-supports', 'options'), Output('edge-helps', 'options'), Output('edge-resources', 'options')],
    [Input('cytoscape-graph', 'tapNodeData'),
     Input('btn-add', 'n_clicks'),
     Input('btn-clear', 'n_clicks'),
     Input('search-node', 'value'),
     Input('cytoscape-graph', 'elements')] # Trigger options update on element changes
)
def populate_editor(data, add_clicks, clear_clicks, search_val, elements):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""

    all_nodes = manager.get_all_nodes()
    # Provide node names for the dropdowns
    options = [{'label': n.name, 'value': n.name} for n in all_nodes]

    if trigger_id in ['btn-add', 'btn-clear']:
        return ["", "Goal", "", "None", "Open", 5, 5, 1.0, 2, [], [], [], [], options, options, options, options]

    name = None
    if trigger_id == 'search-node' and search_val:
        search_val_lower = search_val.lower()
        matched = [n for n in all_nodes if search_val_lower in n.name.lower()]
        if matched:
            node = matched[0]
            name = node.name
            data = node.to_dict()
            data['id'] = name
        else:
            return [dash.no_update] * 13 + [options, options, options, options]
    elif data:
        name = data.get('id')

    if not name or not data:
        return [dash.no_update] * 13 + [options, options, options, options]
        
    edges = manager.get_edges()
    
    needs_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Needs']
    supports_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == 'Needs']
    helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == 'Helps']
    # Add reverse helps for display in multi-select (undirected view)
    helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == 'Helps']
    helps_vals = list(set(helps_vals))
    
    res_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Resource']

    filtered_options = [{'label': n.name, 'value': n.name} for n in all_nodes if n.name != name]

    return [
        name, data.get('type'), data.get('description'),
        data.get('context'), data.get('status'),
        data.get('value', 5), data.get('interest', 5),
        data.get('time', 1), data.get('effort', 2),
        needs_vals, supports_vals, helps_vals, res_vals,
        filtered_options, filtered_options, filtered_options, filtered_options
    ]

@app.callback(
    [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'), 
     Output('suggestions-table', 'children'), Output('traversal-chains', 'children'),
     Output('synergies-list', 'children'),
     Output('clear-interval', 'disabled'), Output('clear-interval', 'n_intervals'),
     Output('filter-community', 'options')],
    [Input('btn-save', 'n_clicks'), Input('btn-delete', 'n_clicks'), 
     Input('filter-context', 'value'), Input('filter-done', 'value'),
     Input('suggestion-algo', 'value'),
     Input('search-node', 'value'),
     Input('cytoscape-graph', 'tapNodeData'),
     Input('filter-community', 'value'),
     Input('community-method', 'value')],
    [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
     State('node-context', 'value'), State('node-status', 'value'),
     State('node-value', 'value'), State('node-interest', 'value'),
     State('node-time', 'value'), State('node-effort', 'value'),
     State('edge-needs', 'value'), State('edge-supports', 'value'), State('edge-helps', 'value'), State('edge-resources', 'value'),
     State('cytoscape-graph', 'elements')]
)
def update_graph(save_clicks, delete_clicks, f_context, f_done, algo_val, search_val, tapped_node,
                 f_community, community_method,
                 name, n_type, desc, context, status, val, interest, time, effort,
                 e_needs, e_supports, e_helps, e_res, current_elements):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""
    msg = ""
    
    # Process Filter Logic
    filters = {}
    if f_context and f_context != "All":
        filters['context'] = f_context if f_context != "None" else None
    if f_done and "hide_done" in f_done:
        filters['hide_done'] = True
        
    active_node_id = None
    if trigger_id == 'search-node' and search_val:
        all_nodes = manager.get_all_nodes()
        search_val_lower = search_val.lower()
        matched = [n for n in all_nodes if search_val_lower in n.name.lower()]
        if matched:
            active_node_id = matched[0].name
    elif trigger_id == 'cytoscape-graph' and tapped_node:
        active_node_id = tapped_node.get('id')
    else:
        active_node_id = name
        
    if trigger_id == 'btn-save' and name and n_type:
        try:
            val = int(val) if val is not None else 5
            interest = int(interest) if interest is not None else 5
            time = float(time) if time is not None else 1.0
            effort = int(effort) if effort is not None else 2
        except ValueError:
            msg = "Error: Please check your numerical inputs."
            return current_elements, msg, dash.no_update, dash.no_update, dash.no_update, False, 0
            
        node = Node(name=name, type=n_type, description=desc or "", value=val, time=time, 
                    interest=interest, effort=effort, status=status or "Open", context=context)
        try:
            if manager.get_node(name):
                manager.update_node(node)
                msg = f"Updated node '{name}'"
            else:
                manager.add_node(node)
                msg = f"Added node '{name}'"

            # Sync Edges
            e_needs = e_needs or []
            e_supports = e_supports or []
            e_helps = e_helps or []
            e_res = e_res or []

            # Needs: (Prereq -> Target) so Prereq is Source
            # We clear existing incoming Needs
            with manager.get_connection() as conn:
                 cursor = conn.cursor()
                 cursor.execute("DELETE FROM Edges WHERE target=? AND type='Needs'", (name,))
                 cursor.execute("DELETE FROM Edges WHERE source=? AND type='Needs'", (name,))
                 conn.commit()
            for src in e_needs:
                 manager.add_edge(src, name, "Needs")
            for trgt in e_supports:
                 manager.add_edge(name, trgt, "Needs")

            # Helps
            with manager.get_connection() as conn:
                 cursor = conn.cursor()
                 cursor.execute("DELETE FROM Edges WHERE (target=? OR source=?) AND type='Helps'", (name, name))
                 conn.commit()
            for linked in e_helps:
                 manager.add_edge(name, linked, "Helps")
                 
            # Resources
            with manager.get_connection() as conn:
                 cursor = conn.cursor()
                 cursor.execute("DELETE FROM Edges WHERE target=? AND type='Resource'", (name,))
                 conn.commit()
            for r_src in e_res:
                 manager.add_edge(r_src, name, "Resource")
                 
            # Ensure final node adheres to block/open logic inherently after edge mutations
            manager._update_node_state(name)

        except Exception as e:
            msg = str(e)
            
    elif trigger_id == 'btn-delete' and name:
        try:
            manager.delete_node(name)
            msg = f"Deleted node '{name}'"
        except Exception as e:
            msg = str(e)

    # Detect communities for the dropdown
    community_method = community_method or "components"
    communities = manager.detect_communities(method=community_method)
    community_options = [{"label": "All", "value": "All"}]
    for i, comm in enumerate(communities):
        label = f"Community {i+1} ({len(comm)} nodes)"
        community_options.append({"label": label, "value": str(i)})
    
    # Apply community filter
    community_names = None
    if f_community and f_community != "All":
        try:
            idx = int(f_community)
            if 0 <= idx < len(communities):
                community_names = communities[idx]
        except (ValueError, IndexError):
            pass
    
    # Re-generate visuals
    elements = generate_elements(filters, active_node_id, community_names=community_names)
    suggs = get_suggestions(filters)
    
    # Format suggestions table
    if suggs:
        table_header = [html.Thead(html.Tr([html.Th("Task"), html.Th("Context"), html.Th("Type"), html.Th("Priority Score"), html.Th("Unlocks")]))]
        row_data = [html.Tr([
            html.Td(s.name), 
            html.Td(str(s.context)), 
            html.Td(s.type), 
            html.Td(f"{getattr(s, 'priority_score', 0):.2f}"),
            html.Td(", ".join(manager.get_directly_unlocked_nodes(s.name)) or "None")
        ]) for s in suggs]
        table_body = [html.Tbody(row_data)]
        sugg_ui = dbc.Table(table_header + table_body, bordered=True, hover=True, size="sm")
    else:
        sugg_ui = html.P("No suggestions found based on current filters and graph state.", className="text-muted")
    # Format traversal UI
    traversal_ui = html.Div(className="text-muted", children="Select a node to see dependencies.")
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")
    if tapped_node:
         node_id = tapped_node.get('id')
         chains = manager.get_prerequisite_chains(node_id)
         
         # Gather synergies
         edges = manager.get_edges()
         synergies = [e['target'] for e in edges if e['source'] == node_id and e['type'] == 'Helps']
         synergies += [e['source'] for e in edges if e['target'] == node_id and e['type'] == 'Helps']
         synergies = list(set(synergies))

         if not chains:
             traversal_ui = html.P("None", className="text-dark")
         else:
             chain_items = []
             for c in chains:
                 # omit the active target node itself from the end of the chain
                 display_chain = c[:-1] if c and c[-1] == active_node_id else c
                 if display_chain:
                     chain_str = " → ".join(display_chain)
                     chain_items.append(html.Div(chain_str))
             if chain_items:
                 traversal_ui = html.Div(chain_items)
             else:
                 traversal_ui = html.P("None", className="text-dark")

         if synergies:
             syn_items = [html.Div(s) for s in synergies]
             synergies_ui = html.Div(syn_items)
         else:
             synergies_ui = html.P("None", className="text-dark")

    return elements, msg, sugg_ui, traversal_ui, synergies_ui, False if msg else True, 0, community_options

@app.callback(
    Output('save-output', 'children', allow_duplicate=True),
    Output('clear-interval', 'disabled', allow_duplicate=True),
    Input('clear-interval', 'n_intervals'),
    prevent_initial_call=True
)
def clear_message(n):
    if n > 0:
        return "", True
    return dash.no_update, dash.no_update

if __name__ == '__main__':
    app.run(debug=True)
