"""The browser's half of the merge: an answer against the editor as it is by then.

Dash runs the two halves apart, so the user can type, or another node can load,
between the server working out an answer and the browser applying it.
"""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.features.editor.merge import MERGE_READS, MERGE_WRITES, register_merge_callbacks
from skilltree.services import AppServices
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
