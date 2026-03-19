import dash
import webbrowser
import threading
import os
import subprocess
import urllib.parse
from flask import request, jsonify
import dash_bootstrap_components as dbc
from layout import build_app_layout
from callbacks import generate_elements, register_callbacks

OBSIDIAN_VAULT = r"C:\Users\jonah\Documents\Obsidian"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "Skill Tree"
app.layout = build_app_layout(initial_elements=generate_elements())
register_callbacks(app)


@app.server.route('/open-obsidian')
def open_obsidian():
    """Opens a file in Obsidian using the obsidian:// URI scheme."""
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return jsonify({'ok': False, 'error': 'No path provided'})
    abs_path = os.path.join(OBSIDIAN_VAULT, rel_path)
    encoded = urllib.parse.quote(abs_path, safe='')
    uri = f'obsidian://open?path={encoded}'
    try:
        subprocess.Popen(['cmd', '/c', 'start', '', uri], shell=False)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.server.route('/browse-obsidian')
def browse_obsidian():
    """Opens a native Windows file dialog rooted at the Obsidian vault and returns the relative path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        abs_path = filedialog.askopenfilename(
            initialdir=OBSIDIAN_VAULT,
            title='Select Obsidian File',
            filetypes=[('Markdown files', '*.md'), ('All files', '*.*')]
        )
        root.destroy()
        if not abs_path:
            return jsonify({'path': None})
        # Normalise separators and strip vault prefix
        abs_path = os.path.normpath(abs_path)
        vault_norm = os.path.normpath(OBSIDIAN_VAULT)
        if abs_path.startswith(vault_norm):
            rel = abs_path[len(vault_norm):].lstrip(os.sep)
        else:
            rel = abs_path
        return jsonify({'path': rel})
    except Exception as e:
        return jsonify({'path': None, 'error': str(e)})


if __name__ == '__main__':
    threading.Timer(1.5, webbrowser.open, args=["http://127.0.0.1:8050"]).start()
    app.run(debug=True, use_reloader=True)
