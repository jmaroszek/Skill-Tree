"""Named Resource migration, storage, and platform opener behavior."""

import database
import pytest
import resource_links as resources
from callback_helpers import build_editor_snapshot, is_form_dirty_vs_snapshot
from graph_manager import GraphManager
from models import Node
from dash.development.base_component import Component


def _node(name, **links):
    return Node(name=name, type="Resource", description="", value=5,
                time_o=1, time_m=1, time_p=1, interest=5, difficulty=5,
                status="Open", context="Mind", **links)


def test_v10_migrates_legacy_links_into_named_sections():
    manager = GraphManager()
    manager.add_node(_node(
        "Reading", obsidian_path='["notes/one.md"]',
        google_drive_path='["https://drive.google.com/file/x", "C:/Drive/book.pdf"]',
        website='["https://example.com"]'))
    with database.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO Settings(key, value) VALUES ('GDRIVE_ROOT_PATH', 'C:/Drive')")
        conn.execute("INSERT OR REPLACE INTO Settings(key, value) VALUES ('GDRIVE_ENABLED', '1')")
        conn.execute("DELETE FROM NodeResourceLinks")
        conn.execute("PRAGMA user_version = 9")
        conn.commit()
    database._initialized = False
    database.init_db()
    sections = resources.get_sections()
    assert [section['name'] for section in sections] == ["Obsidian", "Google Drive", "Website"]
    assert resources.get_node_links("Reading") == {
        "obsidian": ["notes/one.md"],
        "drive": ["https://drive.google.com/file/x", "book.pdf"],
        "website": ["https://example.com"],
    }
    assert manager.get_node("Reading").google_drive_path == (
        '["https://drive.google.com/file/x", "C:/Drive/book.pdf"]')


def test_named_sections_limit_and_preserve_disabled_links(tmp_path):
    manager = GraphManager()
    manager.add_node(_node("Reading"))
    root = tmp_path / "library"
    root.mkdir()
    file = root / "book.pdf"
    file.write_bytes(b"pdf")
    rows = resources.get_sections()
    rows.append({"id": "books", "name": "Books", "kind": "mixed",
                 "root_path": str(root), "enabled": True})
    resources.save_sections(rows)
    resources.save_node_links("Reading", {"books": [str(file)]})
    assert resources.get_node_links("Reading")["books"] == ["book.pdf"]
    snapshot = build_editor_snapshot(manager, "Reading")
    assert snapshot["custom_links"] == {"books": ["book.pdf"]}
    form = dict(snapshot)
    assert not is_form_dirty_vs_snapshot(snapshot, form)
    form["custom_links"] = {"books": ["other.pdf"]}
    assert is_form_dirty_vs_snapshot(snapshot, form)

    rows = resources.get_sections()
    rows[-1]["enabled"] = 0
    resources.save_sections(rows)
    resources.save_node_links("Reading", {"books": []})
    assert resources.get_node_links("Reading")["books"] == ["book.pdf"]
    with pytest.raises(ValueError, match="only empty custom"):
        resources.save_sections(rows[:-1])
    with pytest.raises(ValueError, match="five"):
        resources.save_sections(rows + [dict(rows[-1], id="extra"),
                                        dict(rows[-1], id="another")])

    manager.rename_node("Reading", "Read Books")
    assert resources.get_node_links("Read Books")["books"] == ["book.pdf"]
    assert resources.get_node_links("Reading") == {}


