"""Browser contract for the Events sidebar's contextual default behavior."""

from pathlib import Path
import shutil
import subprocess

import dash
import pytest

from event_callbacks import register_event_callbacks


ASSET = Path(__file__).resolve().parents[1] / "assets" / "events_sidebar.js"


def _run_browser_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Events sidebar contract")

    script = r'''
const assert = require('node:assert/strict');
global.window = {
    dash_clientside: {no_update: 'NO', callback_context: {triggered: []}}
};
require(process.argv[1]);
const toggle = window.dash_clientside.events.toggle_sidebar;
const closed = {left: '-380px'};
const open = {left: '0px'};
const editorOpen = {transform: 'translateX(0px)'};
const goalOpen = {left: '0px'};
const trigger = id => {
    window.dash_clientside.callback_context.triggered = [{prop_id: id + '.value'}];
};
const call = (activeTab, sidebar, selectedEvent, emptyStyle) =>
    toggle(0, 0, 0, activeTab, sidebar, editorOpen, goalOpen, 4,
           selectedEvent, emptyStyle);

trigger('main-tabs');
let result = call('tab-events', closed, null, {display: 'block'});
assert.equal(result[0].left, '0px');
assert.equal(result[1], 5);
assert.equal(result[2].transform, 'translateX(-380px)');
assert.equal(result[3].left, '-380px');

// A loaded event does not take space away from its detail workspace.
assert.deepEqual(call('tab-events', closed, 'Trip', {display: 'none'}),
                 ['NO', 'NO', 'NO', 'NO']);
// A new-event draft has no selected event, but its hidden empty state keeps
// the sidebar from reopening over the active creation workflow.
assert.deepEqual(call('tab-events', closed, null, {display: 'none'}),
                 ['NO', 'NO', 'NO', 'NO']);
// Other tabs and an already-open sidebar are left alone.
assert.deepEqual(call('tab-details', closed, null, {display: 'block'}),
                 ['NO', 'NO', 'NO', 'NO']);
assert.deepEqual(call('tab-events', open, null, {display: 'block'}),
                 ['NO', 'NO', 'NO', 'NO']);

// Existing explicit controls retain their behavior.
trigger('btn-events-sidebar-close');
result = call('tab-events', open, null, {display: 'block'});
assert.equal(result[0].left, '-380px');
trigger('btn-open-events-sidebar');
result = call('tab-events', closed, null, {display: 'block'});
assert.equal(result[0].left, '0px');
'''
    result = subprocess.run(
        [node, "-e", script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_events_sidebar_browser_contract():
    _run_browser_contract()


def test_events_sidebar_callback_listens_for_tab_arrival_and_empty_state():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)

    spec = next(
        callback
        for key, callback in app.callback_map.items()
        if "events-sidebar-container.style" in key
        and any(item["id"] == "btn-events-sidebar-toggle"
                for item in callback["inputs"])
    )
    assert {item["id"] for item in spec["inputs"]} >= {
        "btn-events-sidebar-toggle",
        "btn-events-sidebar-close",
        "btn-open-events-sidebar",
        "main-tabs",
    }
    assert {item["id"] for item in spec["state"]} >= {
        "selected-event-store",
        "event-detail-empty",
    }
