"""Explicit application construction and the desktop/browser launch entry point."""
import logging
import sys
import os
import ctypes
import platform
import importlib
import uuid
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

import config
from app_paths import get_log_dir
import database
from version import __version__

_logger = logging.getLogger(__name__)


# The theme, its Lato font and the icon font, served from assets/vendor rather
# than CDNs, so the app looks right offline and makes no third-party requests.
# Dash leaves the vendor folder out of its automatic includes
# (assets_path_ignore); listing the files here puts them ahead of the app's own
# CSS, which overrides them.
VENDOR_STYLESHEETS = [
    "/assets/vendor/lato/lato.css",
    "/assets/vendor/bootswatch-darkly/bootstrap.min.css",
    "/assets/vendor/bootstrap-icons/bootstrap-icons.min.css",
]


@dataclass(frozen=True)
class AppSettings:
    environment: str = "production"
    configure_logging: bool = True
    # --dev: the page polls for server restarts and reloads itself.
    dev: bool = False


def _configure_logging(environment) -> None:
    """Send INFO+ logs to stderr and a rotating per-user app-data file.

    Sandbox and production write to separate log files so the two never
    interleave. File rotates at 5 MB with 3 backups kept (~20 MB ceiling).
    Werkzeug's request log inherits this config since it propagates to root.
    """
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    log_dir = get_log_dir()
    log_name = 'sandbox_app.log' if environment == 'sandbox' else 'app.log'
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / log_name,
            maxBytes=5_000_000,
            backupCount=3,
            encoding='utf-8',
        )
        file_handler.setFormatter(formatter)
    except OSError as exc:
        # An app folder that can't be written. Keep going on stderr alone, so
        # the launcher can refuse with a reason (exit 7), not a traceback.
        file_handler = None
        unwritable = exc

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # basicConfig elsewhere is a no-op once handlers exist; clear any prior
    # handlers in case this module is re-imported (test harness, REPL).
    root.handlers.clear()
    if file_handler is not None:
        root.addHandler(file_handler)
    # The native-window launch runs under pythonw.exe, which has no console:
    # sys.stderr is None there, and a StreamHandler aimed at it would make every
    # log call fail. Only attach the console handler when a real stderr exists.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
    if file_handler is None:
        root.warning("Can't write the log in %s (%s).", log_dir, unwritable)


def report_callback_error(err):
    """Dash's on_error hook: any exception a callback lets escape lands here.

    Without it a failed callback leaves the page as it was, and nobody learns
    why. Log the traceback with what triggered it, open the error modal
    (layout.build_app_error_modal), and leave every output unchanged.
    """
    try:
        from dash import ctx
        trigger = ", ".join(ctx.triggered_prop_ids) or "page load"
    except Exception:
        trigger = "unknown"
    _logger.error("Callback failed (triggered by %s)", trigger, exc_info=err)
    try:
        from dash import set_props
        set_props("app-error-body", {"children": (
            "That action didn't finish because of an unexpected error. The "
            f"details are in the log, in {get_log_dir()}. If it keeps "
            "happening, please report it and include that log.")})
        set_props("modal-app-error", {"is_open": True})
    except Exception:
        _logger.exception("Could not show the callback error")
    return None


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
    _logger.info("Skill Tree %s starting (%s; Python %s on %s).", __version__,
                 settings.environment, platform.python_version(), platform.platform())

    from config import ConfigManager
    from app_services import AppServices
    database.init_db()
    services = services or AppServices()
    ConfigManager.ensure_action_type()
    ConfigManager.ensure_goal_type()
    ConfigManager.ensure_milestone_type()
    # Diagnostics, and any future migration, can tell which build last opened
    # this data.
    ConfigManager.set_last_app_version(__version__)
    # At most once a day, and never fatal: a failure is logged.
    import backup
    backup.run_daily_backup()
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
    from data_callbacks import register_data_callbacks

    cyto.load_extra_layouts()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = dash.Dash(__name__, external_stylesheets=VENDOR_STYLESHEETS,
                    assets_path_ignore=["vendor"],
                    # Polls every 2 s for a restart; only the dev loop restarts.
                    assets_ignore="" if settings.dev else r"hard_reload_on_restart\.js$",
                    on_error=report_callback_error)
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
                     register_analyze_callbacks, register_sidebars_callbacks,
                     register_data_callbacks):
        register(app, services)
    register_context_picker_callbacks(app)
    register_list_toolbar_callbacks(app)
    # Fails at startup, not on the first page load, if a @prerendered
    # callback would also run in the browser.
    prerendered_specs(app)
    app.server.add_url_rule('/open-resource', view_func=open_resource_route,
                            methods=['POST'])
    if settings.dev:
        # hard_reload_on_restart.js reloads the page when this changes.
        boot_id = uuid.uuid4().hex
        app.server.add_url_rule('/_server_boot_id', view_func=lambda: boot_id)
    return app


