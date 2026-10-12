"""Hours per week and per month save as typed, and stay four weeks apart.

The fields took whole numbers only, so 17.5 read as no value, and a blank or
unreadable field saved as 40 or 160. One of them alone broke the four-week
month that every week, month and year conversion uses.
"""
import inspect

import pytest

from callback_helpers import capacity_hours
from config import ConfigManager, DEFAULT_TIME_SETTINGS
import settings_layout

STORED = {'hours_per_week': 20, 'hours_per_month': 80}


@pytest.mark.parametrize("hpw, hpm, expected", [
    (17.5, 70, (17.5, 70)),
    ("17.5", "70", (17.5, 70)),
    (None, 70, (17.5, 70)),
    (17.5, None, (17.5, 70)),
    (None, None, (20, 80)),
    ("", "abc", (20, 80)),
    (0, -4, (20, 80)),
    (float("inf"), 70, (17.5, 70)),
])
def test_capacity_hours(hpw, hpm, expected):
    result = capacity_hours(hpw, hpm, STORED)
    assert (result['hours_per_week'], result['hours_per_month']) == expected


def _save_settings():
    from settings_callbacks import register_settings_callbacks

    class Registry:
        def __init__(self):
            self.callbacks = {}

        def clientside_callback(self, *args, **kwargs):
            pass

        def callback(self, *dependencies, **kwargs):
            def register(fn):
                self.callbacks[fn.__name__] = fn
                return fn
            return register

    registry = Registry()
    register_settings_callbacks(registry)
    save = registry.callbacks['save_settings']
    return save, {key: None for key in inspect.signature(save).parameters}


def _saved_hours():
    ts = ConfigManager.get_time_settings()
    return ts['hours_per_week'], ts['hours_per_month']


def test_a_fractional_week_saves_as_typed():
    save, args = _save_settings()
    args.update(n_clicks=1, hpw=17.5, hpm=70)

    assert save(**args)[0] == 'Settings saved'
    assert _saved_hours() == (17.5, 70)


def test_blank_fields_keep_the_stored_hours():
    ConfigManager.set_time_settings({'hours_per_week': 35, 'hours_per_month': 140,
                                     'monte_carlo_trials': 4321})
    save, args = _save_settings()
    args.update(n_clicks=1, hpw=None, hpm=None)

    save(**args)

    assert _saved_hours() == (35, 140)
    assert ConfigManager.get_time_settings()['monte_carlo_trials'] == 4321


def test_a_stored_value_missing_a_key_reads_the_default():
    ConfigManager.set_time_settings({'monte_carlo_trials': 4321})

    assert _saved_hours() == (DEFAULT_TIME_SETTINGS['hours_per_week'],
                              DEFAULT_TIME_SETTINGS['hours_per_month'])


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if child is not None and not isinstance(child, (str, int, float)):
            found = _find(child, component_id)
            if found is not None:
                return found
    return None


def test_the_fields_take_fractions():
    tab = settings_layout._build_editing_tab()
    for field in ("setting-hpd", "setting-hpw", "setting-hpm", "setting-hpy"):
        assert _find(tab, field).step == "any"


def test_a_contexts_error_says_which_settings_were_saved():
    """Some settings are written before the contexts are checked, and stay
    saved. The message used to read as if nothing had been."""
    save, args = _save_settings()
    args.update(n_clicks=1, hpw=30, hpm=120, now_node_cap_val=7,
                editor_store={'rows': [{'rid': 'a', 'name': 'STEM', 'subs': []},
                                       {'rid': 'b', 'name': 'Stem', 'subs': []}]})
    message = save(**args)[0]
    assert "Contexts need a fix" in message
    assert "Maximum Now Nodes" in message and "were saved" in message
    assert ConfigManager.get_now_node_cap() == 7
    assert _saved_hours() != (30, 120)  # hours wait for the contexts
