"""Settings > Data: the buttons that back up, restore, export and import."""
import base64
import json

import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

import backup
import data_callbacks
import data_transfer
import database
import settings_callbacks
from config import ConfigManager
from graph_manager import GraphManager
from layout import build_app_layout
from models import Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


def _callbacks(register):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


@pytest.fixture
def data():
    return _callbacks(data_callbacks.register_data_callbacks)


def _ids(component, found=None):
    found = set() if found is None else found
    component_id = getattr(component, "id", None)
    if isinstance(component_id, str):
        found.add(component_id)
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, "children") or hasattr(child, "id"):
            _ids(child, found)
    return found


def test_the_settings_modal_has_a_data_tab():
    ids = _ids(build_app_layout([], env="sandbox"))
    assert {"btn-backup-now", "btn-open-backup-folder", "setting-backup-extra-dir",
            "restore-backup-select", "btn-restore-confirm", "btn-export-json",
            "download-export-json", "download-export-db", "upload-import",
            "data-status"} <= ids


def test_back_up_now_makes_a_copy_and_lists_it(data):
    GraphManager().add_node(_node("Sleep"))

    status, options = data["back_up_now"](1)

    assert "Backed up" in str(status)
    (made,) = backup.list_backups("manual")
    assert options[0]["value"] == str(made["path"])
    assert "made by hand" in options[0]["label"]


def test_opening_the_tab_loads_backups_and_the_extra_folder(data, tmp_path):
    ConfigManager.set_backup_extra_dir(str(tmp_path))
    backup.create_backup("manual")

    options, extra = data["load_data_tab"]("tab-data")

    assert len(options) == 1 and extra == str(tmp_path)
    assert data["load_data_tab"]("tab-recommendations") == (dash.no_update, dash.no_update)


def test_exports_download_as_files(data):
    GraphManager().add_node(_node("Sleep"))

    as_json = data["export_json"](1)
    assert as_json["filename"].endswith(".json")
    assert json.loads(as_json["content"])["format"] == data_transfer.EXPORT_FORMAT

    as_db = data["export_database"](1)
    assert as_db["filename"].endswith(".db") and as_db["base64"]


def _upload(bundle):
    raw = json.dumps(bundle).encode()
    return "data:application/json;base64," + base64.b64encode(raw).decode()


def test_import_fills_an_empty_graph_then_reloads(data, monkeypatch, tmp_path):
    GraphManager().add_node(_node("Sleep"))
    bundle = data_transfer.export_data()
    fresh = str(tmp_path / "fresh.db")
    monkeypatch.setattr(database, "get_db_path", lambda: fresh)
    database._initialized = False
    database.init_db()

    status, reload_trigger = data["import_export"](_upload(bundle), "mine.json")

    assert "Imported 1 nodes" in str(status) and reload_trigger
    assert GraphManager().get_node("Sleep") is not None


def test_import_into_a_graph_with_nodes_is_refused_without_reloading(data):
    GraphManager().add_node(_node("Sleep"))
    status, reload_trigger = data["import_export"](
        _upload(data_transfer.export_data()), "mine.json")
    assert "empty graph" in str(status) and reload_trigger is dash.no_update


def test_a_file_that_isnt_json_is_named_in_the_refusal(data):
    garbage = "data:text/plain;base64," + base64.b64encode(b"\x00\x01nope").decode()
    status, reload_trigger = data["import_export"](garbage, "photo.jpg")
    assert "photo.jpg isn't a Skill Tree export" in str(status)
    assert reload_trigger is dash.no_update


def test_restore_asks_first_then_replaces_the_graph_and_reloads(data):
    manager = GraphManager()
    manager.add_node(_node("Sleep"))
    saved = str(backup.create_backup("manual"))
    manager.delete_node("Sleep")
    options = data_callbacks.backup_options()

    token = context_value.set(AttributeDict(triggered_inputs=[
        {"prop_id": "btn-restore-backup.n_clicks", "value": 1}]))
    try:
        is_open, text = data["confirm_restore"](1, None, saved, options)
    finally:
        context_value.reset(token)
    assert is_open and "backed up first" in text

    status, closed, reload_trigger = data["restore"](1, saved)
    assert "Restored" in str(status) and closed is False and reload_trigger
    assert manager.get_node("Sleep") is not None


def test_settings_save_keeps_the_extra_backup_folder(tmp_path):
    save = _callbacks(settings_callbacks.register_settings_callbacks)["save_settings"]
    status, *_ = save(
        1, [], [], [], [], 40, 160, "hours", 1, 2, 4, "Sage", "title", "",
        [], "definition", "definition", [], 5,
        None, None, None, None, None, None, None,
        backup_extra_dir=f"  {tmp_path}  ")
    assert status.startswith("Settings saved")
    assert ConfigManager.get_backup_extra_dir() == str(tmp_path)
