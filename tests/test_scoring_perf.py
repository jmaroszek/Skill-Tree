"""Tests for scoring algorithm performance instrumentation.

Covers: the ConfigManager on/off flag, the time_phases option on
score_nodes, the gate in calculate_priority_scores, and the rolling
perf.log writer.
"""
from datetime import datetime
from pathlib import Path

import pytest

import perf
from config import ConfigManager
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD
from scoring import score_nodes


@pytest.fixture(autouse=True)
def tmp_perf_log(monkeypatch, tmp_path):
    """Redirect perf.log writes to a per-test temp file, and reset the
    class-level startup-gate so each test starts as if the process just
    booted (otherwise earlier tests that record a startup run leave the
    flag True and later tests wouldn't record anything)."""
    monkeypatch.setattr(perf, "_LOG_PATH", tmp_path / "perf.log")
    GraphManager._startup_perf_recorded = False
    GraphManager._last_perf_timings = None


def _make_node(name, **overrides):
    defaults = dict(
        name=name, type="Learn", description="", value=5,
        time_o=1.0, time_m=2.0, time_p=5.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


def _small_graph():
    # Three nodes: A -> B (hard), A -> C (hard). All Open.
    nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
    edges = [
        {"source": "A", "target": "B", "type": EDGE_NEEDS_HARD},
        {"source": "A", "target": "C", "type": EDGE_NEEDS_HARD},
    ]
    return nodes, edges


HYPERS = {
    'w_v': 1.0, 'w_i': 1.0, 'd_H': 0.6, 'd_S': 0.25,
    'd_Syn_pair': 0.10, 'd_Syn_mul': 0.40,
    'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85, 'goal_boost': 1.5,
}


# ---------------------------------------------------------------------------
# ConfigManager round-trip
# ---------------------------------------------------------------------------

def test_config_roundtrip():
    assert ConfigManager.get_show_scoring_perf() is True  # default
    ConfigManager.set_show_scoring_perf(False)
    assert ConfigManager.get_show_scoring_perf() is False
    ConfigManager.set_show_scoring_perf(True)
    assert ConfigManager.get_show_scoring_perf() is True


# ---------------------------------------------------------------------------
# score_nodes: return-shape and invariance
# ---------------------------------------------------------------------------

def test_score_nodes_returns_list_when_time_phases_false():
    nodes, edges = _small_graph()
    result = score_nodes(nodes, nodes, edges, HYPERS)
    assert isinstance(result, list)
    assert not isinstance(result, tuple)


def test_score_nodes_returns_timings_when_time_phases_true():
    nodes, edges = _small_graph()
    result = score_nodes(nodes, nodes, edges, HYPERS, time_phases=True)
    assert isinstance(result, tuple)
    assert len(result) == 2
    ranked, t = result
    assert isinstance(ranked, list)
    assert set(t.keys()) == {
        'adj_ms', 'goals_ms', 'score_ms', 'rank_ms', 'total_ms',
        'n_nodes', 'n_edges'
    }
    for k in ('adj_ms', 'goals_ms', 'score_ms', 'rank_ms', 'total_ms'):
        assert isinstance(t[k], float) and t[k] >= 0.0
    assert isinstance(t['n_nodes'], int) and t['n_nodes'] == len(ranked)
    assert isinstance(t['n_edges'], int) and t['n_edges'] >= 0


def test_score_nodes_output_unchanged_when_timed():
    """The invariant: adding timing must not change results."""
    nodes_a, edges = _small_graph()
    nodes_b = [_make_node(n.name) for n in nodes_a]  # fresh instances
    out_fast = score_nodes(nodes_a, nodes_a, edges, HYPERS)
    out_timed, _ = score_nodes(nodes_b, nodes_b, edges, HYPERS, time_phases=True)
    assert [n.name for n in out_fast] == [n.name for n in out_timed]
    fast_scores = {n.name: n.priority_score for n in out_fast}
    timed_scores = {n.name: n.priority_score for n in out_timed}
    assert fast_scores == timed_scores


# ---------------------------------------------------------------------------
# calculate_priority_scores: gating behavior
# ---------------------------------------------------------------------------

def _populate_manager_with_small_graph():
    m = GraphManager()
    nodes, edges = _small_graph()
    for n in nodes:
        m.add_node(n)
    for e in edges:
        m.add_edge(e["source"], e["target"], e["type"])
    return m, nodes


def test_calculate_priority_scores_no_log_when_off():
    ConfigManager.set_show_scoring_perf(False)
    m, nodes = _populate_manager_with_small_graph()
    result = m.calculate_priority_scores(nodes)
    assert isinstance(result, list)
    assert not isinstance(result, tuple)
    assert not perf._LOG_PATH.exists()


def test_calculate_priority_scores_logs_when_on():
    ConfigManager.set_show_scoring_perf(True)
    m, nodes = _populate_manager_with_small_graph()
    result = m.calculate_priority_scores(nodes)
    assert isinstance(result, list)
    assert perf._LOG_PATH.exists()

    content = perf._LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    fields = [f.strip() for f in content[0].split("|")]
    assert len(fields) == 8
    # Parseable timestamp
    datetime.strptime(fields[0], "%Y-%m-%dT%H:%M:%SZ")
    # n_nodes, n_edges are ints
    int(fields[1])
    int(fields[2])
    # Numerics are floats
    total_ms, adj_ms, goals_ms, score_ms, rank_ms = [float(x) for x in fields[3:]]
    assert total_ms >= 0
    assert adj_ms + goals_ms + score_ms + rank_ms <= total_ms + 2.0  # tolerance


def test_last_perf_timings_stashed():
    ConfigManager.set_show_scoring_perf(True)
    m, nodes = _populate_manager_with_small_graph()
    GraphManager._last_perf_timings = None
    m.calculate_priority_scores(nodes)
    t = GraphManager._last_perf_timings
    assert isinstance(t, dict)
    assert set(t.keys()) == {
        'adj_ms', 'goals_ms', 'score_ms', 'rank_ms', 'total_ms',
        'n_nodes', 'n_edges'
    }


def test_zero_overhead_path_returns_list():
    """With setting off, calculate_priority_scores must return plain list."""
    ConfigManager.set_show_scoring_perf(False)
    m, nodes = _populate_manager_with_small_graph()
    result = m.calculate_priority_scores(nodes)
    assert type(result) is list


def test_only_startup_run_logs():
    """Setting on: first scoring run logs once, subsequent runs skip logging."""
    ConfigManager.set_show_scoring_perf(True)
    m, nodes = _populate_manager_with_small_graph()
    m.calculate_priority_scores(nodes)
    assert perf._LOG_PATH.exists()
    size_after_first = perf._LOG_PATH.stat().st_size
    assert size_after_first > 0

    # Several more runs must not touch the log.
    for _ in range(5):
        m.calculate_priority_scores(nodes)
    assert perf._LOG_PATH.stat().st_size == size_after_first


def test_startup_flag_set_after_first_recorded_run():
    ConfigManager.set_show_scoring_perf(True)
    m, nodes = _populate_manager_with_small_graph()
    assert GraphManager._startup_perf_recorded is False
    m.calculate_priority_scores(nodes)
    assert GraphManager._startup_perf_recorded is True


def test_subsequent_runs_return_plain_list():
    """After startup is recorded, even with setting on, return path is fast."""
    ConfigManager.set_show_scoring_perf(True)
    m, nodes = _populate_manager_with_small_graph()
    m.calculate_priority_scores(nodes)  # startup
    result = m.calculate_priority_scores(nodes)
    assert type(result) is list


# ---------------------------------------------------------------------------
# Rolling log rotation
# ---------------------------------------------------------------------------

def test_log_rotation_trims():
    # Pre-fill well past the byte threshold (_MAX_LINES * 120 bytes).
    # Pad each line to 120 bytes so a single pre-fill pass exceeds it.
    perf._LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    base = "2026-01-01T00:00:00Z | 67 | 10.00 | 1.00 | 5.00 | 3.00 | 1.00"
    padding_line = base + (" " * (120 - len(base) - 1)) + "\n"  # 120 bytes
    assert len(padding_line.encode("utf-8")) == 120
    with perf._LOG_PATH.open("w", encoding="utf-8") as f:
        for _ in range(perf._MAX_LINES + 50):
            f.write(padding_line)

    perf.append_perf_log({
        'adj_ms': 1.0, 'goals_ms': 5.0, 'score_ms': 3.0,
        'rank_ms': 1.0, 'total_ms': 10.0, 'n_nodes': 67, 'n_edges': 80,
    })

    line_count = sum(1 for _ in perf._LOG_PATH.open("r", encoding="utf-8"))
    # After trim we keep _MAX_LINES // 2 of the old lines, then write one new line.
    assert line_count <= perf._MAX_LINES // 2 + 1
