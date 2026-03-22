import dash
import webbrowser
import threading
import os
import subprocess
import dash_bootstrap_components as dbc
from layout import build_app_layout
from callbacks import generate_elements, register_callbacks
from config import ConfigManager, ENVIRONMENT

# Fix High DPI blurriness for Tkinter dialogs
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "Skill Tree (Sandbox)" if ENVIRONMENT == "sandbox" else "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements(), env=ENVIRONMENT)
register_callbacks(app)


if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(1, webbrowser.open, args=["http://127.0.0.1:8050"]).start()
    app.run(debug=True, use_reloader=False)
