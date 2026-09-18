"""Shared browser boundary preserves dispatch, hook order, and instance isolation."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_input_and_layout_composition():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the browser bridge contract')
    asset = Path(__file__).resolve().parents[1] / 'assets' / '00_browser_bridge.js'
    script = r'''
const assert = require('node:assert/strict');
function Input() { this.events = []; }
Object.defineProperty(Input.prototype, 'value', {
    set(value) { this.nativeValue = value; }
});
Input.prototype.dispatchEvent = function (event) { this.events.push(event); };
global.window = {HTMLInputElement: Input};
require(process.argv[1]);
const api = window.SkillTree;
const input = new Input();
api.setInputValue(input, 'same');
api.setInputValue(input, 'same');
assert.equal(input.nativeValue, 'same');
assert.equal(input.events.length, 2);
assert(input.events.every(e => e.type === 'input' && e.bubbles));
api.setInputValue(null, 'ignored');
const trace = [];
const result = {};
function makeCy() {
    return {layout(options) {
        assert.equal(this, cy);
        trace.push(['base', options.padding]);
        return result;
    }};
}
const cy = makeCy();
api.wrapLayout(cy, 'inner', (next, options) => {
    trace.push(['inner', options.padding]);
    const value = next({...options, padding: options.padding + 1});
    trace.push(['afterInner']);
    return value;
});
api.wrapLayout(cy, 'outer', (next, options) => {
    trace.push(['outer', options.padding]);
    return next({...options, padding: options.padding * 2});
});
api.wrapLayout(cy, 'inner', () => { throw Error('duplicate hook'); });
const options = {padding: 3};
assert.equal(cy.layout(options), result);
assert.deepEqual(trace, [['outer', 3], ['inner', 6], ['base', 7], ['afterInner']]);
assert.deepEqual(options, {padding: 3});
const replacement = {layout(options) { return options; }};
api.wrapLayout(replacement, 'inner', (next, options) => next({...options, fresh: true}));
assert.deepEqual(replacement.layout({}), {fresh: true});
assert.equal(api.getCy(null), null);
const element = {_cyreg: {cy}};
assert.equal(api.getCy(element), cy);
element._cyreg.cy = replacement;
assert.equal(api.getCy(element), replacement);
'''
    result = subprocess.run([node, '-e', script, str(asset)], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr
