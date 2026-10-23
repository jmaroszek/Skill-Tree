"""The suggestions under the filters sidebar's Search field."""
import shutil
import subprocess

import pytest
from support.paths import asset_file


def test_suggestions_hold_every_typed_word_and_lead_with_the_prefix():
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the suggestion contract')
    asset = asset_file("filter_suggest.js")
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
// A word must begin a word of the name, as the filter requires.
assert.deepEqual(suggest.matches('ology'), []);
// A query with operators is a search: choosing a name would drop them.
assert.deepEqual(suggest.matches('psych OR money'), []);
assert.deepEqual(suggest.matches('psych -social'), []);
assert.deepEqual(suggest.matches('"psychology"'), []);
assert.deepEqual(suggest.matches('psych or money'), []);
// A hyphen inside a word is only text.
suggest.setNames(['Self-Control', 'Control Theory']);
assert.deepEqual(suggest.matches('self-control'), ['Self-Control']);

// The list is capped.
suggest.setNames(Array.from({length: 20}, (_, i) => 'Node ' + i));
assert.equal(suggest.matches('node').length, 8);
// A bad payload leaves no names rather than throwing.
suggest.setNames(null);
assert.deepEqual(suggest.matches('node'), []);

// From the node editor Search list's options, an alias is suggested as its
// own text: the field searches aliases, but "alias:..." matches nothing.
suggest.setOptions([
    {label: '8 Fold Path', value: '8 Fold Path'},
    {label: 'Eightfold Path → 8 Fold Path', value: 'alias:Eightfold Path'},
    {label: 'Pathfinding', value: 'Pathfinding'},
]);
assert.deepEqual(suggest.matches('eight'), ['Eightfold Path']);
assert.deepEqual(suggest.matches('path'), ['Pathfinding', '8 Fold Path', 'Eightfold Path']);
suggest.setOptions(undefined);
assert.deepEqual(suggest.matches('path'), []);
'''
    result = subprocess.run([node_binary, '-e', script, str(asset)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_choosing_a_suggestion_commits_the_field_on_enter_keyup():
    """dbc.Input(debounce=True) listens for Enter on keyup, so a keydown applies nothing."""
    source = (asset_file("filter_suggest.js")).read_text()
    choose = source[source.index('function choose('):]
    choose = choose[:choose.index('\n    }\n')]

    assert "new KeyboardEvent('keyup'" in choose
    assert "'keydown'" not in choose
