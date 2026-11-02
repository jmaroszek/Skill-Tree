"""What the editor does next. This table is the rule: read it, not the branches."""
import pytest

from skilltree.features.editor.navigation import ASK, CLOSE, KEEP, LOAD, next_step

# Each row: the intent, then what it does on a clean form, on a form with edits
# in the open editor, and on a form with edits out of sight behind Goals or
# Events.
RULE = [
    # The edits behind a sidebar aren't what a canvas click is about.
    ({'kind': 'tap', 'name': 'B'}, LOAD, ASK, KEEP),
    ({'kind': 'background'}, LOAD, ASK, KEEP),
    # These replace the form, so they ask, with the editor showing what's at stake.
    ({'kind': 'edit', 'name': 'B'}, LOAD, ASK, ASK),
    ({'kind': 'new'}, LOAD, ASK, ASK),
    ({'kind': 'new', 'parent': 'B'}, LOAD, ASK, ASK),
    ({'kind': 'new', 'goal': True}, LOAD, ASK, ASK),
    ({'kind': 'bridge'}, LOAD, ASK, ASK),
    # Neither of these can be reached from out of sight, and asking is the safe
    # answer if one ever is.
    ({'kind': 'close'}, CLOSE, ASK, ASK),
    ({'kind': 'picker', 'name': 'B'}, LOAD, ASK, ASK),
]


@pytest.mark.parametrize("intent, clean, dirty_open, dirty_closed", RULE)
def test_the_rule(intent, clean, dirty_open, dirty_closed):
    assert next_step(intent, editor_open=True, dirty=False) == clean
    assert next_step(intent, editor_open=False, dirty=False) == clean
    assert next_step(intent, editor_open=True, dirty=True) == dirty_open
    assert next_step(intent, editor_open=False, dirty=True) == dirty_closed


@pytest.mark.parametrize("kind", ["tap", "edit", "picker"])
def test_asking_for_the_node_the_form_holds_keeps_its_edits(kind):
    intent = {'kind': kind, 'name': 'A'}
    assert next_step(intent, editor_open=True, dirty=True, holds=True) == KEEP
    assert next_step(intent, editor_open=False, dirty=True, holds=True) == KEEP


@pytest.mark.parametrize("kind", ["tap", "edit", "picker"])
def test_with_nothing_to_lose_it_loads_again(kind):
    intent = {'kind': kind, 'name': 'A'}
    assert next_step(intent, editor_open=True, dirty=False, holds=True) == LOAD
