"""Closing Settings commits the complete draft, or keeps it intact on failure."""
import inspect

import dash

from skilltree.store import database
from skilltree.features.settings import callbacks as settings_callbacks
from skilltree.store import settings
from skilltree.features.settings import draft as settings_draft
from skilltree.features.settings import contexts as settings_contexts
from skilltree.services import AppServices
from skilltree.store.graph.manager import GraphManager


def _callbacks():
    class Registry:
        callbacks = {}

        def callback(self, *args, **kwargs):
            def register(fn):
                self.callbacks[fn.__name__] = fn
                return fn
            return register

        def clientside_callback(self, *args, **kwargs):
            pass

    registry = Registry()
    settings_callbacks.register_settings_callbacks(registry, AppServices())
    return registry.callbacks


def _draft(callbacks):
    save = callbacks['save_settings']
    args = dict.fromkeys(inspect.signature(save).parameters)
    ts = settings.TIME_SETTINGS.get()
    formatting = settings.NAME_FORMATTING.get()
    args.update(
        n_clicks='close-1', hpw=ts['hours_per_week'], hpm=ts['hours_per_month'],
        hp_profile=settings.HP_PROFILE.get(), name_format_mode=formatting['mode'],
        linter_exclusions_val=', '.join(formatting['exclusions']),
        show_scoring_perf_val=['enabled'] if settings.SHOW_SCORING_PERF.get() else [],
        time_calibration_val=['enabled'] if settings.TIME_CALIBRATION_ENABLED.get() else [],
        now_node_cap_val=settings.NOW_NODE_CAP.get(),
        context_sort_mode_val=settings.CONTEXT_SORT_MODE.get(),
        subcontext_sort_mode_val=settings.SUBCONTEXT_SORT_MODE.get(),
        editor_store=settings_contexts.editor_state(GraphManager()),
        section_store=settings_callbacks.get_sections(),
        backup_extra_dir=settings.BACKUP_EXTRA_DIR.get())
    return args


def _stored():
    with database.get_connection() as conn:
        return conn.execute('SELECT key, value FROM Settings ORDER BY key').fetchall()


def test_unchanged_close_writes_nothing_and_preserves_profile_overrides(monkeypatch):
    settings.set_hyperparams({'gamma': 1.25})
    callbacks = _callbacks()
    args = _draft(callbacks)
    before = _stored()

    def unexpected(*_args):
        raise AssertionError('an unchanged close attempted a write')

    monkeypatch.setattr(settings, 'write_stored', unexpected)
    monkeypatch.setattr(settings, 'clear_stored', unexpected)
    monkeypatch.setattr(settings_draft, 'save_sections', unexpected)
    result = callbacks['save_settings'](**args)
    assert result[5] is False and result[6] == 'close-1'
    assert result[0] is dash.no_update
    assert _stored() == before
    assert settings.hyperparams()['gamma'] == 1.25


def test_successful_close_commits_all_fields_and_acknowledges_request():
    callbacks = _callbacks()
    args = _draft(callbacks)
    args.update(now_node_cap_val=7, hp_profile='Explorer', hpw=17.5, hpm=70)
    result = callbacks['save_settings'](**args)
    assert result[0] == 'Settings saved' and result[5] is False
    assert result[6] == 'close-1'
    assert settings.NOW_NODE_CAP.get() == 7
    assert settings.HP_PROFILE.get() == 'Explorer'
    assert settings.TIME_SETTINGS.get()['hours_per_week'] == 17.5


def test_hour_equivalents_default_on_and_round_trip_with_capacity():
    # Older settings have no preference yet; the default still applies.
    settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
    assert settings.TIME_SETTINGS.get()['show_hour_equivalents'] is True
    callbacks = _callbacks()
    args = _draft(callbacks)
    args.update(show_hour_equivalents_val=[], hpw=17.5, hpm=70)
    assert callbacks['save_settings'](**args)[5] is False
    assert settings.TIME_SETTINGS.get() == {
        'hours_per_week': 17.5, 'hours_per_month': 70, 'show_hour_equivalents': False,
    }
    assert callbacks['load_settings'](True)[-2] == []

    args = _draft(callbacks)
    args['show_hour_equivalents_val'] = ['enabled']
    assert callbacks['save_settings'](**args)[5] is False
    assert settings.TIME_SETTINGS.get()['show_hour_equivalents'] is True
    assert callbacks['load_settings'](True)[-2] == ['enabled']


def test_failed_commit_keeps_settings_open_and_rolls_back(monkeypatch):
    callbacks = _callbacks()
    args = _draft(callbacks)
    args.update(now_node_cap_val=7, hpw=17.5, hpm=70)
    args['section_store'][0]['name'] = 'Renamed Links'
    before = _stored()

    def broken(_rows):
        raise RuntimeError('disk full')

    monkeypatch.setattr(settings_draft, 'save_sections', broken)
    result = callbacks['save_settings'](**args)
    assert "Couldn't save settings" in result[0]
    assert result[5] is dash.no_update and result[6] == 'close-1'
    assert _stored() == before
    assert settings_callbacks.get_sections()[0]['name'] != 'Renamed Links'


def test_toolbar_cannot_close_without_the_save_request():
    callbacks = _callbacks()
    assert callbacks['toggle_settings_modal'](1, False) is True
    assert callbacks['toggle_settings_modal'](2, True) is dash.no_update
