"""The suggestions under the filters sidebar's Search field."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_suggestions_hold_every_typed_word_and_lead_with_the_prefix():
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the suggestion contract')
    asset = Path(__file__).resolve().parents[1] / 'assets' / 'filter_suggest.js'
    script = r'''
const assert = require('node:assert/strict');
global.window = {addEventListener() {}};
global.document = {addEventListener() {}};
require(process.argv[1]);
const suggest = window.SkillTree.filterSuggest;
suggest.setNames(['Social Psychology', 'Psychology of Money', 'Psychology',
                  'Pricing', 'Positive Psychology']);

// Names that start with the typed word first, shorter before longer.
assert.deepEqual(suggest.matches('psych'),
    ['Psychology', 'Psychology of Money', 'Social Psychology', 'Positive Psychology']);
// Every word must appear, in any order, ignoring case.
assert.deepEqual(suggest.matches('PSYCHOLOGY social'), ['Social Psychology']);
// Nothing typed, or nothing matching, offers nothing.
assert.deepEqual(suggest.matches(''), []);
assert.deepEqual(suggest.matches('   '), []);
assert.deepEqual(suggest.matches('zzz'), []);

// The list is capped.
suggest.setNames(Array.from({length: 20}, (_, i) => 'Node ' + i));
assert.equal(suggest.matches('node').length, 8);
// A bad payload leaves no names rather than throwing.
suggest.setNames(null);
assert.deepEqual(suggest.matches('node'), []);
'''
    result = subprocess.run([node_binary, '-e', script, str(asset)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
