"""Optional resource settings and legacy link preservation."""

import json
import inspect
from pathlib import Path

import database
from callback_helpers import expand_gdrive_prefix, strip_gdrive_prefix, serialize_links
from config import ConfigManager
from graph_manager import GraphManager
from models import Node
from settings_callbacks import register_settings_callbacks


def _node(name, **links):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1, time_m=1, time_p=1, interest=5,
                difficulty=5, status="Open", context="Mind", **links)


def test_new_database_has_only_website_integration_enabled_by_default():
    assert not ConfigManager.get_obsidian_enabled()
    assert not ConfigManager.get_gdrive_enabled()
    assert ConfigManager.get_obsidian_vault() == ""
    assert ConfigManager.get_gdrive_path() == ""


def test_drive_urls_and_mounted_paths_keep_their_existing_meaning():
    ConfigManager.set_gdrive_enabled(True)
    ConfigManager.set_gdrive_path("G:/My Drive")
    url = "https://drive.google.com/file/d/123/view"
    assert expand_gdrive_prefix(url) == url
    assert strip_gdrive_prefix([url]) == [url]
    assert json.loads(serialize_links([url])) == [url]
    assert expand_gdrive_prefix("notes/file.pdf").replace("\\", "/") == (
        "G:/My Drive/notes/file.pdf")


def test_v9_migration_enables_existing_links_without_changing_them(monkeypatch, tmp_path):
    vault = tmp_path / "Documents" / "Obsidian"
    vault.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    obsidian_link = '["notes/existing.md"]'
    drive_link = '["https://drive.google.com/file/d/existing/view"]'
    manager = GraphManager()
    manager.add_node(_node("Existing", obsidian_path=obsidian_link,
                           google_drive_path=drive_link))

    with database.get_connection() as conn:
        conn.execute("DELETE FROM Settings WHERE key IN "
                     "('OBSIDIAN_ENABLED', 'GDRIVE_ENABLED')")
        conn.execute("PRAGMA user_version = 8")
        conn.commit()
    database._initialized = False
    database.init_db()

    assert ConfigManager.get_obsidian_enabled()
    assert ConfigManager.get_gdrive_enabled()
    assert ConfigManager.get_obsidian_vault() == str(vault)
    node = manager.get_node("Existing")
    assert node.obsidian_path == obsidian_link
    assert node.google_drive_path == drive_link


def test_disabling_integrations_preserves_stored_links():
    manager = GraphManager()
    obsidian_link = '["notes/keep.md"]'
    drive_link = '["https://drive.google.com/file/d/keep/view"]'
    manager.add_node(_node("Keep", obsidian_path=obsidian_link,
                           google_drive_path=drive_link))
    ConfigManager.set_obsidian_enabled(True)
    ConfigManager.set_gdrive_enabled(True)
    ConfigManager.set_obsidian_enabled(False)
    ConfigManager.set_gdrive_enabled(False)

    node = manager.get_node("Keep")
    assert node.obsidian_path == obsidian_link
    assert node.google_drive_path == drive_link


def test_settings_save_supports_drive_urls_without_a_root_path():
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
    save = registry.callbacks["save_settings"]
    args = {key: None for key in inspect.signature(save).parameters}
    args.update(n_clicks=1, obs_path="C:/Vault", gdrive_path="",
                obsidian_enabled_val=["enabled"],
                gdrive_enabled_val=["enabled"], hp_profile="Sage",
                hpw=40, hpm=160)
    assert save(**args)[0] == "Settings saved"
    assert ConfigManager.get_obsidian_enabled()
    assert ConfigManager.get_gdrive_enabled()
    assert ConfigManager.get_gdrive_path() == ""
    assert expand_gdrive_prefix("https://drive.google.com/file") == (
        "https://drive.google.com/file")
    assert registry.callbacks["refresh_resource_visibility"](None, None, None) == (
        {}, {}, {}, {})

    args["obs_path"] = ""
    warning = save(**args)[0]
    assert "vault path" in warning.children
    assert warning.className == "text-danger"
    assert ConfigManager.get_obsidian_vault() == "C:/Vault"
