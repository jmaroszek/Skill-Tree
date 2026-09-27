"""A damaged database: the desktop shell offers the newest good backup (P2.3).

The server refuses a damaged database with exit code 4 (P3.9). First it
names the newest backup that opens cleanly, on stdout beside its READY line:

    SKILLTREE_DAMAGED backup=skilltree_20260926-100000_daily.db when=2026-09-26T10:00:00

so the shell can offer it. Started again with --restore-backup NAME, the
server moves the damaged file aside, puts that backup in its place, and
starts as usual. The damaged file is kept, in case it is ever wanted.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import app as app_module
import backup
import database
import server_runtime
from graph_manager import GraphManager
from models import Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


def _damage(path):
    Path(path).write_bytes(b"this is not a database" * 200)


def _backup_named(when, kind="daily"):
    """A copy of the live database, as a backup taken at ``when``."""
    target = backup.backup_dir() / f"{backup._stem()}_{when:%Y%m%d-%H%M%S}_{kind}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    backup.copy_database(target)
    return target


@pytest.fixture
def launch(monkeypatch):
    """app.main as far as serving: returns whether it would have served."""
    monkeypatch.setattr(app_module, "_configure_logging", lambda environment: None)
    served = []
    monkeypatch.setattr(server_runtime, "serve", lambda *args: served.append(True))

    def run(*args):
        database._initialized = False
        app_module.main(["--no-browser", *args])
        return bool(served)
    return run


@pytest.fixture
def backups():
    """Three backups, oldest first: two good ones, then a damaged one."""
    manager = GraphManager()
    manager.add_node(_node("Old"))
    now = datetime.now()
    older = _backup_named(now - timedelta(days=2))
    manager.add_node(_node("Newer"))
    newer = _backup_named(now - timedelta(days=1))
    broken = _backup_named(now - timedelta(hours=1))
    _damage(broken)
    return older, newer, broken


def test_a_damaged_database_names_the_newest_good_backup(launch, backups, capsys):
    _older, newer, _broken = backups
    _damage(database.get_db_path())

    with pytest.raises(SystemExit) as refused:
        launch()

    assert refused.value.code == database.DatabaseCorruptError.exit_code
    offer = [line for line in capsys.readouterr().out.splitlines()
             if line.startswith("SKILLTREE_DAMAGED")]
    assert offer == [f"SKILLTREE_DAMAGED backup={newer.name} "
                     f"when={backup.describe(newer)['when'].isoformat()}"]


def test_no_good_backup_means_no_offer(launch, capsys):
    _damage(database.get_db_path())

    with pytest.raises(SystemExit):
        launch()

    assert "SKILLTREE_DAMAGED" not in capsys.readouterr().out


def test_restoring_puts_the_backup_in_place_and_keeps_the_damaged_file(launch, backups):
    _older, newer, _broken = backups
    live = Path(database.get_db_path())
    _damage(live)

    assert launch("--restore-backup", newer.name)

    assert {n.name for n in GraphManager().get_all_nodes()} == {"Old", "Newer"}
    kept = list(live.parent.glob(f"{live.name}.damaged-*"))
    assert len(kept) == 1
    assert kept[0].read_bytes().startswith(b"this is not a database")


def test_a_journal_left_by_the_damaged_file_never_reaches_the_restored_copy(
        launch, backups):
    """SQLite would roll a hot journal left beside the damaged file into the
    restored copy. The restore moves one aside; SQLite may also have discarded
    it already, while checking the damaged file."""
    _older, newer, _broken = backups
    live = Path(database.get_db_path())
    _damage(live)
    Path(f"{live}-journal").write_bytes(b"a journal for the damaged file")

    assert launch("--restore-backup", newer.name)

    assert not Path(f"{live}-journal").exists()
    conn = sqlite3.connect(live)
    try:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    assert {n.name for n in GraphManager().get_all_nodes()} == {"Old", "Newer"}


@pytest.mark.parametrize("name", [
    "../skilltree.db", "not_a_backup.db", "skilltree_20260101-000000_daily.db",
])
def test_only_an_existing_good_backup_of_this_database_is_restored(launch, backups, name):
    live = Path(database.get_db_path())
    _damage(live)
    before = live.read_bytes()

    with pytest.raises(SystemExit) as refused:
        launch("--restore-backup", name)

    assert refused.value.code == database.DatabaseCorruptError.exit_code
    assert live.read_bytes() == before


def test_a_damaged_backup_is_refused_and_nothing_moves(launch, backups):
    _older, _newer, broken = backups
    live = Path(database.get_db_path())
    _damage(live)
    before = live.read_bytes()

    with pytest.raises(SystemExit):
        launch("--restore-backup", broken.name)

    assert live.read_bytes() == before
    assert not list(live.parent.glob(f"{live.name}.damaged-*"))


def test_a_healthy_database_is_never_replaced(launch, backups):
    """The flag only ever mends a damaged file: a stale shell or a stray
    restart must not throw away good data."""
    _older, newer, _broken = backups
    GraphManager().add_node(_node("Latest"))

    assert launch("--restore-backup", newer.name)

    assert "Latest" in {n.name for n in GraphManager().get_all_nodes()}


def test_the_restore_itself_moves_a_journal_aside(backups):
    _older, newer, _broken = backups
    live = Path(database.get_db_path())
    _damage(live)
    Path(f"{live}-journal").write_bytes(b"a journal for the damaged file")

    kept = backup.restore_over_damaged(newer.name)

    assert kept.read_bytes().startswith(b"this is not a database")
    assert not Path(f"{live}-journal").exists()
    (aside,) = live.parent.glob(f"{live.name}-journal.damaged-*")
    assert aside.read_bytes() == b"a journal for the damaged file"
    assert not live.with_name(f"{live.name}.restoring").exists()
