"""A loaded node's aliases show by themselves when it has any."""
import pytest

from dash import no_update

from skilltree.features.editor.callbacks import _filled, register_editor_callbacks
from skilltree.features.editor.form import NEW_NODE_SNAPSHOT
from support.callbacks import registered
from support.triggers import fire


@pytest.mark.parametrize("aliases, shown", [
    ([""], False),
    ([], False),
    (["Shuteye"], True),
    (["", "Shuteye"], True),
])
def test_the_alias_section_follows_the_node(aliases, shown):
    snapshot = {**NEW_NODE_SNAPSHOT, "aliases": aliases}
    out = _filled(snapshot, [], status="", original_name="A")
    assert out["aliases_open"] is shown


REMOVE = '{"index":0,"type":"btn-alias-remove"}.n_clicks'


def test_a_rebuilt_row_isnt_a_click_on_its_remove_button():
    modify = registered(register_editor_callbacks)["modify_aliases"]
    fire(REMOVE, value=None)
    assert modify(None, [None], ["Shuteye"], ["Shuteye"], True) == (no_update,) * 4


def test_a_real_click_removes_the_row():
    modify = registered(register_editor_callbacks)["modify_aliases"]
    fire(REMOVE, value=1)
    aliases, is_open, rows, label = modify(None, [1], ["Shuteye"], ["Shuteye"], True)
    assert (aliases, is_open) == ([], False)
    # The rows are drawn in the same answer: one empty row, ready for the next "+".
    assert len(rows) == 1 and label == "Alias"
