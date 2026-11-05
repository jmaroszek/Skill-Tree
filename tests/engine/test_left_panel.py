"""Which left sidebar is open, and who gets to say so."""
import shutil
import subprocess

import pytest

from support.callback_graph import built_app, outputs_of
from support.paths import ROOT

SCRIPT = ROOT / "assets" / "sidebars" / "left_panel.js"

NODE_TEST = r"""
const assert = require('node:assert/strict');
const followed = [];
global.window = {dash_clientside: {
    no_update: 'NO', callback_context: {triggered: []},
    goals: {follow_left_panel: (...args) => followed.push(['goals', ...args])},
    events: {follow_left_panel: (...args) => followed.push(['events', ...args])},
}};
require(process.argv[1]);
const panel = window.dash_clientside.left_panel;
const advance = (current, id, value, state = {}) => {
    window.dash_clientside.callback_context.triggered = [{prop_id: id + '.value', value}];
    return panel.advance(null, null, current, state.selectedEvent, state.emptyStyle,
                         state.selectedNode, 7, 2, 'q', 'manual', null);
};
const opened = (current, id, value, state) => advance(current, id, value, state)[3];
const UNCHANGED = ['NO', 'NO', 'NO', 'NO', 'NO'];

// One open at a time. Only what changes is written, because each output costs
// time before the slide's first frame.
assert.deepEqual(advance(null, 'btn-goals-toggle', 1),
                 ['NO', 'left-sidebar is-open', 'NO', 'goals', 'NO']);
assert.deepEqual(advance('goals', 'btn-events-sidebar-toggle', 1),
                 ['NO', 'left-sidebar', 'left-sidebar is-open', 'events', 'NO']);
assert.deepEqual(advance('events', 'btn-events-sidebar-toggle', 2),
                 ['NO', 'NO', 'left-sidebar', null, 'NO']);
assert.equal(opened('editor', 'btn-goals-toggle', 1), 'goals');
assert.equal(opened('editor', 'btn-events-sidebar-toggle', 1), 'events');

// Goals and Events follow by a plain call, with what the Goals list came from.
followed.length = 0;
advance(null, 'btn-goals-toggle', 1);
assert.deepEqual(followed, [['goals', 'goals', 7, 2, 'q', 'manual', null], ['events', 'goals']]);
followed.length = 0;
advance('editor', 'btn-add', 2);
assert.deepEqual(followed, [], 'nothing changed, so nothing follows');

// Each toggle and X closes its own sidebar.
assert.equal(opened('goals', 'btn-goals-toggle', 2), null);
assert.equal(opened('events', 'btn-events-sidebar-toggle', 2), null);
assert.equal(opened('goals', 'btn-details-goals-close', 1), null);
assert.equal(opened('events', 'btn-events-sidebar-close', 1), null);
assert.deepEqual(advance('editor', 'btn-details-goals-close', 1), UNCHANGED);

// The toolbar icon opens the editor here. On an open editor it's a close, which
// only this script can tell, so it asks the server and changes nothing yet.
assert.equal(opened('goals', 'btn-add', 1), 'editor');
assert.equal(advance('goals', 'btn-add', 1)[4], 'NO');
const asked = advance('editor', 'btn-add', 2);
assert.deepEqual(asked.slice(0, 4), ['NO', 'NO', 'NO', 'NO']);
assert.equal(typeof asked[4], 'number');

// Whatever edits a node, or starts one, opens the editor.
['edit-trigger-input', 'details-edit-trigger-input'].forEach(id => {
    assert.equal(opened('goals', id, 'A|1'), 'editor');
    assert.deepEqual(advance(null, id, ''), UNCHANGED);
});
assert.equal(opened('goals', 'btn-goals-sidebar-new', 1), 'editor');
assert.equal(opened(null, 'btn-bridge-create', 1), 'editor');
assert.deepEqual(advance(null, 'btn-bridge-create', 0), UNCHANGED);
assert.equal(opened(null, 'details-add-choice-input', 'new|1', {selectedNode: 'A'}), 'editor');
assert.deepEqual(advance(null, 'details-add-choice-input', 'new|1', {}), UNCHANGED);
assert.deepEqual(advance(null, 'details-add-choice-input', 'existing|1', {selectedNode: 'A'}), UNCHANGED);
assert.equal(opened('events', 'dormant-add-choice-input', 'new|1', {selectedEvent: 'Trip'}), 'editor');
assert.deepEqual(advance('events', 'dormant-add-choice-input', 'existing|1', {selectedEvent: 'Trip'}), UNCHANGED);

// A late answer from the server closes only what it names.
assert.equal(opened('editor', 'left-panel-request', {close: 'editor', ts: 1}), null);
assert.deepEqual(advance('goals', 'left-panel-request', {close: 'editor', ts: 2}), UNCHANGED);
assert.deepEqual(advance(null, 'left-panel-request', null), UNCHANGED);

// Arriving on Events opens its sidebar when the true empty state is showing.
const empty = {emptyStyle: {display: 'block'}};
assert.equal(opened('editor', 'main-tabs', 'tab-events', empty), 'events');
// A loaded event keeps its detail workspace.
assert.deepEqual(advance(null, 'main-tabs', 'tab-next', empty), UNCHANGED);
assert.deepEqual(advance(null, 'main-tabs', 'tab-events', {selectedEvent: 'Trip', emptyStyle: {display: 'none'}}), UNCHANGED);
// A new-event draft has no selected event, but its hidden empty state keeps
// the sidebar from reopening over the active creation workflow.
assert.deepEqual(advance(null, 'main-tabs', 'tab-next', empty), UNCHANGED);
assert.deepEqual(advance(null, 'main-tabs', 'tab-events', {emptyStyle: {display: 'none'}}), UNCHANGED);
// An already-open sidebar is left alone on arrival.
assert.deepEqual(advance('events', 'main-tabs', 'tab-events', empty), UNCHANGED);
// Leaving Events closes it.
assert.equal(opened('events', 'main-tabs', 'tab-details', empty), null);
// An explicitly opened sidebar stays across unrelated tab changes.
assert.deepEqual(advance('events', 'main-tabs', 'tab-canvas', empty), UNCHANGED);
// Leaving Events leaves another sidebar open.
advance(null, 'main-tabs', 'tab-events', {selectedEvent: 'Trip'});
assert.deepEqual(advance('goals', 'main-tabs', 'tab-next', empty), UNCHANGED);
"""


def test_the_reducer():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the left panel contract")
    result = subprocess.run([node, "-e", NODE_TEST, str(SCRIPT)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_a_click_never_waits_on_the_server():
    """Dash holds a callback back while anything writing one of its Inputs runs.
    A click's door takes nothing a server callback writes as it fires, so a slide
    doesn't wait for the core engine to render."""
    app = built_app()
    door = next(c for c in app._callback_list
                if any(i["id"] == "btn-goals-toggle" for i in c.get("inputs", [])))
    server_outputs = {output for c in app._callback_list
                      if not c.get("clientside_function") for output in outputs_of(c)}
    inputs = {f"{i['id']}.{i['property']}" for i in door["inputs"]}
    # An Edit row's button writes this one, but only ever before it fires.
    assert inputs & server_outputs <= {"details-edit-trigger-input.value"}
