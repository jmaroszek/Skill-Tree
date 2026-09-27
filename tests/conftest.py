"""Shared pytest fixtures for the Skill Tree test suite."""

import pytest
import database


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


@pytest.fixture
def legacy_resource_sections(temp_database):
    """The three Resource sections a new database started with before P5.2
    (Obsidian, Google Drive, Website), for tests written around them. A new
    database now starts with a single "Links" section."""
    with database.transaction() as conn:
        conn.execute("DELETE FROM ResourceSections")
        conn.executemany(
            "INSERT INTO ResourceSections (id, name, kind, root_path, position) "
            "VALUES (?, ?, ?, '', ?)",
            [(section_id, name, kind, position) for position, (section_id, name, kind, *_)
             in enumerate(database._LEGACY_RESOURCE_SECTIONS)])
    return temp_database
