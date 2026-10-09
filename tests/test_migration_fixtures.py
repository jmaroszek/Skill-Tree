"""Every older version's database opens in this one without losing anything (P6.3).

tests/fixtures/schema_vN.db were saved by the code of each schema version
(make_schema_fixtures.py). Opening one runs the whole upgrade ladder from
there. The graph must come through intact, the links old versions kept in
Nodes columns must land in Resource sections, and a copy of the original must
be kept first.
"""
import math
import shutil
import sqlite3
from pathlib import Path

import pytest

import backup
import database
from graph_manager import GraphManager

FIXTURES = sorted(Path(__file__).parent.glob("fixtures/schema_v*.db"),
                  key=lambda p: int(p.stem.split("_v")[1]))


def _rows(path, sql):
    conn = sqlite3.connect(path)
    try:
        return set(conn.execute(sql).fetchall())
    finally:
        conn.close()


def _snapshot(path):
    return {
        "nodes": _rows(path, "SELECT name, type, status, context, value, time_m FROM Nodes"),
        "edges": _rows(path, "SELECT source, target, type FROM Edges"),
        "aliases": _rows(path, "SELECT alias, node_name FROM Aliases"),
        "events": _rows(path, "SELECT name FROM Events"),
        "event_nodes": _rows(path, "SELECT event_name, node_name FROM EventNodes"),
    }


def _version(path):
    return int(path.stem.split("_v")[1])


def _upgrade(source, tmp_path, monkeypatch):
    copy = tmp_path / "Data" / "skilltree.db"
    copy.parent.mkdir()
    shutil.copy(source, copy)
    before = _snapshot(copy)
    monkeypatch.setattr(database, "get_db_path", lambda: str(copy))
    database._initialized = False
    database.init_db()
    return before, copy


@pytest.fixture(params=FIXTURES, ids=lambda p: p.stem)
def upgraded(request, tmp_path, monkeypatch):
    """(original snapshot, path) after opening a copy with the current code."""
    return _upgrade(request.param, tmp_path, monkeypatch)


# Versions before 11 kept a node's links in three Nodes columns, which the
# upgrade moves into sections. Later ones were born with sections.
@pytest.fixture(params=[p for p in FIXTURES if _version(p) < 11], ids=lambda p: p.stem)
def upgraded_with_link_columns(request, tmp_path, monkeypatch):
    return _upgrade(request.param, tmp_path, monkeypatch)


@pytest.fixture(params=[p for p in FIXTURES if _version(p) >= 11], ids=lambda p: p.stem)
def upgraded_with_sections(request, tmp_path, monkeypatch):
    return _upgrade(request.param, tmp_path, monkeypatch)


def test_there_is_a_fixture_for_every_older_version():
    versions = [int(p.stem.split("_v")[1]) for p in FIXTURES]
    assert versions == list(range(4, database.SCHEMA_VERSION))


def test_the_graph_comes_through_intact(upgraded):
    before, path = upgraded
    after = _snapshot(path)
    assert after == before
    assert len(before["nodes"]) == 7 and len(before["edges"]) == 4


def test_it_is_stamped_current_and_passes_the_integrity_check(upgraded):
    _before, path = upgraded
    assert _rows(path, "PRAGMA user_version") == {(database.SCHEMA_VERSION,)}
    database.check_integrity(str(path))


def test_the_original_is_backed_up_first(upgraded):
    _before, path = upgraded
    (kept,) = backup.list_backups("pre-migration")
    conn = sqlite3.connect(kept["path"])
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] < database.SCHEMA_VERSION
    finally:
        conn.close()


def test_links_move_into_resource_sections(upgraded_with_link_columns):
    _before, path = upgraded_with_link_columns
    links = _rows(path, "SELECT node_name, section_id, target FROM NodeResourceLinks")
    assert ("Sleep hygiene", "obsidian", "Notes/Sleep hygiene.md") in links
    # A database born at v12 or later starts with one "links" section, not "website".
    assert any(link in links for link in (
        ("Sleep hygiene", "website", "https://example.com/sleep"),
        ("Sleep hygiene", "links", "https://example.com/sleep")))
    assert ("Blackout curtains", "drive", "Shopping/curtains.pdf") in links
    columns = {row[1] for row in _rows(path, "PRAGMA table_info(Nodes)")}
    assert not columns & {"obsidian_path", "google_drive_path", "website"}


def test_links_in_sections_stay_put(upgraded_with_sections):
    _before, path = upgraded_with_sections
    links = _rows(path, "SELECT node_name, section_id, target FROM NodeResourceLinks")
    # A database born at v12 or later starts with one "links" section, not "website".
    assert any(link in links for link in (
        ("Sleep hygiene", "website", "https://example.com/sleep"),
        ("Sleep hygiene", "links", "https://example.com/sleep")))


@pytest.fixture(params=[p for p in FIXTURES if _version(p) < 12], ids=lambda p: p.stem)
def upgraded_before_v12(request, tmp_path, monkeypatch):
    return _upgrade(request.param, tmp_path, monkeypatch)


def test_history_starts_recording(upgraded_before_v12):
    """v12: the ledger of nodes added and deleted, with the date its coverage
    began, and the ranking columns on Now starts."""
    _before, path = upgraded_before_v12
    assert _rows(path, "SELECT COUNT(*) FROM NodeLedger") == {(0,)}
    marker = _rows(path, "SELECT value FROM Settings WHERE key='node_ledger_started_at'")
    assert len(marker) == 1
    columns = {row[1] for row in _rows(path, "PRAGMA table_info(NodeLifecycleEvents)")}
    assert {"rank", "ranked_of"} <= columns


def test_reflections_get_a_notes_column(upgraded):
    """v13: written reflection notes, empty on every node already there."""
    _before, path = upgraded
    columns = {row[1] for row in _rows(path, "PRAGMA table_info(Nodes)")}
    assert "reflect_notes" in columns
    assert _rows(path, "SELECT DISTINCT reflect_notes FROM Nodes") == {(None,)}


def test_the_upgraded_graph_works(upgraded):
    manager = GraphManager()
    assert manager.recompute_all_statuses() == 0
    scored = manager.calculate_priority_scores(manager.get_now_nodes())
    assert scored and all(math.isfinite(n.priority_score) for n in scored)
    assert manager.get_node("A|B test").dormant  # asleep in its event


def test_opening_it_again_changes_nothing(upgraded):
    _before, path = upgraded
    first = _snapshot(path)
    backups = len(backup.list_backups())
    database._initialized = False
    database.init_db()
    assert _snapshot(path) == first
    assert len(backup.list_backups()) == backups
