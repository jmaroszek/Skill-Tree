import logging
import dash
import webbrowser
import threading
import os
import dash_bootstrap_components as dbc
from layout import build_app_layout
from callbacks import generate_elements, register_callbacks
from config import ENVIRONMENT
import ctypes

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s: %(message)s')

# Fix blurry file explorer on high-DPI Windows displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "Skill Tree (Sandbox)" if ENVIRONMENT == "sandbox" else "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements(), env=ENVIRONMENT)
register_callbacks(app)

@app.server.route('/open-obsidian')
def open_obsidian_route():
    from flask import request, jsonify
    import os
    import urllib.parse
    import subprocess
    from config import ConfigManager
    
    path = request.args.get('path')
    if not path:
        return jsonify({"ok": False, "error": "No path provided"})
        
    vault = ConfigManager.get_obsidian_vault()
    abs_path = os.path.join(vault, path.strip())
    encoded = urllib.parse.quote(abs_path, safe='')
    uri = f'obsidian://open?path={encoded}'
    
    try:
        subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(0.5, webbrowser.open, args=["http://127.0.0.1:8050"]).start()
    app.run(debug=True, dev_tools_ui=False)
