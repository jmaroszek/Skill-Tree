"""How the server runs: where it listens, who may use it, when it stops (P3.2-P3.6)."""
import http.client
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from flask import Flask

import server_runtime
from server_runtime import AccessGuard, InstanceLock, LaunchOptions, parse_args

ROOT = Path(__file__).resolve().parents[1]


# --- Arguments -------------------------------------------------------------

@pytest.mark.parametrize("argv, expected", [
    ([], LaunchOptions("production", 8050, desktop=False, open_browser=True, dev=False)),
    (["--sandbox"], LaunchOptions("sandbox", 8051, False, True, False)),
    (["--port", "9000"], LaunchOptions("production", 9000, False, True, False)),
    (["--port", "nope"], LaunchOptions("production", 8050, False, True, False)),
    (["--port", "70000"], LaunchOptions("production", 8050, False, True, False)),
    (["--no-browser"], LaunchOptions("production", 8050, False, False, False)),
    (["--dev", "--sandbox"], LaunchOptions("sandbox", 8051, False, True, True)),
    # The desktop shell: any free port, no browser, never the debugger.
    (["--desktop"], LaunchOptions("production", 0, True, False, False)),
    (["--desktop", "--sandbox", "--dev"], LaunchOptions("sandbox", 0, True, False, False)),
    (["--desktop", "--port", "9000"], LaunchOptions("production", 9000, True, False, False)),
])
def test_arguments(argv, expected):
    assert parse_args(argv) == expected


def test_a_frozen_build_ignores_dev(monkeypatch):
    """Its Dash has no development bundles to serve (packaging/unused_files.py)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert parse_args(["--dev", "--sandbox"]).dev is False


# --- One server per database (P3.3) ----------------------------------------

def _db(tmp_path, name="skilltree.db"):
    return tmp_path / "Data" / name


def test_the_first_launch_owns_the_database_and_a_second_does_not(tmp_path):
    first, second = InstanceLock(_db(tmp_path)), InstanceLock(_db(tmp_path))
    assert first.acquire() is True     # creates the Data folder too
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_sandbox_and_production_are_separate(tmp_path):
    production = InstanceLock(_db(tmp_path, "skilltree.db"))
    sandbox = InstanceLock(_db(tmp_path, "sandbox_skilltree.db"))
    assert production.acquire() and sandbox.acquire()
    production.release()
    sandbox.release()


def test_the_owner_publishes_where_it_listens(tmp_path):
    owner = InstanceLock(_db(tmp_path))
    owner.acquire()
    assert owner.read_info()["port"] is None      # still starting
    owner.publish(port=51234, token="secret")

    info = InstanceLock(_db(tmp_path)).read_info()
    assert info["port"] == 51234 and info["token"] == "secret"
    assert info["pid"] == os.getpid()
    owner.release()
    assert InstanceLock(_db(tmp_path)).read_info() is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_the_published_token_is_readable_only_by_its_user(tmp_path):
    owner = InstanceLock(_db(tmp_path))
    owner.acquire()
    owner.publish(port=1, token="secret")
    assert owner.info_path.stat().st_mode & 0o077 == 0
    owner.release()


def _hold_lock_in_another_process(db_path):
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from server_runtime import InstanceLock
        lock = InstanceLock({str(db_path)!r})
        print("held" if lock.acquire() else "refused", flush=True)
        time.sleep(60)
    """)
    proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def test_the_lock_holds_across_processes_and_dies_with_its_owner(tmp_path):
    db_path = _db(tmp_path)
    holder = _hold_lock_in_another_process(db_path)
    try:
        assert InstanceLock(db_path).acquire() is False
    finally:
        holder.kill()       # a crash: no cleanup runs
        holder.wait(timeout=10)
        holder.stdout.close()
    late = InstanceLock(db_path)
    assert late.acquire() is True
    late.release()