def test_mixed_url_and_file_resolution(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "note.txt"
    inside.write_text("note")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    section = {"kind": "mixed", "root_path": str(root)}
    assert resources.normalize_link(str(inside), section) == "note.txt"
    assert resources.normalize_link(str(outside), section) == str(outside)
    assert resources.resolve_target("note.txt", section) == ("path", str(inside))
    assert resources.resolve_target("https://example.com", section) == (
        "web", "https://example.com")
    assert resources.resolve_target("example.com", {"kind": "mixed", "root_path": ""}) == (
        "web", "https://example.com")
    assert resources.absolute_path("C:\\Users\\person\\file.txt")
    with pytest.raises(ValueError, match="root folder"):
        resources.resolve_target("missing.txt", {"kind": "mixed", "root_path": ""})


@pytest.mark.parametrize("platform, expected", [
    ("darwin", "open"), ("linux", "xdg-open"),
])
def test_open_path_platform_command(monkeypatch, platform, expected):
    calls = []
    monkeypatch.setattr(resources.sys, "platform", platform)
    monkeypatch.setattr(resources.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    resources.open_path("obsidian://open?path=x")
    assert calls == [([expected, "obsidian://open?path=x"], {"shell": False})]


def test_open_path_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(resources.sys, "platform", "win32")
    monkeypatch.setattr(resources.os, "startfile", calls.append, raising=False)
    resources.open_path("C:\\book.pdf")
    assert calls == ["C:\\book.pdf"]


def test_web_url_uses_browser(monkeypatch):
    calls = []
    monkeypatch.setattr(resources.webbrowser, "open_new_tab", lambda value: calls.append(value) or True)
    resources.open_resource("example.com", {"kind": "mixed", "root_path": ""})
    assert calls == ["https://example.com"]


def test_home_dots_use_named_section_labels():
    from callback_helpers import format_suggestions_table
    manager = GraphManager()
    manager.add_node(_node("Reading", website='["https://example.com"]'))
    rows = resources.get_sections()
    rows[-1]['name'] = 'Articles'
    resources.save_sections(rows)
    node = manager.get_node("Reading")
    node.priority_score = 10
    rendered = format_suggestions_table([node], manager)
    stack = list(rendered)
    titles = []
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, Component):
            title = getattr(item, 'title', None)
            if title:
                titles.append(title)
            stack.append(item.children)
    assert 'Articles' in titles


def test_disabled_custom_editor_section_keeps_its_input_mounted():
    from callback_helpers import render_custom_resource_sections
    rows = resources.get_sections()
    rows.append({'id': 'books', 'name': 'Books', 'kind': 'mixed',
                 'root_path': '', 'enabled': False})
    resources.save_sections(rows)
    rendered = render_custom_resource_sections({'books': ['chapter.pdf']})
    assert len(rendered) == 1
    assert rendered[0].style == {'display': 'none'}
    field = rendered[0].children[1].children[0].children[0]
    assert field.value == 'chapter.pdf'


def test_saved_resource_route_uses_shared_opener(monkeypatch):
    import app as app_module
    import config
    manager = GraphManager()
    manager.add_node(_node("Reading", website='["https://example.com"]'))
    opened = []
    monkeypatch.setattr(resources, 'open_resource',
                        lambda value, section: opened.append((value, section['id'])))
    app = app_module.create_app(app_module.AppSettings(
        environment=config.ENVIRONMENT, configure_logging=False))
    client = app.server.test_client()
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert b'resource-section-settings-store' in layout.data
    assert b'editor-custom-resources' in layout.data
    response = client.post('/open-resource', json={
        'node': 'Reading', 'section': 'website', 'index': 0})
    assert response.status_code == 200
    assert opened == [('https://example.com', 'website')]
    assert client.post('/open-resource', json={
        'node': 'Reading', 'section': 'website', 'index': 1}).status_code == 404


def test_browser_picker_passes_paths_as_arguments(monkeypatch):
    import callback_helpers
    import subprocess
    calls = []

    class Result:
        returncode = 0
        stdout = 'C:/chosen/book.pdf'
        stderr = ''

    monkeypatch.setattr(subprocess, 'run',
                        lambda args, **kwargs: calls.append(args) or Result())
    root = 'C:/Library/has"quote'
    assert callback_helpers.spawn_local_file_picker(
        root, 'Select file', [('All files', '*.*')]) == 'C:/chosen/book.pdf'
    assert calls[0][1] == '-c'
    assert calls[0][3] == root
