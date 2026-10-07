"""Shared pytest fixtures for the Skill Tree test suite."""

import shutil

import pytest
import database


@pytest.fixture(scope="session")
def new_database(tmp_path_factory):
    """A new database, made once per run (once per worker under pytest -n)
    for temp_database to copy. Making one costs a transaction and a sync to
    disk, which every test would otherwise pay again."""
    path = str(tmp_path_factory.mktemp("new_database") / "skilltree.db")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(database, "get_db_path", lambda: path)
        database._initialized = False
        database.init_db()
    database._initialized = False
    return path


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path, new_database):
    """Gives each test its own copy of a new database, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    shutil.copyfile(new_database, tmp_db_path)
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = True
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
