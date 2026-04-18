"""Regression snapshot tests for generate_elements().

Locks in current behavior on empty / seeded / filtered / depth-limited graphs so
later optimizations cannot silently change the rendered element list.
"""

import pytest
from callbacks import generate_elements
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD, EDGE_HELPS


def _make_node(name, **kw):
    defaults = dict(
        name=name, type="Learn", description="", value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


def _seed_graph():
    """5 nodes + 4 edges including a bidirectional (Helps) pair to exercise cycles."""
    mgr = GraphManager()
    for n in ("A", "B", "C", "D", "E"):
        mgr.add_node(_make_node(n))
    mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
    mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
    mgr.add_edge("C", "D", EDGE_HELPS)
    mgr.add_edge("D", "C", EDGE_HELPS)  # bidirectional pair with C
    return mgr


def _signature(elements):
    """Stable, comparable summary: (id, sorted tuple of a few data keys) per element."""
    sig = []
    for el in elements:
        data = el.get("data", {})
        if "source" in data:
            sig.append(("edge", data["id"], data["source"], data["target"], data["type"]))
        else:
            sig.append(("node", data["id"]))
    sig.sort()
    return sig


def test_generate_elements_empty_db_returns_list():
    result = generate_elements()
    assert isinstance(result, list)
    assert result == []


def test_generate_elements_with_seeded_graph_stable_order():
    _seed_graph()
    first = generate_elements()
    second = generate_elements()
    assert _signature(first) == _signature(second)


def test_generate_elements_node_and_edge_counts():
    _seed_graph()
    elements = generate_elements()
    nodes = [e for e in elements if "source" not in e.get("data", {})]
    edges = [e for e in elements if "source" in e.get("data", {})]
    assert len(nodes) == 5
    assert len(edges) == 4


def test_generate_elements_includes_bidirectional_edges():
    _seed_graph()
    elements = generate_elements()
    edge_pairs = {(e["data"]["source"], e["data"]["target"], e["data"]["type"])
                  for e in elements if "source" in e.get("data", {})}
    assert ("C", "D", EDGE_HELPS) in edge_pairs
    assert ("D", "C", EDGE_HELPS) in edge_pairs


def test_generate_elements_filters_by_context():
    mgr = GraphManager()
    mgr.add_node(_make_node("Mind1", context="Mind"))
    mgr.add_node(_make_node("Body1", context="Body"))
    mgr.add_node(_make_node("Mind2", context="Mind"))
    filtered = generate_elements(filters={"context_subcontext_union": [("Body", None)]})
    names = {e["data"]["id"] for e in filtered if "source" not in e.get("data", {})}
    assert names == {"Body1"}


def test_generate_elements_max_depth_bfs_around_active_node():
    mgr = _seed_graph()
    # Additional edge B->E so we can check depth bounds
    mgr.add_edge("B", "E", EDGE_NEEDS_HARD)
    elements = generate_elements(active_node_id="A", max_depth=1)
    node_ids = {e["data"]["id"] for e in elements if "source" not in e.get("data", {})}
    # At depth 1 from A over the undirected view: A, B (A->B edge) only
    assert "A" in node_ids
    assert "B" in node_ids
    assert "C" not in node_ids
    assert "D" not in node_ids
    assert "E" not in node_ids


def test_generate_elements_max_depth_zero_returns_all():
    _seed_graph()
    all_elements = generate_elements()
    depth_zero = generate_elements(active_node_id="A", max_depth=0)
    assert _signature(all_elements) == _signature(depth_zero)


def test_generate_elements_neighbor_links_false_hides_non_touching_edges():
    _seed_graph()
    elements = generate_elements(active_node_id="A", neighbor_links=False)
    edge_pairs = [(e["data"]["source"], e["data"]["target"])
                  for e in elements if "source" in e.get("data", {})]
    # Only edges touching "A" should remain
    assert all("A" in (s, t) for s, t in edge_pairs)


def test_generate_elements_active_node_marked_selected():
    _seed_graph()
    elements = generate_elements(active_node_id="B")
    by_id = {e["data"]["id"]: e for e in elements if "source" not in e.get("data", {})}
    assert by_id["B"].get("selected") is True
    assert by_id["A"].get("selected") in (False, None)


def test_generate_elements_core_engine_callback_registered_once():
    """Drift guard: renames or duplicate registration of core_engine will surface here."""
    import dash
    from callbacks import register_callbacks
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)
    qualnames = []
    for entry in app.callback_map.values():
        cb = entry.get("callback")
        while cb is not None and hasattr(cb, "__wrapped__"):
            cb = cb.__wrapped__
        if cb is not None:
            qualnames.append(getattr(cb, "__qualname__", ""))
    core_engine_hits = [q for q in qualnames if q.endswith("core_engine")]
    assert len(core_engine_hits) == 1, f"expected exactly one core_engine registration, got {core_engine_hits}"
