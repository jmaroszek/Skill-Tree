"""Browser and Dash wiring contracts for docked left-side workspaces."""

from pathlib import Path
import shutil
import subprocess

import dash

from sidebars_callbacks import register_sidebars_callbacks


ASSET = Path(__file__).resolve().parents[1] / "assets" / "left_sidebar_workspace.js"


def test_workspace_reserves_width_for_any_open_left_sidebar():
    node = shutil.which("node")
    if node is None:
        return

    script = r'''
const assert = require('node:assert/strict');
global.window = {dash_clientside: {}};
require(process.argv[1]);
const workspace = window.dash_clientside.leftSidebar.workspace_style;
const closed = {transform: 'translateX(-350px)'};
const open = {transform: 'translateX(0px)'};

let style = workspace(closed, closed, closed);
assert.equal(style.marginLeft, '0');
assert.equal(style.width, '100%');

style = workspace(closed, closed, open);
assert.equal(style.marginLeft, '350px');
assert.equal(style.width, 'calc(100% - 350px)');

// A handoff remains reserved while the incoming sidebar opens and after the
// outgoing sidebar has completed its close.
assert.equal(workspace(closed, open, open).marginLeft, '350px');
assert.equal(workspace(closed, open, closed).marginLeft, '350px');
assert.equal(workspace(open, closed, closed).marginLeft, '350px');
'''
    result = subprocess.run(
        [node, "-e", script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_workspace_callback_observes_every_left_sidebar():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_sidebars_callbacks(app)

    spec = next(
        callback
        for key, callback in app.callback_map.items()
        if "left-sidebar-workspace.style" in key
    )
    assert {item["id"] for item in spec["inputs"]} == {
        "sidebar-editor-container",
        "details-goal-sidebar",
        "events-sidebar-container",
    }
