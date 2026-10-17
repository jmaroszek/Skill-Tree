"""Every way of loading another node asks before it drops unsaved edits.

A canvas tap already asked. The node menu's Edit, the Events table's Edit,
Details' Edit and the editor's node picker replaced the form without asking,
and clearing the picker blanked it. Loading the node the form already holds
reloaded it, which dropped the edits too.
"""
import dash
import pytest

from skilltree.engine import callbacks
from editor_forms import call
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from support.triggers import fire
from skilltree.features.editor import callbacks as editor_callbacks
from skilltree.services import AppServices
from skilltree.features.editor.callbacks import register_editor_callbacks

OPEN = {"transform": "translateX(0px)"}


def _node(name):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


def _registered():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    services = AppServices()
    callbacks.register_engine_callbacks(app, services)
    register_editor_callbacks(app, services)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found.setdefault(getattr(fn, "__name__", None), fn)
    return found


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("A", "B"):
        manager.add_node(_node(name))
    manager.set_aliases("B", ["Bee"])
    return manager


@pytest.fixture
def populate(monkeypatch, manager):
    """populate_editor with A loaded in the open editor, its form dirty or not."""
    fn = _registered()["populate_editor"]

    def run(trigger, dirty=True, **values):
        fire(trigger)
        monkeypatch.setattr(editor_callbacks, "is_form_dirty_vs_snapshot",
                            lambda *_args, **_kwargs: dirty)
        values.setdefault("ed_style", OPEN)
        values.setdefault("original_name", "A")
        values.setdefault("pristine_snapshot", {"name": "A"})
        return call(fn, **values)
    return run


def _asked(out, target):
    return (out["pending_nav"] == target and out["unsaved_open"] is True
            and out["name"] is dash.no_update and out["desc"] is dash.no_update)


@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "B|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "B|1"}),
    ("cytoscape-graph", {"tapped_node": {"id": "B"}}),
])
def test_loading_another_node_asks_first(populate, trigger, values):
    assert _asked(populate(trigger, **values), "B")


def test_the_node_picker_asks_first_and_goes_back_to_the_loaded_node(populate):
    out = populate("search-node", search_val="B")

    assert _asked(out, "B")
    assert out["search"] == "A"  # the form still holds A


def test_an_alias_in_the_picker_asks_for_its_node(populate):
    out = populate("search-node", search_val="alias:Bee")

    assert _asked(out, "B")


def test_clearing_the_picker_asks_before_it_blanks_the_form(populate):
    out = populate("search-node", search_val=None)

    assert _asked(out, "__new_node__")
    assert out["search"] == "A"


@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "A|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "A|1"}),
    ("cytoscape-graph", {"tapped_node": {"id": "A"}}),
    ("search-node", {"search_val": "A"}),
])
def test_the_node_already_open_keeps_its_edits(populate, trigger, values):
    out = populate(trigger, **values)

    assert out["name"] is dash.no_update and out["desc"] is dash.no_update
    assert out["unsaved_open"] is dash.no_update  # no dialog: nothing would be lost


@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "B|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "B|1"}),
    ("search-node", {"search_val": "B"}),
])
def test_a_clean_form_loads_straight_away(populate, trigger, values):
    out = populate(trigger, dirty=False, **values)

    assert out["name"] == "B" and out["original_name"] == "B"
    assert out["unsaved_open"] is False


def test_a_closed_editor_loads_straight_away(populate):
    out = populate("edit-trigger-input", edit_trigger_val="B|1", ed_style={})

    assert out["name"] == "B"


def test_discard_goes_on_to_the_node_edit_asked_for(populate):
    asked = populate("edit-trigger-input", edit_trigger_val="B|1")
    out = populate("btn-unsaved-discard", discard_clicks=1, pending_nav=asked["pending_nav"])

    assert out["name"] == "B" and out["original_name"] == "B"


# --- The dialog itself ------------------------------------------------------

@pytest.fixture
def dialog(monkeypatch):
    fn = _registered()["toggle_unsaved_modal"]

    def run(trigger, dirty=True):
        fire(trigger)
        monkeypatch.setattr(editor_callbacks, "is_form_dirty_vs_snapshot",
                            lambda *_args, **_kwargs: dirty)
        return call(fn, ed_style=OPEN, pristine_snapshot={"name": "A"})
    return run


def test_keep_editing_forgets_where_the_dialog_was_going(dialog):
    # Otherwise a later close's Discard would load the node a cancelled tap
    # was heading for, instead of closing.
    assert dialog("btn-unsaved-cancel") == (False, None)


def test_a_close_with_unsaved_edits_asks_and_goes_nowhere_after(dialog):
    assert dialog("btn-close-editor") == (True, None)
    assert dialog("btn-add") == (True, None)


def test_a_clean_close_asks_nothing(dialog):
    assert dialog("btn-close-editor", dirty=False) == (False, dash.no_update)


def test_save_and_discard_leave_the_navigation_to_the_editor(dialog):
    assert dialog("btn-unsaved-save") == (False, dash.no_update)
    assert dialog("btn-unsaved-discard") == (False, dash.no_update)
