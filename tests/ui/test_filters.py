"""The canvas filters: building them from the sidebar, and whether any is on."""
import pytest
from skilltree.ui.filters import build_filters, is_filters_active
from skilltree.store import settings


# ============================================================================
# build_filters
# ============================================================================

class TestBuildFilters:
    # "Show Done" semantics: f_done = ["show_done"] means done is shown (no
    # hide_done filter); f_done = [] (or any legacy value) means done is
    # hidden. Tests that used to pass [] and expect {} now pass ["show_done"]
    # to signal "no filters at all".

    def test_all_defaults_empty_dict(self):
        result = build_filters("All", "All", ["show_done"])
        assert result == {}

    def test_empty_lists_empty_dict(self):
        result = build_filters([], [], ["show_done"])
        assert result == {}

    def test_context_filter(self):
        result = build_filters("Mind", "All", ["show_done"])
        assert result == {"context": ["Mind"]}

    def test_context_filter_multi(self):
        result = build_filters(["Mind", "Body"], [], ["show_done"])
        assert result == {"context": ["Mind", "Body"]}

    def test_none_context_maps_to_none(self):
        result = build_filters("None", "All", ["show_done"])
        assert result == {"context": [None]}

    def test_show_done_off_hides_done(self):
        # f_done empty (Show Done switch off) → hide_done filter applied.
        result = build_filters("All", "All", [])
        assert result == {"hide_done": True}

    def test_show_done_on_does_not_hide(self):
        result = build_filters("All", "All", ["show_done"])
        assert result == {}

    def test_min_value(self):
        result = build_filters("All", "All", ["show_done"], f_value=[5, 10])
        assert result == {"min_value": 5}

    def test_min_interest(self):
        result = build_filters("All", "All", ["show_done"], f_interest=[3, 10])
        assert result == {"min_interest": 3}

    def test_max_time(self):
        result = build_filters("All", "All", ["show_done"], f_time=10)
        assert result == {"max_time": 10.0}

    def test_max_difficulty(self):
        result = build_filters("All", "All", ["show_done"], f_difficulty=[1, 7])
        assert result == {"max_difficulty": 7}

    def test_max_value_upper_bound(self):
        result = build_filters("All", "All", ["show_done"], f_value=[1, 3])
        assert result == {"max_value": 3}

    def test_value_band_sets_both_bounds(self):
        result = build_filters("All", "All", ["show_done"], f_value=[4, 6])
        assert result == {"min_value": 4, "max_value": 6}

    def test_min_difficulty_lower_bound(self):
        result = build_filters("All", "All", ["show_done"], f_difficulty=[5, 10])
        assert result == {"min_difficulty": 5}

    def test_full_or_missing_rating_range_filters_nothing(self):
        result = build_filters("All", "All", ["show_done"], f_value=[1, 10],
                               f_interest=None, f_difficulty=[1, 10])
        assert result == {}

    def test_min_time(self):
        result = build_filters("All", "All", ["show_done"], f_time_min=2)
        assert result == {"min_time": 2.0}

    def test_time_band_converts_both_ends_with_the_unit(self):
        result = build_filters("All", "All", ["show_done"], f_time_min=1, f_time=2,
                               f_time_unit="days")
        hours_per_day = settings.time_multiplier("days")
        # Rounded as Node.time is, so a node sitting on a bound stays in.
        assert result == {"min_time": round(hours_per_day, 2),
                          "max_time": round(2 * hours_per_day, 2)}

    def test_min_time_above_max_time_filters_nothing(self):
        result = build_filters("All", "All", ["show_done"], f_time_min=10, f_time=2)
        assert result == {}

    def test_zero_or_blank_min_time_filters_nothing(self):
        for blank in (None, "", 0):
            assert build_filters("All", "All", ["show_done"], f_time_min=blank) == {}

    def test_invalid_time_ignored(self):
        result = build_filters("All", "All", ["show_done"], f_time="abc")
        assert "max_time" not in result

    def test_search_filters_by_name_by_default(self):
        result = build_filters("All", "All", ["show_done"],
                               f_search={"text": "  Skill Tree ", "descriptions": False})
        assert result == {"search": "Skill Tree"}

    def test_search_with_descriptions(self):
        result = build_filters("All", "All", ["show_done"],
                               f_search={"text": "tree", "descriptions": True})
        assert result == {"search": "tree", "search_descriptions": True}

    def test_blank_search_filters_nothing(self):
        for blank in (None, {}, {"text": "", "descriptions": True},
                      {"text": "   ", "descriptions": True}):
            assert build_filters("All", "All", ["show_done"], f_search=blank) == {}

    def test_subcontext_filter(self):
        result = build_filters("All", "Rational", ["show_done"])
        assert result == {"subcontext": ["Rational"]}

    def test_subcontext_filter_multi(self):
        result = build_filters("All", ["Rational", "Creative"], ["show_done"])
        assert result == {"subcontext": ["Rational", "Creative"]}

    def test_subcontext_all_ignored(self):
        result = build_filters("All", "All", ["show_done"])
        assert "subcontext" not in result

    def test_composite_subcontext_multi_context_multi_sub(self):
        # Regression: each composite "ctx::sub" value must be routed to its own
        # context. Previously bare "Rational" values forced a reverse-lookup via
        # the stored subcontexts, which could silently drop an entry and fall back to
        # "show all nodes of that context" for Mind.
        result = build_filters(
            ["Mind", "STEM"],
            ["Mind::Rational", "STEM::Math", "STEM::Data Science"],
            ["show_done"],
        )
        assert result == {
            "context_subcontext_union": [
                ("Mind", ["Rational"]),
                ("STEM", ["Math", "Data Science"]),
            ]
        }

    def test_composite_subcontext_selective_union_fallback(self):
        # Mind has no subs in the selection → falls back to None (show all Mind).
        result = build_filters(["Mind", "STEM"], ["STEM::Math"], ["show_done"])
        assert result == {
            "context_subcontext_union": [("Mind", None), ("STEM", ["Math"])]
        }

    def test_composite_subcontext_without_context_flattens(self):
        # No context selected → flatten to a plain subcontext filter (name-only).
        result = build_filters(
            [], ["Mind::Rational", "STEM::Math"], ["show_done"]
        )
        assert result == {"subcontext": ["Rational", "Math"]}

    def test_legacy_plain_subcontext_with_context(self):
        # Legacy state (plain subcontext names, no "::") — apply the list to
        # every selected context.
        result = build_filters(["Mind"], ["Rational"], ["show_done"])
        assert result == {"context_subcontext_union": [("Mind", ["Rational"])]}


