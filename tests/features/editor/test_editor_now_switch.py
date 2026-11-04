"""The editor's Now switch: part of the form, so it waits for Save."""
import dash
import pytest

from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.form import (
    NEW_NODE_SNAPSHOT, editor_form_values_from, is_form_dirty_vs_snapshot, rebase,
)
from skilltree.features.editor.save import save_editor_form
from skilltree.store import settings
from skilltree.store.events import EventManager
from support.callbacks import registered
from support.editor_forms import editor_form, merged
from support.graphs import graph as plain_graph


@pytest.fixture
def graph():
    return plain_graph("A", "B")


@pytest.fixture
def handlers(graph):
    return registered(register_editor_callbacks)


def _form(**fields):
    return editor_form(**{**dict(
        name="A", n_type="Learn", desc="", context="Mind", status_done=[], val=5,
        interest=5, diff=5, time_o=1, time_m=2, time_p=4, time_unit="hours",
        link_values=[], link_ids=[], aliases=[]), **fields})


def _save(graph, *, now, loaded):
    form = _form(now=["now"] if now else [])
    return save_editor_form(
        graph, EventManager(graph), form, "A", original_name="A",
        pristine_snapshot={"name": "A", "now": ["now"] if loaded else []},
        bridge_pending=None, reopen_confirmed=False, via="btn-save", now=now)


def _put_on_now(graph, name):
    node = graph.get_node(name)
    node.now = 1
    graph.update_node(node)


def test_flipping_the_switch_writes_nothing(graph, handlers):
    assert handlers["refuse_now_switch"](["now"], "A", []) == (dash.no_update, dash.no_update)
    assert graph.get_node("A").now == 0


def test_save_adds_the_node_to_now(graph):
    saved = _save(graph, now=True, loaded=False)
    assert graph.get_node("A").now > 0
    assert saved.result["now"] == ["now"]


def test_save_takes_the_node_off_now(graph):
    _put_on_now(graph, "A")
    saved = _save(graph, now=False, loaded=True)
    assert graph.get_node("A").now == 0
    assert saved.result["now"] == []


def test_a_change_from_the_menu_survives_an_untouched_switch(graph):
    # The form loaded with Now off, and the menu has added it since.
    _put_on_now(graph, "A")
    _save(graph, now=False, loaded=False)
    assert graph.get_node("A").now > 0


def test_the_switch_counts_as_an_unsaved_edit(graph):
    snapshot = {**NEW_NODE_SNAPSHOT, "name": "A"}
    form = editor_form_values_from(_form(now=[]))
    flipped = editor_form_values_from(_form(now=["now"]))
    baseline = {**snapshot, **{k: form[k] for k in form if k in snapshot}}
    assert not is_form_dirty_vs_snapshot(baseline, form)
    assert is_form_dirty_vs_snapshot(baseline, flipped)


def test_a_full_list_bounces_the_switch_at_once(graph, handlers):
    settings.NOW_NODE_CAP.set(1)
    _put_on_now(graph, "B")
    switch, toast = handlers["refuse_now_switch"](["now"], "A", [])
    assert switch == [] and toast.startswith("refused|")
    assert graph.get_node("A").now == 0


def test_a_node_already_on_a_full_list_keeps_its_switch(graph, handlers):
    settings.NOW_NODE_CAP.set(1)
    _put_on_now(graph, "A")
    assert handlers["refuse_now_switch"](["now"], "A", []) == (dash.no_update, dash.no_update)


def test_a_list_that_filled_up_meanwhile_doesnt_refuse_the_save(graph):
    settings.NOW_NODE_CAP.set(1)
    _put_on_now(graph, "B")
    saved = _save(graph, now=True, loaded=False)
    assert "at its cap" in saved.message
    assert graph.get_node("A").now == 0
    assert saved.result["now"] == []


def test_the_switch_goes_off_when_the_save_could_not_add_it(graph, handlers):
    saved = _form(now=["now"])
    result = {"name": "A", "via": "btn-save", "form": saved, "now": [], "ts": 1}
    *_, snapshot, now = handlers["sync_original_name_after_save"](result, "A", saved)
    assert now == [] and snapshot["now"] == []


def test_a_save_that_asked_before_reopening_holds_the_switch(graph, handlers):
    saved = _form(now=["now"])
    result = {"name": "A", "via": "btn-save", "form": saved, "now": [],
              "reopen_asked": True, "ts": 1}
    *_, snapshot, now = handlers["sync_original_name_after_save"](result, "A", saved)
    assert now is dash.no_update and snapshot["now"] == []


def _merge(graph, *, switch, loaded):
    return merged(rebase(graph.get_node("A"), {}, {"status_done": [], "now": switch},
                         {"name": "A", "status_done": [], "now": loaded}))


def test_the_switch_follows_a_change_from_the_menu(graph):
    _put_on_now(graph, "A")
    assert _merge(graph, switch=[], loaded=[]) == ({"now": ["now"]}, {"now": ["now"]})


def test_the_switch_keeps_an_unsaved_flip_when_the_menu_changes_it(graph):
    # Loaded on, and then a save elsewhere takes it off.
    assert _merge(graph, switch=["now"], loaded=["now"]) == ({"now": []}, {"now": []})
    # Loaded off, flipped on, and then the menu adds it too.
    _put_on_now(graph, "A")
    assert _merge(graph, switch=["now"], loaded=[]) == ({}, {"now": ["now"]})


def test_a_node_cant_save_onto_a_context_that_no_longer_exists(graph):
    with pytest.raises(ValueError, match="'Gone' is no longer a context"):
        save_editor_form(graph, EventManager(graph), _form(context="Gone"), "A", original_name="A",
                         pristine_snapshot={"name": "A", "context": "Mind"},
                         bridge_pending=None, reopen_confirmed=False, via="btn-save")
    assert graph.get_node("A").context == "Mind"


def test_a_node_cant_save_onto_a_subcontext_that_no_longer_exists(graph):
    with pytest.raises(ValueError, match="'Gone' is no longer a subcontext of 'Mind'"):
        save_editor_form(graph, EventManager(graph), _form(subctx="Gone"), "A", original_name="A",
                         pristine_snapshot={"name": "A", "context": "Mind", "subctx": ""},
                         bridge_pending=None, reopen_confirmed=False, via="btn-save")
