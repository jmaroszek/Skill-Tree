"""Export, import and restore (P2.4, P2.5)."""
import json
import sqlite3

import pytest

import backup
import data_transfer
import database
from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from graph_state import revisions
from models import Event, Node, EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_DONE
from resource_links import save_node_links

# Written around the Resource sections new databases used to start with.
pytestmark = pytest.mark.usefixtures("legacy_resource_sections")


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description=f"about {name}", value=6,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=7, difficulty=3,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _rich_graph():
    """A graph that puts rows in every exported table."""
    manager = GraphManager()
    manager.add_node(_node("Sleep", type="Goal"))
    manager.add_node(_node("Rest", now=1))
    manager.add_node(_node("Nap"))
    manager.add_node(_node("Dream", subcontext="Rational"))
    manager.add_edge("Rest", "Sleep", EDGE_NEEDS_HARD)
    manager.add_edge("Nap", "Sleep", EDGE_NEEDS_SOFT)
    manager.add_edge("Nap", "Rest", EDGE_HELPS)
    manager.set_aliases("Rest", ["Recover"])
    save_node_links("Rest", {"website": ["https://example.org/rest"]})
    rest = manager.get_node("Rest")
    rest.status = STATUS_DONE
    manager.update_node(rest)
    events = EventManager()
    events.add_event(Event(name="Winter", trigger_nodes=["Rest"]))
    events.add_node_to_event("Winter", "Dream", delay_days=3)
    ConfigManager.set_priority_goals(["Sleep"])
    ConfigManager.set_contexts(["Mind", "Body"])
    return manager


