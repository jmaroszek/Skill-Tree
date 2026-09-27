"""Drive the packaged desktop app the way a new user does (P6.5).

    python packaging/app_journey.py APP_EXECUTABLE [--headless]

It starts the app against a throwaway data folder (SKILLTREE_HOME), with
Chromium's DevTools port open, attaches Playwright to the app's own window,
and checks that:
1. the window loads the app through its access token;
2. the welcome appears, and a node added in the editor is saved;
3. closing the window quits the app, and its server with it;
4. a second start opens the same graph, without the welcome.

It needs only Playwright's Python package, not its browsers. --headless
(Linux) runs the app on a virtual screen (xvfb-run), for CI, with Chromium's
sandbox off, which a CI container can't provide. Chromium's own headless
mode won't do: the window has no screen to maximize to and comes out 1x1.
"""
import argparse
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _answers(port, timeout=1.0):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


class App:
    def __init__(self, executable, home, headless):
        self.executable = executable
        self.home = home
        self.headless = headless
        self.proc = None
        self.debug_port = None

    def start(self):
        self.debug_port = _free_port()
        args = [self.executable, f"--remote-debugging-port={self.debug_port}"]
        if self.headless:
            args = ["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", *args, "--no-sandbox"]
        env = {**os.environ, "SKILLTREE_HOME": str(self.home)}
        # Its own process group, so a failed run can stop everything it started.
        self.proc = subprocess.Popen(args, env=env, start_new_session=os.name == "posix")
        deadline = time.monotonic() + 60
        while not _answers(self.debug_port):
            if self.proc.poll() is not None:
                raise RuntimeError(f"the app exited with {self.proc.returncode}")
            if time.monotonic() > deadline:
                raise RuntimeError("the app's DevTools port never opened")
            time.sleep(0.25)
        return self

    def window(self, playwright):
        """The app's page, once it has loaded the server's address."""
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.debug_port}")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            pages = [page for context in browser.contexts for page in context.pages]
            for page in pages:
                if page.url.startswith("http://127.0.0.1:"):
                    page.wait_for_selector("#startup-cover.is-lifted", state="attached",
                                           timeout=120000)
                    return browser, page
            # Playwright's sync API takes in the app's events (a new window, a
            # navigation) only while one of its own calls is waiting.
            try:
                if pages:
                    pages[0].wait_for_timeout(500)
                else:
                    browser.contexts[0].wait_for_event("page", timeout=2000)
            except PlaywrightTimeout:
                pass
        raise RuntimeError("the window never loaded the app")

    def wait_for_exit(self, timeout=60):
        self.proc.wait(timeout=timeout)

    def kill(self):
        if self.proc and self.proc.poll() is None:
            if os.name == "posix":
                os.killpg(self.proc.pid, signal.SIGKILL)
            else:
                self.proc.kill()
            self.proc.wait()


def _server_port(home):
    info = Path(home) / "Data" / "skilltree.instance.json"
    return json.loads(info.read_text())["port"]


def _nodes(home):
    conn = sqlite3.connect(Path(home) / "Data" / "skilltree.db")
    try:
        return [row[0] for row in conn.execute("SELECT name FROM Nodes")]
    finally:
        conn.close()


def _add_node(page, name):
    page.click("#btn-add")
    page.wait_for_function(
        "document.querySelector('#sidebar-editor-container').getBoundingClientRect().left >= -1",
        timeout=15000)
    page.wait_for_timeout(1000)
    page.click("#btn-editor-new")
    page.wait_for_timeout(1000)
    page.fill("#node-name", name)
    page.select_option("#node-type", "Learn")
    page.click("#node-context-picker-trigger")
    page.click("button.context-picker-menu-row[data-context='Mind']")
    page.click("[role=option]:has-text('No subcontext')")
    if page.is_visible("#node-time-m"):
        page.fill("#node-time-m", "2")
    page.click("#btn-save")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes('Added node')",
        timeout=30000)


def _quit(app, browser, page, home):
    """Close the window, as a person would: the app quits, and its server."""
    port = _server_port(home)
    page.close()
    browser.close()
    app.wait_for_exit()
    deadline = time.monotonic() + 30
    while _answers(port):
        if time.monotonic() > deadline:
            raise AssertionError(f"the server on port {port} outlived the app")
        time.sleep(0.5)


def run(executable, headless):
    home = Path(tempfile.mkdtemp(prefix="skilltree-app-journey-"))
    app = App(executable, home, headless)
    try:
        with sync_playwright() as playwright:
            app.start()
            browser, page = app.window(playwright)
            page.wait_for_selector("#welcome-modal", state="visible", timeout=30000)
            print("1. The window loaded the app, and the welcome is showing.")
            page.click("#btn-welcome-suggested")
            page.wait_for_selector("#welcome-modal", state="hidden", timeout=30000)
            _add_node(page, "First Step")
            assert _nodes(home) == ["First Step"], _nodes(home)
            print("2. A node added in the editor was saved.")
            _quit(app, browser, page, home)
            print("3. Closing the window quit the app and its server.")

            app.start()
            browser, page = app.window(playwright)
            page.wait_for_timeout(1500)
            assert not page.is_visible("#welcome-modal"), "the welcome came back"
            page.wait_for_function(
                "document.querySelector('#suggestions-table').innerText.includes('First Step')",
                timeout=30000)
            print("4. A second start opened the same graph, without the welcome.")
            _quit(app, browser, page, home)
    finally:
        app.kill()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("executable")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    run(args.executable, args.headless)
    print("The packaged app passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
