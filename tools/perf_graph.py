"""A synthetic graph for performance checks (P6.6).

Builds a graph of realistic shape with the app's own code, so every row is
one the app itself could have written:
- goals fed by prerequisite subtrees, and a few milestones
- Needs chains with some fan-in, soft prerequisites, and Helps links, mostly
  within a node's own context (area of life), as in a real graph
- some of the work finished, in prerequisite order
- a few Now nodes, three priority goals, and events with sleeping nodes
- aliases, and descriptions of ordinary length

    python tools/perf_graph.py OUT.db [--nodes 1000] [--seed 7]

It writes OUT.db and nothing else, and refuses an OUT.db that exists. To open
it in the app, copy it to <SKILLTREE_HOME>/Data/sandbox_skilltree.db and run
the app with --sandbox and that SKILLTREE_HOME.
"""
import argparse
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOPICS = [
    "Sleep", "Statistics", "Guitar", "Budgeting", "Running", "Spanish", "Cooking",
    "Writing", "Linear Algebra", "Negotiation", "Meditation", "Python", "Drawing",
    "Nutrition", "History", "Chess", "Public Speaking", "Investing", "Chemistry",
    "Photography", "Carpentry", "Poetry", "Economics", "Swimming", "Philosophy",
]
DESCRIPTION = ("Notes on what this covers, why it matters, and where to start. "
               "Long enough to look like something a person wrote.")


