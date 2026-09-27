"""A new user's first minutes: whether to welcome them, and the Getting Started
steps on the Home tab.

The steps read the graph rather than tracking clicks, so they tick themselves
off however the user gets there, and an imported graph arrives with them done.
A step once done stays done: finishing a Now node, say, clears its Now flag.
"""
from dataclasses import dataclass

from config import ConfigManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_DONE


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    hint: str
    done: bool


def should_welcome() -> bool:
    """A first launch: nothing in the graph, and the welcome not yet seen.

    Someone upgrading with a graph already has never seen it either, and
    doesn't need it.
    """
    if ConfigManager.get_welcome_done():
        return False
    import database
    conn = database.get_connection()
    try:
        return conn.execute("SELECT 1 FROM Nodes LIMIT 1").fetchone() is None
    finally:
        conn.close()


def getting_started(manager) -> list:
    steps = _steps_now(manager)
    seen = set(ConfigManager.get_getting_started_progress())
    reached = {step.key for step in steps if step.done}
    if not reached <= seen:
        ConfigManager.set_getting_started_progress(seen | reached)
    return [Step(s.key, s.label, s.hint, s.done or s.key in seen) for s in steps]


def _steps_now(manager) -> list:
    nodes = manager.get_all_nodes()
    edges = manager.get_edges()
    return [
        Step("goal", "Add a goal",
             "An area you're working on, like Sleep or Strength. Open the node "
             "editor (the first icon at the top left), choose the Goal type, "
             "and pick the context it belongs to.",
             any(n.type == "Goal" for n in nodes)),
        Step("connect", "Add what leads to it, and connect them",
             "Add a few things to learn or do, and give the goal a Needs "
             "relationship to each: the goal then waits on them.",
             any(e["type"] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) for e in edges)),
        Step("now", "Pick something to work on now",
             "Right-click a node and choose Now. Now nodes sit at the top of Home.",
             any(getattr(n, "now", 0) for n in nodes)),
        Step("done", "Mark something Done",
             "Finishing a node unblocks what depends on it, and the "
             "recommendations below move on.",
             any(n.status == STATUS_DONE for n in nodes)),
    ]
