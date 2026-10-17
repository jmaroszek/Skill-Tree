"""The stored settings and the functions that combine them."""
from skilltree.store import settings
from skilltree.store.settings import DEFAULT_NODE_TYPES
from skilltree.domain.profiles import DEFAULT_HYPERPARAMS


# ============================================================================
# Settings
# ============================================================================

class TestSettings:
    def test_default_node_types(self):
        assert settings.NODE_TYPES.get() == DEFAULT_NODE_TYPES

    def test_set_and_get_node_types(self):
        custom = ["Alpha", "Beta"]
        settings.NODE_TYPES.set(custom)
        assert settings.NODE_TYPES.get() == custom

    def test_set_and_get_contexts(self):
        custom = ["Work", "Play"]
        settings.CONTEXTS.set(custom)
        assert settings.CONTEXTS.get() == custom

    def test_set_and_get_subcontexts(self):
        custom = {"Mind": ["Rational", "Sensory"], "Body": ["Stress"]}
        settings.SUBCONTEXTS.set(custom)
        assert settings.SUBCONTEXTS.get() == custom

    def test_subcontexts_invalid_json_returns_empty(self):
        # Manually write bad data
        from skilltree.store.database import get_connection
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", ("SUBCONTEXTS", "not valid json"))
            conn.commit()
        assert settings.SUBCONTEXTS.get() == {}

    def test_subcontexts_list_returns_empty(self):
        # Legacy format was a list, should return {} for safety
        settings.write_stored("SUBCONTEXTS", '["a", "b"]')
        assert settings.SUBCONTEXTS.get() == {}

    def test_subcontext_sort_mode_default_is_definition(self):
        from skilltree.domain.contexts import DEFAULT_SUBCONTEXT_SORT_MODE
        assert settings.SUBCONTEXT_SORT_MODE.get() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_subcontext_sort_mode_round_trip(self):
        from skilltree.domain.contexts import (
            SUBCONTEXT_SORT_LENGTH, SUBCONTEXT_SORT_ALPHABETICAL,
            SUBCONTEXT_SORT_DEFINITION,
        )
        for mode in (SUBCONTEXT_SORT_LENGTH, SUBCONTEXT_SORT_ALPHABETICAL, SUBCONTEXT_SORT_DEFINITION):
            settings.SUBCONTEXT_SORT_MODE.set(mode)
            assert settings.SUBCONTEXT_SORT_MODE.get() == mode

    def test_subcontext_sort_mode_invalid_falls_back_to_default(self):
        from skilltree.domain.contexts import DEFAULT_SUBCONTEXT_SORT_MODE
        settings.write_stored("SUBCONTEXT_SORT_MODE", "garbage")
        assert settings.SUBCONTEXT_SORT_MODE.get() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_subcontext_sort_mode_setter_rejects_invalid(self):
        from skilltree.domain.contexts import DEFAULT_SUBCONTEXT_SORT_MODE
        settings.SUBCONTEXT_SORT_MODE.set("not-a-mode")
        assert settings.SUBCONTEXT_SORT_MODE.get() == DEFAULT_SUBCONTEXT_SORT_MODE

    def test_sort_subcontexts_definition_preserves_order(self):
        from skilltree.domain.contexts import (
            sort_subcontexts, SUBCONTEXT_SORT_DEFINITION,
        )
        items = ["Rational", "Sensory", "Judgment"]
        assert sort_subcontexts(items, SUBCONTEXT_SORT_DEFINITION) == items

    def test_sort_subcontexts_length_orders_short_first(self):
        from skilltree.domain.contexts import sort_subcontexts, SUBCONTEXT_SORT_LENGTH
        items = ["Engineering", "Math", "Data Science", "Physics"]
        # Stable: 'Math' (4) < 'Physics' (7) < 'Engineering' (11) == 'Data Science' (12)
        # Length-only key keeps relative order of equal-length entries.
        assert sort_subcontexts(items, SUBCONTEXT_SORT_LENGTH) == [
            "Math", "Physics", "Engineering", "Data Science",
        ]

    def test_sort_subcontexts_alphabetical_case_insensitive(self):
        from skilltree.domain.contexts import (
            sort_subcontexts, SUBCONTEXT_SORT_ALPHABETICAL,
        )
        items = ["banana", "Apple", "cherry"]
        assert sort_subcontexts(items, SUBCONTEXT_SORT_ALPHABETICAL) == ["Apple", "banana", "cherry"]

    def test_sort_subcontexts_does_not_mutate_input(self):
        from skilltree.domain.contexts import (
            sort_subcontexts, SUBCONTEXT_SORT_ALPHABETICAL,
        )
        items = ["zeta", "alpha"]
        sort_subcontexts(items, SUBCONTEXT_SORT_ALPHABETICAL)
        assert items == ["zeta", "alpha"]

    def test_sort_subcontexts_empty(self):
        from skilltree.domain.contexts import sort_subcontexts, SUBCONTEXT_SORT_LENGTH
        assert sort_subcontexts([], SUBCONTEXT_SORT_LENGTH) == []

    def test_set_and_get_hyperparams(self):
        custom = {**DEFAULT_HYPERPARAMS, 'w_v': 2.0}
        settings.set_hyperparams(custom)
        result = settings.hyperparams()
        assert result['w_v'] == 2.0

    def test_sync_shapes_to_types_adds_new(self):
        settings.NODE_SHAPES.set({"Learn": "ellipse", "Goal": "star"})
        settings.sync_shapes_to_types(["Learn", "Goal", "Quest"])
        shapes = settings.NODE_SHAPES.get()
        assert shapes["Quest"] == "rectangle"
        assert shapes["Learn"] == "ellipse"

    def test_sync_shapes_to_types_removes_old(self):
        settings.NODE_SHAPES.set({"Learn": "ellipse", "Goal": "star", "Removed": "diamond"})
        settings.sync_shapes_to_types(["Learn", "Goal"])
        shapes = settings.NODE_SHAPES.get()
        assert "Removed" not in shapes
        assert shapes["Learn"] == "ellipse"


