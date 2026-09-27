"""End-to-end tests: a real server, a real browser (P6.5).

Each test gets its own server on a free port, against a throwaway data
folder (SKILLTREE_HOME), and a Chromium page already through the token link.
The page records console errors and every host it contacted.

Skipped unless Playwright is installed:
    pip install -r requirements-e2e.txt
    python -m playwright install chromium
    pytest tests/e2e
PLAYWRIGHT_CHROMIUM points at a Chromium of your own, if you have one.
"""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

try:
    from playwright import sync_api
except ImportError:     # test_journeys.py reports the skip
    sync_api = None

ROOT = Path(__file__).resolve().parents[2]


class Server:
    """app.py in browser mode, the way a developer or an agent runs it."""

    def __init__(self, home: Path):
        self.home = home
        self.proc = None
        self.port = None
        self.token = None

    @property
    def db_path(self) -> Path:
        return self.home / "Data" / "sandbox_skilltree.db"

    @property
    def link(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    def start(self):
        env = {**os.environ, "SKILLTREE_HOME": str(self.home), "PYTHONUNBUFFERED": "1"}
        env.pop("WERKZEUG_RUN_MAIN", None)
        env.pop("SKILLTREE_TOKEN", None)
        self.proc = subprocess.Popen(
            [sys.executable, "app.py", "--sandbox", "--port", "0", "--no-browser"],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if line.startswith("SKILLTREE_READY"):
                break
            if not line and self.proc.poll() is not None:
                raise RuntimeError(f"the server exited with {self.proc.returncode}")
        info = json.loads((self.home / "Data" / "sandbox_skilltree.instance.json").read_text())
        self.port, self.token = info["port"], info["token"]
        return self

    def stop(self):
        if self.proc and self.proc.poll() is None:
            if sys.platform == "win32":
                self.proc.terminate()
            else:
                self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def query(self, sql, *args):
        """Read the server's database directly, to check what the UI did."""
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM")
        launched = p.chromium.launch(executable_path=executable or None)
        yield launched
        launched.close()


@pytest.fixture
def server(tmp_path):
    running = Server(tmp_path / "home").start()
    yield running
    running.stop()


@pytest.fixture
def open_app(browser):
    """open_app(server) opens the app in a fresh browser context: a page
    through the token link, with the startup cover lifted."""
    contexts = []

    def opener(server):
        context = browser.new_context(viewport={"width": 1400, "height": 900},
                                      accept_downloads=True)
        contexts.append(context)
        page = context.new_page()
        page.console_errors = []
        page.hosts = set()
        page.on("console", lambda m: page.console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: page.console_errors.append(str(e)))
        page.on("request", lambda r: page.hosts.add(urlparse(r.url).hostname))
        page.goto(server.link)
        page.wait_for_selector("#startup-cover.is-lifted", state="attached",
                               timeout=60000)
        return page

    yield opener
    for context in contexts:
        context.close()


@pytest.fixture
def page(open_app, server):
    return open_app(server)
