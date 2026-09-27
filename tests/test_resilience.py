"""A server killed at the worst moment loses only the change it was making (P6.4).

The other resilience cases live beside the code they exercise:
- a damaged, busy or read-only database, and an unwritable data folder:
  test_startup_failures.py, test_data_safety.py
- another program on the port, a second launch, a lock whose owner was
  killed: test_server_runtime.py
"""
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import database
from graph_manager import GraphManager

ROOT = Path(__file__).resolve().parents[1]

# Runs in a child process: commit one node, then die partway through a
# multi-step save, the way a crash, a power cut or a kill -9 would.
_KILLED_MID_SAVE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {root!r})
    import database
    database.get_db_path = lambda: {path!r}
    database.init_db()
    from graph_manager import GraphManager
    from models import Node, EDGE_NEEDS_HARD
    def node(name):
        return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                    time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                    context="Mind")
    manager = GraphManager()
    manager.add_node(node("Kept"))
    with database.transaction():
        manager.add_node(node("Lost"))
        manager.add_edge("Kept", "Lost", EDGE_NEEDS_HARD)
        manager.rename_node("Kept", "Renamed")
        os._exit(137)   # no commit, no cleanup, no atexit
""")


def test_a_server_killed_mid_save_keeps_the_last_committed_graph(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.db")
    child = subprocess.run(
        [sys.executable, "-c", _KILLED_MID_SAVE.format(root=str(ROOT), path=path)],
        capture_output=True, text=True, timeout=120)
    assert child.returncode == 137, child.stderr

    monkeypatch.setattr(database, "get_db_path", lambda: path)
    database._initialized = False
    database.init_db()                      # rolls back the hot journal
    database.check_integrity(path)

    manager = GraphManager()
    assert {n.name for n in manager.get_all_nodes()} == {"Kept"}
    assert manager.get_edges() == []
    assert manager.recompute_all_statuses() == 0


def test_no_journal_is_left_once_it_has_been_recovered(tmp_path, monkeypatch):
    path = tmp_path / "graph.db"
    subprocess.run([sys.executable, "-c",
                    _KILLED_MID_SAVE.format(root=str(ROOT), path=str(path))],
                   capture_output=True, timeout=120)
    monkeypatch.setattr(database, "get_db_path", lambda: str(path))
    database._initialized = False
    database.init_db()
    GraphManager().get_all_nodes()
    assert not Path(str(path) + "-journal").exists()
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    conn.close()
