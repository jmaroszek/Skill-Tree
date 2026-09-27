"""Config getters hand out copies of their defaults, never the defaults."""
import copy

import pytest

import config
from config import ConfigManager


# Every getter whose default is a mutable list or dict. On the fresh test
# database nothing is stored, so each one falls back to its default.
MUTABLE_DEFAULTS = [
    (ConfigManager.get_node_types, "DEFAULT_NODE_TYPES"),
    (ConfigManager.get_contexts, "DEFAULT_CONTEXTS"),
    (ConfigManager.get_subcontexts, "DEFAULT_SUBCONTEXTS"),
    (ConfigManager.get_node_colors, "DEFAULT_NODE_COLORS"),
    (ConfigManager.get_node_shapes, "DEFAULT_NODE_SHAPES"),
    (ConfigManager.get_graph_layout_defaults, "DEFAULT_GRAPH_LAYOUT"),
    (ConfigManager.get_details_graph_layout_defaults, "DEFAULT_DETAILS_GRAPH_LAYOUT"),
    (ConfigManager.get_events_graph_layout_defaults, "DEFAULT_EVENTS_GRAPH_LAYOUT"),
    (ConfigManager.get_analyze_limits, "DEFAULT_ANALYZE_LIMITS"),
    (ConfigManager.get_time_settings, "DEFAULT_TIME_SETTINGS"),
    (ConfigManager.get_time_estimate_defaults, "DEFAULT_TIME_ESTIMATE_DEFAULTS"),
]


@pytest.mark.parametrize("getter, default_name", MUTABLE_DEFAULTS,
                         ids=[name for _, name in MUTABLE_DEFAULTS])
def test_unset_setting_returns_an_equal_copy(getter, default_name):
    default = getattr(config, default_name)
    value = getter()

    assert value == default
    assert value is not default


def test_editing_a_returned_default_leaves_the_default_alone():
    pristine_contexts = list(config.DEFAULT_CONTEXTS)
    pristine_subcontexts = copy.deepcopy(config.DEFAULT_SUBCONTEXTS)
    pristine_limits = dict(config.DEFAULT_ANALYZE_LIMITS)

    ConfigManager.get_contexts().append("Scratch")
    ConfigManager.get_subcontexts()["Mind"].append("Scratch")
    ConfigManager.get_analyze_limits()["goals"] = 1

    assert config.DEFAULT_CONTEXTS == pristine_contexts
    assert config.DEFAULT_SUBCONTEXTS == pristine_subcontexts
    assert config.DEFAULT_ANALYZE_LIMITS == pristine_limits


def test_seeding_types_on_a_fresh_database_leaves_the_default_list_alone():
    """ensure_goal_type used to append 'Goal' to DEFAULT_NODE_TYPES itself."""
    pristine = list(config.DEFAULT_NODE_TYPES)

    ConfigManager.ensure_action_type()
    ConfigManager.ensure_goal_type()
    ConfigManager.ensure_milestone_type()

    assert config.DEFAULT_NODE_TYPES == pristine
    assert {"Goal", "Milestone"} <= set(ConfigManager.get_node_types())
