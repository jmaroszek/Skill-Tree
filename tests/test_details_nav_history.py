"""Details Back and Forward skip nodes that are gone.

The history kept the names of nodes deleted or renamed since they were
visited. Back or Forward could land on one, select a name that no longer
exists, and do nothing.
"""
import json
import shutil
import subprocess

import dash
import pytest

from details_callbacks import register_details_callbacks


def _history_source():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_details_callbacks(app)
    spec = next(c for c in app._callback_list
                if c.get("clientside_function")
                and c["output"].startswith("..details-nav-history.data"))
    function = spec["clientside_function"]
    source = next(s for s in app._inline_scripts
                  if function["function_name"] in s)
    return source, function["namespace"], function["function_name"]


def _run(trigger, *args):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the history contract")
    source, namespace, name = _history_source()
    script = f"""
global.window = {{dash_clientside: {{callback_context: {{triggered_id: {json.dumps(trigger)}}}}}}};
{source}
const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];
console.log(JSON.stringify(fn(...{json.dumps(list(args))})));
"""
    result = subprocess.run([node, "-e", script], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _options(*names):
    return [{"label": n, "value": n} for n in names]


def test_a_deleted_node_leaves_the_history():
    history, index, back_off, fwd_off = _run(
        "details-node-select", "C", 0, 0, _options("A", "C", "D"),
        ["A", "B", "C", "D"], 2)

    assert history == ["A", "C", "D"]
    assert index == 1  # still on C
    assert (back_off, fwd_off) == (False, False)


def test_the_neighbors_it_leaves_side_by_side_merge():
    history, index, _, fwd_off = _run(
        "details-node-select", "A", 0, 0, _options("A", "C"),
        ["A", "B", "A", "C"], 2)

    assert history == ["A", "C"]
    assert index == 0
    assert fwd_off is False


def test_a_renamed_current_node_keeps_the_place_before_it():
    history, index, _, _ = _run(
        "details-node-select", None, 0, 0, _options("A", "B", "Renamed"),
        ["A", "B", "C"], 2)

    assert history == ["A", "B"]
    assert index == 1
