"""Named Resource sections: storage, opening, the editor rows and Settings cards."""

import pytest
import resource_links as resources
from callback_helpers import build_editor_snapshot, is_form_dirty_vs_snapshot
from graph_manager import GraphManager
from models import Node
from dash.development.base_component import Component


def _node(name, **fields):
    return Node(name=name, type="Resource", description="", value=5,
                time_o=1, time_m=1, time_p=1, interest=5, difficulty=5,
                status="Open", context="Mind", **fields)


def _flatten(component):
    stack, found = [component], []
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, Component):
            found.append(item)
            stack.append(getattr(item, 'children', None))
    return found


def _component_types(block):
    return {c.id['type'] for c in _flatten(block) if isinstance(getattr(c, 'id', None), dict)}


def test_sections_store_links_relative_to_their_root_and_follow_renames(tmp_path):
    manager = GraphManager()
    manager.add_node(_node("Reading"))
    root = tmp_path / "library"
    root.mkdir()
    file = root / "book.pdf"
    file.write_bytes(b"pdf")
    rows = resources.get_sections()
    rows.append({"id": "books", "name": "Books", "kind": "mixed", "root_path": str(root)})
    resources.save_sections(rows)
    resources.save_node_links("Reading", {"books": [str(file)]})
    assert resources.get_node_links("Reading")["books"] == ["book.pdf"]

    snapshot = build_editor_snapshot(manager, "Reading")
    assert snapshot["resource_links"] == {"books": ["book.pdf"]}
    form = dict(snapshot)
    assert not is_form_dirty_vs_snapshot(snapshot, form)
    form["resource_links"] = {"books": ["other.pdf"]}
    assert is_form_dirty_vs_snapshot(snapshot, form)

    with pytest.raises(ValueError, match="at most"):
        resources.save_sections(rows + [dict(rows[-1], id="extra", name="Extra"),
                                        dict(rows[-1], id="another", name="Another")])

    manager.rename_node("Reading", "Read Books")
    assert resources.get_node_links("Read Books")["books"] == ["book.pdf"]
    assert resources.get_node_links("Reading") == {}


def test_saving_links_leaves_unsubmitted_sections_alone():
    GraphManager().add_node(_node("Reading", resource_links={
        "drive": ["a.pdf"], "website": ["https://example.com"]}))
    resources.save_node_links("Reading", {"drive": ["b.pdf", ""]})
    assert resources.get_node_links("Reading") == {
        "drive": ["b.pdf"], "website": ["https://example.com"]}


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


def _vault(tmp_path):
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "notes").mkdir()
    return vault


def test_an_obsidian_section_opens_vault_notes_in_the_obsidian_app(tmp_path):
    vault = _vault(tmp_path)
    (vault / "notes" / "a.md").write_text("note")
    section = {"kind": "obsidian", "root_path": str(vault)}
    kind, target = resources.resolve_target("notes/a.md", section)
    assert kind == "uri"
    assert target.startswith("obsidian://open?path=")
    # A web link in the same section still goes to the browser.
    assert resources.resolve_target("https://example.com", section)[0] == "web"


def test_an_obsidian_link_to_a_missing_file_says_so(tmp_path):
    section = {"kind": "obsidian", "root_path": str(_vault(tmp_path))}
    with pytest.raises(FileNotFoundError):
        resources.resolve_target("notes/gone.md", section)


def test_obsidian_hands_other_files_to_the_default_app(tmp_path):
    vault = _vault(tmp_path)
    (vault / "notes" / "report.docx").write_bytes(b"doc")
    outside = tmp_path / "loose.md"
    outside.write_text("not in a vault")
    section = {"kind": "obsidian", "root_path": str(vault)}
    # Obsidian can't open a Word file, even inside the vault.
    assert resources.resolve_target("notes/report.docx", section) == (
        "path", str(vault / "notes" / "report.docx"))
    # Nor a note outside every vault.
    assert resources.resolve_target(str(outside), section) == ("path", str(outside))


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
    manager.add_node(_node("Reading", resource_links={"website": ["https://example.com"]}))
    rows = resources.get_sections()
    rows[-1]['name'] = 'Articles'
    resources.save_sections(rows)
    node = manager.get_node("Reading")
    node.priority_score = 10
    rendered = format_suggestions_table([node], manager)
    titles = [c.title for c in _flatten(rendered) if getattr(c, 'title', None)]
    assert 'Articles' in titles


