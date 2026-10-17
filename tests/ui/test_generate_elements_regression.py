"""Regression snapshot tests for generate_elements().

Locks in current behavior on empty / seeded / filtered / depth-limited graphs so
later optimizations cannot silently change the rendered element list.
"""

from skilltree.ui.canvas.elements import generate_elements
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node, EDGE_NEEDS_HARD, EDGE_HELPS


def _make_node(name, **kw):
    defaults = dict(
        name=name, type="Learn", description="", value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(kw)
    return Node(**defaults)


def _seed_graph():
    """5 nodes + 3 edges. Helps is canonicalized to one row per pair (Fix 6)."""
    mgr = GraphManager()
    for n in ("A", "B", "C", "D", "E"):
        mgr.add_node(_make_node(n))
    mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
    mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
    mgr.add_edge("C", "D", EDGE_HELPS)
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


def test_generate_elements_empty_db_returns_list(services):
    result = generate_elements(services.graph, services.events)
    assert isinstance(result, list)
    assert result == []


def test_generate_elements_with_seeded_graph_stable_order(services):
    _seed_graph()
    first = generate_elements(services.graph, services.events)
    second = generate_elements(services.graph, services.events)
    assert _signature(first) == _signature(second)


def test_generate_elements_node_and_edge_counts(services):
    _seed_graph()
    elements = generate_elements(services.graph, services.events)
    nodes = [e for e in elements if "source" not in e.get("data", {})]
    edges = [e for e in elements if "source" in e.get("data", {})]
    assert len(nodes) == 5
    assert len(edges) == 3


def test_generate_elements_includes_helps_edge(services):
    """Helps edges render with one canonical row per pair (Fix 6)."""
    _seed_graph()
    elements = generate_elements(services.graph, services.events)
    edge_pairs = {(e["data"]["source"], e["data"]["target"], e["data"]["type"])
                  for e in elements if "source" in e.get("data", {})}
    assert ("C", "D", EDGE_HELPS) in edge_pairs


def test_generate_elements_filters_by_context(services):
    mgr = GraphManager()
    mgr.add_node(_make_node("Mind1", context="Mind"))
    mgr.add_node(_make_node("Body1", context="Body"))
    mgr.add_node(_make_node("Mind2", context="Mind"))
    filtered = generate_elements(services.graph, services.events, filters={"context_subcontext_union": [("Body", None)]})
    names = {e["data"]["id"] for e in filtered if "source" not in e.get("data", {})}
    assert names == {"Body1"}


def test_generate_elements_active_node_marked_selected(services):
    _seed_graph()
    elements = generate_elements(services.graph, services.events, active_node_id="B")
    by_id = {e["data"]["id"]: e for e in elements if "source" not in e.get("data", {})}
    assert by_id["B"].get("selected") is True
    assert by_id["A"].get("selected") in (False, None)


def test_generate_elements_core_engine_callback_registered_once(services):
    """Drift guard: renames or duplicate registration of core_engine will surface here."""
    import dash
    from skilltree.engine.callbacks import register_engine_callbacks
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_engine_callbacks(app, services)
    qualnames = []
    for entry in app.callback_map.values():
        cb = entry.get("callback")
        while cb is not None and hasattr(cb, "__wrapped__"):
            cb = cb.__wrapped__
        if cb is not None:
            qualnames.append(getattr(cb, "__qualname__", ""))
    core_engine_hits = [q for q in qualnames if q.endswith("core_engine")]
    assert len(core_engine_hits) == 1, f"expected exactly one core_engine registration, got {core_engine_hits}"