# ============================================================================
# is_filters_active
# ============================================================================

class TestIsFiltersActive:
    def test_all_defaults_inactive(self):
        # Mirrors the "Clear Filters" reset state.
        assert is_filters_active(
            node_type=[], context=[], subcontext=[],
            community="All", community_method="components",
            value=[1, 10], interest=[1, 10], difficulty=[1, 10], time=None,
        ) is False

    def test_no_args_inactive(self):
        # Defensive: when a caller (e.g. Details canvas) passes nothing for
        # filters that don't affect it, the helper must not flag.
        assert is_filters_active() is False

    def test_node_type_active(self):
        assert is_filters_active(node_type=["Learn"]) is True

    def test_context_active(self):
        assert is_filters_active(context=["Mind"]) is True

    def test_subcontext_active(self):
        assert is_filters_active(subcontext=["Rational"]) is True

    def test_community_all_inactive(self):
        assert is_filters_active(community="All") is False

    def test_community_specific_active(self):
        assert is_filters_active(community="3") is True

    def test_orphans_method_active(self):
        # "Orphans" mode narrows visible nodes even with community="All".
        assert is_filters_active(community="All",
                                 community_method="orphans") is True

    def test_default_method_inactive(self):
        assert is_filters_active(community_method="components") is False

    def test_min_value_active(self):
        assert is_filters_active(value=[2, 10]) is True

    def test_min_value_at_floor_inactive(self):
        assert is_filters_active(value=[1, 10]) is False

    def test_min_interest_active(self):
        assert is_filters_active(interest=[5, 10]) is True

    def test_max_difficulty_active(self):
        assert is_filters_active(difficulty=[1, 7]) is True

    def test_max_difficulty_at_ceiling_inactive(self):
        assert is_filters_active(difficulty=[1, 10]) is False

    def test_max_value_active(self):
        assert is_filters_active(value=[1, 3]) is True

    def test_min_difficulty_active(self):
        assert is_filters_active(difficulty=[2, 10]) is True

    def test_min_time_active(self):
        assert is_filters_active(time_min=2) is True

    def test_crossed_time_range_is_not_active(self):
        # build_filters ignores a minimum above the maximum, so nothing is
        # hidden and the "filtered" marker must stay off.
        assert is_filters_active(time_min=10, time=2) is False

    def test_max_time_active(self):
        assert is_filters_active(time=20) is True

    def test_max_time_zero_inactive(self):
        assert is_filters_active(time=0) is False

    def test_search_text_active(self):
        assert is_filters_active(
            search={"text": "skill tree", "descriptions": False}) is True

    def test_blank_search_inactive(self):
        assert is_filters_active(search=None) is False
        assert is_filters_active(search={"text": "   ", "descriptions": True}) is False

    def test_reveal_switches_are_not_filters(self):
        """Show Done and Show Dormant must never set the "filtered" marker.

        Both default to off and can only be switched on, which reveals nodes
        instead of hiding them. The marker warns about a view the user cannot
        tell is narrowed; a wider-than-default view is not that. The helper
        takes no argument for either switch, so passing one is a TypeError —
        that is the guard.
        """
        with pytest.raises(TypeError):
            is_filters_active(done=["show_done"])
        with pytest.raises(TypeError):
            is_filters_active(show_dormant=["show_dormant"])
