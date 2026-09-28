"""How the server runs: where it listens, who may use it, and when it stops.

app.main() builds the app, then hands it here. Four jobs:

- One server per database (InstanceLock). An OS lock beside the database is
  held for the life of the process and dropped by the OS even on a crash. A
  second launch reads where the first one listens and hands over to it.
- Where it listens (serve). Werkzeug binds 127.0.0.1, on any free port for the
  desktop shell, and prints ``SKILLTREE_READY port=<n>`` once it is ready.
- Who may use it (AccessGuard). Only requests addressed to this server by host
  name, and carrying this launch's token, get through.
- When it stops. The desktop shell holds the server's stdin open, and the
  server shuts down when it closes, so a crashed shell leaves no server behind.

``--dev`` swaps serve() for Flask's debug server with hot reload (run_dev).
"""
import hmac
import html
import json
import logging
import os
import secrets
import signal
import socket
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_ENV = "SKILLTREE_TOKEN"
READY = "SKILLTREE_READY"
RUNNING = "SKILLTREE_RUNNING"
# Beside database.DatabaseError's codes (2-7); docs/app_architecture.md lists all.
EXIT_ALREADY_RUNNING = 8
DEFAULT_PORTS = {"production": 8050, "sandbox": 8051}


@dataclass(frozen=True)
class LaunchOptions:
    environment: str = "production"
    port: int = 8050            # 0: any free port
    desktop: bool = False       # launched by the desktop shell
    open_browser: bool = True
    dev: bool = False           # debugger, hot reload, the restart poller
    # A backup's file name, to put in place of a damaged database. The shell
    # passes it once the user has accepted offer_restore()'s offer.
    restore_backup: Optional[str] = None


def parse_args(argv) -> LaunchOptions:
    environment = "sandbox" if "--sandbox" in argv else "production"
    desktop = "--desktop" in argv
    port = 0 if desktop else DEFAULT_PORTS[environment]
    if "--port" in argv:
        i = argv.index("--port")
        try:
            requested = int(argv[i + 1])
        except (IndexError, ValueError):
            requested = None
        if requested is not None and 0 <= requested <= 65535:
            port = requested
    restore = None
    if "--restore-backup" in argv:
        i = argv.index("--restore-backup")
        restore = argv[i + 1] if i + 1 < len(argv) else None
    return LaunchOptions(
        environment=environment,
        port=port,
        desktop=desktop,
        open_browser=not desktop and "--no-browser" not in argv,
        # The shell reads the READY line, which the debug server can't print.
        # A frozen build has no development bundles (packaging/unused_files.py).
        dev="--dev" in argv and not desktop and not getattr(sys, "frozen", False),
        restore_backup=restore,
    )


def launch_token() -> str:
    """This launch's access token: the desktop shell's, or a new one."""
    return os.environ.get(TOKEN_ENV) or secrets.token_urlsafe(32)


def offer_restore(info) -> None:
    """Before refusing a damaged database: name the newest backup that opens
    cleanly (backup.newest_good_backup), which the shell offers to restore."""
    announce(f"SKILLTREE_DAMAGED backup={info['path'].name} when={info['when'].isoformat()}")


def announce(line: str) -> None:
    """A line for whoever launched the server. Never the log file: the lines
    can carry the token."""
    if sys.stdout is None:  # pythonw with nothing attached
        return
    try:
        print(line, flush=True)
    except OSError:  # the shell has gone
        pass


# --- One server per database ------------------------------------------------

