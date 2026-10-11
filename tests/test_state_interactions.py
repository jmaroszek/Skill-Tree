"""State invariants at the boundaries between editing, events, Now and history."""
from datetime import date

import dash
import pytest

import callbacks
import database
import event_callbacks
import event_manager
from config import ConfigManager
from editor_forms import call
from event_manager import EventManager
from graph_manager import GraphManager
from models import Event
from test_atomic_saves import graph, node, save


@pytest.fixture(autouse=True)
def clean_suggestions():
    GraphManager._auto_done_candidates = []
    yield
    GraphManager._auto_done_candidates = []


@pytest.fixture(scope='module')
def handlers():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    event_callbacks.register_event_callbacks(app)
    result = {}
    for spec in app.callback_map.values():
        fn = spec.get('callback')
        while hasattr(fn, '__wrapped__'):
            fn = fn.__wrapped__
        if fn is not None:
            result[fn.__name__] = fn
    return result


def complete(manager, name):
    item = manager.get_node(name)
    item.status = 'Done'
    manager.update_node(item)


def history(manager, name):
    return [entry['event_type'] for entry in manager.get_node_lifecycle_events(name)]


def run_core(handlers, monkeypatch, trigger='btn-save', **state):
    monkeypatch.setattr(callbacks, 'get_trigger_id', lambda: trigger)
    monkeypatch.setattr(callbacks, 'get_all_triggered_ids', lambda: {trigger})
    form = dict(n_type='Learn', desc='edited', context='Mind', status_done=[],
                val=5, interest=5, diff=5, time_o=1, time_m=2, time_p=4,
                time_unit='hours', link_values=[], link_ids=[], aliases=[],
                ed_style={'transform': 'translateX(0px)'})
    form.update(state)
    return callbacks.CoreResponse(*call(handlers['core_engine'], **form))


def test_auto_completion_reaches_the_open_editor(handlers):
    manager = graph('Child')
    manager.add_node(node('Goal', type='Goal'))
    manager.add_edge('Child', 'Goal', 'Needs_Hard')
    complete(manager, 'Child')
    assert manager.complete_suggested_node('Goal')
    switch, snapshot, now = handlers['sync_editor_status'](
        1, 'Goal', [], {'name': 'Goal', 'desc': 'unsaved notes', 'status_done': []}, [])
    assert switch == ['Done'] and now is dash.no_update
    # Only the status key is patched: the rest may be newer than this copy.
    ops = snapshot.to_plotly_json()['operations']
    assert [(op['operation'], op['location'], op['params']['value']) for op in ops] == [
        ('Assign', ['status_done'], ['Done'])]


def test_editor_keeps_a_deliberate_unsaved_flip_but_follows_now(handlers):
    manager = graph('A')
    item = manager.get_node('A')
    item.now = 1
    manager.update_node(item)
    complete(manager, 'A')
    switch, snapshot, now = handlers['sync_editor_status'](
        1, 'A', ['Done'], {'name': 'A', 'status_done': []}, ['now'])
    assert switch is dash.no_update  # already shows what is stored
    assert now == []
    # The user flipped Done off after loading a Done node: their flip stays.
    switch, _, _ = handlers['sync_editor_status'](
        2, 'A', [], {'name': 'A', 'status_done': ['Done']}, [])
    assert switch is dash.no_update


def test_save_preserves_completion_even_before_editor_refresh(handlers, monkeypatch):
    manager = graph('Child')
    manager.add_node(node('Goal', type='Goal'))
    manager.add_edge('Child', 'Goal', 'Needs_Hard')
    complete(manager, 'Child')
    assert manager.complete_suggested_node('Goal')
    result = run_core(handlers, monkeypatch, name='Goal', original_name='Goal',
                      n_type='Goal', e_needs_h=['Child'], status_done=[],
                      pristine_snapshot={'name': 'Goal', 'status_done': []})
    assert manager.get_node('Goal').status == 'Done'
    assert manager.get_node('Goal').description == 'edited'
    assert history(manager, 'Goal') == ['completed']
    assert result.editor_done == ['Done']
    assert result.save_result['status_done'] == ['Done']


def test_save_preserves_a_deliberate_unsaved_reopen(handlers, monkeypatch):
    manager = graph('A')
    complete(manager, 'A')
    run_core(handlers, monkeypatch, name='A', original_name='A', status_done=[],
             pristine_snapshot={'name': 'A', 'status_done': ['Done']})
    assert manager.get_node('A').status == 'Open'


