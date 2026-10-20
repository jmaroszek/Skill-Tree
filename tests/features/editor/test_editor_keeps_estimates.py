"""Saving the editor leaves an estimate it didn't change as it is.

The editor shows a node's hours in days or weeks, rounded to two decimals, at
the hours per week Settings held when it loaded, and Save converts the form
back to hours at the rate Settings holds then. So a save that only changed
the description rescaled the estimate after the hours per week changed (two
weeks of a 10-hour week became two weeks of a 20-hour one), and re-rounded it
at a rate that doesn't divide it evenly.
"""
import dash
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


ESTIMATE = ("time_o", "time_m", "time_p", "time_unit")


def _follow(handlers, form, snapshot, status="Settings saved"):
    return handlers["follow_editor_estimate"](
        status, "Essay", snapshot, {key: form[key] for key in ESTIMATE})


def _patched(snapshot, patch):
    patched = {**snapshot}
    for operation in patch.to_plotly_json()["operations"]:
        patched[operation["location"][0]] = operation["params"]["value"]
    return patched


def test_the_open_editor_shows_the_estimate_at_the_new_rate(handlers):
    manager = GraphManager()
    _rate(10)
    _add(manager, 10, 20, 40)
    form, snapshot = _loaded(manager)

    _rate(20)
    o, m, p, patch = _follow(handlers, form, snapshot)

    assert (o, m, p) == (0.5, 1, 2)
    snapshot = _patched(snapshot, patch)
    assert (snapshot["time_o"], snapshot["time_m"], snapshot["time_p"]) == (0.5, 1, 2)
    # Editing one value afterwards leaves the other two as they were.
    _save(handlers, {**form, "time_o": o, "time_m": m, "time_p": p}, snapshot, time_m=1.5)
    assert _hours(manager) == (10, 30, 40)


def test_an_estimate_being_edited_stays_while_the_baseline_follows(handlers):
    manager = GraphManager()
    _rate(10)
    _add(manager, 10, 20, 40)
    form, snapshot = _loaded(manager)

    _rate(20)
    o, m, p, patch = _follow(handlers, {**form, "time_m": 3}, snapshot)

    assert (o, m, p) == (dash.no_update,) * 3
    assert _patched(snapshot, patch)["time_m"] == 1


def test_the_estimate_stays_when_the_rate_does(handlers):
    manager = GraphManager()
    _rate(15)
    _add(manager, 8, 16, 32)
    form, snapshot = _loaded(manager)

    assert _follow(handlers, form, snapshot) == (dash.no_update,) * 4


def test_only_a_settings_save_moves_the_estimate(handlers):
    manager = GraphManager()
    _rate(10)
    _add(manager, 10, 20, 40)
    form, snapshot = _loaded(manager)

    _rate(20)
    assert _follow(handlers, form, snapshot, status="") == (dash.no_update,) * 4
    assert _follow(handlers, form, {**snapshot, "name": "Another"}) == (
        dash.no_update,) * 4
