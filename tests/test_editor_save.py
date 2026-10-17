"""The node editor's Save, called directly: no Dash and no callback."""
import pytest

from support.editor_forms import editor_form
from skilltree.domain.models import STATUS_BLOCKED, STATUS_DONE, STATUS_OPEN
from skilltree.features.editor.form import EDITOR_FORM, build_editor_snapshot
from skilltree.features.editor.save import save_editor_form
from skilltree.store.commands import ReopensDoneNodes


def _form(**fields):
    values = dict(n_type='Learn', desc='', context='Mind', status_done=[], val=5,
                  interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                  time_unit='hours', link_values=[], link_ids=[], aliases=[])
    values.update(fields)
    return editor_form(**values)


def _save(services, name, form=None, *, original_name=None, pristine_snapshot=None,
          reopen_confirmed=False):
    return save_editor_form(
        services.graph, services.events, form or _form(), name,
        original_name=original_name, pristine_snapshot=pristine_snapshot,
        bridge_pending=None, reopen_confirmed=reopen_confirmed, via='btn-save')


def _edges(graph):
    return {(e['source'], e['target'], e['type']) for e in graph.get_edges()}


def test_a_new_node_saves_with_its_prerequisites(services):
    _save(services, 'Basics')
    saved = _save(services, 'Applied', _form(e_needs_h=['Basics']))

    assert ('Basics', 'Applied', 'Needs_Hard') in _edges(services.graph)
    assert services.graph.get_node('Applied').status == STATUS_BLOCKED
    assert saved.result['name'] == 'Applied'
    assert saved.result['via'] == 'btn-save'
    assert saved.result['status_done'] == []
    assert saved.completed is None and saved.undo_pending is None


def test_a_refused_estimate_saves_nothing(services):
    with pytest.raises(ValueError):
        _save(services, 'Backwards', _form(time_o=5, time_m=2, time_p=1))
    assert services.graph.get_node('Backwards') is None


def test_only_a_new_completion_is_reported(services):
    saved = _save(services, 'Finished', _form(status_done=[STATUS_DONE]))
    assert saved.completed == 'Finished'
    assert saved.result['status_done'] == [STATUS_DONE]

    again = _save(services, 'Finished', _form(status_done=[STATUS_DONE]),
                  original_name='Finished',
                  pristine_snapshot={'name': 'Finished', 'status_done': [STATUS_DONE]})
    assert again.completed is None


def test_unmarking_a_node_whose_dependents_are_done_waits_for_the_user(services):
    _save(services, 'First', _form(status_done=[STATUS_DONE]))
    _save(services, 'Second', _form(e_needs_h=['First'], status_done=[STATUS_DONE]))

    # The editor as it loaded First, with the Done switch then turned off.
    snapshot = build_editor_snapshot(services.graph, services.events, 'First')
    loaded = {key: value for key, value in snapshot.items() if key in EDITOR_FORM}
    saved = _save(services, 'First', _form(**{**loaded, 'status_done': []}),
                  original_name='First', pristine_snapshot=snapshot)

    # It stays Done until the undo-Done modal's answer.
    assert services.graph.get_node('First').status == STATUS_DONE
    assert saved.undo_pending == ['First']
    assert saved.undo_downstream == ['Second']


def test_a_save_that_would_reopen_done_nodes_asks_first(services):
    _save(services, 'Goal Reached', _form(status_done=[STATUS_DONE]))

    with pytest.raises(ReopensDoneNodes) as asked:
        _save(services, 'Missing Step', _form(e_supp_h=['Goal Reached']))
    assert asked.value.names == ['Goal Reached']
    assert services.graph.get_node('Missing Step') is None

    _save(services, 'Missing Step', _form(e_supp_h=['Goal Reached']), reopen_confirmed=True)
    assert services.graph.get_node('Missing Step').status == STATUS_OPEN
    assert services.graph.get_node('Goal Reached').status == STATUS_BLOCKED
