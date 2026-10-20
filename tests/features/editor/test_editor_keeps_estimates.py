"""Saving the editor leaves an estimate it didn't change as it is.

The editor shows a node's hours in days or weeks, rounded to two decimals, at
the hours per week Settings held when it loaded, and Save converts the form
back to hours at the rate Settings holds then. So a save that only changed
the description rescaled the estimate after the hours per week changed (two
weeks of a 10-hour week became two weeks of a 20-hour one), and re-rounded it
at a rate that doesn't divide it evenly.
"""
import pytest

from skilltree.domain.models import Node, STATUS_OPEN
from skilltree.engine import callbacks
from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.form import EDITOR_FORM, build_editor_snapshot
from skilltree.store import settings
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from support.callbacks import registered
from support.editor_forms import call
from support.triggers import fire


@pytest.fixture
def handlers():
    return registered(callbacks.register_engine_callbacks, register_editor_callbacks)


def _rate(hours_per_week):
    settings.TIME_SETTINGS.set({**settings.TIME_SETTINGS.get(),
                                "hours_per_week": hours_per_week,
                                "hours_per_month": 4 * hours_per_week})


def _add(manager, o, m, p):
    manager.add_node(Node(name="Essay", type="Action", description="", value=5,
                          time_o=o, time_m=m, time_p=p, interest=5, difficulty=5,
                          status=STATUS_OPEN, context="Mind"))


def _loaded(manager):
    snapshot = build_editor_snapshot(manager, EventManager(GraphManager()), "Essay")
    form = {key: snapshot[key] for key in EDITOR_FORM if key in snapshot}
    return form, snapshot


def _save(handlers, form, snapshot, **edits):
    fire("btn-save")
    values = {**form, "link_values": [], "link_ids": [], **edits}
    return callbacks.CoreResponse(*call(
        handlers["core_engine"], original_name="Essay", pristine_snapshot=snapshot,
        ed_style={"transform": "translateX(0px)"}, **values))


def _hours(manager):
    node = manager.get_node("Essay")
    return node.time_o, node.time_m, node.time_p


def test_a_new_hours_per_week_leaves_an_untouched_estimate_alone(handlers):
    manager = GraphManager()
    _rate(10)
    _add(manager, 10, 20, 40)
    form, snapshot = _loaded(manager)
    assert (form["time_o"], form["time_m"], form["time_p"], form["time_unit"]) == (
        1, 2, 4, "weeks")

    _rate(20)
    _save(handlers, form, snapshot, desc="an unrelated edit")

    assert manager.get_node("Essay").description == "an unrelated edit"
    assert _hours(manager) == (10, 20, 40)


def test_an_untouched_estimate_is_not_rounded_again(handlers):
    manager = GraphManager()
    _rate(15)
    _add(manager, 8, 16, 32)
    form, snapshot = _loaded(manager)
    assert (form["time_o"], form["time_m"], form["time_p"]) == (0.53, 1.07, 2.13)

    _save(handlers, form, snapshot, desc="an unrelated edit")

    assert _hours(manager) == (8, 16, 32)


def test_an_estimate_the_user_changed_is_read_at_todays_rate(handlers):
    manager = GraphManager()
    _rate(10)
    _add(manager, 10, 20, 40)
    form, snapshot = _loaded(manager)

    _rate(20)
    _save(handlers, form, snapshot, time_m=3)

    assert _hours(manager) == (20, 60, 80)
