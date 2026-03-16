import dash
from dash import html, dcc, Input, Output, State, ALL
import dash_cytoscape as cyto
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from models import Node
import pandas as pd

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
            'source-arrow-color': '#888',
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

def generate_elements(filters=None):
    if filters is None:
        filters = {}
        
    nodes = manager.get_all_nodes()
    filtered_nodes = manager.filter_nodes(nodes, filters)
    valid_names = {n.name for n in filtered_nodes}
    edges = manager.get_edges()
    
    elements = []
    
    for n in filtered_nodes:
        elements.append({
            'data': {
                'id': n.name,
                'label': n.name,
                'color': NODE_COLORS.get(n.status, '#888'),
                'shape': NODE_SHAPES.get(n.type, 'rectangle'),
                **n.to_dict() # attach full data for tooltips
            }
        })
        
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
        html.Hr(),
        html.P("Select a node on the graph to edit or Add new:", className="lead"),
        
        dbc.Form([
            dbc.Label("Name"),
            dbc.Input(id="node-name", type="text", placeholder="Node Name"),
            
            dbc.Label("Type"),
            dbc.Select(id="node-type", options=[{"label": i, "value": i} for i in ["Goal", "Topic", "Skill", "Habit", "Resource"]]),
            
            dbc.Label("Description"),
            dbc.Input(id="node-desc", type="text"),
            
            dbc.Label("Context"),
            dbc.Select(id="node-context", options=[{"label": i, "value": i} for i in ["Mind", "Body", "Social", "Action"]]),
            
            dbc.Label("Status"),
            dbc.Select(id="node-status", options=[{"label": i, "value": i} for i in ["Open", "In Progress", "Blocked", "Done"]]),
            
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
            dbc.Label("Needs (Prerequisites)"),
            dcc.Dropdown(id="edge-needs", multi=True, placeholder="Select Prerequisite Nodes..."),
            
            dbc.Label("Helps (Synergy)"),
            dcc.Dropdown(id="edge-helps", multi=True, placeholder="Select Synergistic Nodes..."),
            
            dbc.Label("Resources Supported By"),
            dcc.Dropdown(id="edge-resources", multi=True, placeholder="Select Existing Resources..."),

            html.Br(),
            dbc.Button("Save Node & Edges", id="btn-save", color="primary", className="me-1"),
            dbc.Button("Delete Node", id="btn-delete", color="danger"),
            html.Div(id="save-output", className="text-danger mt-2")
        ])
    ],
    className="bg-light p-3",
    style={"height": "100vh", "overflowY": "scroll"}
)

graph_view = html.Div([
    html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Label("Filter Context"),
                dbc.Select(id="filter-context", options=[{"label": "All", "value": "All"}, {"label": "Mind", "value": "Mind"}, {"label": "Body", "value": "Body"}, {"label": "Social", "value": "Social"}]),
            ], width=3),
            dbc.Col([
                dbc.Checklist(
                    options=[{"label": "Hide 'Done' nodes", "value": "hide_done"}],
                    value=[],
                    id="filter-done",
                    switch=True,
                )
            ], width=3, className="d-flex align-items-center mt-4"),
             dbc.Col([
                  html.Div(id="hover-tooltip", className="bg-white border rounded p-2", style={"minHeight": "80px"})
             ], width=6)
        ], className="mb-3")
    ]),
    
    cyto.Cytoscape(
        id='cytoscape-graph',
        layout={'name': 'breadthfirst', 'directed': True}, # DAG-friendly layout builtin avoiding dagre issue
        style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'},
        elements=generate_elements(),
        stylesheet=stylesheet
    )
])

traversal_view = html.Div([
    html.H4("Dependency Traversal"),
    html.Div(id="traversal-chains")
], className="mt-4 p-3 bg-light border rounded")

suggestions_view = html.Div([
    html.H4("Top Suggestions to Work On"),
    html.Div(id="suggestions-table")
], className="mt-4 p-3 bg-light border rounded")

