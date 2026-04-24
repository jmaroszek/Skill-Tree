import logging
import sys
import os
import ctypes
import uuid

# Set environment before importing modules that read config.ENVIRONMENT (e.g. database.py)
import config

if "-sandbox" in sys.argv:
    config.ENVIRONMENT = "sandbox"
ENVIRONMENT = config.ENVIRONMENT

import dash
import dash_cytoscape as cyto
import webbrowser
import threading
import dash_bootstrap_components as dbc
from layout import build_app_layout

cyto.load_extra_layouts()
from callbacks import generate_elements, register_callbacks
from event_callbacks import register_event_callbacks
from details_callbacks import register_details_callbacks
from next_callbacks import register_next_callbacks
from settings_callbacks import register_settings_callbacks
from analyze_callbacks import register_analyze_callbacks
from config import ConfigManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s: %(message)s')

# Fix blurry file explorer on high-DPI Windows displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

ConfigManager.ensure_action_type()
ConfigManager.ensure_goal_type()

# Safety-net: repair any drift between stored node.status and what the cascade
# would derive from current Needs_Hard edges. Covers cases where a mutation
# path bypassed _update_node_state (e.g. add_edge IntegrityError, direct SQL).
from graph_manager import GraphManager
GraphManager().recompute_all_statuses()

app = dash.Dash(__name__, external_stylesheets=[
    dbc.themes.DARKLY,
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
])
app.title = "Skill Tree (Sandbox)" if ENVIRONMENT == "sandbox" else "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements(), env=ENVIRONMENT)
register_callbacks(app)
register_event_callbacks(app)
register_details_callbacks(app)
register_next_callbacks(app)
register_settings_callbacks(app)
register_analyze_callbacks(app)

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

SERVER_BOOT_ID = uuid.uuid4().hex

@app.server.route('/_server_boot_id')
def _server_boot_id():
    return SERVER_BOOT_ID

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(0.5, webbrowser.open, args=["http://127.0.0.1:8050"]).start()
    app.run(debug=True, dev_tools_ui=False, dev_tools_hot_reload=False)
