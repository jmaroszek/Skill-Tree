"""Prerequisite chains on the Nodes tab: counted, then listed only as far as shown.

The number of chains ending at a node multiplies with every shared
prerequisite. The top Goal of the 1,000-node benchmark graph had 681, and the
panel drew every one of them: a query per step, a line each, 221 KB sent.
Now the chains of each kind are counted without being listed, the panel
lists the first TRAVERSAL_CHAIN_LIMIT, and says how many more there are.
"""
import random
import time

import pytest
from dash import html

import database
from callback_helpers import TRAVERSAL_CHAIN_LIMIT, format_traversal_ui
from graph_manager import GraphManager
from models import EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_DONE, Node


def _node(name, status="Open"):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status=status,
                context="Mind")


def _graph(names, edges, done=()):
    manager = GraphManager()
    for name in names:
        manager.add_node(_node(name, STATUS_DONE if name in done else "Open"))
    for source, target, kind in edges:
        manager.add_edge(source, target, kind)
    return manager


def _every_chain(manager, target):
    """The chains as the old walk found them: every path, one at a time."""
    statuses = {n.name: n.status for n in manager.get_all_nodes(include_dormant=True)}
    incoming = {}
    for e in manager.get_edges():
        if e["type"] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            incoming.setdefault(e["target"], []).append((e["source"], e["type"]))
    found = []

    def walk(path, soft):
        prereqs = incoming.get(path[-1], [])
        if not prereqs:
            if any(statuses.get(p) != STATUS_DONE for p in path):
                found.append((list(reversed(path)), "Soft" if soft else "Hard"))
            return
        for source, kind in prereqs:
            if source not in path:
                walk(path + [source], soft or kind == EDGE_NEEDS_SOFT)
    walk([target], False)
    return found


@pytest.mark.parametrize("seed", range(12))
def test_the_chains_are_the_ones_an_exhaustive_walk_finds(seed):
    rng = random.Random(seed)
    names = [f"N{i:02d}" for i in range(12)]
    edges = set()
    for _ in range(22):
        a, b = sorted(rng.sample(range(len(names)), 2))
        edges.add((names[a], names[b], rng.choice([EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT])))
    # One prerequisite per pair, as the editor allows.
    pairs = {}
    for source, target, kind in sorted(edges):
        pairs.setdefault((source, target), (source, target, kind))
    manager = _graph(names, pairs.values(), done=set(rng.sample(names, 5)))

    for target in names:
        expected = _every_chain(manager, target)
        found = manager.prerequisite_chains(target)
        assert sorted(map(tuple, found["Hard"])) == sorted(
            tuple(c) for c, kind in expected if kind == "Hard")
        assert sorted(map(tuple, found["Soft"])) == sorted(
            tuple(c) for c, kind in expected if kind == "Soft")
        assert found["totals"] == {
            "Hard": sum(kind == "Hard" for _, kind in expected),
            "Soft": sum(kind == "Soft" for _, kind in expected)}


def _lattice(layers):
    """A target over ``layers`` rows of two nodes, each row needing both
    nodes of the row beneath it: 2**layers chains end at the target."""
    names = ["Target"] + [f"{side}{row}" for row in range(1, layers + 1) for side in "AB"]
    edges = [(f"{side}1", "Target", EDGE_NEEDS_HARD) for side in "AB"]
    edges += [(f"{low}{row + 1}", f"{high}{row}", EDGE_NEEDS_HARD)
              for row in range(1, layers) for low in "AB" for high in "AB"]
    # One soft edge at the bottom, so half the chains are Soft.
    names.append("Soft Root")
    edges.append(("Soft Root", f"A{layers}", EDGE_NEEDS_SOFT))
    return _graph(names, edges)


def test_a_limit_lists_a_few_while_the_totals_count_them_all():
    manager = _lattice(18)
    started = time.perf_counter()
    found = manager.prerequisite_chains("Target", limit=5)
    elapsed = time.perf_counter() - started

    # B18 is a root; A18 needs the soft root, so its chains are Soft.
    assert found["totals"] == {"Hard": 2 ** 17, "Soft": 2 ** 17}
    assert len(found["Hard"]) == 5 and len(found["Soft"]) == 5
    assert all(chain[-1] == "Target" for chain in found["Hard"] + found["Soft"])
    # Listing a quarter of a million chains one by one took minutes.
    assert elapsed < 2.0


def test_chains_come_in_name_order():
    manager = _graph(["Target", "Beta", "Alpha"],
                     [("Beta", "Target", EDGE_NEEDS_HARD),
                      ("Alpha", "Target", EDGE_NEEDS_HARD)])
    assert manager.prerequisite_chains("Target")["Hard"] == [
        ["Alpha", "Target"], ["Beta", "Target"]]


def test_a_cycle_the_editor_would_refuse_doesnt_hang_the_walk():
    manager = _graph(["A", "B", "C"], [("C", "A", EDGE_NEEDS_HARD)])
    with database.get_connection() as conn:   # the loop add_edge refuses
        conn.executemany("INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                         [("A", "B", EDGE_NEEDS_HARD), ("B", "A", EDGE_NEEDS_HARD)])
    found = manager.prerequisite_chains("A")
    assert found["totals"]["Hard"] >= 1


def _texts(component):
    return [child.children for child in component.children]


def test_the_panel_lists_the_first_chains_and_counts_the_rest():
    more = 5
    count = TRAVERSAL_CHAIN_LIMIT + more
    prereqs = [f"Step {i:02d}" for i in range(count)]
    manager = _graph(["Goal", "Helper"] + prereqs,
                     [(p, "Goal", EDGE_NEEDS_HARD) for p in prereqs]
                     + [("Helper", "Goal", EDGE_HELPS)])

    with database.read_snapshot():
        hard, soft, synergies, _description = format_traversal_ui(None, "Goal", manager)

    lines = _texts(hard)
    assert lines[:TRAVERSAL_CHAIN_LIMIT] == prereqs[:TRAVERSAL_CHAIN_LIMIT]
    assert lines[-1] == f"… and {more} more"
    assert len(lines) == TRAVERSAL_CHAIN_LIMIT + 1
    assert isinstance(soft, html.P) and soft.children == "None"
    assert _texts(synergies) == ["Helper"]


def test_a_node_with_no_prerequisites_shows_none():
    manager = _graph(["Alone"], [])
    hard, soft, _synergies, _description = format_traversal_ui({"id": "Alone"}, None, manager)
    assert hard.children == "None" and soft.children == "None"
