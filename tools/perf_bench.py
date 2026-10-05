"""How long the things a user waits on take, on a synthetic graph (P6.6).

    python tools/perf_bench.py [--nodes 1000] [--browser] [--budgets]
                               [--summary FILE]

Builds a graph with perf_graph.py in a throwaway folder, then times:

- in this process, the server's share (median of several runs): the Home
  ranking after an edit and on an unchanged graph, the Nodes canvas payload,
  an editor save, Done and back with a cascade, the launch repair, export,
  a backup, and the time simulation for the goal with the largest prerequisite tree;
- with --browser (needs Playwright, see requirements-e2e.txt), what a person
  sees, in Chromium against a real server: its boot, the first load until the
  startup cover lifts, the first Nodes visit until the canvas is drawn, and
  an editor save until its message shows.

--budgets exits 1 when a timing is over its budget. The budgets are
generous: they catch a regression by a multiple, not noise. --summary appends
the table, as Markdown, to FILE (CI passes $GITHUB_STEP_SUMMARY).
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for folder in (ROOT, TOOLS):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

# Seconds. Roughly ten times what the Linux container that set them took at
# 1,000 nodes (docs/performance.md), and more for what a browser draws, since
# CI's macOS runners are slower still.
BUDGETS = {
    "Home ranking after an edit": 5.0,
    "Home ranking, unchanged graph": 3.0,
    "Nodes canvas payload": 3.0,
    "Editor save": 3.0,
    "Done and back, with a cascade": 5.0,
    "Launch repair": 3.0,
    "Export (JSON)": 3.0,
    "Backup": 5.0,
    "Time simulation, largest goal": 5.0,
    "Server boot to ready": 30.0,
    "First load, cover lifts": 30.0,
    "First Nodes visit, canvas drawn": 30.0,
    "Editor save, click to message": 10.0,
}


def _median(action, repeats):
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def server_timings(db_path, repeats=5):
    """Time the server's share of each interaction, in this process."""
    import database
    database.get_db_path = lambda: str(db_path)
    database._initialized = False
    database.init_db()

    import backup
    import callbacks
    import data_transfer
    import next_view
    import node_commands
    from callback_helpers import format_suggestions_table
    from config import ConfigManager
    from graph_manager import GraphManager
    from models import EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_DONE
    from simulation_service import simulation_service

    manager = GraphManager()
    nodes = {n.name: n for n in manager.get_all_nodes(include_dormant=True)}
    edges = manager.get_edges()
    hard_out, hard_in = {}, {}
    for e in edges:
        if e["type"] == EDGE_NEEDS_HARD:
            hard_out.setdefault(e["source"], []).append(e["target"])
            hard_in.setdefault(e["target"], []).append(e["source"])

    def reach(start, step):
        seen, stack = set(), [start]
        while stack:
            for nxt in step.get(stack.pop(), []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    results = {}

    # An edit bumps the scoring version, so the ranking is computed afresh.
    busiest = max((n for n in nodes.values() if n.type not in ("Goal", "Milestone")),
                  key=lambda n: len(hard_in.get(n.name, [])) + len(hard_out.get(n.name, [])))

    def rank():
        ranked = next_view.get_suggestions({}, 25)
        format_suggestions_table(ranked.rows, manager, pinned_steps=ranked.pinned_steps)

    def rank_after_edit():
        node = manager.get_node(busiest.name)
        node.value = 11 - node.value if 1 <= node.value <= 10 else 5
        manager.update_node(node)
        rank()
    results["Home ranking after an edit"] = _median(rank_after_edit, repeats)
    results["Home ranking, unchanged graph"] = _median(rank, repeats)

    results["Nodes canvas payload"] = _median(lambda: callbacks.generate_elements(), repeats)

    def relations(name):
        pick = lambda kind, end, key: sorted(  # noqa: E731
            e[key] for e in edges if e["type"] == kind and e[end] == name)
        helps = sorted({e["target"] for e in edges if e["type"] == EDGE_HELPS and e["source"] == name}
                       | {e["source"] for e in edges if e["type"] == EDGE_HELPS and e["target"] == name})
        return (pick(EDGE_NEEDS_HARD, "target", "source"), pick(EDGE_NEEDS_SOFT, "target", "source"),
                pick(EDGE_NEEDS_HARD, "source", "target"), pick(EDGE_NEEDS_SOFT, "source", "target"),
                helps)

    def editor_save():
        node = manager.get_node(busiest.name)
        node_commands.handle_save(
            manager, node.name, node.type, node.description + ".", node.value,
            node.time_o, node.time_m, node.time_p, node.interest, node.difficulty,
            [STATUS_DONE] if node.status == STATUS_DONE else [], node.context,
            node.subcontext, None, *relations(node.name))
    results["Editor save"] = _median(editor_save, repeats)

    # The Open node whose completion unblocks the most.
    startable = [n for n in nodes.values() if n.status == "Open" and not n.now
                 and n.type not in ("Goal", "Milestone")]
    lever = max(startable, key=lambda n: len(reach(n.name, hard_out)))

    def done_and_back():
        node_commands.handle_toggle_done(manager, {"id": lever.name})
        node_commands.handle_toggle_done(manager, {"id": lever.name})
    results["Done and back, with a cascade"] = _median(done_and_back, repeats)

    results["Launch repair"] = _median(manager.recompute_all_statuses, repeats)
    results["Export (JSON)"] = _median(data_transfer.export_json, repeats)
    results["Backup"] = _median(lambda: backup.create_backup("manual"), repeats)

    goal = max((n for n in nodes.values() if n.type == "Goal"),
               key=lambda n: len(reach(n.name, hard_in)))
    tree = reach(goal.name, hard_in) | {goal.name}
    fresh = {name: manager.get_node(name) for name in tree}
    sim_edges = [e for e in manager.get_edges()
                 if e["type"] == EDGE_NEEDS_HARD and e["source"] in tree and e["target"] in tree]
    trials = ConfigManager.get_monte_carlo_trials()
    start = time.perf_counter()
    simulation_service.summarize(goal.name, fresh, sim_edges, False, False, trials)
    results["Time simulation, largest goal"] = time.perf_counter() - start
    results["_goal_tree"] = len(tree)
    results["_lever_reach"] = len(reach(lever.name, hard_out))
    return results


def browser_timings(db_path, home):
    """Time what a person sees, in Chromium against a real server."""
    from playwright.sync_api import sync_playwright
    from local_server import Server

    data = Path(home) / "Data"
    data.mkdir(parents=True, exist_ok=True)
    shutil.copy(db_path, data / "sandbox_skilltree.db")
    server = Server(Path(home))
    results = {}
    start = time.perf_counter()
    server.start()
    results["Server boot to ready"] = time.perf_counter() - start
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(server.link)
            page.wait_for_selector("#startup-cover.is-lifted", state="attached", timeout=120000)
            results["First load, cover lifts"] = page.evaluate(
                "performance.getEntriesByName('skill-tree-ready')[0].startTime") / 1000

            start = time.perf_counter()
            page.click("a.nav-link:has-text('Nodes')")
            page.wait_for_selector("#canvas-first-paint-cover.is-lifted", state="attached",
                                   timeout=120000)
            results["First Nodes visit, canvas drawn"] = time.perf_counter() - start

            name = server.query("SELECT name FROM Nodes WHERE type = 'Learn' "
                                "ORDER BY name LIMIT 1")[0][0]
            page.click("#btn-add")
            page.click("#search-node")
            page.wait_for_selector("#search-node[aria-expanded=true]", timeout=10000)
            popover = page.locator(
                f"[id={json.dumps(page.get_attribute('#search-node', 'aria-controls'))}]")
            popover.locator("input.dash-dropdown-search").fill(name)
            popover.locator("[role=option]", has_text=name).first.click()
            page.wait_for_function(
                "name => document.querySelector('#node-name').value === name",
                arg=name, timeout=60000)
            page.wait_for_timeout(1500)
            page.fill("#node-desc", "Timed.")
            start = time.perf_counter()
            page.click("#btn-save")
            page.wait_for_function(
                "document.querySelector('#save-output').innerText.includes('Updated node')",
                timeout=60000)
            results["Editor save, click to message"] = time.perf_counter() - start
            browser.close()
    finally:
        server.stop()
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--budgets", action="store_true")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="skilltree-perf-"))
    os.environ["SKILLTREE_HOME"] = str(work / "bench-home")
    import perf_graph
    db = work / "graph.db"
    counts = perf_graph.build(db, args.nodes)
    pristine = work / "pristine.db"
    shutil.copy(db, pristine)

    results = server_timings(db)
    if args.browser:
        results.update(browser_timings(pristine, work / "browser-home"))

    title = (f"{counts['nodes']} nodes, {counts['edges']} edges; the largest goal has "
             f"{results.pop('_goal_tree') - 1} prerequisites, and completing the busiest "
             f"open node reaches {results.pop('_lever_reach')} nodes")
    lines = [f"### Performance at {args.nodes} nodes", "", title, "",
             "| | Seconds | Budget |", "|---|---:|---:|"]
    over = []
    for label, seconds in results.items():
        budget = BUDGETS.get(label)
        flag = ""
        if budget is not None and seconds > budget:
            over.append(label)
            flag = " **over**"
        lines.append(f"| {label} | {seconds:.3f}{flag} | {budget if budget else ''} |")
    table = "\n".join(lines) + "\n"
    print(table)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as out:
            out.write(table + "\n")
    shutil.rmtree(work, ignore_errors=True)
    if args.budgets and over:
        print("Over budget: " + ", ".join(over))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