class InstanceLock:
    """One server per database file.

    ``<db>.lock`` is locked, never written. ``<db>.instance.json`` says
    where the owner listens, and carries its token, so it gets the same
    protection as the database beside it.
    """

    def __init__(self, db_path):
        db_path = Path(db_path)
        self.lock_path = db_path.with_name(db_path.stem + ".lock")
        self.info_path = db_path.with_name(db_path.stem + ".instance.json")
        self._handle = None

    def acquire(self) -> bool:
        """True if this process now owns the database, False if another does.

        OSError when the data folder can't be created or written.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        try:
            _lock(handle)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        self._write_info({"pid": os.getpid(), "port": None})
        return True

    def publish(self, port: int, token: str) -> None:
        from version import __version__
        self._write_info({"pid": os.getpid(), "port": port, "token": token,
                          "version": __version__})

    def release(self) -> None:
        if self._handle is None:
            return
        info = self.read_info()
        if info and info.get("pid") == os.getpid():
            try:
                self.info_path.unlink()
            except OSError:
                pass
        try:
            _unlock(self._handle)
        except OSError:
            pass
        self._handle.close()
        self._handle = None

    def read_info(self):
        try:
            return json.loads(self.info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def wait_for_running(self, timeout: float = 30.0):
        """The owner's info once it is serving, or None if it never is."""
        deadline = time.monotonic() + timeout
        while True:
            info = self.read_info()
            if info and info.get("port"):
                return info
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def _write_info(self, info: dict) -> None:
        tmp = self.info_path.with_name(self.info_path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(info, f)
        # Windows refuses to replace a file another process has open; a second
        # launch only ever holds it for a moment.
        for attempt in range(20):
            try:
                os.replace(tmp, self.info_path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)


if sys.platform == "win32":
    import msvcrt

    def _lock(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def hand_over(lock: InstanceLock, options: LaunchOptions) -> int:
    """Another process owns this database: point at it. Returns the exit code."""
    info = lock.wait_for_running()
    if info is None:
        message = ("Another Skill Tree is using this data but isn't answering. "
                   "Close it, or wait a moment and try again.")
        logger.warning(message)
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        return EXIT_ALREADY_RUNNING
    port, token = info["port"], info.get("token", "")
    if options.desktop:
        announce(f"{RUNNING} port={port} token={token}")
        return EXIT_ALREADY_RUNNING
    logger.info("Skill Tree is already running on port %s (process %s).", port,
                info.get("pid"))
    link = f"http://127.0.0.1:{port}/?token={token}"
    if options.open_browser:
        webbrowser.open(link)
    else:
        announce(f"Skill Tree is already running at {link}")
    return 0


# --- Who may use the server -------------------------------------------------

_REFUSED_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Skill Tree</title></head>
<body style="background:#222;color:#dee2e6;font-family:sans-serif;margin:3rem">
<h1 style="font-weight:400">Skill Tree</h1>
<p>{message}</p></body></html>"""

_SESSION_BOOTSTRAP = """<!doctype html>
<html><head><meta charset="utf-8"><title>Skill Tree</title></head>
<body style="background:#222;color:#dee2e6;font-family:sans-serif;margin:3rem">
<p id="message">Opening Skill Tree&hellip;</p>
<script>
try {
  const token = sessionStorage.getItem('skilltree_launch_token');
  if (token) location.replace('/?token=' + encodeURIComponent(token));
  else document.getElementById('message').textContent =
    'Use the window or link Skill Tree opened for this launch.';
} catch (_) {
  document.getElementById('message').textContent =
    'Use the window or link Skill Tree opened for this launch.';
}
</script></body></html>"""


class AccessGuard:
    """Only this launch's own window may use the server.

    Every request passes these checks, ahead of anything Dash does:

    - The Host header is 127.0.0.1 or localhost, on this port. A web page
      that rebinds its own domain to 127.0.0.1 still sends its domain, and
      fails here.
    - The launch link serves the page once with its token. That page keeps the
      token in origin-scoped sessionStorage and sends it in a request header.
      A cookie would also be sent to a different listener on the same host,
      since browser cookies are not scoped by port.
    - A request that could change something (anything but GET or HEAD) and
      says where it comes from must come from this server's own page. A
      browser counts every port of 127.0.0.1 as one site. Such a request names
      that page in its Origin header, and fails here.
    """

    def __init__(self, token: str, port: int, environment: str):
        self._token = token.encode("utf-8")
        self._hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self._origins = {f"http://{host}" for host in self._hosts}
        self._legacy_cookie = f"skilltree_{environment}"

    def install(self, flask_app) -> None:
        flask_app.before_request_funcs.setdefault(None, []).insert(0, self.check)
        flask_app.after_request(self._protect_launch_response)

    def _protect_launch_response(self, response):
        from flask import request
        if request.path == "/":
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
            if "token" in request.args and response.status_code == 200:
                response.delete_cookie(self._legacy_cookie, path="/")
        return response

    def _matches(self, value) -> bool:
        return hmac.compare_digest(str(value).encode("utf-8"), self._token)

    def check(self):
        from flask import request
        if request.host not in self._hosts:
            return _refused("This server only answers Skill Tree's own window.")
        # A request without an Origin header still needs the token header.
        # "null" (a sandboxed or file: page) is refused.
        origin = request.headers.get("Origin")
        if (request.method not in ("GET", "HEAD") and origin is not None
                and origin not in self._origins):
            return _refused("This server only answers Skill Tree's own window.")
        if request.path == "/" and "token" in request.args:
            if not self._matches(request.args.get("token", "")):
                return _refused("This link is out of date. Start Skill Tree again.")
            # Dash renders the page; the inline bootstrap removes the query
            # from browser history before Dash makes any data requests.
            return None
        if request.method in ("GET", "HEAD") and (
                request.path.startswith("/assets/")
                or request.path.startswith("/_dash-component-suites/")
                or request.path == "/_favicon.ico"):
            # These are static files. No graph data is served from them.
            return None
        if self._matches(request.headers.get("X-Skill-Tree-Token", "")):
            return None
        if request.path == "/" and request.method == "GET":
            return _SESSION_BOOTSTRAP, 200, {"Content-Type": "text/html; charset=utf-8"}
        return _refused("This page needs the link Skill Tree opened it with. If "
                        "Skill Tree restarted, use the window or tab it just "
                        "opened, or start it again.")


def _refused(message):
    from flask import request
    if request.method == "GET" and request.accept_mimetypes.accept_html:
        return _REFUSED_PAGE.format(message=html.escape(message)), 403
    return message, 403, {"Content-Type": "text/plain; charset=utf-8"}


# --- Serving ------------------------------------------------------------------

def quiet_request_log() -> None:
    """One log line per request is noise outside development."""
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def watch_stdin(on_eof):
    """Call on_eof when stdin closes: the desktop shell has quit or died."""
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        logger.warning("No stdin to watch; the server won't notice the shell closing.")
        return None

    def wait():
        try:
            while stream.read1(4096):   # the shell never writes; this only waits
                pass
        except (OSError, ValueError):
            pass
        logger.info("The desktop shell closed; shutting down.")
        on_eof()

    thread = threading.Thread(target=wait, name="shell-watchdog", daemon=True)
    thread.start()
    return thread


def _listening_socket(port: int) -> socket.socket:
    """A socket listening on 127.0.0.1 that no other program shares."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            # Windows. Its SO_REUSEADDR, which Werkzeug would set, lets a
            # second program bind a port another is listening on, and then
            # either may get the connections. Exclusive use refuses a taken
            # port, and stops anyone taking ours.
            sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        else:
            # Elsewhere it only allows rebinding a port a previous run left
            # in TIME_WAIT.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(128)
    except OSError:
        sock.close()
        raise
    return sock


def make_http_server(flask_app, port: int):
    """A threaded server on 127.0.0.1: on ``port``, or any free port if that
    one is taken.

    The socket is bound here, not by Werkzeug, which would exit the process
    on a taken port. Closing the server waits for requests in progress
    (block_on_close), so a save made just before quitting still lands.
    """
    from werkzeug.serving import make_server
    try:
        sock = _listening_socket(port)
    except OSError as exc:
        if port == 0:
            raise
        # Not another Skill Tree for this data: that one would hold the lock.
        logger.warning("Port %d is taken (%s); using a free port instead.", port, exc)
        sock = _listening_socket(0)
    try:
        return make_server("127.0.0.1", sock.getsockname()[1], flask_app,
                           threaded=True, fd=sock.fileno())
    finally:
        sock.close()  # the server holds its own duplicate


def serve(app, options: LaunchOptions, lock: InstanceLock, token: str) -> None:
    """Serve until interrupted, or until the desktop shell closes stdin."""
    server = make_http_server(app.server, options.port)
    port = server.port
    AccessGuard(token, port, options.environment).install(app.server)
    quiet_request_log()
    lock.publish(port, token)
    logger.info("Serving on http://127.0.0.1:%d", port)

    def stop(*_args):
        # shutdown() waits for serve_forever(), so it can't run on its thread.
        threading.Thread(target=server.shutdown, name="shutdown", daemon=True).start()

    if options.desktop:
        watch_stdin(stop)
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, stop)
    link = f"http://127.0.0.1:{port}/?token={token}"
    announce(f"{READY} port={port}")
    if options.open_browser:
        threading.Timer(0.2, webbrowser.open, args=[link]).start()
    elif not options.desktop:
        announce(f"Skill Tree is running at {link}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lock.release()
        logger.info("Stopped.")


def run_dev(app, options: LaunchOptions, lock: InstanceLock, token: str,
            reloader_child: bool) -> None:
    """--dev: Flask's debugger on a fixed port, with hot reload in the sandbox.

    Werkzeug's reloader runs the app in a child process that it restarts on
    every edit. The parent holds the lock and passes the token down, so the
    open tab keeps working across reloads.
    """
    port = options.port or DEFAULT_PORTS[options.environment]
    AccessGuard(token, port, options.environment).install(app.server)
    hot = options.environment == "sandbox"
    link = f"http://127.0.0.1:{port}/?token={token}"
    if not reloader_child:
        lock.publish(port, token)
        os.environ[TOKEN_ENV] = token
        announce(f"Skill Tree (dev) is running at {link}")
        if options.open_browser:
            threading.Timer(0.5, webbrowser.open, args=[link]).start()
    try:
        app.run(debug=True, dev_tools_ui=False, dev_tools_hot_reload=hot,
                use_reloader=hot, port=port)
    finally:
        if not reloader_child:
            lock.release()