# ============================================================================
# Settings — Time Multiplier
# ============================================================================

class TestTimeMultiplier:
    def test_hours_returns_one(self):
        assert settings.time_multiplier('hours') == 1.0

    def test_weeks_returns_hours_per_week(self):
        result = settings.time_multiplier('weeks')
        assert result == settings.TIME_SETTINGS.get()['hours_per_week']

    def test_months_returns_hours_per_month(self):
        result = settings.time_multiplier('months')
        assert result == settings.TIME_SETTINGS.get()['hours_per_month']

    def test_unknown_unit_returns_one(self):
        assert settings.time_multiplier('fortnights') == 1.0

    def test_days_is_a_seventh_of_a_week(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 21, 'hours_per_month': 84})
        assert settings.time_multiplier('days') == 3
        settings.TIME_SETTINGS.set({'hours_per_week': 70, 'hours_per_month': 280})
        assert settings.time_multiplier('days') == 10

    def test_custom_settings_reflected(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
        assert settings.time_multiplier('weeks') == 20
        assert settings.time_multiplier('months') == 80

    def test_years_returns_thirteen_months(self):
        settings.TIME_SETTINGS.set({'hours_per_week': 20, 'hours_per_month': 80})
        assert settings.time_multiplier('years') == 13 * 80


# ============================================================================
# Settings — Priority Goals
# ============================================================================

class TestPriorityGoals:
    def test_default_empty(self):
        assert settings.PRIORITY_GOALS.get() == []

    def test_set_and_get(self):
        settings.PRIORITY_GOALS.set(["Goal A", "Goal B"])
        result = settings.PRIORITY_GOALS.get()
        assert result == ["Goal A", "Goal B"]

    def test_capped_at_three(self):
        settings.PRIORITY_GOALS.set(["A", "B", "C", "D", "E"])
        result = settings.PRIORITY_GOALS.get()
        assert len(result) == 3

    def test_empty_list(self):
        settings.PRIORITY_GOALS.set([])
        assert settings.PRIORITY_GOALS.get() == []


# ============================================================================
# Settings — ensure_node_type('Action')
# ============================================================================

class TestEnsureActionType:
    def test_adds_action_if_missing(self):
        settings.NODE_TYPES.set(["Learn", "Goal"])
        settings.ensure_node_type('Action')
        types = settings.NODE_TYPES.get()
        assert "Action" in types

    def test_no_duplicate_if_present(self):
        settings.NODE_TYPES.set(["Learn", "Action", "Goal"])
        settings.ensure_node_type('Action')
        types = settings.NODE_TYPES.get()
        assert types.count("Action") == 1

    def test_shape_added_for_new_type(self):
        settings.NODE_TYPES.set(["Learn"])
        settings.NODE_SHAPES.set({"Learn": "ellipse"})
        settings.ensure_node_type('Action')
        shapes = settings.NODE_SHAPES.get()
        assert "Action" in shapes


# ============================================================================
# Settings — ensure_node_type('Goal')
# ============================================================================

class TestEnsureGoalType:
    def test_adds_goal_if_missing(self):
        settings.NODE_TYPES.set(["Learn", "Action"])
        settings.ensure_node_type('Goal')
        types = settings.NODE_TYPES.get()
        assert "Goal" in types

    def test_no_duplicate_if_present(self):
        settings.NODE_TYPES.set(["Learn", "Action", "Goal"])
        settings.ensure_node_type('Goal')
        types = settings.NODE_TYPES.get()
        assert types.count("Goal") == 1

    def test_shape_added_for_new_type(self):
        settings.NODE_TYPES.set(["Learn"])
        settings.NODE_SHAPES.set({"Learn": "ellipse"})
        settings.ensure_node_type('Goal')
        shapes = settings.NODE_SHAPES.get()
        assert "Goal" in shapes


# ============================================================================
# Settings — ensure_node_type('Milestone')
# ============================================================================

class TestEnsureMilestoneType:
    def test_adds_milestone_if_missing(self):
        settings.NODE_TYPES.set(["Learn", "Action", "Goal"])
        settings.ensure_node_type('Milestone')
        types = settings.NODE_TYPES.get()
        assert "Milestone" in types

    def test_no_duplicate_if_present(self):
        settings.NODE_TYPES.set(["Learn", "Action", "Goal", "Milestone"])
        settings.ensure_node_type('Milestone')
        types = settings.NODE_TYPES.get()
        assert types.count("Milestone") == 1

    def test_shape_added_for_new_type(self):
        settings.NODE_TYPES.set(["Learn"])
        settings.NODE_SHAPES.set({"Learn": "ellipse"})
        settings.ensure_node_type('Milestone')
        shapes = settings.NODE_SHAPES.get()
        assert shapes.get("Milestone") == "diamond"


class TestEstimateCorrelationSetting:
    """The one free parameter in the duration model — guard its bounds."""

    def _with(self, stored, temp_database):
        from skilltree.store.settings import DEFAULT_ESTIMATE_CORRELATION
        time_settings = settings.TIME_SETTINGS.get()
        if stored is not None:
            time_settings['estimate_correlation'] = stored
        settings.TIME_SETTINGS.set(time_settings)
        return settings.estimate_correlation(), DEFAULT_ESTIMATE_CORRELATION

    def test_default_when_unset(self, temp_database):
        value, default = self._with(None, temp_database)
        assert value == default

    def test_reads_a_stored_value(self, temp_database):
        value, _ = self._with(0.25, temp_database)
        assert value == 0.25

    def test_accepts_the_endpoints(self, temp_database):
        assert self._with(0.0, temp_database)[0] == 0.0
        assert self._with(1.0, temp_database)[0] == 1.0

    def test_falls_back_on_out_of_range_or_junk(self, temp_database):
        for bad in (-0.5, 1.5, "abc", None if False else float('nan')):
            value, default = self._with(bad, temp_database)
            assert value == default, bad
