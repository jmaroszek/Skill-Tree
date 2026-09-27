"""Names that break naive code, through the paths a name actually travels (P6.2).

A node name is text the user types, or text in someone else's export. It
travels through the editor save, the value|timestamp and JSON bridges the
page scripts write, the context menu, renames, the canvas, and export and
import. Each of these names must come back out exactly as it went in, and
must never be read as markup.
"""
import json
import re
from pathlib import Path

import pytest

import bridge_payloads
import data_transfer
import database
import graph_rules
import node_commands
from callback_helpers import CanvasNodeStyles, build_node_element
from config import DEFAULT_NODE_COLORS
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, STATUS_DONE

ROOT = Path(__file__).resolve().parents[1]

HOSTILE = [
    "A|B|C", "ends with a pipe|", "|starts with a pipe",
    "O'Brien", 'say "hi"', "back\\slash", "C:\\Users\\name", "a: b", "ratio 1:2",
    "Moon 🌙✨", "Grüße", "日本語のノード", "עברית מימין לשמאל",
    "<script>alert(1)</script>", "<b>bold</b> & more", '{"json": true}', "[1, 2]",
    "100% done", "#hash", "?query=1&x=2", "a/b/c", "spaces    inside",
    "x" * graph_rules.NAME_MAX_LENGTH,
]


def _save(manager, name, **extra):
    return node_commands.handle_save(
        manager, name, "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5, [], "Mind", None, {},
        [], [], [], [], [], **extra)


@pytest.fixture
def manager():
    return GraphManager()


@pytest.mark.parametrize("name", HOSTILE)
def test_the_editor_saves_it_exactly(manager, name):
    _save(manager, name)
    assert manager.get_node(name).name == name


@pytest.mark.parametrize("name", HOSTILE)
def test_the_page_bridges_hand_it_back_exactly(name):
    stamp = "1790000000000"
    assert bridge_payloads.strip_stamp(f"{name}|{stamp}") == name
    assert bridge_payloads.fields(f"{name}|2|{stamp}", 2) == [name, "2"]
    assert bridge_payloads.names(json.dumps([name, "Other"]) + f"|{stamp}") == [name, "Other"]
    key = bridge_payloads.edge_key(name, "Other", EDGE_NEEDS_HARD)
    assert bridge_payloads.parse_edge_key(key) == (name, "Other", EDGE_NEEDS_HARD)


@pytest.mark.parametrize("name", HOSTILE)
def test_toggle_done_and_rename_touch_only_that_node(manager, name):
    _save(manager, name)
    _save(manager, "Neighbour")
    manager.add_edge(name, "Neighbour", EDGE_NEEDS_HARD)
    node_commands.handle_toggle_done(manager, {"id": name})
    assert manager.get_node(name).status == STATUS_DONE
    assert manager.get_node("Neighbour").status != STATUS_DONE

    manager.rename_node(name, "Plain")
    manager.rename_node("Plain", name)
    assert manager.get_node(name) is not None
    edges = {(e["source"], e["target"]) for e in manager.get_edges()}
    assert (name, "Neighbour") in edges


@pytest.mark.parametrize("name", HOSTILE)
def test_the_canvas_carries_it_as_data(manager, name):
    _save(manager, name)
    styles = CanvasNodeStyles(colors=dict(DEFAULT_NODE_COLORS), shapes={},
                              trigger_names=frozenset())
    element = build_node_element(manager.get_node(name), styles)
    assert element["data"]["id"] == name


def test_export_and_import_keep_every_name(manager, tmp_path, monkeypatch):
    for name in HOSTILE:
        _save(manager, name)
    bundle = json.loads(data_transfer.export_json())

    fresh = str(tmp_path / "fresh.db")
    monkeypatch.setattr(database, "get_db_path", lambda: fresh)
    database._initialized = False
    database.init_db()
    data_transfer.import_data(bundle)

    assert {n.name for n in GraphManager().get_all_nodes()} == set(HOSTILE)


@pytest.mark.parametrize("name, fragment", [
    ("x" * (graph_rules.NAME_MAX_LENGTH + 1), "characters"),
    (" padded ", "space"),
    ("line\nbreak", "character"),
])
def test_names_that_cant_work_are_refused_with_a_reason(manager, name, fragment):
    with pytest.raises(ValueError, match=fragment):
        _save(manager, name)


def test_no_page_script_writes_raw_html():
    """Names reach the page as text (Dash escapes, scripts use textContent).
    innerHTML would let a name like <img onerror=...> run as markup."""
    offenders = []
    for path in sorted((ROOT / "assets").glob("*.js")):
        if re.search(r"\.(inner|outer)HTML\s*=|insertAdjacentHTML|document\.write\(",
                     path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == []
