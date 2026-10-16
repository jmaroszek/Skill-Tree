"""A priority rank belongs to an unfinished Goal.

A priority Goal converted to another type kept its rank. Its old subtree went
on being boosted, and the Goals sidebar, which lists only Goals, could not
clear the slot it held. A finished Goal kept its rank too, and the sidebar,
which hides finished Goals, could not clear that slot either.
"""
import dash
import pytest

from skilltree.store import database
from skilltree.features.goals import callbacks as sidebars_callbacks
from skilltree.store.settings import ConfigManager
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from test_atomic_saves import node


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("Neuroscience", "Literature", "Video"):
        manager.add_node(node(name, type="Goal", time_mode="inherited"))
    manager.add_node(node("Essay"))
    manager.add_edge("Essay", "Literature", "Needs_Hard")
    ConfigManager.set_priority_goals(["Neuroscience", "Literature", "Video"])
    return manager


def _convert(manager, name, to_type="Action"):
    item = manager.get_node(name)
    item.type, item.time_mode = to_type, "manual"
    manager.update_node(item)


def test_a_goal_turned_into_another_type_loses_its_rank(manager):
    _convert(manager, "Literature")

    # The ranks after it move up, and the third slot is free again.
    assert ConfigManager.get_priority_goals() == ["Neuroscience", "Video"]


def test_its_old_subtree_is_no_longer_boosted(manager):
    def essay_score():
        nodes = manager.get_all_nodes()
        scored = manager.calculate_priority_scores(
            nodes, priority_goals=ConfigManager.get_priority_goals())
        return next(n.priority_score for n in scored if n.name == "Essay")

    ConfigManager.set_hyperparams({**ConfigManager.get_hyperparams(), "goal_boost": 1.5})
    boosted = essay_score()
    _convert(manager, "Literature")

    assert essay_score() < boosted


def _set_status(manager, name, status):
    item = manager.get_node(name)
    item.status = status
    manager.update_node(item)


def test_a_finished_goal_frees_its_slot(manager):
    _set_status(manager, "Neuroscience", STATUS_DONE)

    assert ConfigManager.get_priority_goals() == ["Literature", "Video"]

    # Reopening it doesn't take a slot back.
    _set_status(manager, "Neuroscience", STATUS_OPEN)
    assert ConfigManager.get_priority_goals() == ["Literature", "Video"]


def test_a_finished_goal_cannot_take_a_rank(manager):
    _set_status(manager, "Video", STATUS_DONE)

    assert _set_priority()("Video|1|1700000000000") is dash.no_update
    assert ConfigManager.get_priority_goals() == ["Neuroscience", "Literature"]


def test_other_edits_keep_the_rank(manager):
    item = manager.get_node("Literature")
    item.description = "Reading and writing"
    manager.update_node(item)

    assert ConfigManager.get_priority_goals() == ["Neuroscience", "Literature", "Video"]


def test_a_rolled_back_save_keeps_the_rank(manager):
    with pytest.raises(RuntimeError):
        with database.transaction():
            _convert(manager, "Literature")
            raise RuntimeError("the save was refused")

    assert ConfigManager.get_priority_goals() == ["Neuroscience", "Literature", "Video"]
    assert manager.get_node("Literature").type == "Goal"


def test_the_launch_repair_clears_ranks_held_by_non_goals(manager):
    # Older data: a rank kept by a node converted before the save dropped it,
    # and one kept by a name no node has.
    item = manager.get_node("Video")
    item.type, item.time_mode = "Action", "manual"
    manager.update_node(item)
    ConfigManager.set_priority_goals(["Video", "Neuroscience", "Ghost"])

    assert manager.prune_priority_goals() == ["Video", "Ghost"]
    assert ConfigManager.get_priority_goals() == ["Neuroscience"]
    assert manager.prune_priority_goals() == []


def test_the_launch_repair_clears_ranks_held_by_finished_goals(manager):
    # Older data: a Goal finished before the save dropped its rank.
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Done' WHERE name='Literature'")

    assert manager.prune_priority_goals() == ["Literature"]
    assert ConfigManager.get_priority_goals() == ["Neuroscience", "Video"]


def _set_priority():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_sidebars_callbacks(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if getattr(fn, "__name__", None) == "handle_goal_priority_change":
            return fn
    raise LookupError("handle_goal_priority_change")


def test_only_a_goal_takes_a_rank(manager):
    ConfigManager.set_priority_goals([])
    handle = _set_priority()

    assert handle("Essay|1|1700000000000") is dash.no_update
    assert ConfigManager.get_priority_goals() == []

    handle("Video|1|1700000000000")
    assert ConfigManager.get_priority_goals() == ["Video"]


def test_clearing_a_rank_works_whatever_holds_it(manager):
    ConfigManager.set_priority_goals(["Essay", "Video"])

    _set_priority()("Essay|clear|1700000000000")

    assert ConfigManager.get_priority_goals() == ["Video"]
