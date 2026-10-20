"""A server that stays open keeps making the daily backup.

create_app makes the day's backup at launch, and tests/store/test_data_safety.py
covers what makes one due. A server left running for days needs one on each new
day after that, so main starts a timer that asks again every hour. The timer
runs in the process that serves. It does not run in the dev reloader's parent,
which only watches files, or in create_app, which is how the rest of the suite
builds an app.

Nothing here sleeps. The timer waits on a threading.Event, so a stand-in that
answers at once and moves a fake clock as it goes plays out days in a moment.
"""
import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from skilltree import app as app_module
from skilltree.runtime import paths
from skilltree.runtime import server as server_runtime
from skilltree.store import backup, database, settings
from support.graphs import graph, make_node

LAUNCH = datetime(2026, 10, 19, 9, 30)
HOUR = 60 * 60


class FakeTime:
    """The timer's stop event and its clock in one, for a test that must not sleep.

    Each wait() lets the interval pass on the fake clock, after running what
    the test says happens in that stretch (``edits``, keyed by the number of
    the check it comes before). It answers "go on" for ``checks`` waits and
    "stop" after that.
    """

    def __init__(self, checks, edits=None):
        self.checks = checks
        self.edits = edits or {}
        self.now = LAUNCH
        self.waits = []

    def wait(self, timeout):
        self.waits.append(timeout)
        if len(self.waits) > self.checks:
            return True
        self.now += timedelta(seconds=timeout)
        edit = self.edits.get(len(self.waits))
        if edit:
            edit()
        return False

    def clock(self):
        return self.now


def _nodes_in(path):
    conn = sqlite3.connect(path)
    try:
        return sorted(row[0] for row in conn.execute("SELECT name FROM Nodes"))
    finally:
        conn.close()


# --- The timer ----------------------------------------------------------------

def test_the_timer_asks_once_per_interval(monkeypatch):
    asked = []
    monkeypatch.setattr(backup, "run_daily_backup", asked.append)
    fake = FakeTime(checks=3)

    app_module.run_backup_timer(fake, interval=600, clock=fake.clock)

    assert fake.waits == [600] * 4  # three checks, then the stop
    assert asked == [LAUNCH + timedelta(minutes=10 * n) for n in (1, 2, 3)]


def test_a_server_left_open_makes_a_backup_on_each_new_day():
    sleep = graph("Sleep")
    assert backup.run_daily_backup(LAUNCH) is not None  # create_app's, at launch
    fake = FakeTime(checks=72, edits={
        5: lambda: sleep.add_node(make_node("Strength")),  # 14:30 on the first day
        45: lambda: sleep.add_node(make_node("Cooking")),  # 06:30 on the third
    })

    app_module.run_backup_timer(fake, interval=HOUR, clock=fake.clock)

    daily = backup.list_backups("daily")
    assert [info["when"] for info in daily] == [
        LAUNCH,                         # at launch
        datetime(2026, 10, 20, 0, 30),  # the first check of the second day, which found Strength
        datetime(2026, 10, 21, 6, 30),  # the first check after Cooking, on the third day
    ]
    # Strength came after the first day's copy, so only the second day's holds
    # it. Nothing changed between that copy and the third day's first check,
    # which keeps nothing, so the next copy waits for Cooking.
    assert [_nodes_in(info["path"]) for info in daily] == [
        ["Sleep"], ["Sleep", "Strength"], ["Cooking", "Sleep", "Strength"]]


def test_a_running_server_follows_the_backup_switch_in_settings():
    graph("Sleep")
    fake = FakeTime(checks=48, edits={
        1: lambda: settings.AUTO_BACKUP.set(False),
        30: lambda: settings.AUTO_BACKUP.set(True),  # 15:30 on the second day
    })

    app_module.run_backup_timer(fake, interval=HOUR, clock=fake.clock)

    assert [info["when"] for info in backup.list_backups("daily")] == [
        datetime(2026, 10, 20, 15, 30)]


