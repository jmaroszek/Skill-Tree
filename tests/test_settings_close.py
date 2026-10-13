"""Closing Settings commits the complete draft, or keeps it intact on failure."""
import inspect

import dash

import database
import settings_callbacks
from config import ConfigManager


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
    settings_callbacks.register_settings_callbacks(registry)
    return registry.callbacks


def _draft(callbacks):
    save = callbacks['save_settings']
    args = dict.fromkeys(inspect.signature(save).parameters)
    ts = ConfigManager.get_time_settings()
    ted = ConfigManager.get_time_estimate_defaults()
    formatting = ConfigManager.get_name_formatting()
    args.update(
        n_clicks='close-1', hpw=ts['hours_per_week'], hpm=ts['hours_per_month'],
        def_time_unit=ted['unit'], def_time_o=ted['optimistic'],
        def_time_m=ted['expected'], def_time_p=ted['pessimistic'],
        hp_profile=ConfigManager.get_hp_profile(), name_format_mode=formatting['mode'],
        linter_exclusions_val=', '.join(formatting['exclusions']),
        show_scoring_perf_val=['enabled'] if ConfigManager.get_show_scoring_perf() else [],
        time_calibration_val=['enabled'] if ConfigManager.get_time_calibration_enabled() else [],
        now_node_cap_val=ConfigManager.get_now_node_cap(),
        context_sort_mode_val=ConfigManager.get_context_sort_mode(),
        subcontext_sort_mode_val=ConfigManager.get_subcontext_sort_mode(),
        editor_store=settings_callbacks._editor_state(settings_callbacks.manager),
        section_store=settings_callbacks.get_sections(),
        backup_extra_dir=ConfigManager.get_backup_extra_dir())
    return args


def _stored():
    with database.get_connection() as conn:
        return conn.execute('SELECT key, value FROM Settings ORDER BY key').fetchall()


def test_unchanged_close_writes_nothing_and_preserves_profile_overrides(monkeypatch):
    ConfigManager.set_hyperparams({'gamma': 1.25})
    callbacks = _callbacks()
    args = _draft(callbacks)
    before = _stored()

    def unexpected(*_args):
        raise AssertionError('an unchanged close attempted a write')

    monkeypatch.setattr(ConfigManager, '_set_db_value', unexpected)
    monkeypatch.setattr(settings_callbacks, 'save_sections', unexpected)
    result = callbacks['save_settings'](**args)
    assert result[5] is False and result[6] == 'close-1'
    assert result[0] is dash.no_update
    assert _stored() == before
    assert ConfigManager.get_hyperparams()['gamma'] == 1.25


def test_successful_close_commits_all_fields_and_acknowledges_request():
    callbacks = _callbacks()
    args = _draft(callbacks)
    args.update(now_node_cap_val=7, hp_profile='Explorer', hpw=17.5, hpm=70)
    result = callbacks['save_settings'](**args)
    assert result[0] == 'Settings saved' and result[5] is False
    assert result[6] == 'close-1'
    assert ConfigManager.get_now_node_cap() == 7
    assert ConfigManager.get_hp_profile() == 'Explorer'
    assert ConfigManager.get_time_settings()['hours_per_week'] == 17.5


def test_failed_commit_keeps_settings_open_and_rolls_back(monkeypatch):
    callbacks = _callbacks()
    args = _draft(callbacks)
    args.update(now_node_cap_val=7, hpw=17.5, hpm=70)
    args['section_store'][0]['name'] = 'Renamed Links'
    before = _stored()

    def broken(_rows):
        raise RuntimeError('disk full')

    monkeypatch.setattr(settings_callbacks, 'save_sections', broken)
    result = callbacks['save_settings'](**args)
    assert "Couldn't save settings" in result[0]
    assert result[5] is dash.no_update and result[6] == 'close-1'
    assert _stored() == before
    assert settings_callbacks.get_sections()[0]['name'] != 'Renamed Links'


def test_toolbar_cannot_close_without_the_save_request():
    callbacks = _callbacks()
    assert callbacks['toggle_settings_modal'](1, False) is True
    assert callbacks['toggle_settings_modal'](2, True) is dash.no_update
