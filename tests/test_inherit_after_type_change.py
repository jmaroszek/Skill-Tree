"""Changing a Goal or Milestone into another type gives back its own estimate.

The editor forces Inherit on for a Goal's or Milestone's time, and a
Milestone's ratings. Changing the type kept it on, so an Action or Resource
had no time of its own and scored at no cost. A Learn may be a header over
its children, so it keeps Inherit, with a note.
"""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.engine import callbacks


def _lock(output):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    spec = next(c for c in app._callback_list
                if c.get("clientside_function") and output in c["output"])
    function = spec["clientside_function"]
    source = next(s for s in app._inline_scripts if function["function_name"] in s)
    return source, function["namespace"], function["function_name"]


def _run(output, calls):
    """Run the lock once per (triggered ids, mode value, node type) in order,
    in one page, and return each result."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the editor lock contract")
    source, namespace, name = _lock(output)
    script = f"""
global.window = {{dash_clientside: {{no_update: "NO_UPDATE", callback_context: {{}}}}}};
{source}
const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];
const out = [];
for (const [ids, mode, type] of {json.dumps(calls)}) {{
    window.dash_clientside.callback_context.triggered =
        ids.map(id => ({{prop_id: id + '.value'}}));
    out.push(fn(mode, type));
}}
console.log(JSON.stringify(out));
"""
    result = subprocess.run([node, "-e", script], capture_output=True, text=True,
                            timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


LOAD_GOAL = [["node-time-mode", "node-type"], ["inherited"], "Goal"]


@pytest.mark.parametrize("to_type", ["Action", "Resource"])
def test_a_goal_turned_into_an_action_gets_its_own_estimate(to_type):
    _, (mode, style, _) = _run("time-mode-warning.style",
                               [LOAD_GOAL, [["node-type"], ["inherited"], to_type]])
    assert mode == [] and style["display"] == "none"


def test_a_goal_turned_into_a_learn_keeps_inherit_with_a_note():
    _, (mode, style, text) = _run("time-mode-warning.style",
                                  [LOAD_GOAL, [["node-type"], ["inherited"], "Learn"]])
    assert mode == "NO_UPDATE" and style["display"] == "block"
    assert "header" in text


def test_loading_an_inheriting_learn_changes_nothing():
    _, (mode, style, _) = _run("time-mode-warning.style", [
        LOAD_GOAL, [["node-time-mode", "node-type"], ["inherited"], "Learn"]])
    assert mode == ["inherited"] and style["display"] == "none"


def test_a_milestone_turned_into_an_action_gets_its_own_ratings():
    _, (mode, style, _) = _run("value-mode-warning.style", [
        [["node-value-mode", "node-type"], ["inherited"], "Milestone"],
        [["node-type"], ["inherited"], "Action"]])
    assert mode == [] and style["display"] == "none"
