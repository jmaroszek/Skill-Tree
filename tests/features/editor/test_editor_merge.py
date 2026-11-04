"""The browser's half of the merge: an answer against the editor as it is by then.

Dash runs the two halves apart, so the user can type, or another node can load,
between the server working out an answer and the browser applying it.
"""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.domain.models import EDGE_NEEDS_HARD, Event, Node, STATUS_DONE, STATUS_OPEN
from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.form import (
    EDITOR_FORM,
    NEW_EVENT_OPTION,
    NEW_NODE_DORMANCY,
    build_dormancy_snapshot,
    build_editor_snapshot,
    editor_form_values_from,
    rebase,
    stored_relationships,
)
from skilltree.features.editor.merge import MERGE_READS, MERGE_WRITES, register_merge_callbacks
from skilltree.features.editor.save import save_editor_form
from skilltree.services import AppServices
from support.callbacks import registered
from support.clientside import clientside_source

_RUN = """
const assert = require('node:assert/strict');
global.window = {dash_clientside: {no_update: 'NO', PreventUpdate: {prevented: true}}};
eval(process.argv[1]);
const {answer, name, snapshot, form, namespace, fn} = JSON.parse(process.argv[2]);
const args = [answer, name, snapshot, ...answer.reads.map(key => form[key])];
process.stdout.write(JSON.stringify(window.dash_clientside[namespace][fn](...args)));
"""


def _group(key, value, baseline, seen):
    return {"fields": {key: value} if value is not None else {}, "baseline": {key: baseline},
            "seen_form": {key: seen}, "seen_baseline": {key: seen}}


def _answer(*groups, name="A"):
    return {"name": name, "groups": list(groups), "reads": list(MERGE_READS),
            "writes": list(MERGE_WRITES)}