def _fresh_database(monkeypatch, tmp_path, name="fresh"):
    folder = tmp_path / name
    folder.mkdir()
    path = str(folder / "skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: path)
    database._initialized = False
    database.init_db()
    return path


def _comparable(bundle):
    return {table: rows for table, rows in bundle["tables"].items()}


class TestExportImport:
    def test_a_round_trip_reproduces_every_table(self, monkeypatch, tmp_path):
        _rich_graph()
        exported = data_transfer.export_data()
        assert all(exported["tables"][table] for table in data_transfer.TABLES), (
            "the fixture should exercise every table")

        _fresh_database(monkeypatch, tmp_path)
        counts = data_transfer.import_data(json.loads(json.dumps(exported)))

        assert counts["Nodes"] == 4
        assert _comparable(data_transfer.export_data()) == _comparable(exported)

    def test_the_json_names_its_format_and_versions(self):
        _rich_graph()
        bundle = json.loads(data_transfer.export_json())
        assert bundle["format"] == data_transfer.EXPORT_FORMAT
        assert bundle["schema_version"] == database.SCHEMA_VERSION
        assert bundle["app_version"]

    def test_the_database_file_export_opens_with_the_graph(self, tmp_path):
        _rich_graph()
        copy = tmp_path / "exported.db"
        copy.write_bytes(data_transfer.export_database_bytes())
        conn = sqlite3.connect(copy)
        assert conn.execute("SELECT COUNT(*) FROM Nodes").fetchone()[0] == 4
        conn.close()

    def test_import_needs_an_empty_graph(self):
        bundle = data_transfer.export_data()
        GraphManager().add_node(_node("Existing"))
        with pytest.raises(data_transfer.TransferRefused, match="empty graph"):
            data_transfer.import_data(bundle)

    @pytest.mark.parametrize("bundle, fragment", [
        ({"format": "something-else"}, "isn't a Skill Tree export"),
        ({"format": data_transfer.EXPORT_FORMAT, "version": 1,
          "schema_version": database.SCHEMA_VERSION + 1, "tables": {}}, "newer version"),
        ({"format": data_transfer.EXPORT_FORMAT, "version": 1,
          "schema_version": 1, "tables": {"Nodes": "oops"}}, "malformed"),
    ])
    def test_a_file_it_cant_trust_is_refused(self, bundle, fragment):
        with pytest.raises(data_transfer.TransferRefused, match=fragment):
            data_transfer.import_data(bundle)

    def test_a_bad_row_imports_nothing(self, monkeypatch, tmp_path):
        _rich_graph()
        bundle = data_transfer.export_data()
        # An edge to a node the export doesn't have fails its foreign key.
        bundle["tables"]["Edges"].append(
            {"source": "Rest", "target": "Missing", "type": EDGE_NEEDS_HARD})
        _fresh_database(monkeypatch, tmp_path)
        before = data_transfer.export_data()["tables"]

        with pytest.raises(data_transfer.TransferRefused, match="Nothing was changed"):
            data_transfer.import_data(bundle)

        assert data_transfer.export_data()["tables"] == before


def _row_like(bundle, table, index=0, **changes):
    """A copy of one exported row with some fields changed."""
    return {**bundle["tables"][table][index], **changes}


class TestImportChecksTheGraph:
    """Import holds the rows to the rules the editor checks on every save, so a
    hand-edited or damaged export can't load a graph the app couldn't build."""

    def _refused(self, monkeypatch, tmp_path, change, fragment):
        _rich_graph()
        bundle = data_transfer.export_data()
        change(bundle)
        _fresh_database(monkeypatch, tmp_path)
        before = data_transfer.export_data()["tables"]
        with pytest.raises(data_transfer.TransferRefused, match=fragment) as refused:
            data_transfer.import_data(bundle)
        assert "Nothing was changed" in str(refused.value)
        assert data_transfer.export_data()["tables"] == before
        # Refused before anything was written, the backup included.
        assert backup.list_backups("before-import") == []

    def _edge(self, source, target, kind):
        return {"source": source, "target": target, "type": kind}

    def test_prerequisites_that_loop_are_refused(self, monkeypatch, tmp_path):
        # Rest -> Sleep is in the graph; these two close the loop.
        def loop(bundle):
            bundle["tables"]["Edges"] += [self._edge("Sleep", "Dream", EDGE_NEEDS_HARD),
                                          self._edge("Dream", "Rest", EDGE_NEEDS_SOFT)]
        self._refused(monkeypatch, tmp_path, loop, "loop back")

    def test_two_prerequisites_between_one_pair_are_refused(self, monkeypatch, tmp_path):
        def twice(bundle):
            bundle["tables"]["Edges"].append(self._edge("Rest", "Sleep", EDGE_NEEDS_SOFT))
        self._refused(monkeypatch, tmp_path, twice, "more than one prerequisite")

    @pytest.mark.parametrize("edge, fragment", [
        (("Nap", "Nap", EDGE_HELPS), "related to itself"),
        (("Nap", "Dream", "Blocks"), "unknown type"),
        (("Nap", "Nobody", EDGE_NEEDS_HARD), "doesn't include"),
    ])
    def test_an_impossible_relationship_is_refused(self, monkeypatch, tmp_path, edge, fragment):
        def add(bundle):
            bundle["tables"]["Edges"].append(self._edge(*edge))
        self._refused(monkeypatch, tmp_path, add, fragment)

    @pytest.mark.parametrize("table, changes, fragment", [
        ("Nodes", {"name": "Two\nlines"}, "single line"),
        ("Nodes", {"name": " Padded"}, "start or end with a space"),
        ("Nodes", {"name": "x" * 201}, "201 characters"),
        ("Nodes", {"name": "Extra", "status": "Finished"}, "unknown status"),
        ("Events", {"name": "Tab\there"}, "single line"),
        ("Aliases", {"alias": ""}, "required"),
    ])
    def test_a_name_or_status_the_editor_refuses_is_refused(self, monkeypatch, tmp_path,
                                                            table, changes, fragment):
        def add(bundle):
            bundle["tables"][table].append(_row_like(bundle, table, **changes))
        self._refused(monkeypatch, tmp_path, add, fragment)

    def test_helps_rows_are_put_in_order_not_refused(self, monkeypatch, tmp_path):
        """A rename in the exporting app can leave a Helps row back to front."""
        _rich_graph()
        bundle = data_transfer.export_data()
        edges = bundle["tables"]["Edges"]
        edges[:] = [e for e in edges if e["type"] != EDGE_HELPS]
        edges += [self._edge("Rest", "Nap", EDGE_HELPS), self._edge("Nap", "Rest", EDGE_HELPS)]
        _fresh_database(monkeypatch, tmp_path)

        data_transfer.import_data(bundle)

        helps = [e for e in GraphManager().get_edges() if e["type"] == EDGE_HELPS]
        assert helps == [{"source": "Nap", "target": "Rest", "type": EDGE_HELPS}]


class TestRestore:
    def test_restore_brings_back_the_backed_up_graph(self):
        manager = _rich_graph()
        saved = backup.create_backup("manual")
        before = _comparable(data_transfer.export_data())
        manager.delete_node("Nap")
        manager.add_node(_node("Afterwards"))
        version_before = revisions.graph

        data_transfer.restore_backup(saved)

        assert _comparable(data_transfer.export_data()) == before
        # What it replaced was kept, and caches were told the graph changed.
        (kept,) = backup.list_backups("before-restore")
        conn = sqlite3.connect(kept["path"])
        assert conn.execute("SELECT 1 FROM Nodes WHERE name='Afterwards'").fetchone()
        conn.close()
        assert revisions.graph > version_before

    def test_an_older_backup_is_upgraded_after_restoring(self):
        _rich_graph()
        saved = backup.create_backup("manual")
        conn = sqlite3.connect(saved)
        conn.execute(f"PRAGMA user_version = {database.SCHEMA_VERSION - 1}")
        conn.commit()
        conn.close()

        data_transfer.restore_backup(saved)

        conn = sqlite3.connect(database.get_db_path())
        assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        conn.close()

    def test_a_damaged_backup_is_refused_and_nothing_changes(self, tmp_path):
        _rich_graph()
        before = _comparable(data_transfer.export_data())
        damaged = tmp_path / "damaged.db"
        damaged.write_bytes(b"garbage" * 500)

        with pytest.raises(data_transfer.TransferRefused, match="damaged"):
            data_transfer.restore_backup(damaged)

        assert _comparable(data_transfer.export_data()) == before
        assert backup.list_backups("before-restore") == []

    def test_a_backup_from_a_newer_version_is_refused(self):
        _rich_graph()
        saved = backup.create_backup("manual")
        conn = sqlite3.connect(saved)
        conn.execute(f"PRAGMA user_version = {database.SCHEMA_VERSION + 1}")
        conn.commit()
        conn.close()

        with pytest.raises(data_transfer.TransferRefused, match="newer version"):
            data_transfer.restore_backup(saved)
