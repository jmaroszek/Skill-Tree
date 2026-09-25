"""Explicit application construction and the desktop/browser launch entry point."""
import logging
import sys
import os
import ctypes
import importlib
import uuid
import webbrowser
import threading
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

import config
from app_paths import get_log_dir
import database

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppSettings:
    environment: str = "production"
    configure_logging: bool = True


def _configure_logging(environment) -> None:
    """Send INFO+ logs to stderr and a rotating per-user app-data file.

    Sandbox and production write to separate log files so the two never
    interleave. File rotates at 5 MB with 3 backups kept (~20 MB ceiling).
    Werkzeug's request log inherits this config since it propagates to root.
    """
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = 'sandbox_app.log' if environment == 'sandbox' else 'app.log'

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


def create_app(settings=None, services=None):
    """Build one app after selecting its database and running startup repairs.

    Like the desktop launcher, this process owns one database. Tests may
    replace database.get_db_path before construction to use disposable data.
    """
    settings = settings or AppSettings()
    if settings.environment not in {"production", "sandbox"}:
        raise ValueError("Unknown application environment")
    if database._db_path_cache is not None and config.ENVIRONMENT != settings.environment:
        raise RuntimeError("A process cannot switch databases after startup")
    config.ENVIRONMENT = settings.environment
    if settings.configure_logging:
        _configure_logging(settings.environment)

    from config import ConfigManager
    from app_services import AppServices
    database.init_db()
    services = services or AppServices()
    ConfigManager.ensure_action_type()
    ConfigManager.ensure_goal_type()
    ConfigManager.ensure_milestone_type()
    with database.get_connection() as conn:
        node_count = conn.execute("SELECT COUNT(*) FROM Nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM Edges").fetchone()[0]
    _logger.info(
        "Using database %s (%d nodes, %d edges).",
        database.get_db_path(), node_count, edge_count,
    )
    repaired = services.graph.recompute_all_statuses()
    if repaired:
        _logger.info("Startup safety-net repaired %d node status(es).", repaired)
    rewoken = services.events.reconcile_dormant_flags()
    if rewoken:
        _logger.info("Startup safety-net rewoke %d node(s) their event had "
                     "already activated.", rewoken)

    import dash
    import dash_cytoscape as cyto
    import dash_bootstrap_components as dbc
    from layout import build_app_layout, build_index_string
    from canvases import install_client_registry
    from prerender import prerender_layout, prerendered_specs
    from callbacks import register_callbacks
    from event_callbacks import register_event_callbacks
    from details_callbacks import register_details_callbacks
    from next_callbacks import register_next_callbacks
    from settings_callbacks import register_settings_callbacks
    from review_hub_callbacks import register_review_hub_callbacks
    from analyze_callbacks import register_analyze_callbacks
    from sidebars_callbacks import register_sidebars_callbacks
    from context_picker import register_context_picker_callbacks
    from list_toolbar import register_list_toolbar_callbacks

    cyto.load_extra_layouts()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = dash.Dash(__name__, external_stylesheets=[
        dbc.themes.DARKLY,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ])
    app.title = "Skill Tree (Sandbox)" if settings.environment == "sandbox" else "Skill Tree"
    app.index_string = build_index_string()
    app.skill_tree_services = services
    install_client_registry(app)
    # Built per request, after registration below. prerender_layout runs the
    # @prerendered callbacks' initial calls into the layout, so the browser
    # doesn't ask for them on load.
    app.layout = database.snapshot_read(
        lambda: prerender_layout(
            build_app_layout(initial_elements=[], env=settings.environment),
            app))
    for register in (register_callbacks, register_event_callbacks,
                     register_details_callbacks, register_next_callbacks,
                     register_settings_callbacks, register_review_hub_callbacks,
                     register_analyze_callbacks, register_sidebars_callbacks):
        register(app, services)
    register_context_picker_callbacks(app)
    register_list_toolbar_callbacks(app)
    # Fails at startup, not on the first page load, if a @prerendered
    # callback would also run in the browser.
    prerendered_specs(app)
    app.server.add_url_rule('/open-obsidian', view_func=open_obsidian_route)
    app.server.add_url_rule('/open-resource', view_func=open_resource_route,
                            methods=['POST'])
    boot_id = uuid.uuid4().hex
    app.server.add_url_rule('/_server_boot_id', view_func=lambda: boot_id)
    return app


def open_obsidian_route():
    from flask import request, jsonify
    from resource_links import get_sections, open_resource
    
    path = request.args.get('path')
    if not path:
        return jsonify({"ok": False, "error": "No path provided"})
        
    try:
        section = next(row for row in get_sections() if row['id'] == 'obsidian')
        open_resource(path, section)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def open_resource_route():
    """Open one saved link selected from a node's context menu."""
    from flask import request, jsonify
    from graph_manager import GraphManager
    from resource_links import get_sections, get_node_links, open_resource

    payload = request.get_json(silent=True) or {}
    name = payload.get('node')
    section_id = payload.get('section')
    index = payload.get('index', 0)
    if not isinstance(name, str) or not isinstance(section_id, str) or not isinstance(index, int):
        return jsonify({"ok": False, "error": "Invalid Resource selection"}), 400
    if GraphManager().get_node(name) is None:
        return jsonify({"ok": False, "error": "Node not found"}), 404
    section = next((s for s in get_sections() if s['id'] == section_id and s['enabled']), None)
    links = get_node_links(name).get(section_id, [])
    if section is None or not 0 <= index < len(links):
        return jsonify({"ok": False, "error": "Resource link not found"}), 404
    try:
        open_resource(links[index], section)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    environment = "sandbox" if "--sandbox" in argv else "production"
    app = create_app(AppSettings(environment=environment))
    # Optional --port flag so a sandbox instance can run alongside production
    # without colliding on 8050.
    _port = _parse_port(argv)
    # --no-browser: just run the server, don't auto-open a browser. Used when the
    # Electron desktop shell hosts the page and loads the URL itself.
    _no_browser = "--no-browser" in argv

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and _existing_instance_running(_port):
        _logger.info("Skill Tree is already running on port %d; exiting duplicate launch.", _port)
        sys.exit(0)

    # The first canvas render detects communities with NetworkX, hundreds of
    # modules that the server needn't load before it can answer. Loading them
    # here overlaps the window opening and the page fetching its layout.
    threading.Thread(target=importlib.import_module, args=("networkx",),
                     name="warm-networkx", daemon=True).start()

    if _no_browser:
        # Server-only mode for the Electron desktop shell: no browser tab.
        # threaded=True handles Dash's concurrent callbacks.
        app.run(debug=False, dev_tools_ui=False, dev_tools_hot_reload=False,
                use_reloader=False, port=_port, threaded=True)
    else:
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            threading.Timer(0.5, webbrowser.open, args=[f"http://127.0.0.1:{_port}"]).start()
        # Sandbox launches turn on hot reload so edits to assets (CSS/JS) and to
        # Python source apply in the browser without a manual kill-and-relaunch —
        # the fast edit loop. Cost: the reloader re-execs the module in a child
        # process, so every import and the startup status recompute run twice
        # (~2.4s of duplicated boot). That's worth it in the throwaway sandbox but
        # not in production, where this path stays single-boot with no reload.
        # The duplicate-launch guard above is reloader-safe: it only runs in the
        # parent (WERKZEUG_RUN_MAIN unset) and is skipped in the child the
        # reloader spawns (WERKZEUG_RUN_MAIN=="true"). debug=True also keeps the
        # in-browser error pages.
        _hot_reload = (environment == "sandbox")
        app.run(debug=True, dev_tools_ui=False, dev_tools_hot_reload=_hot_reload,
                use_reloader=_hot_reload, port=_port)


if __name__ == "__main__":
    main()
