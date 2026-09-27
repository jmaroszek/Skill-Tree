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
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from local_server import Server  # noqa: E402

try:
    from playwright import sync_api
except ImportError:     # test_journeys.py reports the skip
    sync_api = None


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM")
        launched = p.chromium.launch(executable_path=executable or None)
        yield launched
        launched.close()


@pytest.fixture
def start_server(tmp_path):
    """start_server(folder) starts another install, with its own data folder."""
    started = []

    def starter(folder):
        running = Server(tmp_path / folder).start()
        started.append(running)
        return running

    yield starter
    for running in started:
        running.stop()


@pytest.fixture
def server(start_server):
    return start_server("home")


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
