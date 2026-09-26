"""Startup refusals say what is actually wrong (P3.9).

The desktop shell turns each exit code into a dialog, and on "damaged" it
offers to restore a backup. So a database that is only busy, or only
read-only, must never be reported as damaged: restoring over it would throw
away good data to fix a problem it doesn't have.
"""
import sqlite3

import pytest

import app as app_module
import data_transfer
import database
from graph_manager import GraphManager
from models import Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


@pytest.fixture
def fast_busy_timeout(monkeypatch):
    monkeypatch.setattr(database, "BUSY_TIMEOUT_S", 0.05)


@pytest.fixture
def held_by_another_program():
    """Another program's write lock on the database, the way a sync tool or a
    database viewer can hold one."""
    blocker = sqlite3.connect(database.get_db_path())
    blocker.execute("BEGIN EXCLUSIVE")
    yield
    blocker.rollback()
    blocker.close()


def _read_only(monkeypatch):
    """Open the database the way SQLite does when the file can't be written."""
    def connect():
        uri = f"file:{database.get_db_path()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, factory=database._ClosingConnection)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    monkeypatch.setattr(database, "get_connection", connect)


def test_a_busy_database_is_in_use_not_damaged(fast_busy_timeout, held_by_another_program):
    database._initialized = False
    with pytest.raises(database.DatabaseError) as refused:
        database.init_db()

    assert type(refused.value) is database.DatabaseLockedError
    assert refused.value.exit_code == 6
    assert "in use by another program" in str(refused.value)
    assert database.get_db_path() in str(refused.value)


def test_a_database_that_cant_be_written_is_named_as_such(monkeypatch):
    GraphManager().add_node(_node("Sleep"))
    database._initialized = False
    _read_only(monkeypatch)
    # Force the upgrade path, which has to write.
    monkeypatch.setattr(database, "SCHEMA_VERSION", database.SCHEMA_VERSION + 1)
    monkeypatch.setattr(database, "_migrate", lambda cursor, version: None)
    monkeypatch.setattr("backup.create_backup", lambda kind: None)

    with pytest.raises(database.DatabaseError) as refused:
        database.init_db()

    assert type(refused.value) is database.DatabaseUnwritableError
    assert refused.value.exit_code == 7
    assert "can't write" in str(refused.value)


def test_a_file_that_isnt_a_database_is_still_damaged(tmp_path, monkeypatch):
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"garbage" * 500)
    monkeypatch.setattr(database, "get_db_path", lambda: str(garbage))
    database._initialized = False

    with pytest.raises(database.DatabaseCorruptError):
        database.init_db()


def test_the_integrity_check_of_a_busy_file_is_in_use_not_damaged(
        fast_busy_timeout, held_by_another_program):
    with pytest.raises(database.DatabaseLockedError):
        database.check_integrity(database.get_db_path())


def test_restoring_a_backup_another_program_holds_says_so(
        tmp_path, fast_busy_timeout):
    import backup
    GraphManager().add_node(_node("Sleep"))
    saved = backup.create_backup("manual")
    blocker = sqlite3.connect(saved)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(data_transfer.TransferRefused) as refused:
            data_transfer.restore_backup(saved)
    finally:
        blocker.rollback()
        blocker.close()
    assert "in use by another program" in str(refused.value)
    assert "damaged" not in str(refused.value)


def test_restoring_into_a_busy_database_changes_nothing(fast_busy_timeout):
    import backup
    manager = GraphManager()
    manager.add_node(_node("Sleep"))
    saved = backup.create_backup("manual")
    manager.add_node(_node("Afterwards"))
    blocker = sqlite3.connect(database.get_db_path())
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(data_transfer.TransferRefused, match="in use"):
            data_transfer.restore_backup(saved)
    finally:
        blocker.rollback()
        blocker.close()
    assert manager.get_node("Afterwards") is not None


@pytest.mark.parametrize("error", [
    database.NewerDatabaseError, database.DatabaseCorruptError,
    database.SQLiteTooOldError, database.DatabaseLockedError,
    database.DatabaseUnwritableError,
])
def test_the_launcher_exits_with_each_refusals_own_code(monkeypatch, error):
    def refuse(_settings):
        raise error("reason")
    monkeypatch.setattr(app_module, "create_app", refuse)
    monkeypatch.setattr(app_module, "_configure_logging", lambda environment: None)

    with pytest.raises(SystemExit) as exited:
        app_module.main(["--no-browser"])
    assert exited.value.code == error.exit_code


def test_every_refusal_has_its_own_exit_code():
    codes = [cls.exit_code for cls in (
        database.DatabaseError, database.NewerDatabaseError,
        database.DatabaseCorruptError, database.SQLiteTooOldError,
        database.DatabaseLockedError, database.DatabaseUnwritableError)]
    assert len(set(codes)) == len(codes)


def test_a_restore_whose_upgrade_is_refused_says_to_restart(monkeypatch):
    import backup
    GraphManager().add_node(_node("Sleep"))
    saved = backup.create_backup("manual")
    real_init = database.init_db

    def refuse_once():
        monkeypatch.setattr(database, "init_db", real_init)
        raise database.DatabaseLockedError("in use")
    monkeypatch.setattr(database, "init_db", refuse_once)

    with pytest.raises(data_transfer.TransferRefused, match="Restart Skill Tree"):
        data_transfer.restore_backup(saved)


def test_an_unwritable_app_folder_is_refused_with_a_reason(monkeypatch, tmp_path, capsys):
    """The Logs and Data folders can't be created: say so, exit 7, no traceback."""
    import logging
    import app_paths
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the app folder should be")
    monkeypatch.setenv(app_paths.HOME_ENV, str(blocker))
    monkeypatch.setattr(database, "get_db_path",
                        lambda: str(app_paths.get_data_dir() / "skilltree.db"))
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        with pytest.raises(SystemExit) as exited:
            app_module.main(["--no-browser"])
    finally:
        root.handlers[:], _ = saved[0], root.setLevel(saved[1])
    assert exited.value.code == database.DatabaseUnwritableError.exit_code
    assert "can't write to its data folder" in capsys.readouterr().err