def build(path, nodes=1000, seed=7):
    """Write a synthetic graph of about ``nodes`` nodes to a new database at
    ``path``. Returns counts of what it wrote."""
    # Anything else the app writes along the way (a log, a backup) goes to a
    # throwaway folder, never to the real data folder.
    os.environ.setdefault("SKILLTREE_HOME", tempfile.mkdtemp(prefix="skilltree-perf-"))
    import database
    database.get_db_path = lambda: str(path)
    database._initialized = False
    database.init_db()

    from config import ConfigManager, DEFAULT_CONTEXTS, DEFAULT_SUBCONTEXTS
    from event_manager import EventManager
    from graph_manager import GraphManager
    from models import (EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Event, Node,
                        STATUS_DONE, STATUS_OPEN)

    rng = random.Random(seed)
    manager = GraphManager()
    events = EventManager()
    goal_count = max(5, nodes // 40)
    milestone_count = max(2, nodes // 100)
    work_count = nodes - goal_count - milestone_count
    hard_prereqs = {}          # name -> set of hard prerequisites
    directional = set()        # pairs with a Needs edge: a pair takes only one
    helps = set()

    def node(name, node_type, context, **fields):
        likely = rng.choice([0.5, 1, 2, 3, 5, 8, 13, 20, 40])
        values = dict(
            name=name, type=node_type, description=DESCRIPTION,
            value=rng.randint(1, 10), time_o=likely / 2, time_m=likely,
            time_p=likely * rng.choice([1.5, 2, 3]), interest=rng.randint(1, 10),
            difficulty=rng.randint(1, 10), status=STATUS_OPEN, context=context,
            subcontext=rng.choice(DEFAULT_SUBCONTEXTS[context] + [None]))
        values.update(fields)
        return Node(**values)

    def link(source, target, edge_type):
        # Every write here must be one the app accepts: a refused write inside
        # the transaction rolls the whole build back. Needs edges only run
        # from earlier work to later work, or into goals and milestones, so
        # they never close a cycle; what's left is a pair's second edge.
        pair = frozenset((source, target))
        seen = helps if edge_type == EDGE_HELPS else directional
        if pair in seen:
            return
        seen.add(pair)
        manager.add_edge(source, target, edge_type)
        if edge_type == EDGE_NEEDS_HARD:
            hard_prereqs.setdefault(target, set()).add(source)

    with database.transaction():
        ConfigManager.set_contexts(list(DEFAULT_CONTEXTS))
        ConfigManager.set_subcontexts({k: list(v) for k, v in DEFAULT_SUBCONTEXTS.items()})
        ConfigManager.set_welcome_done(True)

        work = []
        by_context = {context: [] for context in DEFAULT_CONTEXTS}
        work_types = ["Learn"] * 45 + ["Action"] * 35 + ["Resource"] * 20

        def earlier(context, local, recent=None):
            """Earlier work to link from: usually the same context's, else
            anyone's; with ``recent``, only that many of the latest."""
            pool = by_context[context] if rng.random() < local else work
            return pool[-recent:] if recent else pool

        for i in range(work_count):
            name = f"{rng.choice(TOPICS)} {i + 1}"
            context = rng.choice(DEFAULT_CONTEXTS)
            manager.add_node(node(name, rng.choice(work_types), context))
            # Earlier nodes lead to later ones, mostly recent ones, which makes
            # chains; sometimes several at once, which makes fan-in.
            if work and rng.random() < 0.55:
                pool = earlier(context, 0.85, recent=25)
                for source in rng.sample(pool, min(len(pool), rng.choice([1, 1, 1, 2, 2, 3]))):
                    link(source, name, EDGE_NEEDS_HARD)
            if work and rng.random() < 0.35:
                pool = earlier(context, 0.7)
                for source in rng.sample(pool, min(len(pool), rng.choice([1, 2]))):
                    link(source, name, EDGE_NEEDS_SOFT)
            if work and rng.random() < 0.08:
                pool = earlier(context, 0.5)
                if pool:
                    link(name, rng.choice(pool), EDGE_HELPS)
            work.append(name)
            by_context[context].append(name)

        goals = []
        for g in range(goal_count):
            name = f"Goal {g + 1}: {rng.choice(TOPICS)}"
            context = DEFAULT_CONTEXTS[g % len(DEFAULT_CONTEXTS)]
            manager.add_node(node(name, "Goal", context, value=rng.randint(7, 10),
                                  time_mode="inherited"))
            goals.append(name)
            for source in rng.sample(earlier(context, 0.8), rng.randint(5, 15)):
                link(source, name, EDGE_NEEDS_HARD)
            for source in rng.sample(earlier(context, 0.8), rng.randint(0, 5)):
                link(source, name, EDGE_NEEDS_SOFT)
        for m in range(milestone_count):
            name = f"Milestone {m + 1}"
            context = rng.choice(DEFAULT_CONTEXTS)
            manager.add_node(node(name, "Milestone", context, time_mode="inherited",
                                  value_mode="inherited"))
            for source in rng.sample(earlier(context, 0.8), rng.randint(2, 5)):
                link(source, name, EDGE_NEEDS_HARD)

        # Finish some of the work, prerequisites first.
        done = set()
        for name in work:
            if rng.random() < 0.3 and hard_prereqs.get(name, set()) <= done:
                finished = manager.get_node(name)
                finished.status = STATUS_DONE
                manager.update_node(finished)
                done.add(name)

        startable = [n for n in work
                     if n not in done and hard_prereqs.get(n, set()) <= done]
        rng.shuffle(startable)
        now = set(startable[:8])
        for name in now:
            current = manager.get_node(name)
            current.now = 1
            manager.update_node(current)
        ConfigManager.set_priority_goals(goals[:3])

        sleepers = [n for n in work if n not in done and n not in now][-15:]
        for e in range(3):
            event = f"Event {e + 1}"
            events.add_event(Event(name=event))
            for name in sleepers[e * 5:(e + 1) * 5]:
                events.add_node_to_event(event, name)

        for name in rng.sample(work, max(1, work_count // 20)):
            manager.set_aliases(name, [f"{name} (alias)"])

    counts = {"nodes": len(manager.get_all_nodes(include_dormant=True)),
              "edges": len(manager.get_edges()), "goals": goal_count,
              "done": len(done), "now": len(now)}
    if (counts["nodes"], counts["edges"]) != (work_count + goal_count + milestone_count,
                                              len(directional) + len(helps)):
        raise RuntimeError(f"the database doesn't hold what was built: {counts}")
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} exists; choose a new path")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    counts = build(args.out.resolve(), args.nodes, args.seed)
    print(", ".join(f"{v} {k}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
