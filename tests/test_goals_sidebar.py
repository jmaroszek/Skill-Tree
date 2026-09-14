"""The Goals sidebar: its toggle's browser contract, the left-sidebar mutex,
and how its list is built."""

from contextvars import copy_context
from pathlib import Path
import shutil
import subprocess

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict
import dash_bootstrap_components as dbc
import pytest

import callbacks
import database
import sidebars_callbacks
from config import SIDEBAR_TRANSLATE_CLOSED
from graph_manager import GraphManager
from models import Node
from sidebars_layout import build_goals_sidebar


ASSET = Path(__file__).resolve().parents[1] / "assets" / "goals_sidebar.js"


def test_goals_sidebar_browser_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Goals sidebar contract")

    script = r'''
const assert = require('node:assert/strict');
const setProps = [];
global.window = {
    dash_clientside: {
        no_update: 'NO',
        callback_context: {triggered: []},
        set_props: (id, props) => setProps.push([id, props]),
    }
};
global.document = {addEventListener: () => {}};
// Timers run only when the test says the slide has finished.
let timers = [];
global.setTimeout = fn => { timers.push(fn); return fn; };
global.clearTimeout = fn => { timers = timers.filter(t => t !== fn); };
const finishSlide = () => {
    const due = timers;
    timers = [];
    due.forEach(fn => fn());
};
require(process.argv[1]);
const toggle = window.dash_clientside.goals.toggle_sidebar;
const closed = {transform: 'translateX(-350px)'};
const open = {transform: 'translateX(0px)'};
const trigger = id => {
    window.dash_clientside.callback_context.triggered = [{prop_id: id + '.n_clicks'}];
};

// Opening slides the sidebar in and slides the editor and Events shut.
trigger('btn-goals-toggle');
let result = toggle(1, 0, closed, open, open, 4);
assert.equal(result.length, 3);
assert.equal(result[0].transform, 'translateX(0px)');
assert.equal(result[0].left, '0');
assert.equal(result[1].transform, 'translateX(-350px)');
assert.equal(result[2].transform, 'translateX(-350px)');
// The list refresh waits for the slide to finish.
assert.deepEqual(setProps, []);
finishSlide();
assert.deepEqual(setProps, [['goals-ui-refresh-trigger', {data: 5}]]);
setProps.length = 0;

// Peers that are already shut are left alone.
result = toggle(2, 0, closed, closed, closed, 5);
assert.equal(result[1], 'NO');
assert.equal(result[2], 'NO');

// Closing before the slide finishes drops the pending refresh.
trigger('btn-details-goals-close');
result = toggle(2, 1, open, closed, closed, 5);
assert.equal(result[0].transform, 'translateX(-350px)');
finishSlide();
assert.deepEqual(setProps, []);

// The toggle closes an open sidebar.
trigger('btn-goals-toggle');
result = toggle(3, 1, open, closed, closed, 5);
assert.equal(result[0].transform, 'translateX(-350px)');
'''
    result = subprocess.run(
        [node, "-e", script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_opening_the_editor_slides_goals_and_events_shut():
    open_style = {"transform": "translateX(0px)", "left": "0"}
    _, goal_style, events_style = callbacks._compute_sidebar_styles(
        "btn-new-node", {"btn-new-node"}, None,
        None, open_style, open_style, None, {},
    )
    assert goal_style["transform"] == SIDEBAR_TRANSLATE_CLOSED
    assert events_style["transform"] == SIDEBAR_TRANSLATE_CLOSED
    assert goal_style["left"] == "0"


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _find(child, component_id)
            if found is not None:
                return found
    return None


def test_goal_list_shows_a_spinner_until_its_first_render():
    container = _find(build_goals_sidebar(), "details-goal-list-container")
    cover = container.children
    assert cover.className == "loading-cover"
    assert isinstance(cover.children[0], dbc.Spinner)


def _render_goal_list(trigger, sidebar_style):
    """Run render_goal_list as Dash would for a single triggering input."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_sidebars_callbacks(app)
    render = next(
        spec["callback"].__wrapped__ for spec in app.callback_map.values()
        if getattr(spec.get("callback"), "__wrapped__", None) is not None
        and spec["callback"].__wrapped__.__name__ == "render_goal_list"
    )

    def run():
        context_value.set(AttributeDict(triggered_inputs=[{"prop_id": trigger, "value": 1}]))
        return render("tab-next", None, None, None, None, "priority", None, 1, None,
                      sidebar_style)
    return copy_context().run(run)


def _add_goals(*names):
    manager = GraphManager()
    for name in names:
        manager.add_node(Node(name=name, type="Goal", description="", value=5,
                              interest=5, difficulty=5, time_o=1, time_m=2,
                              time_p=4, context="Mind", status="Open"))


def test_goal_list_builds_from_one_database_snapshot(monkeypatch):
    _add_goals("Alpha", "Beta", "Gamma")
    built = []

    class CountingSnapshot(database.ReadSnapshot):
        def __init__(self):
            built.append(self)
            super().__init__()

    monkeypatch.setattr(database, "ReadSnapshot", CountingSnapshot)
    cards = _render_goal_list("goals-ui-refresh-trigger.data",
                              {"transform": "translateX(0px)"})
    assert len(cards) == 3
    assert len(built) == 1


def test_closed_goal_list_builds_only_for_the_background_prewarm():
    _add_goals("Alpha")
    closed = {"transform": SIDEBAR_TRANSLATE_CLOSED}
    assert _render_goal_list("graph-version-store.data", closed) is dash.no_update
    cards = _render_goal_list("goals-prewarm-store.data", closed)
    assert len(cards) == 1
