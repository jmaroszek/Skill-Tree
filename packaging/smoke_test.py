"""Smoke-test a built Skill Tree server before it ships.

    python packaging/smoke_test.py dist/skilltree-server/skilltree-server

Starts the server the way the desktop shell does, against a throwaway data
folder, and checks:
- the READY handshake;
- that graph data needs the token header and the token link opens the page;
- that every script and stylesheet the page names is served (a frozen build
  missing a package's data files fails here);
- that a second launch hands over instead of serving;
- that closing stdin stops it cleanly.

Standard library only, so it runs on any CI runner. Exits non-zero with the
reason on the first failure.
"""
import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def fail(message, proc=None):
    if proc is not None and proc.poll() is None:
        proc.kill()
    print(f"SMOKE TEST FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def launch(command, home, token):
    env = {**os.environ, "SKILLTREE_HOME": str(home), "SKILLTREE_TOKEN": token}
    return subprocess.Popen(command + ["--desktop", "--sandbox"], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def line_starting(proc, prefix, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line.startswith(prefix):
            return line.strip()
        if not line and proc.poll() is not None:
            break
    fail(f"no {prefix} line within {timeout}s (exit {proc.poll()}); "
         f"stderr: {proc.stderr.read()[-2000:] if proc.poll() is not None else ''}", proc)


def get(port, path, token=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn.request("GET", path, headers={"X-Skill-Tree-Token": token} if token else {})
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response, body


def main(argv):
    if len(argv) < 2:
        fail("usage: smoke_test.py <server binary> [args...]")
    binary = Path(argv[1])
    if not binary.exists() and binary.with_name(binary.name + ".exe").exists():
        binary = binary.with_name(binary.name + ".exe")   # Windows
    if not binary.exists():
        fail(f"no server binary at {argv[1]}")
    command = [str(binary.resolve())] + argv[2:]
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as home:
        token = secrets.token_urlsafe(16)
        server = launch(command, home, token)
        ready = line_starting(server, "SKILLTREE_READY", timeout=180)
        port = int(ready.split("port=")[1])
        print(f"ready on port {port} after {time.monotonic() - started:.1f}s")

        refused, _ = get(port, "/_dash-layout")
        if refused.status != 403:
            fail(f"graph data without the token got {refused.status}, not 403", server)
        login, _ = get(port, f"/?token={token}")
        if login.status != 200 or token in (login.getheader("Set-Cookie") or ""):
            fail(f"the token link got {login.status} or issued a bearer cookie", server)

        page, body = get(port, "/", token)
        html = body.decode("utf-8", "replace")
        if page.status != 200 or 'id="startup-cover"' not in html:
            fail(f"the page got {page.status} or isn't Skill Tree's", server)
        urls = re.findall(r'<(?:script|link)\b[^>]*?(?:src|href)="(/[^"]+)"', html)
        for path in ["/_dash-layout", "/_dash-dependencies"] + urls:
            response, content = get(port, path, token)
            if response.status != 200 or not content:
                fail(f"{path} got {response.status} ({len(content)} bytes)", server)
        layout = json.loads(get(port, "/_dash-layout", token)[1])
        if not layout:
            fail("the layout is empty", server)
        print(f"served the page and its {len(urls)} scripts and stylesheets")

        second = launch(command, home, "another-token")
        running = line_starting(second, "SKILLTREE_RUNNING", timeout=120)
        if f"port={port}" not in running or second.wait(timeout=60) != 8:
            fail(f"a second launch didn't hand over: {running!r}, exit {second.poll()}",
                 server)
        print("a second launch handed over to the first")

        server.stdin.close()
        try:
            code = server.wait(timeout=60)
        except subprocess.TimeoutExpired:
            fail("the server didn't stop when stdin closed", server)
        if code != 0:
            fail(f"the server exited with {code} after stdin closed")
        instance = Path(home) / "Data" / "sandbox_skilltree.instance.json"
        if instance.exists():
            fail("the server left its instance file behind")
    print(f"smoke test passed in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main(sys.argv)
