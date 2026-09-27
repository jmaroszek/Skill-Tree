"""Rules the graph enforces itself, whatever path a change takes (found by P6.1).

- A non-Goal node can't be Done while a hard prerequisite isn't. The Toggle
  Done menu and the editor used to allow it, and the next launch's repair
  quietly put the node back to Blocked, undoing what the user did.
- Names are unique ignoring case (P1.1's rule) in add_node and rename_node
  too, not only in the editor. A rename onto an existing name used to surface
  SQLite's raw "UNIQUE constraint failed".
"""
import pytest

import node_commands
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_BLOCKED, STATUS_DONE, Node


def _node(name, node_type="Learn", **overrides):
    fields = dict(name=name, type=node_type, description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                  context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def chain():
    """Theory unlocks Practice, which unlocks Mastery (all Needs_Hard)."""
    manager = GraphManager()
    for name in ("Theory", "Practice", "Mastery"):
        manager.add_node(_node(name))
    manager.add_edge("Theory", "Practice", EDGE_NEEDS_HARD)
    manager.add_edge("Practice", "Mastery", EDGE_NEEDS_HARD)
    return manager


# --- Done waits for hard prerequisites ------------------------------------

def test_a_blocked_node_cant_be_toggled_done(chain):
    assert chain.get_node("Practice").status == STATUS_BLOCKED
    with pytest.raises(ValueError, match="Theory"):
        node_commands.handle_toggle_done(chain, {"id": "Practice"})
    practice = chain.get_node("Practice")
    assert practice.status == STATUS_BLOCKED and practice.done_date is None
    assert chain.recompute_all_statuses() == 0


def test_once_the_prerequisite_is_done_it_can_be(chain):
    node_commands.handle_toggle_done(chain, {"id": "Theory"})
    node_commands.handle_toggle_done(chain, {"id": "Practice"})
    assert chain.get_node("Practice").status == STATUS_DONE
    assert chain.recompute_all_statuses() == 0


def test_soft_prerequisites_never_block_completion():
    manager = GraphManager()
    manager.add_node(_node("Warmup"))
    manager.add_node(_node("Run"))
    manager.add_edge("Warmup", "Run", EDGE_NEEDS_SOFT)
    node_commands.handle_toggle_done(manager, {"id": "Run"})
    assert manager.get_node("Run").status == STATUS_DONE


def test_a_goal_is_the_users_to_complete(chain):
    """Goals keep user-controlled status (recompute_all_statuses leaves them)."""
    chain.add_node(_node("Craft", "Goal"))
    chain.add_edge("Mastery", "Craft", EDGE_NEEDS_HARD)
    node_commands.handle_toggle_done(chain, {"id": "Craft"})
    assert chain.get_node("Craft").status == STATUS_DONE
    assert chain.recompute_all_statuses() == 0


def test_completing_a_whole_chain_at_once_works_in_any_order(chain):
    order = chain.completion_order(["Mastery", "Theory", "Practice"])
    assert order == ["Theory", "Practice", "Mastery"]
    # Unrelated names keep their places.
    chain.add_node(_node("Aside"))
    assert chain.completion_order(["Aside", "Practice", "Theory"]) == ["Aside", "Theory", "Practice"]


def test_one_transaction_in_completion_order_completes_the_chain(chain):
    """What the bulk Toggle Done does with a selection picked out of order."""
    import database
    with database.transaction():
        for name in chain.completion_order(["Mastery", "Practice", "Theory"]):
            node = chain.get_node(name)
            node.status = STATUS_DONE
            chain.update_node(node)
    assert all(chain.get_node(n).status == STATUS_DONE for n in ("Theory", "Practice", "Mastery"))
    assert chain.recompute_all_statuses() == 0


# --- Names are unique, ignoring case ----------------------------------------

def test_a_rename_onto_another_nodes_name_is_refused_plainly():
    manager = GraphManager()
    manager.add_node(_node("Sleep"))
    manager.add_node(_node("Rest"))
    with pytest.raises(ValueError, match="already exists"):
        manager.rename_node("Rest", "Sleep")
    with pytest.raises(ValueError, match="already exists"):
        manager.rename_node("Rest", "SLEEP")
    assert {n.name for n in manager.get_all_nodes()} == {"Sleep", "Rest"}


def test_a_node_can_change_the_case_of_its_own_name():
    manager = GraphManager()
    manager.add_node(_node("sleep"))
    manager.rename_node("sleep", "Sleep")
    assert manager.get_node("Sleep") is not None


def test_a_new_node_whose_name_differs_only_by_case_is_refused():
    manager = GraphManager()
    manager.add_node(_node("Grüße"))
    with pytest.raises(ValueError, match="already exists"):
        manager.add_node(_node("GRÜSSE"))
