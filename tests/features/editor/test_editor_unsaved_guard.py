"""Every way of loading another node asks before it drops unsaved edits.

A canvas tap already asked. The node menu's Edit, the Events table's Edit,
Details' Edit and the editor's node picker replaced the form without asking,
and clearing the picker blanked it. Loading the node the form already holds
reloaded it, which dropped the edits too.
"""
import dash
import pytest

from skilltree.engine import callbacks
from support.editor_forms import call
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from support.triggers import fire
from skilltree.features.editor import callbacks as editor_callbacks
from skilltree.features.editor.callbacks import register_editor_callbacks
from support.callbacks import registered

def _node(name):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


def _registered():
    return registered(callbacks.register_engine_callbacks, register_editor_callbacks)


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
        fire(*([trigger] if isinstance(trigger, str) else trigger))
        monkeypatch.setattr(editor_callbacks, "is_form_dirty_vs_snapshot",
                            lambda *_args, **_kwargs: dirty)
        values.setdefault("left_panel", "editor")
        values.setdefault("original_name", "A")
        values.setdefault("pristine_snapshot", {"name": "A"})
        return call(fn, **values)
    return run


def _asked(out, target):
    """The dialog opened to go on to ``target``: an intent, or a node's name."""
    pending = out["pending_nav"]
    goes_on = pending == target or (isinstance(target, str) and pending.get("name") == target)
    return (goes_on and out["unsaved_open"] is True
            and out["name"] is dash.no_update and out["desc"] is dash.no_update)


@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "B|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "B|1"}),
    ("editor-tap-store", {"tapped_node": {"id": "B"}}),
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

    assert _asked(out, {"kind": "new"})
    assert out["search"] == "A"


@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "A|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "A|1"}),
    ("editor-tap-store", {"tapped_node": {"id": "A"}}),
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


def test_a_closed_editor_with_nothing_to_lose_loads_straight_away(populate):
    out = populate("edit-trigger-input", dirty=False, edit_trigger_val="B|1", left_panel=None)

    assert out["name"] == "B"


# Opening Goals or Events slides the editor away with its form as it was, and
# reopening it brings the edits back. A closed editor can still hold them.

@pytest.mark.parametrize("trigger, values", [
    ("edit-trigger-input", {"edit_trigger_val": "B|1"}),
    ("details-edit-trigger-input", {"details_edit_trigger_val": "B|1"}),
])
def test_an_edit_asks_about_edits_left_behind_a_sidebar(populate, trigger, values):
    assert _asked(populate(trigger, left_panel=None, **values), "B")


@pytest.mark.parametrize("trigger, values, target", [
    ("details-add-choice-input",
     {"details_add_choice": "new|1", "details_selected_node": "B"}, {"kind": "new", "parent": "B"}),
    ("btn-bridge-create", {"bridge_clicks": 1}, {"kind": "bridge"}),
    ("btn-goals-sidebar-new", {"goal_new_clicks": 1}, {"kind": "new", "goal": True}),
])
def test_opening_a_new_form_asks_about_edits_left_behind_a_sidebar(
        populate, trigger, values, target):
    assert _asked(populate(trigger, left_panel=None, **values), target)


@pytest.mark.parametrize("trigger, values", [
    ("editor-tap-store", {"tapped_node": {"id": "B"}}),
    ("background-click-input", {}),
])
def test_a_click_on_the_canvas_leaves_edits_behind_a_sidebar_alone(populate, trigger, values):
    # A tap only fills a closed editor in the background, and an empty click
    # only blanks it. Neither is about the form, so neither asks or replaces it.
    out = populate(trigger, left_panel=None, **values)

    assert out["name"] is dash.no_update and out["desc"] is dash.no_update
    assert out["unsaved_open"] is dash.no_update


def test_a_tap_still_fills_a_closed_editor_that_holds_no_edits(populate):
    out = populate("editor-tap-store", dirty=False, tapped_node={"id": "B"}, left_panel=None)

    assert out["name"] == "B" and out["unsaved_open"] is False


def test_an_empty_click_still_blanks_a_closed_editor_that_holds_no_edits(populate):
    out = populate("background-click-input", dirty=False, left_panel=None)

    assert out["name"] == "" and out["original_name"] is None


def test_an_empty_click_asks_when_the_open_editor_holds_edits(populate):
    assert _asked(populate("background-click-input"), {"kind": "background"})


# --- The Goals sidebar's + --------------------------------------------------

def test_the_goals_plus_starts_a_blank_goal(populate):
    # It only set the type, which turned the node the form held into a Goal
    # and left its name and everything else in place.
    out = populate("btn-goals-sidebar-new", dirty=False, goal_new_clicks=1)

    assert out["n_type"] == "Goal" and out["time_mode"] == ["inherited"]
    assert out["name"] == "" and out["desc"] == "" and out["original_name"] is None
    assert out["snapshot"]["n_type"] == "Goal"  # so the blank form counts as clean


@pytest.mark.parametrize("answer, values", [
    ("btn-unsaved-discard", {"discard_clicks": 1}),
    ("editor-save-result-store", {"save_result": {"via": "btn-unsaved-save"}}),
])
def test_answering_the_dialog_goes_on_to_the_blank_goal(populate, answer, values):
    out = populate(answer, pending_nav={"kind": "new", "goal": True}, **values)

    assert out["n_type"] == "Goal" and out["name"] == ""
    assert out["unsaved_open"] is False and out["pending_nav"] is None