def test_add_to_event_ends_now_and_cannot_bypass_cap_on_wake(handlers):
    manager = graph('A', 'B')
    ConfigManager.set_now_node_cap(1)
    item = manager.get_node('A')
    item.now = 1
    manager.update_node(item)
    events = EventManager()
    events.add_event(Event('Later'))
    handlers['save_add_to_event'](1, ['A'], 'Later', 0, 'days', [])
    assert manager.get_node('A').now == 0
    assert history(manager, 'A') == ['now_started', 'now_stopped']
    item = manager.get_node('B')
    item.now = 1
    manager.update_node(item)
    events.trigger_event_manually('Later')
    assert [n.name for n in manager.get_now_nodes()] == ['B']
    assert not manager.get_node('A').dormant


def test_event_now_intent_still_obeys_cap_after_sleeping(handlers):
    manager = graph('A', 'B')
    ConfigManager.set_now_node_cap(1)
    handlers['handle_now_trigger']('["A"]|1')
    events = EventManager()
    events.add_event(Event('Later'))
    handlers['save_add_to_event'](1, ['A'], 'Later', 0, 'days', ['on'])
    handlers['handle_now_trigger']('["B"]|2')
    result = events.trigger_event_manually('Later')
    assert result['now_skipped'] == ['A']
    assert [n.name for n in manager.get_now_nodes()] == ['B']


@pytest.mark.parametrize('via', ['menu', 'editor', 'manager'])
@pytest.mark.parametrize('state', ['Done', 'Dormant'])
def test_ineligible_nodes_cannot_enter_now(handlers, via, state):
    manager = graph('A')
    if state == 'Done':
        complete(manager, 'A')
    else:
        EventManager().add_event(Event('Later'))
        EventManager().add_node_to_event('Later', 'A')
    before = history(manager, 'A')
    if via == 'menu':
        handlers['handle_now_trigger']('["A"]|1')
    elif via == 'editor':
        handlers['dispatch_now_toggle'](['now'], 'A')
    else:
        item = manager.get_node('A')
        item.now = 1
        manager.update_node(item)
    assert manager.get_node('A').now == 0
    assert history(manager, 'A') == before


def test_sleeping_completion_is_refused_without_firing_events(handlers, monkeypatch):
    manager = graph('A', 'Reward')
    events = EventManager()
    events.add_event(Event('Later'))
    events.add_node_to_event('Later', 'A')
    events.add_event(Event('On Done', trigger_nodes=['A']))
    events.add_node_to_event('On Done', 'Reward')
    result = run_core(handlers, monkeypatch, 'toggle-done-trigger-input',
                      toggle_done_trigger_data='["A"]|1')
    assert result.message.startswith('Error:')
    assert manager.get_node('A').status == 'Open'
    assert events.get_event('On Done').status == 'Pending'
    assert history(manager, 'A') == []


def test_done_node_cannot_be_attached_by_a_stale_event_dialog(handlers):
    manager = graph('A')
    EventManager().add_event(Event('Later'))
    complete(manager, 'A')
    result = handlers['save_add_to_event'](1, ['A'], 'Later', 0, 'days', [])
    assert 'Reopen' in result[1]
    assert not manager.get_node('A').dormant
    assert EventManager().get_node_membership('A') is None


def test_removing_the_blocker_and_completing_is_one_valid_save():
    manager = graph('A', 'B')
    manager.add_edge('A', 'B', 'Needs_Hard')
    save(manager, 'B', status_done=['Done'])
    assert manager.get_node('B').status == 'Done'
    assert manager.get_edges() == []
    assert history(manager, 'B') == ['completed']


@pytest.mark.parametrize('existing', [False, True])
def test_new_blocker_and_completion_refuse_the_entire_save(handlers, monkeypatch, existing):
    manager = graph('A', *(['B'] if existing else []))
    ConfigManager.set_time_calibration_enabled(True)
    result = run_core(handlers, monkeypatch, name='B',
                      original_name='B' if existing else None,
                      status_done=['Done'], e_needs_h=['A'])
    assert result.message.startswith('Error:')
    assert result.save_result is dash.no_update
    assert result.calibration_open is not True
    assert manager.get_edges() == []
    assert history(manager, 'B') == []
    assert (manager.get_node('B').status if existing else manager.get_node('B')) == (
        'Open' if existing else None)


def test_wake_and_complete_can_share_a_save(handlers, monkeypatch):
    manager = graph('A')
    events = EventManager()
    events.add_event(Event('Later'))
    events.add_node_to_event('Later', 'A')
    run_core(handlers, monkeypatch, name='A', original_name='A',
             status_done=['Done'], dormancy={'dormant': False})
    assert manager.get_node('A').status == 'Done'
    assert not manager.get_node('A').dormant
    assert events.get_node_membership('A') is None