def test_editor_renders_every_section_with_its_links():
    from callback_helpers import render_resource_sections
    blocks = render_resource_sections({'drive': ['a.pdf', 'b.pdf']})
    assert [getattr(b, 'data-resource-id') for b in blocks] == ['obsidian', 'drive', 'website']
    assert getattr(blocks[0], 'data-resource-kind') == 'obsidian'
    drive_inputs = [c for c in _flatten(blocks[1])
                    if getattr(c, 'id', None) and c.id.get('type') == 'resource-link']
    assert sorted(c.value for c in drive_inputs) == ['a.pdf', 'b.pdf']
    assert sorted(c.id['index'] for c in drive_inputs) == ['drive:0', 'drive:1']
    # An empty section still offers one row, and no remove on it.
    assert 'resource-link' in _component_types(blocks[2])
    assert 'resource-remove' not in _component_types(blocks[2])


def test_mounted_inputs_are_the_editor_links():
    from callback_helpers import resource_link_values
    ids = [{'type': 'resource-link', 'index': index}
           for index in ('drive:1', 'drive:0', 'books:0')]
    assert resource_link_values(['b.pdf', 'a.pdf', ''], ids) == {
        'drive': ['a.pdf', 'b.pdf'], 'books': ['']}


def test_saved_resource_route_uses_shared_opener(monkeypatch):
    import app as app_module
    import config
    manager = GraphManager()
    manager.add_node(_node("Reading", resource_links={"website": ["https://example.com"]}))
    opened = []
    monkeypatch.setattr(resources, 'open_resource',
                        lambda value, section: opened.append((value, section['id'])))
    app = app_module.create_app(app_module.AppSettings(
        environment=config.ENVIRONMENT, configure_logging=False))
    client = app.server.test_client()
    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert b'resource-section-settings-store' in layout.data
    assert b'editor-resources' in layout.data
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


def test_browser_picker_can_choose_a_folder(monkeypatch):
    import callback_helpers
    import subprocess
    calls = []

    class Result:
        returncode = 0
        stdout = 'C:/Library'
        stderr = ''

    monkeypatch.setattr(subprocess, 'run',
                        lambda args, **kwargs: calls.append(args) or Result())
    assert callback_helpers.spawn_local_file_picker(
        '', 'Select folder', None, directory=True) == 'C:/Library'
    assert calls[0][-1] == '1'


def test_settings_cards_carry_their_switches_and_a_removed_card_holds():
    from settings_layout import build_resource_setting_rows
    rows = resources.get_sections()
    rows[1]['deleted'] = True
    cards = build_resource_setting_rows(rows, {'drive': 3})
    obsidian, drive, website = cards
    for card in (obsidian, website):
        assert {'resource-section-name', 'resource-section-remove',
                'resource-section-root-enabled', 'resource-section-obsidian',
                'resource-section-root'} <= _component_types(card)
    switch = next(c for c in _flatten(obsidian)
                  if getattr(c, 'id', None) == {'type': 'resource-section-obsidian',
                                                'index': 'obsidian'})
    assert switch.value == ['obsidian']
    root_switch = next(c for c in _flatten(website)
                       if getattr(c, 'id', None) == {'type': 'resource-section-root-enabled',
                                                     'index': 'website'})
    assert root_switch.value == []
    assert _component_types(drive) == {'resource-section-undelete'}
    assert any('3 links' in (c.children or '') for c in _flatten(drive)
               if isinstance(getattr(c, 'children', None), str))


def test_section_draft_reads_switches_from_the_cards():
    from settings_callbacks import _section_form_rows
    store = [{'id': 'books', 'name': 'Books', 'kind': 'mixed',
              'root_path': 'C:/Library', 'position': 0}]
    ids = [{'type': 'x', 'index': 'books'}]
    rows = _section_form_rows(store, None, None, ['C:/Library'], ids,
                              [[]], ids, [['obsidian']], ids)
    assert rows[0]['root_path'] == ''
    assert rows[0]['kind'] == 'obsidian'
    rows = _section_form_rows(store, None, None, ['C:/Library'], ids,
                              [['enabled']], ids, [[]], ids)
    assert rows[0]['root_path'] == 'C:/Library'
    assert rows[0]['kind'] == 'mixed'