def test_discard_goes_on_to_the_node_edit_asked_for(populate):
    asked = populate("edit-trigger-input", edit_trigger_val="B|1")
    out = populate("btn-unsaved-discard", discard_clicks=1, pending_nav=asked["pending_nav"])

    assert out["name"] == "B" and out["original_name"] == "B"


# --- The dialog itself ------------------------------------------------------

def test_keep_editing_forgets_where_the_dialog_was_going(populate):
    # Otherwise a later close's Discard would load the node a cancelled tap
    # was heading for, instead of closing.
    out = populate("btn-unsaved-cancel", pending_nav={"kind": "tap", "name": "B"})
    assert out["pending_nav"] is None and out["unsaved_open"] is False
    assert out["name"] is dash.no_update


@pytest.mark.parametrize("trigger, values", [
    ("btn-close-editor", {}),
    ("editor-close-ask", {"close_asked": 1}),
])
def test_a_close_with_unsaved_edits_asks_and_stays(populate, trigger, values):
    out = populate(trigger, **values)
    assert _asked(out, {"kind": "close"})
    assert out["close_request"] is dash.no_update


@pytest.mark.parametrize("trigger, values", [
    ("btn-close-editor", {}),
    ("editor-close-ask", {"close_asked": 1}),
])
def test_a_clean_close_asks_nothing_and_keeps_the_form(populate, trigger, values):
    out = populate(trigger, dirty=False, **values)
    assert out["close_request"]["close"] == "editor"
    assert out["unsaved_open"] is dash.no_update
    assert out["name"] is dash.no_update


def test_the_close_ask_counts_when_it_arrives_with_the_click(populate):
    """Dash merges the two into one run, and the click is what's named first."""
    fired = ["btn-add", "editor-close-ask"]
    assert _asked(populate(fired, close_asked=1, add_clicks=2), {"kind": "close"})
    out = populate(fired, dirty=False, close_asked=1, add_clicks=2)
    assert out["close_request"]["close"] == "editor"


def test_the_toolbar_icon_alone_closes_nothing(populate):
    """left_panel.js sends editor-close-ask when this click found the editor
    open. The store can already say what the click did by the time this runs."""
    out = populate("btn-add", add_clicks=2)
    assert out["close_request"] is dash.no_update
    assert out["unsaved_open"] is dash.no_update


def test_the_dialogs_save_waits_for_the_commit(populate):
    """A refused save has to keep the form, so nothing moves on at the click."""
    out = populate("btn-unsaved-save", pending_nav={"kind": "close"})
    assert out["unsaved_open"] is False
    assert out["pending_nav"] is dash.no_update
    assert out["name"] is dash.no_update
    assert out["close_request"] is dash.no_update


@pytest.mark.parametrize("kind", ["close", "background"])
def test_discard_closes_and_leaves_a_blank_form(populate, kind):
    out = populate("btn-unsaved-discard", discard_clicks=1, pending_nav={"kind": kind})
    assert out["close_request"]["close"] == "editor"
    assert out["name"] == "" and out["original_name"] is None
    assert out["search"] is None, "the picker doesn't name a node the form isn't showing"


@pytest.mark.parametrize("kind", ["close", "background"])
def test_a_committed_save_closes_too(populate, kind):
    out = populate("editor-save-result-store", pending_nav={"kind": kind},
                   save_result={"name": "A", "via": "btn-unsaved-save", "ts": 1})
    assert out["close_request"]["close"] == "editor"


@pytest.mark.parametrize("first", ["btn-unsaved-save", "search-node"])
def test_the_commit_counts_when_it_arrives_with_something_else(populate, first):
    """Dash holds this callback back during a save, and merges what fired."""
    out = populate([first, "editor-save-result-store"], pending_nav={"kind": "close"},
                   save_result={"name": "A", "via": "btn-unsaved-save", "ts": 1})
    assert out["close_request"]["close"] == "editor"


def test_a_rename_emptying_the_picker_is_not_a_request_for_a_blank_form(populate):
    out = populate(["search-node", "editor-save-result-store"], search_val=None,
                   save_result={"name": "A", "via": "btn-save", "ts": 1})
    assert out["name"] is dash.no_update and out["unsaved_open"] is dash.no_update


def test_another_saves_result_moves_nothing(populate):
    out = populate("editor-save-result-store", pending_nav={"kind": "close"},
                   save_result={"name": "A", "via": "btn-save", "ts": 1})
    assert out["close_request"] is dash.no_update
    assert out["name"] is dash.no_update


def test_going_on_to_a_node_deleted_meanwhile_starts_a_blank_form(populate):
    out = populate("btn-unsaved-discard", discard_clicks=1,
                   pending_nav={"kind": "tap", "name": "Gone"})
    assert out["name"] == "" and out["original_name"] is None


def test_what_does_nothing_sends_no_options(populate):
    """They're about 230 KB, and only a form or an opening editor needs them."""
    for out in (populate("btn-close-editor"), populate("btn-unsaved-cancel"),
                populate("background-click-input", left_panel=None)):
        assert out["e_needs_h_options"] is dash.no_update