app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(sidebar, width=3),
        dbc.Col([
            graph_view,
            dbc.Row([
                dbc.Col(suggestions_view, width=6),
                dbc.Col(traversal_view, width=6)
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
        return "Hover over a node to see details."
    return [
        html.Strong(data['label']), " - ", data.get('type', ''), html.Br(),
        f"Status: {data.get('status', '')} | Context: {data.get('context', '')}", html.Br(),
        f"Value: {data.get('value', '')} | Effort: {data.get('effort', '')} | Time: {data.get('time', '')}h",
    ]

@app.callback(
    [Output('node-name', 'value'), Output('node-type', 'value'), Output('node-desc', 'value'),
     Output('node-context', 'value'), Output('node-status', 'value'),
     Output('node-value', 'value'), Output('node-interest', 'value'), 
     Output('node-time', 'value'), Output('node-effort', 'value'),
     Output('edge-needs', 'value'), Output('edge-helps', 'value'), Output('edge-resources', 'value'),
     Output('edge-needs', 'options'), Output('edge-helps', 'options'), Output('edge-resources', 'options')],
    [Input('cytoscape-graph', 'tapNodeData'),
     Input('cytoscape-graph', 'elements')] # Trigger options update on element changes
)
def populate_editor(data, elements):
    all_nodes = manager.get_all_nodes()
    # Provide node names for the dropdowns
    options = [{'label': n.name, 'value': n.name} for n in all_nodes]

    if not data:
        return [dash.no_update] * 9 + [[], [], [], options, options, options]
        
    name = data.get('id')
    edges = manager.get_edges()
    
    needs_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Needs']
    helps_vals = [e['target'] for e in edges if e['source'] == name and e['type'] == 'Helps']
    # Add reverse helps for display in multi-select (undirected view)
    helps_vals += [e['source'] for e in edges if e['target'] == name and e['type'] == 'Helps']
    helps_vals = list(set(helps_vals))
    
    res_vals = [e['source'] for e in edges if e['target'] == name and e['type'] == 'Resource']

    return [
        name, data.get('type'), data.get('description'),
        data.get('context'), data.get('status'),
        data.get('value', 5), data.get('interest', 5),
        data.get('time', 1), data.get('effort', 2),
        needs_vals, helps_vals, res_vals,
        options, options, options
    ]

@app.callback(
    [Output('cytoscape-graph', 'elements'), Output('save-output', 'children'), 
     Output('suggestions-table', 'children'), Output('traversal-chains', 'children')],
    [Input('btn-save', 'n_clicks'), Input('btn-delete', 'n_clicks'), 
     Input('filter-context', 'value'), Input('filter-done', 'value'),
     Input('cytoscape-graph', 'tapNodeData')],
    [State('node-name', 'value'), State('node-type', 'value'), State('node-desc', 'value'),
     State('node-context', 'value'), State('node-status', 'value'),
     State('node-value', 'value'), State('node-interest', 'value'),
     State('node-time', 'value'), State('node-effort', 'value'),
     State('edge-needs', 'value'), State('edge-helps', 'value'), State('edge-resources', 'value'),
     State('cytoscape-graph', 'elements')]
)
def update_graph(save_clicks, delete_clicks, f_context, f_done, tapped_node,
                 name, n_type, desc, context, status, val, interest, time, effort,
                 e_needs, e_helps, e_res, current_elements):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""
    msg = ""
    
    # Process Filter Logic
    filters = {}
    if f_context and f_context != "All":
        filters['context'] = f_context
    if f_done and "hide_done" in f_done:
        filters['hide_done'] = True
        
    if trigger_id == 'btn-save' and name and n_type:
        try:
            val = int(val) if val is not None else 5
            interest = int(interest) if interest is not None else 5
            time = float(time) if time is not None else 1.0
            effort = int(effort) if effort is not None else 2
        except ValueError:
            msg = "Error: Please check your numerical inputs."
            return elements, msg, sugg_ui, html.Div()
            
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
            e_helps = e_helps or []
            e_res = e_res or []

            # Needs: (Prereq -> Target) so Prereq is Source
            # We clear existing incoming Needs
            with manager.get_connection() as conn:
                 cursor = conn.cursor()
                 cursor.execute("DELETE FROM Edges WHERE target=? AND type='Needs'", (name,))
                 conn.commit()
            for src in e_needs:
                 manager.add_edge(src, name, "Needs")

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

        except Exception as e:
            msg = str(e)
            
    elif trigger_id == 'btn-delete' and name:
        try:
            manager.delete_node(name)
            msg = f"Deleted node '{name}'"
        except Exception as e:
            msg = str(e)

    # Re-generate visuals
    elements = generate_elements(filters)
    suggs = get_suggestions(filters)
    
    # Format suggestions table
    if suggs:
        table_header = [html.Thead(html.Tr([html.Th("Task Name"), html.Th("Priority Score"), html.Th("Context"), html.Th("Type")]))]
        row_data = [html.Tr([html.Td(s.name), html.Td(html.Strong(f"{getattr(s, 'priority_score', 0):.2f}")), html.Td(s.context), html.Td(s.type)]) for s in suggs]
        table_body = [html.Tbody(row_data)]
        sugg_ui = dbc.Table(table_header + table_body, bordered=True, hover=True, size="sm")
    # Format traversal UI
    traversal_ui = html.Div(className="text-muted", children="Select a goal node to see prerequisites.")
    if tapped_node and tapped_node.get('type') == 'Goal':
         chains = manager.get_prerequisite_chains(tapped_node.get('id'))
         if not chains:
             traversal_ui = html.P("No incomplete dependencies.", className="text-success")
         else:
             chain_items = []
             for c in chains:
                 chain_items.append(html.Li(" → ".join(c)))
             traversal_ui = html.Ul(chain_items)
             
    elif tapped_node:
        traversal_ui = html.Div(className="text-muted", children=f"Traversal view applies to 'Goal' nodes. Currently selected: {tapped_node.get('type')}")

    return elements, msg, sugg_ui, traversal_ui

if __name__ == '__main__':
    app.run(debug=True)
