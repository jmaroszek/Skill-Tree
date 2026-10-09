"""Contract for the drag handles between panels.

A handle resizes the panels on either side of it, so the layout tests check
that every handle has the right panel on each side. The Node tests drive
assets/split_handles.js with stand-in elements.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from canvases import client_registry
from details_layout import build_details_tab_content
from events_layout import build_events_tab_content
from ui_kit import split_handle

ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'split_handles.js'


def _children(component):
    children = getattr(component, 'children', None)
    if children is None or isinstance(children, (str, int, float)):
        return []
    return list(children) if isinstance(children, (list, tuple)) else [children]


def _handles_between(component):
    """Each split handle under ``component``, with the ids of its neighbours."""
    siblings = _children(component)
    for i, child in enumerate(siblings):
        if 'split-handle' in (getattr(child, 'className', None) or '').split():
            before = siblings[i - 1] if i > 0 else None
            after = siblings[i + 1] if i + 1 < len(siblings) else None
            yield child.id, (getattr(before, 'id', None), getattr(after, 'id', None))
        yield from _handles_between(child)


@pytest.mark.parametrize('build, expected', [
    (build_details_tab_content, {
        'details-v-drag-upper': ('details-left-panel', 'details-dep-graph-container'),
        'details-h-drag': ('details-upper-section', 'details-lower-section'),
        'details-v-drag-lower': ('details-subtasks-section', 'details-sim-section'),
    }),
    (build_events_tab_content, {
        'events-v-drag': ('events-detail-panel', 'events-detail-graph-container'),
    }),
])
def test_each_handle_sits_between_the_panels_it_resizes(build, expected):
    assert dict(_handles_between(build())) == expected


def test_a_handle_carries_its_axis_and_minimum():
    props = split_handle('some-handle', 'rows', 100).to_plotly_json()['props']

    assert props['className'] == 'split-handle split-handle-rows'
    assert props['data-min-size'] == '100'
    # The look lives in theme.css, so hover can't drift per handle.
    assert 'style' not in props


HARNESS = r'''
const assert = require('node:assert/strict');
const listeners = {};
const byId = {};
let drag = null;
global.window = {
    SkillTree: {
        canvases: __CANVASES__,
        getCy: el => (el && el.cy) || null,
        drag: {start: handlers => { drag = handlers; }},
    },
    getComputedStyle: el => el.computed || {},
};
global.document = {
    addEventListener: (type, listener) => { listeners[type] = listener; },
    getElementById: id => byId[id] || null,
};
function panel(width, height, computed) {
    return {offsetWidth: width, offsetHeight: height, style: {}, computed};
}
function container(...members) {
    return {contains: el => members.includes(el)};
}
function handle(axis, first, second, minSize, parent = container()) {
    const el = {
        previousElementSibling: first,
        nextElementSibling: second,
        parentElement: parent,
        dataset: {minSize: String(minSize)},
        attributes: {},
        setAttribute(name, value) { el.attributes[name] = String(value); },
        matches: selector => selector === '.split-handle',
        classList: {contains: name => name === 'split-handle' || name === 'split-handle-' + axis},
        getAttribute: name => (name === 'data-min-size' ? String(minSize) : null),
        closest: selector => (selector === '.split-handle' ? el : null),
    };
    return el;
}
function press(target, x, y, button = 0) {
    drag = null;
    const event = {button, target, clientX: x, clientY: y, prevented: false,
                   preventDefault() { event.prevented = true; }};
    listeners.mousedown(event);
    return event;
}
require(process.argv[1]);
'''


def _run(body):
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the split handle contract')
    script = HARNESS.replace('__CANVASES__', json.dumps(client_registry())) + body
    result = subprocess.run(
        [node_binary, '-e', script, str(ASSET)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_a_column_drag_shares_the_width_by_flex_grow():
    _run(r'''
const left = panel(400, 0, {paddingLeft: '24px', paddingRight: '24px'});
left.style = {width: '698px', maxWidth: '698px', minWidth: '360px'};
const right = panel(600, 0);
const down = press(handle('cols', left, right, 150), 500, 0);
assert.ok(down.prevented, 'the drag must not start a text selection');
assert.equal(drag.cursor, 'col-resize');

// The left panel's 48px of padding is outside what flex-grow shares, so it
// comes off its share: 450 and 550 split the 1000px the pair had.
drag.onMove({clientX: 550, clientY: 0});
assert.deepEqual([left.style.flex, right.style.flex], ['402 1 0', '550 1 0']);
// No fixed width is left to hold the pair at its dragged size when the window
// grows, and the build-time ceiling and floor are lifted.
assert.equal(left.style.width, '');
assert.equal(left.style.maxWidth, 'none');
assert.equal(left.style.minWidth, '0');

drag.onMove({clientX: -1000, clientY: 0});
assert.deepEqual([left.style.flex, right.style.flex], ['102 1 0', '850 1 0']);
drag.onMove({clientX: 5000, clientY: 0});
assert.deepEqual([left.style.flex, right.style.flex], ['802 1 0', '150 1 0']);
''')


def test_a_row_drag_shares_the_height_by_flex_grow():
    _run(r'''
const upper = panel(0, 500);
const lower = panel(0, 300, {paddingTop: '8px', paddingBottom: '8px'});
press(handle('rows', upper, lower, 100), 0, 500);
assert.equal(drag.cursor, 'ns-resize');

// The lower panel's 16px of padding is outside what flex-grow shares, so it
// comes off its share: 560 and 224 + 16 split the 800px the pair had.
drag.onMove({clientX: 0, clientY: 560});
assert.deepEqual([upper.style.flex, lower.style.flex], ['560 1 0', '224 1 0']);

drag.onMove({clientX: 0, clientY: -1000});
assert.deepEqual([upper.style.flex, lower.style.flex], ['100 1 0', '684 1 0']);
''')


def test_the_end_of_a_drag_resizes_only_the_canvases_it_moved():
    _run(r'''
const resized = [];
const canvasEl = {};
for (const canvas of window.SkillTree.canvases) {
    canvasEl[canvas.key] = byId[canvas.cytoscapeId] = {
        cy: {resize() { resized.push(canvas.key); }},
    };
}
press(handle('cols', panel(400, 0), panel(600, 0), 150, container(canvasEl.details)), 500, 0);
drag.onEnd({cancelled: false});
assert.deepEqual(resized, ['details']);
''')


def test_only_a_left_press_on_a_handle_between_two_panels_drags():
    _run(r'''
const right = press(handle('cols', panel(400, 0), panel(600, 0), 150), 500, 0, 2);
assert.equal(drag, null);
assert.equal(right.prevented, false, 'a right-click keeps its context menu');

press({closest: () => null}, 500, 0);
assert.equal(drag, null);

press(handle('cols', panel(400, 0), null, 150), 500, 0);
assert.equal(drag, null);
''')


def test_keyboard_resizing_uses_the_axis_and_clamps_at_the_minimum():
    _run(r'''
const first = panel(400, 0), second = panel(600, 0);
const divider = handle('cols', first, second, 150);
function key(key, shiftKey=false) {
    const event = {target: divider, key, shiftKey, prevented: false,
        preventDefault() { event.prevented = true; }};
    listeners.keydown(event);
    return event;
}
assert.ok(key('ArrowRight').prevented);
assert.deepEqual([first.style.flex, second.style.flex], ['410 1 0', '590 1 0']);
key('ArrowLeft', true);
assert.deepEqual([first.style.flex, second.style.flex], ['350 1 0', '650 1 0']);
key('Home');
assert.deepEqual([first.style.flex, second.style.flex], ['150 1 0', '850 1 0']);
key('End');
assert.deepEqual([first.style.flex, second.style.flex], ['850 1 0', '150 1 0']);
assert.equal(key('ArrowDown').prevented, false);
assert.equal(divider.attributes['aria-valuenow'], '40');
assert.equal(divider.attributes['aria-valuetext'], '400 pixels');
''')
