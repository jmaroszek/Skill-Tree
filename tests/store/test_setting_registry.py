"""Every stored setting (store/settings.SETTINGS): it reads back what it
stores, hands out copies of its default, and reads its default when the
stored text is unusable."""
import copy

import pytest

from skilltree.domain.names import NAME_FORMAT_TITLE
from skilltree.store import settings
from skilltree.store.graph.state import revisions

# A value each setting stores and reads back unchanged.
SAMPLES = {
    'NODE_TYPES': ['Learn', 'Quest'],
    'CONTEXTS': ['Work', 'Play'],
    'SUBCONTEXTS': {'Work': ['Email', 'Meetings']},
    'CONTEXT_SORT_MODE': 'alphabetical',
    'SUBCONTEXT_SORT_MODE': 'length',
    'CONTEXT_WEIGHTS': {'Work': 2.0},
    'NODE_COLORS': {**settings.DEFAULT_NODE_COLORS, 'Goal': '#123456'},
    'NODE_SHAPES': {'Learn': 'star', 'Goal': 'star'},
    'GRAPH_LAYOUT_DEFAULTS': {'edge_length': 80, 'gravity': 1, 'repulsion': 900},
    'DETAILS_GRAPH_LAYOUT_DEFAULTS': {'edge_length': 60, 'gravity': 0.5, 'repulsion': 800},
    'EVENTS_GRAPH_LAYOUT_DEFAULTS': {'edge_length': 70, 'gravity': 0.1, 'repulsion': 700},
    'SHOW_SCORING_PERF': True,
    'HP_PROFILE': 'Explorer',
    'HYPERPARAMS': {'w_v': 2.0, '_schema': 5},
    'PRIORITY_GOALS': ['A', 'B', 'C'],
    'TIME_SETTINGS': {**settings.DEFAULT_TIME_SETTINGS, 'hours_per_week': 20},
    'TIME_CALIBRATION_ENABLED': False,
    'RATINGS_DEFINITIONS': [{'rating': 1, 'value': 'v', 'interest': 'i', 'effort': 'e'}],
    'REFLECTION_RATINGS_DEFINITIONS': [{'rating': 2, 'value': 'v', 'interest': 'i',
                                        'effort': 'e'}],
    'TITLECASE_LINTER': {'mode': NAME_FORMAT_TITLE, 'enabled': True, 'exclusions': ['of']},
    'GOAL_ORDER': ['B', 'A'],
    'EVENT_ORDER': ['Trip'],
    'LIST_SORTS': {'goals-sort-store': 'alphabetical'},
    'NEXT_TABLE_ROWS': 25,
    'NOW_NODE_CAP': 7,
    'UNBLOCKING_STEPS_PER_NOW': 4,
    'PENDING_EVENT_NOTIFICATIONS': [{'kind': 'fired', 'events': ['Trip']}],
    'ANALYZE_LIMITS': {**settings.DEFAULT_ANALYZE_LIMITS, 'goals': 5},
    'AUTO_BACKUP': False,
    'BACKUP_EXTRA_DIR': 'D:/Sync',
    'WELCOME_DONE': True,
    'GETTING_STARTED_PROGRESS': ['add-node', 'mark-done'],
    'GETTING_STARTED_DISMISSED': True,
    'LAST_APP_VERSION': '1.2.3',
}

ALL = sorted(settings.SETTINGS.values(), key=lambda setting: setting.key)
by_key = pytest.mark.parametrize("setting", ALL, ids=[setting.key for setting in ALL])

# Settings stored as plain text, which read any text as some value.
READS_ANY_TEXT = {'HP_PROFILE', 'BACKUP_EXTRA_DIR', 'LAST_APP_VERSION', 'AUTO_BACKUP',
                  'SHOW_SCORING_PERF', 'TIME_CALIBRATION_ENABLED', 'WELCOME_DONE',
                  'GETTING_STARTED_DISMISSED'}


def test_every_setting_has_a_sample():
    assert set(SAMPLES) == set(settings.SETTINGS)


@by_key
def test_a_setting_reads_back_what_it_stores(setting):
    setting.set(SAMPLES[setting.key])
    assert setting.get() == SAMPLES[setting.key]


@by_key
def test_an_unset_setting_reads_a_copy_of_its_default(setting):
    pristine = copy.deepcopy(setting.default)
    value = setting.get()
    assert value == setting.default
    if isinstance(value, (list, dict)):
        assert value is not setting.default
        # Editing what a getter returns leaves the default alone.
        value.clear()
        assert setting.default == pristine


@by_key
def test_unusable_stored_text_reads_the_default(setting):
    if setting.key in READS_ANY_TEXT:
        pytest.skip("any text is a value")
    settings.write_stored(setting.key, '{"not": json')
    # The legacy list format, or anything else unreadable, means none.
    expected = {} if setting is settings.SUBCONTEXTS else setting.default
    assert setting.get() == expected


@by_key
def test_only_settings_that_change_scores_or_the_canvas_redraw_it(setting):
    before = revisions.graph
    setting.set(SAMPLES[setting.key])
    assert (revisions.graph != before) == setting.refreshes_graph


def test_a_stored_dict_missing_a_key_reads_that_keys_default():
    settings.write_stored('TIME_SETTINGS', '{"hours_per_week": 30}')
    assert settings.TIME_SETTINGS.get() == {**settings.DEFAULT_TIME_SETTINGS,
                                            'hours_per_week': 30}


def test_name_lists_follow_a_rename_and_a_delete():
    settings.GOAL_ORDER.set(['A', 'B', 'C'])
    settings.GOAL_ORDER.rename('B', 'Bee')
    settings.GOAL_ORDER.drop('A')
    assert settings.GOAL_ORDER.get() == ['Bee', 'C']


def test_seeding_types_on_a_fresh_database_leaves_the_default_list_alone():
    """Seeding Goal used to append 'Goal' to DEFAULT_NODE_TYPES itself."""
    pristine = list(settings.DEFAULT_NODE_TYPES)

    settings.ensure_node_type('Action')
    settings.ensure_node_type('Goal')
    settings.ensure_node_type('Milestone')

    assert settings.DEFAULT_NODE_TYPES == pristine
    assert {"Goal", "Milestone"} <= set(settings.NODE_TYPES.get())
