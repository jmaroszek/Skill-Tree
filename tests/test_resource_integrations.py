"""The v11 move to named sections only, and saving sections from Settings."""

import inspect

import database
import resource_links as resources
from graph_manager import GraphManager
from models import Node
from settings_callbacks import register_settings_callbacks


def _node(name, **fields):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1, time_m=1, time_p=1, interest=5,
                difficulty=5, status="Open", context="Mind", **fields)


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _reopen_at(version):
    with database.get_connection() as conn:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    database._initialized = False
    database.init_db()


def test_a_fresh_database_starts_with_three_plain_sections():
    assert [(s["id"], s["kind"]) for s in resources.get_sections()] == [
        ("obsidian", "obsidian"), ("drive", "mixed"), ("website", "mixed")]
    with database.get_connection() as conn:
        assert "obsidian_path" not in _columns(conn, "Nodes")
        assert "enabled" not in _columns(conn, "ResourceSections")


def test_v11_keeps_every_link_and_drops_the_legacy_copies():
    """A v10 database: legacy columns mirror the table, except one link the
    table lacks. v11 keeps the table's links, copies the missing one, and
    drops the columns, the on/off switch, and the old integration settings."""
    GraphManager().add_node(_node("Reading", resource_links={"drive": ["Notes/a.gdoc"]}))
    with database.get_connection() as conn:
        for column in ("obsidian_path", "google_drive_path", "website"):
            conn.execute(f"ALTER TABLE Nodes ADD COLUMN {column} TEXT")
        conn.execute("ALTER TABLE ResourceSections ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE ResourceSections SET enabled=0 WHERE id='website'")
        conn.execute("UPDATE Nodes SET google_drive_path=?, website=? WHERE name='Reading'",
                     ('["G:/My Drive/Notes/a.gdoc"]', '["https://example.com"]'))
        conn.execute("INSERT OR REPLACE INTO Settings(key, value) VALUES ('GDRIVE_ENABLED', '1')")
        conn.commit()

    _reopen_at(10)

    assert GraphManager().get_node("Reading").resource_links == {
        "drive": ["Notes/a.gdoc"], "website": ["https://example.com"]}
    assert [s["id"] for s in resources.get_sections()] == ["obsidian", "drive", "website"]
    with database.get_connection() as conn:
        assert not {"obsidian_path", "google_drive_path", "website"} & _columns(conn, "Nodes")
        assert "enabled" not in _columns(conn, "ResourceSections")
        assert conn.execute("SELECT 1 FROM Settings WHERE key='GDRIVE_ENABLED'").fetchone() is None


def _settings_callbacks():
    class Registry:
        def __init__(self):
            self.callbacks = {}

        def callback(self, *dependencies, **kwargs):
            def register(fn):
                self.callbacks[fn.__name__] = fn
                return fn
            return register

        def clientside_callback(self, *args, **kwargs):
            pass

    registry = Registry()
    register_settings_callbacks(registry)
    return registry.callbacks


def _save(store, cards):
    """Run save_settings with the draft store and the mounted card fields."""
    save = _settings_callbacks()["save_settings"]
    args = {key: None for key in inspect.signature(save).parameters}
    ids = [{"index": card["id"]} for card in cards]
    args.update(
        n_clicks=1, hp_profile="Sage", hpw=40, hpm=160, section_store=store,
        section_names=[card["name"] for card in cards], section_name_ids=ids,
        section_roots=[card.get("root_path", "") for card in cards], section_root_ids=ids,
        section_use_roots=[["enabled"] if card.get("use_root", True) else []
                           for card in cards],
        section_use_root_ids=ids,
        section_obsidian=[["obsidian"] if card.get("kind") == "obsidian" else []
                          for card in cards],
        section_obsidian_ids=ids)
    return save(**args)


def test_settings_save_renames_switches_and_clears_an_unused_root():
    store = resources.get_sections()
    cards = [
        {"id": "obsidian", "name": "Notes", "kind": "obsidian", "root_path": "C:/Vault"},
        {"id": "drive", "name": "Drive", "kind": "mixed", "root_path": "G:/Drive",
         "use_root": False},
        {"id": "website", "name": "Web", "kind": "obsidian", "root_path": ""},
    ]
    assert _save(store, cards)[0] == "Settings saved"
    saved = {s["id"]: s for s in resources.get_sections()}
    assert saved["obsidian"]["name"] == "Notes"
    assert saved["obsidian"]["root_path"] == "C:/Vault"
    assert saved["drive"]["root_path"] == ""
    assert saved["website"]["kind"] == "obsidian"


def test_settings_save_removes_a_held_section_with_its_links():
    GraphManager().add_node(_node("Reading", resource_links={
        "drive": ["a.pdf"], "website": ["https://example.com"]}))
    store = resources.get_sections()
    for row in store:
        if row["id"] == "drive":
            row["deleted"] = True
    cards = [dict(row) for row in store if not row.get("deleted")]
    assert _save(store, cards)[0] == "Settings saved"
    assert [s["id"] for s in resources.get_sections()] == ["obsidian", "website"]
    assert GraphManager().get_node("Reading").resource_links == {
        "website": ["https://example.com"]}


def test_settings_save_refuses_duplicate_names():
    store = resources.get_sections()
    cards = [dict(row, name="Same") for row in store]
    warning = _save(store, cards)[0]
    assert warning.className == "text-danger"
    assert [s["name"] for s in resources.get_sections()] == ["Obsidian", "Google Drive", "Website"]
