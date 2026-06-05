import logging
import sys
import os
import ctypes
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Set environment before importing modules that read config.ENVIRONMENT (e.g. database.py)
import config

if "--sandbox" in sys.argv:
    config.ENVIRONMENT = "sandbox"
ENVIRONMENT = config.ENVIRONMENT


def _configure_logging() -> None:
    """Send INFO+ logs to stderr AND a rotating file in data/.

    Sandbox and production write to separate log files so the two never
    interleave. File rotates at 5 MB with 3 backups kept (~20 MB ceiling).
    Werkzeug's request log inherits this config since it propagates to root.
    """
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    log_dir = Path(__file__).parent / 'data'
    log_dir.mkdir(exist_ok=True)
    log_name = 'sandbox_app.log' if ENVIRONMENT == 'sandbox' else 'app.log'

    file_handler = RotatingFileHandler(
        log_dir / log_name,
        maxBytes=5_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # basicConfig elsewhere is a no-op once handlers exist; clear any prior
    # handlers in case this module is re-imported (test harness, REPL).
    root.handlers.clear()
    root.addHandler(file_handler)
    # The native-window launch runs under pythonw.exe, which has no console:
    # sys.stderr is None there, and a StreamHandler aimed at it would make every
    # log call fail. Only attach the console handler when a real stderr exists.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)


_configure_logging()

import dash
import dash_cytoscape as cyto
import webbrowser
import threading
import socket
import urllib.error
import urllib.request
import dash_bootstrap_components as dbc
from layout import build_app_layout

cyto.load_extra_layouts()
from callbacks import generate_elements, register_callbacks
from event_callbacks import register_event_callbacks
from details_callbacks import register_details_callbacks
from next_callbacks import register_next_callbacks
from settings_callbacks import register_settings_callbacks
from review_hub_callbacks import register_review_hub_callbacks
from analyze_callbacks import register_analyze_callbacks
from sidebars_callbacks import register_sidebars_callbacks
from config import ConfigManager

# Fix blurry file explorer on high-DPI Windows displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

ConfigManager.ensure_action_type()
ConfigManager.ensure_goal_type()
ConfigManager.ensure_milestone_type()

# Safety-net: repair any drift between stored node.status and what the cascade
# would derive from current Needs_Hard edges. Covers cases where a mutation
# path bypassed _update_node_state (e.g. add_edge IntegrityError, direct SQL).
from graph_manager import GraphManager
_logger = logging.getLogger(__name__)
_repaired = GraphManager().recompute_all_statuses()
if _repaired:
    _logger.info("Startup safety-net repaired %d node status(es).", _repaired)

app = dash.Dash(__name__, external_stylesheets=[
    dbc.themes.DARKLY,
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
])
app.title = "Skill Tree (Sandbox)" if ENVIRONMENT == "sandbox" else "Skill Tree"
app.layout = lambda: build_app_layout(initial_elements=generate_elements(), env=ENVIRONMENT)
register_callbacks(app)
register_event_callbacks(app)
register_details_callbacks(app)
register_next_callbacks(app)
register_settings_callbacks(app)
register_review_hub_callbacks(app)
register_analyze_callbacks(app)
register_sidebars_callbacks(app)

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


def _parse_port(argv) -> int:
    """Return the requested app port, defaulting to the project standard."""
    port = 8050
    if "--port" in argv:
        i = argv.index("--port")
        if i + 1 < len(argv):
            try:
                port = int(argv[i + 1])
            except ValueError:
                pass
    return port


def _port_is_free(port: int) -> bool:
    """True when nothing is bound to the loopback port.

    A bind attempt answers this instantly and authoritatively. A connect
    probe can't: on Windows a connection to a *closed* port isn't refused
    promptly (the SYN is dropped, so a raw connect only fails after ~2s),
    which means a connect-with-timeout would burn its full timeout on every
    normal launch — the common case where no server is running yet. bind()
    never waits.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _existing_skill_tree_server(port: int) -> bool:
    """True when a Skill Tree server is already answering on this port.

    Only reached once the port is known to be occupied, so the connection
    succeeds immediately and the short timeout is never spent waiting on a
    dropped SYN — it only guards against a foreign process that accepts the
    connection but stalls before responding.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/_server_boot_id",
            timeout=0.35,
        ) as response:
            body = response.read(128).decode("utf-8", errors="ignore").strip()
            return response.status == 200 and bool(body)
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _existing_instance_running(port: int) -> bool:
    """True when this launch should exit because our app is already running.

    Fast path: a free port means no instance exists, so return immediately
    with no network round-trip. Only when the port is occupied do we confirm
    (via the boot-id endpoint) that the occupant is actually a Skill Tree
    server rather than some unrelated process holding the port.
    """
    if _port_is_free(port):
        return False
    return _existing_skill_tree_server(port)