def _apply(answer, *, name="A", snapshot=None, form=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to run the merge's browser half")
    app = dash.Dash(__name__)
    register_merge_callbacks(app, AppServices())
    output = next(c["output"] for c in app._callback_list if c.get("clientside_function"))
    source, namespace, fn = clientside_source(app, output.split("...")[1])
    payload = {"answer": answer, "name": name, "form": form or {}, "namespace": namespace,
               "fn": fn, "snapshot": snapshot if snapshot is not None else {"name": "A"}}
    done = subprocess.run([node, "-e", _RUN, source, json.dumps(payload)],
                          capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    written = {key: value for key, value in zip(MERGE_WRITES, out) if value != "NO"}
    return written, (None if out[-1] == "NO" else out[-1])


def test_an_answer_lands_on_the_form_it_was_worked_out_against():
    written, baseline = _apply(
        _answer(_group("e_helps", ["B"], ["B"], ["C"])),
        snapshot={"name": "A", "e_helps": ["C"], "desc": "kept"}, form={"e_helps": ["C"]})

    assert written == {"e_helps": ["B"]}
    assert baseline == {"name": "A", "e_helps": ["B"], "desc": "kept"}


def test_an_answer_for_another_node_is_dropped():
    answer = _answer(_group("e_helps", ["B"], ["B"], ["C"]))
    snapshot = {"name": "A", "e_helps": ["C"]}
    assert _apply(answer, name="Other", snapshot=snapshot, form={"e_helps": ["C"]}) == ({}, None)
    assert _apply(answer, snapshot={**snapshot, "name": "Other"},
                  form={"e_helps": ["C"]}) == ({}, None)


def test_a_field_changed_meanwhile_keeps_it_and_its_baseline():
    written, baseline = _apply(
        _answer(_group("e_helps", ["C", "B"], ["B"], ["C"])),
        snapshot={"name": "A", "e_helps": ["C"]}, form={"e_helps": ["C", "D"]})

    assert written == {}
    assert baseline is None


def test_a_baseline_changed_meanwhile_drops_the_group():
    """A save landed first. Its new snapshot asks the server again."""
    written, baseline = _apply(
        _answer(_group("e_helps", ["B"], ["B"], ["C"])),
        snapshot={"name": "A", "e_helps": ["D"]}, form={"e_helps": ["C"]})

    assert (written, baseline) == ({}, None)


def test_the_other_groups_still_land():
    written, baseline = _apply(
        _answer(_group("e_helps", ["B"], ["B"], ["C"]),
                _group("e_needs_h", ["Y"], ["Y"], ["X"])),
        snapshot={"name": "A", "e_helps": ["C"], "e_needs_h": ["X"]},
        form={"e_helps": ["typed"], "e_needs_h": ["X"]})

    assert written == {"e_needs_h": ["Y"]}
    assert baseline == {"name": "A", "e_helps": ["C"], "e_needs_h": ["Y"]}


def test_a_group_with_no_new_value_still_moves_the_baseline():
    written, baseline = _apply(
        _answer(_group("e_helps", None, ["B"], ["C"])),
        snapshot={"name": "A", "e_helps": ["C"]}, form={"e_helps": ["C"]})

    assert written == {}
    assert baseline["e_helps"] == ["B"]


def test_a_dict_compares_the_same_whatever_order_its_keys_came_back_in():
    """The server's JSON can sort a dict's keys."""
    group = _group("e_helps", ["B"], ["B"], {"a": 1, "b": 2})
    written, _ = _apply(_answer(group),
                        snapshot={"name": "A", "e_helps": {"b": 2, "a": 1}},
                        form={"e_helps": {"b": 2, "a": 1}})

    assert written == {"e_helps": ["B"]}


# --- A form the merge has no business touching ----------------------------------------

def _plain(graph, _events):
    graph.add_node(_node("It"))


def _habit(graph, _events):
    graph.add_node(_node("It", time_mode="habit", habit_duration=6, habit_duration_unit="weeks",
                         habit_intensity_o=20, habit_intensity_m=30, habit_intensity_p=45,
                         habit_intensity_unit="min_per_session", habit_days="0,2"))


def _rounded(graph, _events):
    """Hours that no number of weeks shows exactly."""
    graph.add_node(_node("It", time_o=7.0, time_m=13.0, time_p=29.0))


def _goal_with_inherited_time(graph, _events):
    graph.add_node(_node("Child"))
    graph.add_node(_node("It", type="Goal", time_mode="inherited"))
    graph.add_edge("Child", "It", EDGE_NEEDS_HARD)


def _inherited_ratings(graph, _events):
    graph.add_node(_node("It", value_mode="inherited"))


def _milestone(graph, _events):
    graph.add_node(_node("It", type="Milestone"))


def _done(graph, _events):
    graph.add_node(_node("It", status=STATUS_DONE))


def _in_now(graph, _events):
    graph.add_node(_node("It", now=1))


def _asleep(graph, events):
    graph.add_node(_node("It"))
    events.add_event(Event(name="Later"))
    events.add_node_to_event("Later", "It")


def _asleep_with_a_delay(graph, events):
    graph.add_node(_node("It"))
    events.add_event(Event(name="Later"))
    events.add_node_to_event("Later", "It", delay_days=10, now_on_trigger=True)


def _waiting_on_a_wake_date(graph, events):
    graph.add_node(_node("It"))
    events.add_event(Event(name="Later"))
    events.add_node_to_event("Later", "It", delay_days=10)
    events.trigger_event_manually("Later")


SHAPES = (_plain, _habit, _rounded, _goal_with_inherited_time, _inherited_ratings, _milestone,
          _done, _in_now, _asleep, _asleep_with_a_delay, _waiting_on_a_wake_date)


def _node(name, **fields):
    return Node(**{**dict(name=name, type="Action", description="", value=5, time_o=1.0,
                          time_m=2.0, time_p=4.0, interest=5, difficulty=5, status=STATUS_OPEN,
                          context="Mind"), **fields})


def _what_moves(services, form, snapshot):
    node = services.graph.get_node("It")
    return rebase(node, stored_relationships(services.graph.get_edges(), "It"), form, snapshot,
                  stored_dormancy=build_dormancy_snapshot(node, services.events))


def _saved(services, form, snapshot):
    """The baseline and form a committed save leaves, as the post-save sync makes it."""
    saved = save_editor_form(services.graph, services.events, form, "It", original_name="It",
                             pristine_snapshot=snapshot, bridge_pending=None,
                             reopen_confirmed=False, via="btn-save", now=bool(form.get("now")))
    sync = registered(register_editor_callbacks)["sync_original_name_after_save"]
    *_, baseline, _ = sync(saved.result, "It", None)
    return editor_form_values_from(saved.result["form"]), baseline


def _loaded_form(services):
    snapshot = build_editor_snapshot(services.graph, services.events, "It")
    return {**{key: snapshot[key] for key in EDITOR_FORM if key in snapshot},
            "link_values": [], "link_ids": []}, snapshot


@pytest.mark.parametrize("shape", SHAPES, ids=lambda shape: shape.__name__)
def test_a_loaded_form_and_a_saved_one_leave_the_merge_nothing_to_do(services, shape):
    """It runs on every change, so anything here would rewrite the form for no
    reason, or write a baseline that sets it off again."""
    shape(services.graph, services.events)
    form, snapshot = _loaded_form(services)
    assert _what_moves(services, form, snapshot) == []

    form, baseline = _saved(services, form, snapshot)

    assert _what_moves(services, form, baseline) == []


def test_a_new_event_saved_from_the_form_settles_after_one_answer(services):
    services.graph.add_node(_node("It"))
    form, snapshot = _loaded_form(services)
    form["dormancy"] = {**NEW_NODE_DORMANCY, "dormant": True, "event": NEW_EVENT_OPTION,
                        "event_name": "Fresh"}

    form, baseline = _saved(services, form, snapshot)
    [group] = _what_moves(services, form, baseline)

    assert group["fields"]["dormant_event"] == "Fresh"
    settled = {**baseline, **group["baseline"]}
    assert _what_moves(services, {**form, "dormancy": group["baseline"]["dormancy"]}, settled) == []
