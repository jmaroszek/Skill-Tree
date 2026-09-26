"""Backups, safe migrations and the startup integrity check (P2.1-P2.3)."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import backup
import database
from config import ConfigManager
from graph_manager import GraphManager
from models import Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


def _names_in(path):
    conn = sqlite3.connect(path)
    try:
        return sorted(row[0] for row in conn.execute("SELECT name FROM Nodes"))
    finally:
        conn.close()


def _user_version(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def db_in(monkeypatch, tmp_path):
    """Move the test database into a folder of the caller's choosing."""
    def move(folder_name):
        folder = tmp_path / folder_name
        folder.mkdir()
        path = str(folder / "skilltree.db")
        monkeypatch.setattr(database, "get_db_path", lambda: path)
        database._initialized = False
        database.init_db()
        return path
    return move


# --- Backups ----------------------------------------------------------------

class TestBackups:
    def test_a_backup_is_a_complete_copy_beside_the_database(self):
        GraphManager().add_node(_node("Sleep"))

        path = backup.create_backup("manual")

        assert path.parent == Path(database.get_db_path()).parent / "Backups"
        assert path.name.startswith(Path(database.get_db_path()).stem + "_")
        assert path.name.endswith("_manual.db")
        assert _names_in(path) == ["Sleep"]

    def test_a_folder_with_quotes_and_uri_characters_is_fine(self, db_in):
        """backup.py used to build its SQL by string formatting."""
        db_in("O'Brien's #1 data?")
        GraphManager().add_node(_node("Sleep"))
        assert _names_in(backup.create_backup("manual")) == ["Sleep"]

    def test_daily_backup_runs_once_a_day_and_skips_unchanged_graphs(self):
        GraphManager().add_node(_node("Sleep"))
        today = datetime.now()

        first = backup.run_daily_backup(now=today)
        assert first is not None
        assert backup.run_daily_backup(now=today) is None  # already done today

        # Tomorrow, nothing changed: the newest backup already covers it.
        assert backup.run_daily_backup(now=today + timedelta(days=1)) is None
        assert len(backup.list_backups("daily")) == 1

    def test_old_copies_are_pruned_per_kind(self, monkeypatch):
        monkeypatch.setitem(backup.KEEP, "daily", 2)
        folder = backup.backup_dir()
        folder.mkdir()
        stem = Path(database.get_db_path()).stem
        for day in ("20260101", "20260102", "20260103"):
            (folder / f"{stem}_{day}-090000_daily.db").write_bytes(b"x")
        keep_other = folder / f"{stem}_20250101-090000_manual.db"
        keep_other.write_bytes(b"x")

        backup._prune("daily", folder)

        assert [i["when"].day for i in backup.list_backups("daily")] == [2, 3]
        assert keep_other.exists()

    def test_backups_can_be_mirrored_to_an_extra_folder(self, tmp_path):
        extra = tmp_path / "Synced"
        extra.mkdir()
        ConfigManager.set_backup_extra_dir(str(extra))
        GraphManager().add_node(_node("Sleep"))

        path = backup.run_daily_backup()

        assert (extra / path.name).exists()

    def test_an_unreachable_extra_folder_does_not_stop_the_backup(self, tmp_path):
        ConfigManager.set_backup_extra_dir(str(tmp_path / "Unmounted"))
        GraphManager().add_node(_node("Sleep"))

        assert backup.run_daily_backup() is not None


# --- Migrations and integrity ----------------------------------------------

def _set_user_version(version):
    conn = sqlite3.connect(database.get_db_path())
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


class TestSafeStartup:
    def test_a_newer_database_is_refused_and_left_alone(self):
        _set_user_version(database.SCHEMA_VERSION + 1)
        database._initialized = False

        with pytest.raises(database.NewerDatabaseError, match="newer version"):
            database.init_db()

        # It used to be stamped back down to this build's version.
        assert _user_version(database.get_db_path()) == database.SCHEMA_VERSION + 1

    def test_a_damaged_file_is_refused_and_left_alone(self):
        path = Path(database.get_db_path())
        path.write_bytes(b"not a database" * 100)
        database._initialized = False

        with pytest.raises(database.DatabaseCorruptError, match="damaged"):
            database.init_db()
        assert path.read_bytes() == b"not a database" * 100

    def test_an_upgrade_is_backed_up_first(self):
        GraphManager().add_node(_node("Sleep"))
        _set_user_version(database.SCHEMA_VERSION - 1)
        database._initialized = False

        database.init_db()

        (snapshot,) = backup.list_backups("pre-migration")
        assert _user_version(snapshot["path"]) == database.SCHEMA_VERSION - 1
        assert _names_in(snapshot["path"]) == ["Sleep"]
        assert _user_version(database.get_db_path()) == database.SCHEMA_VERSION

    def test_a_failed_upgrade_changes_nothing(self, monkeypatch):
        GraphManager().add_node(_node("Sleep"))
        _set_user_version(database.SCHEMA_VERSION - 1)
        database._initialized = False

        def failing_step(cursor, from_version):
            cursor.execute("DELETE FROM Nodes")
            raise RuntimeError("step failed")
        monkeypatch.setattr(database, "_migrate", failing_step)

        with pytest.raises(RuntimeError, match="step failed"):
            database.init_db()

        assert _names_in(database.get_db_path()) == ["Sleep"]
        assert _user_version(database.get_db_path()) == database.SCHEMA_VERSION - 1
        assert database._initialized is False

    def test_an_old_sqlite_is_refused_with_a_reason(self, monkeypatch):
        monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 31, 1))
        database._initialized = False
        with pytest.raises(database.SQLiteTooOldError, match="3.35.0"):
            database.init_db()


def test_the_launcher_exits_with_the_refusals_code(monkeypatch):
    import app as app_module

    def refuse(_settings):
        raise database.NewerDatabaseError("saved by a newer version")
    monkeypatch.setattr(app_module, "create_app", refuse)

    with pytest.raises(SystemExit) as exited:
        app_module.main([])
    assert exited.value.code == database.NewerDatabaseError.exit_code
