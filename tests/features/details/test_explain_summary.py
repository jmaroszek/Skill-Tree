"""The Explain panel's summary, hover text and rank wording."""
from skilltree.features.details.explain import (
    build_explain_summary, format_value_rank, format_priority_rank, _ordinal,
    _contributor_hover,
)


# ============================================================================
# build_explain_summary — plain-language calculation details
# ============================================================================

def _minimal_breakdown(**overrides):
    """Build the minimal dict shape that _explain_summary_table consumes."""
    bd = {
        'node': 'X',
        'context': 'Mind',
        'subcontext': None,
        'score': 1.23,
        'raw_score': 1.23,
        'eligible': True,
        'block_reason': None,
        'intrinsic': {'value': 5, 'interest': 5, 'iv': 10.0},
        'cost': {'difficulty': 5, 'time': 2.0, 'time_overridden': False, 'cost': 15.5},
        'composition': {
            'iv': 10.0,
            'hard_cascade': 2.0,
            'soft_cascade': 0.5,
            'synergy': 0.0,
            'total_value': 12.5,
        },
        'goal_boost': None,
        'variety': None,
        'context_adjustment': {
            'weight': 1.0, 'n_bucket': 1,
            'density_mult': 1.0, 'combined_multiplier': 1.0,
        },
        'contributors': [],
    }
    bd.update(overrides)
    return bd


def _render_text(component):
    """Flatten a Dash component tree into a string for substring assertions."""
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return " ".join(_render_text(c) for c in component)
    children = getattr(component, 'children', None)
    return _render_text(children) if children is not None else ""


class TestContributorHover:
    def test_downstream_contributor_is_name_route_and_ratings(self):
        row = {'name': 'Health', 'via': 'Hard', 'depth': 2, 'iv': 181.0,
               'value': 9, 'interest': 10, 'pct_of_tv': 14.5, 'contribution': 40.0,
               'remaining_hours': 400.0, 'future_discount': 0.67}
        assert _contributor_hover(row) == (
            "<b>Health</b><br>Value 9 · Interest 10<br>2 steps away via hard prerequisite"
            "<br>Passes on 22% of its value")

    def test_self_bar_shows_only_name_and_ratings(self):
        row = {'name': 'X', 'via': 'Self', 'depth': 0, 'iv': 10.0,
               'value': 5, 'interest': 5}
        assert _contributor_hover(row) == "<b>X</b><br>Value 5 · Interest 5"

    def test_type_leads_the_ratings_line(self):
        row = {'name': 'Health', 'type': 'Goal', 'via': 'Self', 'depth': 0,
               'iv': 10.0, 'value': 9, 'interest': 10}
        assert _contributor_hover(row) == "<b>Health</b><br>Goal · Value 9 · Interest 10"

    def test_type_stands_alone_without_ratings(self):
        row = {'name': 'M', 'type': 'Milestone', 'via': 'Hard', 'depth': 1, 'iv': 0.0}
        assert _contributor_hover(row) == (
            "<b>M</b><br>Milestone<br>1 step away via hard prerequisite")

    def test_names_are_escaped(self):
        row = {'name': 'A <b> B', 'via': 'Synergy', 'depth': 1, 'iv': 0.0}
        assert _contributor_hover(row) == (
            "<b>A &lt;b&gt; B</b><br>1 step away via synergy partner")


