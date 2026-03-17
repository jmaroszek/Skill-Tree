"""
Skill Tree — Entry Point

A Dash application for managing and prioritizing tasks, goals, and projects
using a graph-based data structure.
"""

import dash
import dash_bootstrap_components as dbc
from layout import build_app_layout
from callbacks import generate_elements, register_callbacks

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements())
register_callbacks(app)

if __name__ == '__main__':
    app.run(debug=True)
