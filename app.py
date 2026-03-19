import dash
import webbrowser
import threading
import os
import dash_bootstrap_components as dbc
from layout import build_app_layout
from callbacks import generate_elements, register_callbacks

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements())
register_callbacks(app)

if __name__ == '__main__':
    # Only open browser in the reloader child process to avoid duplicate tabs
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.5, webbrowser.open, args=["http://127.0.0.1:8050"]).start()
    app.run(debug=True)
