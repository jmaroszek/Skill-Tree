"""Bound database work per read operation without leaking stale/shared state."""
import sqlite3

import pytest

import database
from callback_helpers import format_suggestions_table
from config import ConfigManager
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD as HARD
from test_atomic_saves import graph, node


def test_next_rows_use_one_connection_and_one_settings_read(monkeypatch):
    m = graph(*(f"N{i}" for i in range(25)))
    nodes = m.get_all_nodes()
    for n in nodes:
        n.priority_score = 1.0
    opened, statements = [], []
    original = database.get_connection
    def traced():
        conn = original()
        opened.append(conn)
        conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(database, "get_connection", traced)
    format_suggestions_table(nodes, m)
    assert len(opened) == 1
    assert sum("FROM Settings" in sql for sql in statements) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_snapshot_is_detached_and_node_objects_are_not_shared():
    m = graph("A")
    with database.read_snapshot():
        a = m.get_node("A")
        a.value = 99
        assert m.get_node("A").value == 5
        edges = m.get_edges()
        edges.append(dict(source="A", target="Missing", type=HARD))
        assert m.get_edges() == []
    assert database.current_snapshot() is None


def test_now_snapshot_materializes_only_awake_now_nodes_and_detaches_links(monkeypatch):
    from models import Node

    m = graph(*(f'N{i}' for i in range(30)))
    m.add_node(node('First', now=1, resource_links={'links': ['https://example.com']}))
    m.add_node(node('Second', now=2))
    m.add_node(node('Sleeping', now=1, dormant=1))
    built = []
    original = Node.__post_init__

    def track(instance):
        built.append(instance.name)
        original(instance)

    monkeypatch.setattr(Node, '__post_init__', track)
    with database.read_snapshot():
        now = m.get_now_nodes()
        assert [n.name for n in now] == ['First', 'Second']
        assert built == ['First', 'Second']
        now[0].resource_links['links'].append('https://example.com/changed')
        now[0].now = 9
        fresh = m.get_now_nodes()
        assert fresh[0].now == 1
        assert fresh[0].resource_links == {'links': ['https://example.com']}
        assert built == ['First', 'Second']


def test_snapshot_normalizes_rows_once_and_keeps_templates_private(monkeypatch):
    from models import Node

    m = graph('A', 'B')
    built = []
    original = Node.__post_init__

    def track(instance):
        built.append(instance.name)
        original(instance)

    monkeypatch.setattr(Node, '__post_init__', track)
    with database.read_snapshot():
        first = m.get_all_nodes()
        first[0].value = 99
        first[0].total_value = 100
        first[0].variety = {'divisor': 9}
        second = GraphManager().get_all_nodes()
        assert second[0] is not first[0]
        assert second[0].value == 5
        assert not hasattr(second[0], 'total_value')
        assert not hasattr(second[0], 'variety')
        assert m.get_node('A').value == 5
        assert built == ['A', 'B']
    with database.read_snapshot():
        assert m.get_node('A').value == 5
        assert built == ['A', 'B', 'A']


def test_write_invalidates_snapshot_and_next_read_sees_new_values():
    m = graph("A")
    with database.read_snapshot():
        assert m.get_node("A").value == 5
        a = m.get_node("A")
        a.value = 8
        m.update_node(a)
        assert m.get_node("A").value == 8
        ConfigManager.set_time_settings({'hours_per_week': 20})
        assert ConfigManager.get_time_settings()['hours_per_week'] == 20
    with database.read_snapshot():
        assert m.get_node("A").value == 8


def test_inherited_times_and_completion_use_snapshot_without_per_node_queries(monkeypatch):
    m = graph(*(f"N{i}" for i in range(40)))
    m.add_node(node("Goal", type="Goal"))
    with database.transaction():
        for i in range(40):
            m.add_edge(f"N{i}", "Goal", HARD)
    expected = sum(n.time for n in m.get_all_nodes())
    original, calls = database.get_connection, []
    def tracked():
        calls.append(True)
        return original()
    monkeypatch.setattr(database, "get_connection", tracked)
    with database.read_snapshot():
        assert m.get_effective_time("Goal") == round(expected, 2)
        assert m.get_goal_completion("Goal")['total'] == 40
        assert len(m.get_dependency_view("Goal", filters={})['node_names']) == 41
    assert len(calls) == 1


def test_connections_close_on_success_and_failure():
    for fail in (False, True):
        conn = database.get_connection()
        try:
            with conn:
                conn.execute("SELECT 1")
                if fail:
                    raise ValueError("read failed")
        except ValueError:
            pass
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_community_cache_is_bounded_and_discards_old_versions():
    m = GraphManager()
    for i in range(40):
        m.add_node(node(f"N{i}", context=f"C{i}"))
    for i in range(40):
        m.detect_communities(filters={'context': [f"C{i}"]})
    assert len(m._community_cache) <= 32
    for _ in range(20):
        m._bump_version(scoring=False)
        m.detect_communities()
        assert len(m._community_cache) == 1


def test_subtree_cache_is_bounded():
    m = graph("A")
    for i in range(160):
        m.get_goal_subtree(f"Absent{i}")
    assert len(m._goal_subtree_cache) <= 128


def test_snapshot_scope_is_released_after_exception():
    graph("A")
    with pytest.raises(ValueError):
        with database.read_snapshot():
            raise ValueError("render failed")
    assert database.current_snapshot() is None
