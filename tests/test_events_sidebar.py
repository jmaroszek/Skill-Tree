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
const setProps = [];
global.window = {
    dash_clientside: {
        no_update: 'NO',
        callback_context: {triggered: []},
        set_props: (id, props) => setProps.push([id, props]),
    }
};
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
const toggle = window.dash_clientside.events.toggle_sidebar;
const adjust = window.dash_clientside.events.adjust_tab_inner;
const closed = {transform: 'translateX(-350px)'};
const open = {transform: 'translateX(0px)'};
const editorOpen = {transform: 'translateX(0px)'};
const goalOpen = {transform: 'translateX(0px)'};
const trigger = id => {
    window.dash_clientside.callback_context.triggered = [{prop_id: id + '.value'}];
};
const call = (activeTab, sidebar, selectedEvent, emptyStyle) =>
    toggle(0, 0, activeTab, sidebar, editorOpen, goalOpen, 4,
           selectedEvent, emptyStyle);

trigger('main-tabs');
let result = call('tab-events', closed, null, {display: 'block'});
assert.equal(result[0].transform, 'translateX(0px)');
// The tab content glides aside in the same return, so it starts with the slide.
assert.equal(result[1].marginLeft, '350px');
assert.equal(result[1].width, 'calc(100% - 350px)');
assert.match(result[1].transition, /margin-left 0.3s ease/);
assert.equal(result[2].transform, 'translateX(-350px)');
assert.equal(result[3].transform, 'translateX(-350px)');
// The list refresh waits for the slide to finish.
assert.deepEqual(setProps, []);
finishSlide();
assert.deepEqual(setProps, [['events-ui-refresh-trigger', {data: 5}]]);
setProps.length = 0;

// A loaded event does not take space away from its detail workspace.
assert.deepEqual(call('tab-events', closed, 'Trip', {display: 'none'}),
                 ['NO', 'NO', 'NO', 'NO']);
// A new-event draft has no selected event, but its hidden empty state keeps
// the sidebar from reopening over the active creation workflow.
assert.deepEqual(call('tab-events', closed, null, {display: 'none'}),
                 ['NO', 'NO', 'NO', 'NO']);
// Leaving Events closes an open sidebar and restores the full-width content.
result = call('tab-details', open, null, {display: 'block'});
assert.equal(result[0].transform, 'translateX(-350px)');
assert.equal(result[1].marginLeft, '0');
assert.equal(result[1].width, '100%');

// An explicitly opened sidebar remains available across unrelated tab changes.
trigger('btn-events-sidebar-toggle');
result = call('tab-details', closed, null, {display: 'block'});
assert.equal(result[0].transform, 'translateX(0px)');
trigger('main-tabs');
assert.deepEqual(call('tab-canvas', open, null, {display: 'block'}),
                 ['NO', 'NO', 'NO', 'NO']);

// An already-open sidebar is left alone when arriving on Events.
trigger('main-tabs');
assert.deepEqual(call('tab-events', open, null, {display: 'block'}),
                 ['NO', 'NO', 'NO', 'NO']);

// Existing explicit controls retain their behavior.
trigger('btn-events-sidebar-close');
result = call('tab-events', open, null, {display: 'block'});
assert.equal(result[0].transform, 'translateX(-350px)');
assert.equal(result[1].marginLeft, '0');
trigger('btn-events-sidebar-toggle');
result = call('tab-events', closed, null, {display: 'block'});
assert.equal(result[0].transform, 'translateX(0px)');

// Closing before the slide finishes drops the pending refresh.
trigger('btn-events-sidebar-close');
call('tab-events', open, null, {display: 'block'});
finishSlide();
assert.deepEqual(setProps, []);

// Other writers of the sidebar style get the same tab content style.
trigger('btn-events-sidebar-toggle');
assert.deepEqual(adjust(open), call('tab-events', closed, null, {display: 'block'})[1]);
assert.deepEqual(adjust(closed), call('tab-events', open, null, {display: 'block'})[1]);
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
        "main-tabs",
    }
    assert {item["id"] for item in spec["state"]} >= {
        "selected-event-store",
        "event-detail-empty",
    }
