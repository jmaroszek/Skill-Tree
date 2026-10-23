"""A click with Ctrl, Cmd or Shift held only picks nodes on the Nodes canvas.

With the editor open, it loaded the clicked node and named it in the node
picker. The core engine took that as a search and selected that node alone,
so a second node could never join the first for Bridge.
"""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.engine import callbacks
from skilltree.services import AppServices
from skilltree.features.editor.callbacks import register_editor_callbacks
from support.clientside import clientside_source


def _relay(taps):
    """Run the relay once per (tap data, held) in order, and return each result."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the editor tap relay")
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    services = AppServices()
    callbacks.register_engine_callbacks(app, services)
    register_editor_callbacks(app, services)
    source, namespace, name = clientside_source(app, "editor-tap-store.data")
    script = f"""
global.window = {{dash_clientside: {{no_update: "NO_UPDATE"}}, SkillTree: {{}}}};
{source}
const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];
const out = [];
for (const [tap, held] of {json.dumps(taps)}) {{
    window.SkillTree.additiveTap = held;
    out.push(fn(tap));
}}
console.log(JSON.stringify(out));
"""
    result = subprocess.run([node, "-e", script], capture_output=True, text=True,
                            timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_held_click_leaves_the_editor_alone():
    assert _relay([[{"id": "Business"}, True]]) == ["NO_UPDATE"]


def test_a_plain_click_loads_the_node_each_time():
    first, second = _relay([[{"id": "Business"}, False], [{"id": "Business"}, False]])
    assert first["id"] == second["id"] == "Business"
    assert "stamp" in first


def test_a_plain_click_after_a_held_one_loads_again():
    held, plain = _relay([[{"id": "Business"}, True], [{"id": "Sales"}, False]])
    assert held == "NO_UPDATE" and plain["id"] == "Sales"