def test_a_data_folder_that_cant_be_created_is_an_error(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the Data folder should be")
    with pytest.raises(OSError):
        InstanceLock(blocker / "Data" / "skilltree.db").acquire()


# --- Only this launch's window may use the server (P3.4) --------------------

PORT = 8123


@pytest.fixture
def guarded():
    app = Flask(__name__)
    app.add_url_rule("/", "page", view_func=lambda: "the app")
    app.add_url_rule("/_dash-update-component", "update", view_func=lambda: "ok",
                     methods=["POST"])
    AccessGuard("t0ken", PORT, "sandbox").install(app)
    return app.test_client()


def _get(client, path="/", host=f"127.0.0.1:{PORT}", **kwargs):
    return client.get(path, headers={"Host": host}, **kwargs)


def test_without_the_token_the_server_refuses(guarded):
    response = _get(guarded)
    assert response.status_code == 403
    assert "link" in response.get_data(as_text=True)


def test_the_token_link_sets_a_strict_cookie_and_drops_the_token(guarded):
    response = _get(guarded, "/?token=t0ken")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/")
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("skilltree_sandbox=t0ken")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie

    assert _get(guarded).status_code == 200            # the cookie now rides along
    posted = guarded.post("/_dash-update-component", headers={"Host": f"127.0.0.1:{PORT}"})
    assert posted.status_code == 200


@pytest.mark.parametrize("token", ["wrong", "", "t0ken-and-more", "töken"])
def test_a_wrong_token_is_refused_and_sets_nothing(guarded, token):
    response = _get(guarded, f"/?token={token}")
    assert response.status_code == 403
    assert "Set-Cookie" not in response.headers


@pytest.mark.parametrize("host", ["evil.example", f"evil.example:{PORT}",
                                  "127.0.0.1:9999", "127.0.0.1", "0.0.0.0:8123"])
def test_another_host_name_is_refused_even_with_the_cookie(guarded, host):
    """A DNS-rebinding page reaches 127.0.0.1 under its own host name."""
    _get(guarded, "/?token=t0ken")
    assert _get(guarded, host=host).status_code == 403


def test_localhost_is_the_same_server(guarded):
    assert _get(guarded, "/?token=t0ken", host=f"localhost:{PORT}").status_code in (302, 303)
    assert _get(guarded, host=f"localhost:{PORT}").status_code == 200


def _post(client, origin=None, host=f"127.0.0.1:{PORT}"):
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/_dash-update-component", headers=headers)


@pytest.mark.parametrize("origin", ["http://127.0.0.1:9999", "http://localhost:3000",
                                    "null", "https://127.0.0.1:8123", "http://evil.example"])
def test_a_change_from_another_page_is_refused_even_with_the_cookie(guarded, origin):
    """Every port of 127.0.0.1 is one site to a browser, so SameSite=Strict
    still sends the cookie with a request from a page on another local port."""
    _get(guarded, "/?token=t0ken")
    assert _post(guarded, origin).status_code == 403


@pytest.mark.parametrize("origin", [f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", None])
def test_the_apps_own_page_and_non_browser_clients_get_through(guarded, origin):
    _get(guarded, "/?token=t0ken")
    assert _post(guarded, origin).status_code == 200


def test_a_read_from_elsewhere_still_only_needs_the_cookie(guarded):
    """Origin matters for requests that can change something. A read without
    the cookie is refused as before, and the page can't see a response."""
    _get(guarded, "/?token=t0ken")
    headers = {"Host": f"127.0.0.1:{PORT}", "Origin": "http://127.0.0.1:9999"}
    assert guarded.get("/", headers=headers).status_code == 200


def test_the_real_app_is_guarded_before_dash_does_any_work(monkeypatch):
    import app as app_module
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    dash_app = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))
    AccessGuard("t0ken", PORT, "sandbox").install(dash_app.server)
    client = dash_app.server.test_client()

    for path in ("/", "/_dash-layout", "/_dash-dependencies", "/assets/theme.css"):
        assert _get(client, path).status_code == 403, path
    assert client.post("/open-resource", json={}, headers={"Host": f"127.0.0.1:{PORT}"}
                       ).status_code == 403
    _get(client, "/?token=t0ken")
    page = _get(client)
    assert page.status_code == 200 and 'id="startup-cover"' in page.get_data(as_text=True)


# --- Debug is for developers (P3.5) ----------------------------------------

@pytest.mark.parametrize("dev", [False, True])
def test_the_restart_poller_ships_only_in_dev(monkeypatch, dev):
    import app as app_module
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    dash_app = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False, dev=dev))
    client = dash_app.server.test_client()
    page = client.get("/").get_data(as_text=True)
    assert ("hard_reload_on_restart.js" in page) is dev
    # Dash answers unknown paths with the page, so check what came back.
    boot_id = client.get("/_server_boot_id").get_data(as_text=True)
    assert bool(re.fullmatch(r"[0-9a-f]{32}", boot_id)) is dev


