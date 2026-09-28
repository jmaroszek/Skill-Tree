"""Browser checks for the local server's origin-scoped launch credential."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Thread

import pytest

pytest.importorskip("playwright.sync_api")


def test_a_second_loopback_port_never_receives_the_launch_token(page, server):
    # The app has completed Dash startup, including authenticated layout and
    # callback requests. The URL is already cleaned by the page bootstrap.
    assert page.evaluate("location.search") == ""
    assert page.evaluate("fetch('/_dash-layout').then(response => response.status)") == 200
    page.reload()
    page.wait_for_selector("#startup-cover.is-lifted", state="attached", timeout=60000)
    assert page.evaluate("location.search") == ""
    assert page.evaluate("fetch('/_dash-layout').then(response => response.status)") == 200

    requests = Queue()

    class OtherListener(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.put(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"another local app")

        def log_message(self, *_args):
            pass

    other = ThreadingHTTPServer(("127.0.0.1", 0), OtherListener)
    thread = Thread(target=other.serve_forever, daemon=True)
    thread.start()
    try:
        page.goto(f"http://127.0.0.1:{other.server_port}/")
        headers = requests.get(timeout=10)
        assert server.token not in repr(headers)
        assert "skilltree" not in headers.get("Cookie", "").lower()
        assert "Referer" not in headers
    finally:
        other.shutdown()
        other.server_close()
        thread.join(timeout=10)