def open_resource_route():
    """Open one saved link selected from a node's context menu."""
    from flask import request, jsonify
    from graph_manager import GraphManager
    from resource_links import (NeedsConfirmation, get_sections, get_node_links,
                                open_resource)

    payload = request.get_json(silent=True) or {}
    name = payload.get('node')
    section_id = payload.get('section')
    index = payload.get('index', 0)
    if not isinstance(name, str) or not isinstance(section_id, str) or not isinstance(index, int):
        return jsonify({"ok": False, "error": "Invalid Resource selection"}), 400
    if GraphManager().get_node(name) is None:
        return jsonify({"ok": False, "error": "Node not found"}), 404
    section = next((s for s in get_sections() if s['id'] == section_id), None)
    links = get_node_links(name).get(section_id, [])
    if section is None or not 0 <= index < len(links):
        return jsonify({"ok": False, "error": "Resource link not found"}), 404
    try:
        open_resource(links[index], section, confirmed=payload.get('confirmed') is True)
        return jsonify({"ok": True})
    except NeedsConfirmation as ask:
        # The page asks, and sends the request again with confirmed: true.
        return jsonify({"ok": False, "confirm": str(ask)})
    except Exception as exc:
        _logger.warning("Opening a %s link failed: %s", section['name'], exc)
        return jsonify({"ok": False, "error": str(exc)}), 400


def main(argv=None):
    """Launch: own this database, build the app, then serve it (server_runtime)."""
    import server_runtime
    options = server_runtime.parse_args(sys.argv[1:] if argv is None else argv)
    # With --dev in the sandbox, Werkzeug's reloader runs this again in a child
    # process, and restarts that child on every edit. The parent keeps the lock.
    reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    config.ENVIRONMENT = options.environment
    _configure_logging(options.environment)
    lock = server_runtime.InstanceLock(database.get_db_path())
    if not reloader_child:
        try:
            owned = lock.acquire()
        except OSError as exc:
            _refuse(f"Skill Tree can't write to its data folder "
                    f"{lock.lock_path.parent} ({exc}).",
                    database.DatabaseUnwritableError.exit_code)
        if not owned:
            sys.exit(server_runtime.hand_over(lock, options))
    token = server_runtime.launch_token()
    if not options.dev:
        # Nothing this process starts needs it.
        os.environ.pop(server_runtime.TOKEN_ENV, None)
    try:
        app = create_app(AppSettings(environment=options.environment,
                                     configure_logging=False, dev=options.dev))
    except database.DatabaseError as exc:
        # A database this build won't open (newer, damaged, busy, read-only,
        # or an SQLite too old for it). The file is untouched.
        lock.release()
        _refuse(str(exc), exc.exit_code)

    # The first canvas render detects communities with NetworkX, hundreds of
    # modules that the server needn't load before it can answer. Loading them
    # here overlaps the window opening and the page fetching its layout.
    threading.Thread(target=importlib.import_module, args=("networkx",),
                     name="warm-networkx", daemon=True).start()

    if options.dev:
        server_runtime.run_dev(app, options, lock, token, reloader_child)
    else:
        server_runtime.serve(app, options, lock, token)


def _refuse(message, exit_code):
    """Say why Skill Tree can't start, and exit with a code the shell can tell
    apart (docs/app_architecture.md lists them)."""
    _logger.critical("%s", message)
    if sys.stderr is not None:
        print(f"Skill Tree can't start: {message}", file=sys.stderr)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