@pytest.mark.parametrize('change', ['prerequisite', 'dormant', 'type', 'no_prerequisites'])
def test_stale_auto_done_is_not_accepted_or_displayed(handlers, monkeypatch, change):
    manager = graph('Child')
    manager.add_node(node('Goal', type='Goal'))
    manager.add_edge('Child', 'Goal', 'Needs_Hard')
    complete(manager, 'Child')
    candidates = manager.pop_auto_done_candidates()
    assert candidates == ['Goal']
    item = manager.get_node('Goal' if change != 'prerequisite' else 'Child')
    if change == 'prerequisite':
        item.status = 'Open'
        manager.update_node(item)
    elif change == 'dormant':
        EventManager().add_event(Event('Later'))
        EventManager().add_node_to_event('Later', 'Goal')
    elif change == 'type':
        item.type, item.time_mode = 'Learn', 'manual'
        manager.update_node(item)
    else:
        manager.remove_edge('Child', 'Goal', 'Needs_Hard')
    monkeypatch.setattr(callbacks, 'get_trigger_id', lambda: 'btn-auto-done-confirm')
    result = handlers['manage_auto_done_modal'](1, 1, 0, candidates, 'tab-next', None)
    assert manager.get_node('Goal').status != 'Done'
    assert result[0] is False and result[2] == []
    monkeypatch.setattr(callbacks, 'get_trigger_id', lambda: 'graph-version-store')
    result = handlers['manage_auto_done_modal'](2, 0, 0, candidates, 'tab-next', None)
    assert result[0] is False and result[2] == []


def test_dormant_container_is_never_suggested():
    manager = graph('Child')
    manager.add_node(node('Goal', type='Goal'))
    manager.add_edge('Child', 'Goal', 'Needs_Hard')
    EventManager().add_event(Event('Later'))
    EventManager().add_node_to_event('Later', 'Goal')
    complete(manager, 'Child')
    assert manager.pop_auto_done_candidates() == []


@pytest.mark.parametrize('via', ['editor', 'manager'])
def test_new_done_has_completion_date_and_history(handlers, monkeypatch, via):
    manager = GraphManager()
    if via == 'editor':
        run_core(handlers, monkeypatch, name='A', status_done=['Done'])
    else:
        manager.add_node(node('A', status='Done'))
    assert manager.get_node('A').done_date == date.today().isoformat()
    assert history(manager, 'A') == ['completed']


@pytest.fixture
def october_11(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 11)
    monkeypatch.setattr(event_manager, 'date', Today)


def test_overdue_date_event_wakes_overdue_nodes_immediately(october_11):
    manager = graph('Overdue', 'Future')
    events = EventManager()
    events.add_event(Event('October', trigger_date='2026-10-01'))
    events.add_node_to_event('October', 'Overdue', 2, now_on_trigger=True)
    events.add_node_to_event('October', 'Future', 20)
    events.check_scheduled_triggers()
    assert not manager.get_node('Overdue').dormant
    assert manager.get_node('Overdue').now > 0
    woke = {row['node'].name: row['activation_date'] for row in events.get_event_nodes('October')}
    assert woke['Overdue'] == '2026-10-03'
    assert events.get_node_membership('Future')['activation_date'] == '2026-10-21'
    # A fired event's date can't move its nodes again.
    events.update_event('October', Event('Renamed', status='Triggered', trigger_date='2026-11-01'))
    events.check_scheduled_triggers()
    assert events.get_node_membership('Future')['activation_date'] == '2026-10-21'


def test_late_manual_firing_also_counts_from_the_date(october_11):
    graph('A')
    events = EventManager()
    events.add_event(Event('Past', trigger_date='2026-10-01'))
    events.add_node_to_event('Past', 'A', 20)
    events.trigger_event_manually('Past')
    assert events.get_node_membership('A')['activation_date'] == '2026-10-21'


def test_manual_early_firing_anchors_delays_to_today(october_11):
    graph('A')
    events = EventManager()
    events.add_event(Event('Later', trigger_date='2026-12-01'))
    events.add_node_to_event('Later', 'A', 2)
    events.trigger_event_manually('Later')
    assert events.get_node_membership('A')['activation_date'] == '2026-10-13'


def test_existing_missing_done_dates_stay_unknown():
    manager = graph('A')
    with database.get_connection() as conn:
        conn.execute("UPDATE Nodes SET status='Done', done_date=NULL WHERE name='A'")
    database._initialized = False
    database.init_db()
    item = manager.get_node('A')
    assert item.done_date is None
    item.description = 'edited'
    manager.update_node(item)
    assert manager.get_node('A').done_date is None