def test_a_check_that_fails_is_logged_and_the_timer_carries_on(monkeypatch, caplog):
    asked = []

    def flaky(now):
        asked.append(now)
        if len(asked) == 1:
            raise RuntimeError("the check broke")
    monkeypatch.setattr(backup, "run_daily_backup", flaky)
    fake = FakeTime(checks=3)

    app_module.run_backup_timer(fake, interval=HOUR, clock=fake.clock)

    assert len(asked) == 3
    assert "The daily backup check failed" in caplog.text
    assert "the check broke" in caplog.text


def test_a_backup_that_fails_does_not_end_the_backups(monkeypatch, caplog):
    graph("Sleep")
    real = backup.create_backup
    attempts = []

    def full_disk(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("no space left on device")
        return real(*args, **kwargs)
    monkeypatch.setattr(backup, "create_backup", full_disk)
    fake = FakeTime(checks=2)

    app_module.run_backup_timer(fake, interval=HOUR, clock=fake.clock)

    # The first check couldn't copy anything; the next, an hour later, did.
    assert [info["when"] for info in backup.list_backups("daily")] == [
        LAUNCH + timedelta(hours=2)]
    assert "Daily backup failed" in caplog.text


def test_the_timer_runs_on_a_daemon_thread_that_ends_when_stopped(monkeypatch):
    asked = []
    monkeypatch.setattr(backup, "run_daily_backup", asked.append)
    stop = threading.Event()

    thread = app_module.start_backup_timer(stop)
    try:
        assert thread.daemon  # it never keeps the process alive
        assert thread.name == "daily-backup"
        assert thread.is_alive()  # waiting out its first interval
    finally:
        stop.set()  # a failed assertion must not leave it waiting for an hour
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert asked == []  # stopped before its first check


# --- Where main starts it -----------------------------------------------------

@pytest.fixture
def launched(monkeypatch):
    """Run app.main as far as serving, with the app and the server stood in for.
    Returns the stop events main gave the timers it started, one for each."""
    monkeypatch.setattr(app_module, "_configure_logging", lambda environment: None)
    monkeypatch.setattr(app_module, "create_app", lambda app_settings: object())
    monkeypatch.setattr(paths, "ENVIRONMENT", paths.ENVIRONMENT)  # main sets it; this puts it back
    timers = []
    monkeypatch.setattr(app_module, "start_backup_timer", timers.append)
    monkeypatch.setattr(server_runtime, "serve", lambda *args: None)
    monkeypatch.setattr(server_runtime, "run_dev", lambda *args: None)

    def run(*argv):
        app_module.main(["--no-browser", *argv])
        return timers
    run.timers = timers
    return run


@pytest.mark.parametrize("argv, reloader_child, starts", [
    ([], False, True),
    (["--sandbox"], False, True),
    # Production's debug server doesn't reload, so its one process serves.
    (["--dev"], False, True),
    # The sandbox's reloader runs the app again in a child that serves, and
    # leaves the parent, which only watches files.
    (["--dev", "--sandbox"], True, True),
    (["--dev", "--sandbox"], False, False),
], ids=["browser", "sandbox", "production debug server", "reloader child", "reloader parent"])
def test_only_a_process_that_serves_starts_the_timer(
        launched, monkeypatch, argv, reloader_child, starts):
    if reloader_child:
        monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    else:
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)

    assert len(launched(*argv)) == (1 if starts else 0)


def test_the_timer_stops_when_the_server_does(launched):
    (stop,) = launched()

    assert stop.is_set()


def test_a_refused_launch_starts_no_timer(launched, monkeypatch):
    def refuse(app_settings):
        raise database.DatabaseLockedError("in use")
    monkeypatch.setattr(app_module, "create_app", refuse)

    with pytest.raises(SystemExit):
        launched()

    assert launched.timers == []


def test_building_the_app_starts_no_timer(monkeypatch):
    """Only main starts it. The suite builds an app all the time, and each
    build must not grow a thread."""
    def refuse(*args, **kwargs):
        raise AssertionError("create_app started the backup timer")
    monkeypatch.setattr(app_module, "start_backup_timer", refuse)
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    before = set(threading.enumerate())

    app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))

    started = set(threading.enumerate()) - before
    assert "daily-backup" not in {thread.name for thread in started}
