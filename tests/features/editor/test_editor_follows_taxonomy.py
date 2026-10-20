"""The editor's context follows a rename or a move made in Settings.

A Settings save carries a renamed context, or a subcontext moved to another,
onto every node. The editor open on one of them still held the names it had
loaded, and the next Save wrote them back: the node went back to a context
Settings no longer has, and lost its subcontext, which that context doesn't
list.
"""
import dash
import pytest

from skilltree.domain.models import Node, STATUS_OPEN
from skilltree.engine import callbacks
from skilltree.features.editor.callbacks import register_editor_callbacks
from skilltree.features.editor.form import EDITOR_FORM, build_editor_snapshot
from skilltree.store import settings
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from support.callbacks import registered
from support.editor_forms import call
from support.triggers import fire


@pytest.fixture
def manager():
    manager = GraphManager()
    manager.add_node(Node(name="Sleep Theory", type="Learn", description="", value=5,
                          time_o=1.0, time_m=2.0, time_p=4.0, interest=5,
                          difficulty=5, status=STATUS_OPEN, context="Health",
                          subcontext="Sleep"))
    return manager


@pytest.fixture
def handlers():
    return registered(callbacks.register_engine_callbacks, register_editor_callbacks)


def _loaded(manager):
    """The editor's form and snapshot as populate_editor leaves them."""
    snapshot = build_editor_snapshot(manager, EventManager(GraphManager()), "Sleep Theory")
    form = {key: snapshot[key] for key in EDITOR_FORM if key in snapshot}
    return form, snapshot


def _rename_context(manager, old, new):
    """What a Settings save writes for a context renamed in its editor."""
    subcontexts = settings.SUBCONTEXTS.get()
    subcontexts[new] = subcontexts.pop(old)
    settings.CONTEXTS.set([new if c == old else c for c in settings.CONTEXTS.get()])
    settings.SUBCONTEXTS.set(subcontexts)
    manager.apply_taxonomy_migration({old: new}, [])


def _rename_subcontext(manager, context, old, new):
    subcontexts = settings.SUBCONTEXTS.get()
    subcontexts[context] = [new if s == old else s for s in subcontexts[context]]
    settings.SUBCONTEXTS.set(subcontexts)
    manager.apply_taxonomy_migration({}, [(context, old, context, new)])


def _save(handlers, form, snapshot, **edits):
    fire("btn-save")
    values = {**form, "link_values": [], "link_ids": [], **edits}
    return callbacks.CoreResponse(*call(
        handlers["core_engine"], original_name="Sleep Theory",
        pristine_snapshot=snapshot, ed_style={"transform": "translateX(0px)"},
        **values))


def _stored(manager):
    node = manager.get_node("Sleep Theory")
    return node.context, node.subcontext


def test_a_save_after_a_context_rename_keeps_the_new_name(manager, handlers):
    form, snapshot = _loaded(manager)
    _rename_context(manager, "Health", "Body")

    _save(handlers, form, snapshot, desc="an unrelated edit")

    assert manager.get_node("Sleep Theory").description == "an unrelated edit"
    assert _stored(manager) == ("Body", "Sleep")


def test_a_save_after_a_subcontext_rename_keeps_the_new_name(manager, handlers):
    form, snapshot = _loaded(manager)
    _rename_subcontext(manager, "Health", "Sleep", "Rest")

    _save(handlers, form, snapshot, desc="an unrelated edit")

    assert _stored(manager) == ("Health", "Rest")


def test_a_context_the_user_picked_is_saved(manager, handlers):
    form, snapshot = _loaded(manager)
    _rename_context(manager, "Health", "Body")

    _save(handlers, form, snapshot, context="Mind", subctx="Habits")

    assert _stored(manager) == ("Mind", "Habits")


def test_the_open_editor_shows_the_new_names(manager, handlers):
    form, snapshot = _loaded(manager)
    _rename_context(manager, "Health", "Body")

    context, subctx, patch = handlers["follow_editor_taxonomy"](
        [], snapshot, "Sleep Theory", form["context"], form["subctx"])

    assert (context, subctx) == ("Body", "Sleep")
    patched = {**snapshot}
    for operation in patch.to_plotly_json()["operations"]:
        patched[operation["location"][0]] = operation["params"]["value"]
    assert (patched["context"], patched["subctx"]) == ("Body", "Sleep")


def test_a_context_being_edited_stays_while_the_baseline_follows(manager, handlers):
    _, snapshot = _loaded(manager)
    _rename_context(manager, "Health", "Body")

    context, subctx, patch = handlers["follow_editor_taxonomy"](
        [], snapshot, "Sleep Theory", "Mind", "Habits")

    assert (context, subctx) == (dash.no_update, dash.no_update)
    assert patch is not dash.no_update


def test_nothing_changes_when_the_editor_already_agrees(manager, handlers):
    form, snapshot = _loaded(manager)

    assert handlers["follow_editor_taxonomy"](
        [], snapshot, "Sleep Theory", form["context"], form["subctx"]) == (
        dash.no_update,) * 3


def test_another_nodes_snapshot_is_left_alone(manager, handlers):
    form, snapshot = _loaded(manager)
    _rename_context(manager, "Health", "Body")

    assert handlers["follow_editor_taxonomy"](
        [], {**snapshot, "name": "Another"}, "Sleep Theory", form["context"],
        form["subctx"]) == (dash.no_update,) * 3