def _wait_until_serving(port: int, timeout: float = 20.0) -> None:
    """Block until the local server answers, so the window never loads a dead URL.

    The server boots on a background thread; this gives it a moment to start
    accepting before the window points at it. Returns as soon as the boot-id
    route responds, and gives up after `timeout` rather than hanging forever
    (the window then just shows whatever state the server is in).
    """
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _existing_skill_tree_server(port):
            return
        time.sleep(0.15)


# The native window, set once it exists. Kept module-level — NOT as an attribute
# of the js_api object — so the object pywebview bridges to JS holds no reference
# back to the Window. That circular reference jams pywebview's bridge setup and
# hangs the window the moment the page loads.
_native_window = None


class _WindowControls:
    """JS-callable window controls for the frameless native window.

    Exposed to the page as ``window.pywebview.api.*``; the custom title-bar
    buttons (assets/window_controls.js) call these. Methods reach the window via
    the module-level ``_native_window`` rather than holding it as an attribute —
    see the note above.
    """

    def __init__(self) -> None:
        self._maximized = False

    def minimize(self) -> None:
        if _native_window is not None:
            _native_window.minimize()

    def toggle_maximize(self) -> bool:
        if _native_window is None:
            return self._maximized
        if self._maximized:
            _native_window.restore()
        else:
            _native_window.maximize()
        self._maximized = not self._maximized
        return self._maximized

    def close(self) -> None:
        if _native_window is not None:
            _native_window.destroy()


def _run_in_window(port: int) -> None:
    """Run Skill Tree as a frameless native desktop window — no terminal, no
    browser tab, and no OS title bar.

    The Dash/Flask server runs on a daemon thread while pywebview owns the main
    thread and the OS window. Closing the window returns from webview.start(),
    the process exits, and the daemon server thread dies with it. So the window
    *is* the app's lifecycle — unlike a browser tab, which is just an HTTP client
    whose closing leaves the server running.

    frameless=True drops the OS caption; the window controls live in the app's
    own top bar (layout.main_tabs + assets/window_controls.js) and call back
    through ``controls`` over pywebview's JS API. easy_drag=False so only the top
    bar (class .pywebview-drag-region) moves the window, never the canvas.
    """
    import webview

    def _serve() -> None:
        # debug=False: the in-browser Werkzeug debugger is pointless inside a
        # native window, and debug-mode signal handling is fussy off the main
        # thread. Tracebacks still land in data/<env>_app.log. threaded=True lets
        # the dev server handle Dash's concurrent callback requests.
        app.run(debug=False, dev_tools_ui=False, dev_tools_hot_reload=False,
                use_reloader=False, port=port, threaded=True)

    threading.Thread(target=_serve, daemon=True).start()
    _wait_until_serving(port)

    global _native_window
    window = webview.create_window(
        app.title,
        f"http://127.0.0.1:{port}",
        width=1400,
        height=900,
        min_size=(900, 600),
        frameless=True,
        easy_drag=False,
        js_api=_WindowControls(),
    )
    _native_window = window
    webview.start()


if __name__ == '__main__':
    # Optional --port flag so a sandbox instance can run alongside production
    # without colliding on 8050.
    _port = _parse_port(sys.argv)
    # --window: run as a native desktop window (launched via pythonw, so no
    # terminal) instead of auto-opening a browser tab. The desktop shortcut uses
    # this; plain `python app.py` keeps the browser flow for development.
    _native_window = "--window" in sys.argv
    # --no-browser: just run the server, don't auto-open a browser. Used when an
    # external shell (the Electron app) hosts the page and loads the URL itself.
    _no_browser = "--no-browser" in sys.argv

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and _existing_instance_running(_port):
        _logger.info("Skill Tree is already running on port %d; exiting duplicate launch.", _port)
        sys.exit(0)

    if _native_window:
        _run_in_window(_port)
    elif _no_browser:
        # Server-only mode for an external shell (Electron): no browser tab and
        # no native window. threaded=True handles Dash's concurrent callbacks.
        app.run(debug=False, dev_tools_ui=False, dev_tools_hot_reload=False,
                use_reloader=False, port=_port, threaded=True)
    else:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            threading.Timer(0.5, webbrowser.open, args=[f"http://127.0.0.1:{_port}"]).start()
        # use_reloader=False: with the reloader on (Flask's default under debug=True)
        # Werkzeug re-execs the whole module in a child process, so every import and
        # the startup status recompute run twice — ~2.4s of duplicated boot work.
        # Hot reload is already disabled (dev_tools_hot_reload=False), so the reloader
        # bought nothing here. debug=True is kept for the in-browser error pages.
        app.run(debug=True, dev_tools_ui=False, dev_tools_hot_reload=False,
                use_reloader=False, port=_port)