class TestExplainSummary:
    def test_value_is_shown_as_shares_not_internal_quantities(self):
        """10 + 2 + 0.5 of 12.5 → 80% / 16% / 4.0%; no raw value or cost."""
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Own ratings Value 5 · Interest 5 80%" in text
        assert "Unlocks 16%" in text
        assert "Prepares you for 4.0%" in text
        for internal in ("10.00", "12.50", "15.50", "1.23", "Raw", "Intrinsic"):
            assert internal not in text

    def test_synergy_has_one_unified_row_at_the_end_of_value(self):
        bd = _minimal_breakdown(composition={
            'iv': 10.0, 'hard_cascade': 2.0, 'soft_cascade': 0.5, 'synergy': 5.0,
            'done_synergy_count': 1, 'total_value': 17.5,
        })
        text = _render_text(build_explain_summary(bd, normalized=80))
        assert "Prepares you for 2.9% Synergy partners 29% Cost" in text
        assert "Finished synergy partners" not in text

    def test_value_sources_with_no_share_are_left_out(self):
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "ynergy partners" not in text

    def test_cost_is_shown_as_time_and_effort(self):
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Time 1.4d" in text
        assert "Effort 5 of 10" in text

    def test_inherited_value_and_time_read_as_none_of_its_own(self):
        bd = _minimal_breakdown(
            intrinsic={'value': 7, 'interest': 6, 'iv': 0.0, 'value_overridden': True},
            cost={'difficulty': 4, 'time': 0.0, 'time_overridden': True,
                  'effort_overridden': True, 'cost': 1.0},
        )
        text = _render_text(build_explain_summary(bd, normalized=None))
        assert "Value 7" not in text
        assert "Own ratings none of its own" in text
        assert "Time None of its own" in text
        assert "Effort None of its own" in text

    def test_no_adjustments_section_when_all_trivial(self):
        """With weight=1, density=1, no goal boost or variety: no Adjustments header."""
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Adjustments" not in text
        assert "Priority 80 of 100" in text

    def test_density_reads_as_crowding_without_parameters(self):
        bd = _minimal_breakdown(subcontext='Focus', context_adjustment={
            'weight': 1.0, 'n_bucket': 17, 'alpha': 0.3,
            'density_mult': 0.432, 'combined_multiplier': 0.432,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Crowding 17 goals in Mind · Focus −57%" in text
        assert "α" not in text and "n=17" not in text
        assert "Together" not in text

    def test_context_weight_reads_as_a_percent_change(self):
        bd = _minimal_breakdown(context_adjustment={
            'weight': 2.0, 'n_bucket': 5,
            'density_mult': 1.0, 'combined_multiplier': 2.0,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Context weight Mind +100%" in text
        assert "×" not in text

    def test_variety_names_its_place_in_context_and_subcontext(self):
        bd = _minimal_breakdown(variety={
            'divisor': 1.25, 'context': 'Mind', 'subcontext': 'Focus',
            'context_rank': 3, 'subcontext_rank': 2,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Variety 3rd from Mind, 2nd from Focus −20%" in text

    def test_several_adjustments_add_a_together_row(self):
        bd = _minimal_breakdown(
            goal_boost={'multiplier': 1.5, 'goal': 'Health', 'rank': 1},
            context_adjustment={
                'weight': 2.0, 'n_bucket': 1, 'alpha': 0.0,
                'density_mult': 1.0, 'combined_multiplier': 2.0,
            },
        )
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Priority goal Health (#1) +50%" in text
        assert "Context weight Mind +100%" in text
        assert "Together +200%" in text

    def test_goal_breakdown_shows_goal_credit_and_work_left(self):
        bd = _minimal_breakdown(
            is_goal=True,
            cost={'goal': True, 'remaining_time': 6.0, 'n_tasks': 2,
                  'cost': 2.0, 'time_overridden': False},
            composition={'iv': 6.0, 'goal_credit': 3.0, 'other_goal_credit': 1.0,
                         'hard_cascade': 0.0, 'soft_cascade': 0.0,
                         'synergy': 0.0, 'total_value': 10.0},
            goal_boost={'multiplier': 1.5, 'goal': 'X', 'rank': 2},
        )
        text = _render_text(build_explain_summary(bd, normalized=40))
        assert "Ratings of the work left 60%" in text
        assert "Credit for this goal Value 5 · Interest 5 30%" in text
        assert "Credit for other goals 10%" in text
        assert "Work left 2 tasks 4.2d" in text
        assert "Effort" not in text
        assert "Priority goal X (#2) +50%" in text

    def test_ineligible_shows_reason_instead_of_priority(self):
        bd = _minimal_breakdown(eligible=False, block_reason="Blocked")
        text = _render_text(build_explain_summary(bd, normalized=None))
        assert "Not ranked Blocked" in text
        assert "of 100" not in text


# ============================================================================
# format_value_rank — the Explain modal's header stat
# ============================================================================

class TestFormatValueRank:
    """Total value is an internal quantity, so only the rank is shown."""

    POOL = [900.0, 800.0, 700.0, 600.0, 500.0, 400.0, 300.0, 200.0, 100.0, 50.0]

    def test_best_node(self):
        assert format_value_rank(900.0, self.POOL, "projects") == \
            "Ranks 1st of 10 projects"

    def test_worst_node(self):
        assert format_value_rank(50.0, self.POOL, "projects") == \
            "Ranks 10th of 10 projects"

    def test_middle_node(self):
        assert format_value_rank(600.0, self.POOL) == "Ranks 4th of 10 projects"

    def test_ties_share_the_better_rank(self):
        assert format_value_rank(5.0, [10.0, 5.0, 5.0, 1.0]) == "Ranks 2nd of 4 projects"

    def test_noun_is_used_verbatim(self):
        assert format_value_rank(900.0, self.POOL, "goals").endswith("goals")

    def test_the_raw_value_is_never_shown(self):
        """The number has no units and shifts with the profile; it stays out."""
        out = format_value_rank(12345.6, [99999.0, 12345.6, 1.0])
        assert "12345" not in out and "12,345" not in out

    def test_no_percentile_is_shown(self):
        assert "%" not in format_value_rank(900.0, self.POOL)

    def test_returns_empty_when_there_is_nothing_to_compare(self):
        assert format_value_rank(5.0, [5.0]) == ""
        assert format_value_rank(5.0, []) == ""
        assert format_value_rank(5.0, None) == ""

    def test_returns_empty_without_a_value(self):
        assert format_value_rank(None, self.POOL) == ""

    def test_ignores_missing_peer_values(self):
        """A peer with no computed total value must not skew the count."""
        assert format_value_rank(10.0, [10.0, 5.0, None, None]) == "Ranks 1st of 2 projects"


class TestFormatPriorityRank:
    def test_ordinary_node(self):
        assert format_priority_rank(3, 41) == "Ranks 3rd of 41 projects"

    def test_now_node_reads_as_hypothetical(self):
        assert format_priority_rank(3, 41, in_now=True) == \
            "Would rank 3rd of 41 projects if it weren't in Now"


class TestOrdinal:
    def test_common_suffixes(self):
        assert [_ordinal(n) for n in (1, 2, 3, 4)] == ["1st", "2nd", "3rd", "4th"]

    def test_teens_are_all_th(self):
        assert [_ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]

    def test_suffix_repeats_past_twenty(self):
        assert [_ordinal(n) for n in (21, 22, 23, 111, 112)] == \
            ["21st", "22nd", "23rd", "111th", "112th"]
