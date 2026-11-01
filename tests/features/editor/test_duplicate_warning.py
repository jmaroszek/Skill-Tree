"""The duplicate name warning hides after three seconds, and can come back.

The timer hid only the element. Dash still held the warning as the field's
content and its style as showing, so the next blur with the same answer changed
nothing and the warning stayed hidden.
"""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.services import AppServices
from support.clientside import clientside_source


def _run(steps):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the duplicate warning timer")
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_editor_callbacks(app, AppServices())
    source, namespace, name = clientside_source(app, "node-name-duplicate-warning.title")
    script = f"""
const timers = new Map();
let next = 1;
global.setTimeout = (fn) => {{ timers.set(next, fn); return next++; }};
global.clearTimeout = (id) => timers.delete(id);
const sets = [];
global.window = {{SkillTree: {{}}, dash_clientside: {{
    no_update: "NO_UPDATE", set_props: (id, props) => sets.push([id, props])}}}};
{source}
const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];
for (const children of {json.dumps(steps)}) fn(children);
const pending = timers.size;
for (const run of [...timers.values()]) run();
console.log(JSON.stringify({{pending, sets}}));
"""
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_timer_clears_the_warning_through_dash():
    out = _run([{"props": {"children": "Possible duplicate: A"}}])

    assert out["sets"] == [["node-name-duplicate-warning",
                            {"children": "", "style": {"display": "none"}}]]


def test_nothing_is_timed_when_there_is_no_warning():
    assert _run([""]) == {"pending": 0, "sets": []}


def test_a_new_warning_gets_its_full_three_seconds():
    assert _run(["first", "", "second"])["pending"] == 1
