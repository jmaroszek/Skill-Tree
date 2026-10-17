"""The core engine's handlers, called directly with a Request."""
import dash

from support.editor_forms import editor_form
from skilltree.domain.models import STATUS_DONE, STATUS_OPEN, Node
from skilltree.engine.handlers import Outcome, Request, handle
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED

OPEN_EDITOR = {'transform': 'translateX(0px)'}


def _request(services, trigger, **fields):
    values = dict(graph=services.graph, events=services.events, trigger=trigger,
                  form=editor_form(), original_name=None, pristine_snapshot=None,
                  bridge_pending=None, reopen_confirmed=False, tapped_node=None,
                  toggle_done_trigger_data=None, pending_undo_done=None,
                  group_delete_data=None,
                  sidebars=(dict(OPEN_EDITOR), {'display': 'none'}, {'display': 'none'}))
    values.update(fields)
    return Request(**values)


def _node(name, **fields):
    values = dict(name=name, type="Learn", description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status=STATUS_OPEN, context="Mind")
    values.update(fields)
    return Node(**values)


def test_anything_else_changes_nothing(services):
    assert handle(_request(services, 'filter-context')) == Outcome()


def test_a_save_without_a_name_closes_a_blank_form(services):
    outcome = handle(_request(services, 'btn-save', form=editor_form(n_type='Learn')))
    assert outcome.response.message == ""
    assert outcome.response.editor_style['transform'] == SIDEBAR_TRANSLATE_CLOSED


def test_a_save_without_a_name_says_so_when_the_form_has_content(services):
    outcome = handle(_request(services, 'btn-save',
                              form=editor_form(n_type='Learn', desc='notes')))
    assert outcome.response.message == "Error: Node name is required."
    assert services.graph.get_all_nodes() == []


def test_a_save_may_not_take_another_nodes_name(services):
    services.graph.add_node(_node("Taken"))
    outcome = handle(_request(services, 'btn-save',
                              form=editor_form(name="Taken", n_type='Learn')))
    assert outcome.response.message.startswith("Error: A node named 'Taken' already exists")
    assert outcome.response.editor_style == OPEN_EDITOR
    # Nothing that renders the graph or opens a modal.
    assert outcome.response.elements is dash.no_update
    assert outcome.response.undo_open is dash.no_update


def test_delete_without_a_loaded_node_deletes_nothing(services):
    services.graph.add_node(_node("Typed Over"))
    outcome = handle(_request(services, 'btn-node-delete-confirm',
                              form=editor_form(name="Typed Over")))
    assert outcome == Outcome()
    assert services.graph.get_node("Typed Over") is not None


def test_a_sleeping_selection_cannot_be_marked_done(services):
    services.graph.add_node(_node("Asleep", dormant=1))
    outcome = handle(_request(services, 'toggle-done-trigger-input',
                              toggle_done_trigger_data='["Asleep"]|1'))
    assert outcome.message.startswith("Error: a sleeping node can't be marked Done")


def test_reopening_a_node_with_done_dependents_asks_first(services):
    graph = services.graph
    graph.add_node(_node("First", status=STATUS_DONE))
    graph.add_node(_node("Second", status=STATUS_DONE))
    graph.add_edge("First", "Second", "Needs_Hard")

    outcome = handle(_request(services, 'btn-toggle-done-node', tapped_node={'id': 'First'}))
    assert outcome.response.undo_open is True
    assert outcome.response.undo_pending == ["First"]
    assert graph.get_node("First").status == STATUS_DONE

    confirmed = handle(_request(services, 'btn-undo-done-confirm', pending_undo_done=["First"]))
    assert confirmed.message == "Un-marked 'First' (Done → Open)"
    assert graph.get_node("First").status == STATUS_OPEN
    assert graph.get_node("Second").status != STATUS_DONE


def test_marking_one_node_done_reports_it_for_calibration(services):
    services.graph.add_node(_node("Task"))
    outcome = handle(_request(services, 'btn-toggle-done-node', tapped_node={'id': 'Task'}))
    assert outcome.completed == "Task"
    assert services.graph.get_node("Task").status == STATUS_DONE
