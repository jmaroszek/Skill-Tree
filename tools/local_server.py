"""Run the app's server the way a developer or an agent does, and read its
database: the browser journeys (tests/e2e) and the performance check
(tools/perf_bench.py) share this.

    server = Server(home).start()      # app.py --sandbox --port 0 --no-browser
    page.goto(server.link)             # the token link seeds origin-scoped sessionStorage
    server.query("SELECT name FROM Nodes")
    server.stop()

``home`` becomes SKILLTREE_HOME, so the server's Data and Logs live there and
nothing touches the real data folder. A database already at
home/Data/sandbox_skilltree.db is the one it opens.
"""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