def test_a_taken_port_falls_back_to_a_free_one():
    import socket
    squatter = socket.socket()
    squatter.bind(("127.0.0.1", 0))
    squatter.listen()
    taken = squatter.getsockname()[1]
    try:
        server = server_runtime.make_http_server(Flask(__name__), taken)
        assert server.port not in (0, taken)
        server.server_close()
    finally:
        squatter.close()


def test_the_server_answers_on_the_port_it_reports():
    import threading
    import urllib.request
    app = Flask(__name__)
    app.add_url_rule("/", "page", view_func=lambda: "hello")
    server = server_runtime.make_http_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=10) as r:
            assert r.read() == b"hello"
    finally:
        server.shutdown()
        server.server_close()


def test_closing_the_server_waits_for_requests_in_progress():
    server = server_runtime.make_http_server(Flask(__name__), 0)
    assert server.block_on_close is True
    server.server_close()


def test_serving_quiets_the_per_request_log():
    server_runtime.quiet_request_log()
    import logging
    assert logging.getLogger("werkzeug").level == logging.WARNING


# --- The desktop handshake, end to end (P3.2, P3.3, P3.6) --------------------

def _launch(home, *args, token="desk-token"):
    env = {**os.environ, "SKILLTREE_HOME": str(home), "SKILLTREE_TOKEN": token,
           "PYTHONUNBUFFERED": "1"}
    env.pop("WERKZEUG_RUN_MAIN", None)
    return subprocess.Popen([sys.executable, str(ROOT / "app.py"), *args], cwd=ROOT,
                            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)


def _line_starting(proc, prefix, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        if line.startswith(prefix):
            return line.strip()
    raise AssertionError(f"no {prefix} line; exit code {proc.poll()}")


def _request(port, path, cookie=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    response = conn.getresponse()
    body = response.read().decode("utf-8", "replace")
    conn.close()
    return response, body


def test_the_desktop_server_handshake_end_to_end(tmp_path):
    server = _launch(tmp_path, "--desktop", "--sandbox")
    try:
        ready = _line_starting(server, "SKILLTREE_READY")
        port = int(ready.split("port=")[1])
        assert port not in (8050, 8051)          # any free port, not the defaults

        refused, _ = _request(port, "/")
        assert refused.status == 403
        login, _ = _request(port, "/?token=desk-token")
        assert login.status in (302, 303)
        cookie = login.getheader("Set-Cookie").split(";")[0]
        page, body = _request(port, "/", cookie)
        assert page.status == 200 and "Skill Tree (Sandbox)" in body

        info = json.loads((tmp_path / "Data" / "sandbox_skilltree.instance.json").read_text())
        assert info["port"] == port and info["pid"] == server.pid

        # A second desktop launch finds it and hands over instead of serving.
        with _launch(tmp_path, "--desktop", "--sandbox", token="other") as second:
            running = _line_starting(second, "SKILLTREE_RUNNING")
            assert f"port={port}" in running and "token=desk-token" in running
            assert second.wait(timeout=60) == server_runtime.EXIT_ALREADY_RUNNING
    finally:
        # The shell closing (or dying) closes the server's stdin.
        server.stdin.close()
        try:
            code = server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            raise
        finally:
            server.stdout.close()
    assert code == 0
    assert not (tmp_path / "Data" / "sandbox_skilltree.instance.json").exists()
