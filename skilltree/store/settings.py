"""The user's settings, stored in the Settings table.

ConfigManager is a classmethod-only gateway to that key/value table: each
getter reads a stored JSON value, or a copy of its DEFAULT_* when nothing is
stored, and each setter writes one back. All state lives in SQLite, so every
module shares it through one import.
"""

import copy
import json
from skilltree.store import database
from typing import Optional
from skilltree.store.database import get_connection
from skilltree.domain.models import STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from skilltree.domain.synergy import synergy_parameters
from skilltree.domain.time import DAYS_PER_WEEK, HOURS_PER_YEAR_MULT, hours_per_unit
from skilltree.domain.profiles import (
    DEFAULT_HYPERPARAMS, HYPERPARAMS_SCHEMA_VERSION, PROFILES, PROFILE_ALIASES,
)
from skilltree.domain.names import (
    DEFAULT_TITLECASE_EXCLUSIONS, NAME_FORMAT_MODES, NAME_FORMAT_NONE, NAME_FORMAT_TITLE,
)
from skilltree.domain.contexts import (
    CONTEXT_SORT_MODES, DEFAULT_CONTEXT_SORT_MODE, DEFAULT_SUBCONTEXT_SORT_MODE,
    SUBCONTEXT_SORT_MODES,
)


DEFAULT_NODE_TYPES = ["Learn", "Action", "Resource"]
SUPPORTED_NODE_TYPES = ("Learn", "Action", "Resource", "Goal", "Milestone")
# The welcome dialog offers these to a new user, who saves them as their own
# list (onboarding_callbacks.py). Editing them never moves an existing user's
# contexts. Broad pillars anyone has, a few common subcontexts in each.
DEFAULT_CONTEXTS = [
    "Health", "Mind", "Relationships", "Learning",
    "Creative", "Career", "Money", "Leisure",
]
DEFAULT_SUBCONTEXTS = {
    "Health":        ["Exercise", "Nutrition", "Sleep"],
    "Mind":          ["Habits", "Mindfulness", "Emotions"],
    "Relationships": ["Family", "Friends", "Partner", "Community"],
    "Learning":      ["Science", "Languages", "History", "Philosophy"],
    "Creative":      ["Art", "Music", "Writing", "Crafts"],
    "Career":        ["Skills", "Projects", "Networking"],
    "Money":         ["Budgeting", "Saving", "Investing"],
    "Leisure":       ["Games", "Sports", "Outdoors", "Travel"],
}


DEFAULT_NODE_COLORS = {
    STATUS_BLOCKED: '#dc3545',
    STATUS_OPEN: '#0d6efd',
    STATUS_DONE: '#198754',
    'Goal': '#d3c41d',
    'Action': '#fd7e14',
    'Learn': '#0d6efd',
    'Resource': '#9047b8',
    'Milestone': '#17a2b8',
    'Now': '#ffd000',
}

# Default soft cap on simultaneously-Now nodes, overridable via the Recommendations
# settings tab (ConfigManager.get_now_node_cap). Setting Now is refused
# once the cap is reached; clearing is always allowed. 5 keeps focus
# fairly tight without blocking brief overlap during handoffs.
DEFAULT_NOW_NODE_CAP = 5

# How many actionable prerequisites the Home tab pins above the suggestions for
# each Now node that can't be started yet (see GraphManager.get_unblocking_steps).
# Small on purpose: the question is "what's the best next step toward this",
# not "show me the whole subtree" — a real target can have 17 actionable
# prerequisites, and pinning all of them buries the ranking underneath.
DEFAULT_UNBLOCKING_STEPS_PER_NOW = 3

DEFAULT_NODE_SHAPES = {
    'Learn': 'ellipse',
    'Action': 'triangle',
    'Goal': 'star',
    'Resource': 'pentagon',
    'Milestone': 'diamond',
}


DEFAULT_TIME_SETTINGS = {
    # Hobbies and personal interests, outside a working week.
    'hours_per_week': 10,
    'hours_per_month': 40,
    'show_hour_equivalents': True,
}

DEFAULT_MONTE_CARLO_TRIALS = 10000

# Fraction of each task's log-variance that is shared with every other task in a
# simulated chain — systematic estimating bias, as opposed to a surprise
# specific to one task. At 0 the simulator treats tasks as independent, which
# makes a long project's relative spread shrink like 1/sqrt(N) and quotes a
# 116-task forecast to +/-3%. At 1 there is no diversification at all and a
# whole project has fully shared log-duration shocks. The 0.4 default is a
# provisional modeling assumption, not a calibrated estimate. Future estimation
# requires original forecasts and grouped outcomes across projects or periods
# to separate common variation from task-specific error and persistent bias.
DEFAULT_ESTIMATE_CORRELATION = 0.4

DEFAULT_GRAPH_LAYOUT = {
    'edge_length': 100,
    'gravity': 0,
    'repulsion': 50000,
}

DEFAULT_DETAILS_GRAPH_LAYOUT = {
    'edge_length': 50,
    'gravity': 0.25,
    'repulsion': 4500,
}

DEFAULT_EVENTS_GRAPH_LAYOUT = {
    'edge_length': 50,
    'gravity': 0.25,
    'repulsion': 4500,
}

DEFAULT_ANALYZE_LIMITS = {
    'bottlenecks': 15,
    'goals': 15,
    # A new graph has weeks of history, not quarters: one quarterly bar says little.
    'throughput_granularity': 'month',  # 'month' | 'quarter' | 'year'
    'throughput_color': 'context',  # 'context' | 'type': what stacks the bars
    'throughput_start': None,  # ISO date string; None = earliest done_date
    'throughput_end': None,    # ISO date string; None = latest done_date
}

DEFAULT_RATINGS_DEFINITIONS = [
    {"rating": 1,
     "value": "Trivial: a small gain for a small area.",
     "interest": "Averse: I'd have to force myself throughout.",
     "effort": "Automatic: I can do this unconsciously."},
    {"rating": 2,
     "value": "Marginal: a modest gain for a small area.",
     "interest": "Reluctant: I'd have to force myself to start.",
     "effort": "Easy: well within my abilities, and it needs little attention."},
    {"rating": 3,
     "value": "Minor: a big gain for a small area.",
     "interest": "Unappealing: I'd sometimes have to force myself to start.",
     "effort": "Straightforward: within my abilities, but it needs my attention."},
    {"rating": 4,
     "value": "Helpful: a small gain for a big area.",
     "interest": "Tolerable: I wouldn't choose it, but I wouldn't mind.",
     "effort": "Tricky: within my abilities, but a few parts are tricky."},
    {"rating": 5,
     "value": "Solid: a modest gain for a big area.",
     "interest": "Indifferent: no strong feelings either way.",
     "effort": "Substantial: within my abilities, but only with real effort."},
    {"rating": 6,
     "value": "Significant: a big gain for a big area.",
     "interest": "Curious: I'd pick it up when I have spare time.",
     "effort": "Difficult: my abilities are just enough, but only at my best."},
    {"rating": 7,
     "value": "Important: a big gain for a core area.",
     "interest": "Eager: I'd make time for it.",
     "effort": "Demanding: modestly beyond my abilities; I'll learn as I go."},
    {"rating": 8,
     "value": "Crucial: a big gain for a couple of core areas.",
     "interest": "Invested: I'd choose it over other things I enjoy.",
     "effort": "Formidable: well beyond my abilities; I'll need new skills first."},
    {"rating": 9,
     "value": "Transformative: a profound gain for my whole life.",
     "interest": "Magnetic: I'd give up other things I enjoy to make room for it.",
     "effort": "Daunting: far beyond my abilities; I can't yet see the path."},
    {"rating": 10,
     "value": "Defining: one of the most important things I'll ever do.",
     "interest": "Calling: there is nothing I would rather do.",
     "effort": "Herculean: probably beyond what I could ever do, even with unlimited time."},
]

# Retrospective counterpart to DEFAULT_RATINGS_DEFINITIONS, used only by the
# Reflection modal ("Actual ratings"). Same 1-10 ladder and anchor words
# so reflect_* values stay comparable to the estimate columns (Analyze diffs
# them), but each clause is reworded from "what do I anticipate?" to "what
# actually happened?" — e.g. Interest asks what I actually chose and traded
# away, where the estimate asks what I would choose.
DEFAULT_REFLECTION_RATINGS_DEFINITIONS = [
    {"rating": 1,
     "value": "Trivial: it was a small gain for a small area.",
     "interest": "Averse: I had to force myself throughout.",
     "effort": "Automatic: I did this unconsciously."},
    {"rating": 2,
     "value": "Marginal: it was a modest gain for a small area.",
     "interest": "Reluctant: I had to force myself to start.",
     "effort": "Easy: well within my abilities, and it needed little attention."},
    {"rating": 3,
     "value": "Minor: it was a big gain for a small area.",
     "interest": "Unappealing: I sometimes had to force myself to start.",
     "effort": "Straightforward: within my abilities, but it needed my attention."},
    {"rating": 4,
     "value": "Helpful: it was a small gain for a big area.",
     "interest": "Tolerable: I wouldn't have chosen it, but I didn't mind.",
     "effort": "Tricky: within my abilities, but a few parts were tricky."},
    {"rating": 5,
     "value": "Solid: it was a modest gain for a big area.",
     "interest": "Indifferent: I had no strong feelings either way.",
     "effort": "Substantial: within my abilities, but only with real effort."},
    {"rating": 6,
     "value": "Significant: it was a big gain for a big area.",
     "interest": "Curious: I picked it up when I had spare time.",
     "effort": "Difficult: my abilities were just enough, but only at my best."},
    {"rating": 7,
     "value": "Important: it was a big gain for a core area.",
     "interest": "Eager: I made time for it.",
     "effort": "Demanding: modestly beyond my abilities; I had to learn as I went."},
    {"rating": 8,
     "value": "Crucial: it was a big gain for a couple of core areas.",
     "interest": "Invested: I chose it over other things I enjoy.",
     "effort": "Formidable: well beyond my abilities; I needed new skills first."},
    {"rating": 9,
     "value": "Transformative: it was a profound gain for my whole life.",
     "interest": "Magnetic: I gave up other things I enjoy to make room for it.",
     "effort": "Daunting: far beyond my abilities; I couldn't see the path until late."},
    {"rating": 10,
     "value": "Defining: it turned out to be one of the most important things I've done.",
     "interest": "Calling: there was nothing I would rather have been doing.",
     "effort": "Herculean: it took more than I thought I was capable of when I started."},
]


# Names stay as typed unless the user opts in: Title Case would turn "iOS"
# into "IOS".
DEFAULT_TITLECASE_LINTER = {
    'mode': NAME_FORMAT_NONE,
    'enabled': False,
    'exclusions': DEFAULT_TITLECASE_EXCLUSIONS,
}


DEFAULT_NEXT_TABLE_ROWS = 10

DEFAULT_SHOW_SCORING_PERF = False

DEFAULT_TIME_CALIBRATION_ENABLED = True


class ConfigManager:
    """Classmethod-only facade over the Settings key/value table.

    Getters read SQLite or the current operation's detached read snapshot,
    falling back to copies of the DEFAULT_* constants, so a caller that edits
    what it gets back can't change the defaults for the rest of the process.
    Setters write back and invalidate that snapshot. There is no settings
    cache retained between operations.
    """

    @staticmethod
    def _get_db_value(key: str) -> Optional[str]:
        snapshot = database.current_snapshot()
        if snapshot is not None:
            return snapshot.settings.get(key)
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM Settings WHERE key=?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    @database.atomic
    def _set_db_value(key: str, value: str):
        with get_connection() as conn:
            cursor = conn.cursor()
            previous = cursor.execute("SELECT value FROM Settings WHERE key=?", (key,)).fetchone()
            if previous and previous[0] == value:
                return
            cursor.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
        if key in {"HYPERPARAMS", "HP_PROFILE", "CONTEXT_WEIGHTS", "TIME_SETTINGS",
                   "PRIORITY_GOALS", "NODE_COLORS", "NODE_SHAPES"}:
            from skilltree.store.graph.manager import GraphManager
            GraphManager()._bump_version(scoring=False)

    @classmethod
    def get_node_types(cls):
        val = cls._get_db_value("NODE_TYPES")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_NODE_TYPES)

    @classmethod
    def set_node_types(cls, types: list):
        cls._set_db_value("NODE_TYPES", json.dumps(types))

    @classmethod
    def get_context_weights(cls) -> dict:
        val = cls._get_db_value("CONTEXT_WEIGHTS")
        return json.loads(val) if val else {}

    @classmethod
    def set_context_weights(cls, weights: dict):
        cls._set_db_value("CONTEXT_WEIGHTS", json.dumps(weights))

    @classmethod
    def get_contexts(cls):
        val = cls._get_db_value("CONTEXTS")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_CONTEXTS)

    @classmethod
    def set_contexts(cls, contexts: list):
        cls._set_db_value("CONTEXTS", json.dumps(contexts))

    @classmethod
    def get_subcontexts(cls):
        val = cls._get_db_value("SUBCONTEXTS")
        if not val:
            return copy.deepcopy(DEFAULT_SUBCONTEXTS)
        try:
            data = json.loads(val)
            if isinstance(data, list):
                return {}
            return data
        except (json.JSONDecodeError, TypeError):
            return {}

    @classmethod
    def set_subcontexts(cls, subcontexts: dict):
        cls._set_db_value("SUBCONTEXTS", json.dumps(subcontexts))

    @classmethod
    def get_subcontext_sort_mode(cls) -> str:
        val = cls._get_db_value("SUBCONTEXT_SORT_MODE")
        if val in SUBCONTEXT_SORT_MODES:
            return val
        return DEFAULT_SUBCONTEXT_SORT_MODE

    @classmethod
    def set_subcontext_sort_mode(cls, mode: str):
        if mode not in SUBCONTEXT_SORT_MODES:
            mode = DEFAULT_SUBCONTEXT_SORT_MODE
        cls._set_db_value("SUBCONTEXT_SORT_MODE", mode)

    @classmethod
    def get_context_sort_mode(cls) -> str:
        val = cls._get_db_value("CONTEXT_SORT_MODE")
        if val in CONTEXT_SORT_MODES:
            return val
        return DEFAULT_CONTEXT_SORT_MODE

    @classmethod
    def set_context_sort_mode(cls, mode: str):
        if mode not in CONTEXT_SORT_MODES:
            mode = DEFAULT_CONTEXT_SORT_MODE
        cls._set_db_value("CONTEXT_SORT_MODE", mode)

    @classmethod
    def get_node_colors(cls):
        val = cls._get_db_value("NODE_COLORS")
        if val:
            stored = json.loads(val)
            # Legacy rename: 'Active' → 'Now'. Migrate in-memory so consumers
            # see the new key without forcing a write on every read.
            if 'Active' in stored and 'Now' not in stored:
                stored['Now'] = stored.pop('Active')
            return {**DEFAULT_NODE_COLORS, **stored}
        return dict(DEFAULT_NODE_COLORS)

    @classmethod
    def set_node_colors(cls, colors: dict):
        cls._set_db_value("NODE_COLORS", json.dumps(colors))

    @classmethod
    def get_node_shapes(cls):
        val = cls._get_db_value("NODE_SHAPES")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_NODE_SHAPES)

    @classmethod
    def set_node_shapes(cls, shapes: dict):
        cls._set_db_value("NODE_SHAPES", json.dumps(shapes))

    @classmethod
    def get_hyperparams(cls):
        """The scoring settings: the chosen profile, as the code defines it now.

        Settings stores only the profile's name, so a retune reaches every
        install. A bundle written with set_hyperparams overrides it. A row
        from before is a snapshot an older Settings save took of its profile,
        and is ignored (see HYPERPARAMS_SCHEMA_VERSION).
        """
        name = cls._get_db_value("HP_PROFILE")
        merged = dict(DEFAULT_HYPERPARAMS)
        merged.update(PROFILES.get(PROFILE_ALIASES.get(name, name), DEFAULT_HYPERPARAMS))
        val = cls._get_db_value("HYPERPARAMS")
        if val:
            stored = json.loads(val)
            if stored.get('_schema', 1) >= 5:
                merged.update(stored)
        merged.pop('_schema', None)
        merged.pop('alpha', None)
        # Reads never write. Preserve v5 custom overrides, including pair-only
        # bundles, without allowing anticipation to exceed completed strength.
        strength, _, cross = synergy_parameters(merged['d_Syn_pair'],
            merged['d_Syn_mul'], merged['cross_context_mult'])
        merged['d_Syn_mul'] = strength
        merged['cross_context_mult'] = cross
        return merged

    @classmethod
    def set_hyperparams(cls, params: dict):
        """Override the profile's scoring settings, for tests and tools.
        Settings never calls this: it stores the profile's name only."""
        stamped = dict(params)
        stamped.pop('alpha', None)
        name = cls._get_db_value('HP_PROFILE')
        effective = dict(DEFAULT_HYPERPARAMS)
        effective.update(PROFILES.get(PROFILE_ALIASES.get(name, name), DEFAULT_HYPERPARAMS))
        effective.update(stamped)
        strength, _, _ = synergy_parameters(effective['d_Syn_pair'],
            effective['d_Syn_mul'], effective['cross_context_mult'])
        if strength != effective['d_Syn_mul']:
            stamped['d_Syn_mul'] = strength
        stamped['_schema'] = HYPERPARAMS_SCHEMA_VERSION
        cls._set_db_value("HYPERPARAMS", json.dumps(stamped))

    @classmethod
    @database.atomic
    def clear_hyperparams(cls):
        """Drop any stored scoring settings, so the profile alone decides."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM Settings WHERE key='HYPERPARAMS'")
            removed = cursor.rowcount
            conn.commit()
        if removed:
            from skilltree.store.graph.manager import GraphManager
            GraphManager()._bump_version(scoring=False)

    @classmethod
    def get_graph_layout_defaults(cls):
        val = cls._get_db_value("GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_GRAPH_LAYOUT)

    @classmethod
    def set_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_details_graph_layout_defaults(cls):
        val = cls._get_db_value("DETAILS_GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_DETAILS_GRAPH_LAYOUT)

    @classmethod
    def set_details_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("DETAILS_GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_events_graph_layout_defaults(cls):
        val = cls._get_db_value("EVENTS_GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else copy.deepcopy(DEFAULT_EVENTS_GRAPH_LAYOUT)

    @classmethod
    def set_events_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("EVENTS_GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_analyze_limits(cls):
        val = cls._get_db_value("ANALYZE_LIMITS")
        # A stored value missing a key reads that key's default.
        return {**DEFAULT_ANALYZE_LIMITS, **json.loads(val)} if val else copy.deepcopy(DEFAULT_ANALYZE_LIMITS)

    @classmethod
    def set_analyze_limits(cls, params: dict):
        cls._set_db_value("ANALYZE_LIMITS", json.dumps(params))

    @classmethod
    def get_ratings_definitions(cls):
        val = cls._get_db_value("RATINGS_DEFINITIONS")
        if val:
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        return [dict(d) for d in DEFAULT_RATINGS_DEFINITIONS]

    @classmethod
    def set_ratings_definitions(cls, defs: list):
        cls._set_db_value("RATINGS_DEFINITIONS", json.dumps(defs))

    @classmethod
    def get_reflection_ratings_definitions(cls):
        val = cls._get_db_value("REFLECTION_RATINGS_DEFINITIONS")
        if val:
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        return [dict(d) for d in DEFAULT_REFLECTION_RATINGS_DEFINITIONS]

    @classmethod
    def set_reflection_ratings_definitions(cls, defs: list):
        cls._set_db_value("REFLECTION_RATINGS_DEFINITIONS", json.dumps(defs))

    @classmethod
    def get_time_settings(cls):
        val = cls._get_db_value("TIME_SETTINGS")
        # A stored value missing a key reads that key's default.
        return {**DEFAULT_TIME_SETTINGS, **json.loads(val)} if val else copy.deepcopy(DEFAULT_TIME_SETTINGS)

    @classmethod
    def set_time_settings(cls, params: dict):
        cls._set_db_value("TIME_SETTINGS", json.dumps(params))

    @classmethod
    def get_monte_carlo_trials(cls) -> int:
        """Number of Monte Carlo trials for the Time Simulation panel."""
        try:
            n = int(cls.get_time_settings().get(
                'monte_carlo_trials', DEFAULT_MONTE_CARLO_TRIALS))
        except (TypeError, ValueError):
            return DEFAULT_MONTE_CARLO_TRIALS
        return n if n > 0 else DEFAULT_MONTE_CARLO_TRIALS

    @classmethod
    def get_estimate_correlation(cls) -> float:
        """Shared-bias fraction used by the Time Simulation panel."""
        try:
            rho = float(cls.get_time_settings().get(
                'estimate_correlation', DEFAULT_ESTIMATE_CORRELATION))
        except (TypeError, ValueError):
            return DEFAULT_ESTIMATE_CORRELATION
        if not 0.0 <= rho <= 1.0:
            return DEFAULT_ESTIMATE_CORRELATION
        return rho

    @classmethod
    def get_goal_order(cls):
        val = cls._get_db_value("GOAL_ORDER")
        return json.loads(val) if val else []

    @classmethod
    def set_goal_order(cls, order: list):
        cls._set_db_value("GOAL_ORDER", json.dumps(order))

    @classmethod
    def get_event_order(cls) -> list:
        """The Events list's manual (drag) order, as event names."""
        val = cls._get_db_value("EVENT_ORDER")
        try:
            order = json.loads(val) if val else []
        except (json.JSONDecodeError, TypeError):
            return []
        return order if isinstance(order, list) else []

    @classmethod
    def set_event_order(cls, order: list):
        cls._set_db_value("EVENT_ORDER", json.dumps(order))

    @classmethod
    def rename_event_references(cls, old_name: str, new_name: str) -> None:
        """Carry an event rename into the settings that store event names."""
        order = cls.get_event_order()
        if old_name in order:
            cls.set_event_order([new_name if e == old_name else e for e in order])

    @classmethod
    def delete_event_references(cls, name: str) -> None:
        """Drop a deleted event from the settings that store event names."""
        order = cls.get_event_order()
        if name in order:
            cls.set_event_order([e for e in order if e != name])

    @classmethod
    def get_list_sort(cls, list_id: str, default: str) -> str:
        """The saved sort of one sidebar list, keyed by its store id."""
        val = cls._get_db_value("LIST_SORTS")
        try:
            sorts = json.loads(val) if val else {}
        except (json.JSONDecodeError, TypeError):
            sorts = {}
        value = sorts.get(list_id) if isinstance(sorts, dict) else None
        return value if isinstance(value, str) else default

    @classmethod
    def set_list_sort(cls, list_id: str, value: str):
        val = cls._get_db_value("LIST_SORTS")
        try:
            sorts = json.loads(val) if val else {}
        except (json.JSONDecodeError, TypeError):
            sorts = {}
        if not isinstance(sorts, dict):
            sorts = {}
        sorts[list_id] = value
        cls._set_db_value("LIST_SORTS", json.dumps(sorts, sort_keys=True))

    @classmethod
    def get_hours_per_year(cls) -> float:
        return HOURS_PER_YEAR_MULT * cls.get_time_settings()['hours_per_month']

    @classmethod
    def get_hours_per_day(cls) -> float:
        return cls.get_time_settings()['hours_per_week'] / DAYS_PER_WEEK

    @classmethod
    def get_time_multiplier(cls, unit: str) -> float:
        """Hours in one `unit` ('hours', 'days', 'weeks', 'months' or 'years'),
        for converting a time input to hours."""
        return hours_per_unit(unit, cls.get_time_settings())

    @classmethod
    def get_hp_profile(cls) -> str:
        val = cls._get_db_value("HP_PROFILE")
        if not val:
            return "Sage"
        # Profile renames over time — quietly translate any leftover DB
        # value so the dropdown stays populated and the profile keeps
        # working. Each branch persists the new name so the upgrade is
        # one-time.
        #   Industrious → Pragmatic → Pragmatist (2026-05)
        #   Default     → Sage                   (2026-05)
        #   Curious     → Explorer               (2026-05)
        #   Sprinter    → Glider                 (2026-05)
        #   Compounder  → Investor               (2026-10)
        if val in PROFILE_ALIASES:
            cls._set_db_value("HP_PROFILE", PROFILE_ALIASES[val])
            return PROFILE_ALIASES[val]
        return val

    @classmethod
    def set_hp_profile(cls, profile: str):
        cls._set_db_value("HP_PROFILE", profile)

    # Types that always keep their shape even if not in the user's type list.
    # Goal and Milestone are referenced by literal string in scoring.py and
    # the canvas hover tooltip, so their visual identity must persist even
    # if a user removes them from the editable type list.
    _PERMANENT_SHAPE_TYPES = {'Goal', 'Milestone'}

    @classmethod
    def sync_shapes_to_types(cls, new_types: list):
        """Prune shapes for removed types and add defaults for new types."""
        shapes = cls.get_node_shapes()
        # Remove shapes for types that no longer exist, but preserve permanent types
        shapes = {k: v for k, v in shapes.items()
                  if k in new_types or k in cls._PERMANENT_SHAPE_TYPES}
        # Add default shape for new types
        for t in new_types:
            if t not in shapes:
                shapes[t] = DEFAULT_NODE_SHAPES.get(t, 'rectangle')
        cls.set_node_shapes(shapes)

    @classmethod
    def get_priority_goals(cls):
        val = cls._get_db_value("PRIORITY_GOALS")
        return json.loads(val) if val else []

    @classmethod
    def set_priority_goals(cls, goals: list):
        cls._set_db_value("PRIORITY_GOALS", json.dumps(goals[:3]))

    @classmethod
    def drop_priority_goal(cls, name: str) -> None:
        """Take ``name``'s priority rank away, if it has one. The ranks after
        it move up."""
        pg = cls.get_priority_goals()
        if name in pg:
            cls.set_priority_goals([g for g in pg if g != name])

    @classmethod
    def rename_node_references(cls, old_name: str, new_name: str) -> None:
        """Propagate a node rename to every config entry that stores a node name.

        Called from GraphManager.rename_node so callers don't have to remember
        which config keys hold names — the failure mode when they forget is a
        silent drop (lazy cleanup treats the old name as a deleted node).
        """
        if not old_name or not new_name or old_name == new_name:
            return

        pg = cls.get_priority_goals()
        if old_name in pg:
            cls.set_priority_goals([new_name if g == old_name else g for g in pg])

        order = cls.get_goal_order()
        if old_name in order:
            cls.set_goal_order([new_name if g == old_name else g for g in order])

    @classmethod
    def delete_node_references(cls, name: str) -> None:
        """Prune every config entry that stores a node name.

        Symmetric to `rename_node_references`. Called from
        GraphManager.delete_node so callers don't each have to remember which
        config keys hold names. Without this, deletes leave dangling
        references that fail silently (a priority goal wastes a rank slot on a
        node nobody can reach, etc.).
        """
        if not name:
            return

        cls.drop_priority_goal(name)

        order = cls.get_goal_order()
        if name in order:
            cls.set_goal_order([g for g in order if g != name])

    # --- Pending Event Notifications (the Events Triggered announcement) ---

    @classmethod
    def get_pending_event_notifications(cls) -> list:
        val = cls._get_db_value("PENDING_EVENT_NOTIFICATIONS")
        return json.loads(val) if val else []

    @classmethod
    def add_pending_event_notification(cls, entry: dict):
        entries = cls.get_pending_event_notifications()
        entries.append(entry)
        cls._set_db_value("PENDING_EVENT_NOTIFICATIONS", json.dumps(entries))

    @classmethod
    def clear_pending_event_notifications(cls):
        cls._set_db_value("PENDING_EVENT_NOTIFICATIONS", json.dumps([]))

    @classmethod
    def set_pending_event_notifications(cls, entries: list):
        cls._set_db_value("PENDING_EVENT_NOTIFICATIONS", json.dumps(entries))

    @classmethod
    @database.atomic
    def remove_pending_event_notifications(cls, shown: list):
        """Drop the notifications the announcement showed, and only those.
        One queued while it was open waits for the next announcement."""
        entries = cls.get_pending_event_notifications()
        remaining = [entry for entry in entries if entry not in (shown or [])]
        if len(remaining) != len(entries):
            cls.set_pending_event_notifications(remaining)

    @classmethod
    def ensure_action_type(cls):
        """Ensure 'Action' type exists in stored node types (migration for existing DBs)."""
        types = cls.get_node_types()
        if 'Action' not in types:
            types.append('Action')
            cls.set_node_types(types)
            cls.sync_shapes_to_types(types)

    @classmethod
    def ensure_goal_type(cls):
        """Ensure 'Goal' type exists in stored node types (migration for existing DBs)."""
        types = cls.get_node_types()
        if 'Goal' not in types:
            types.append('Goal')
            cls.set_node_types(types)
            cls.sync_shapes_to_types(types)

    @classmethod
    def ensure_milestone_type(cls):
        """Ensure 'Milestone' type exists in stored node types (migration for existing DBs)."""
        types = cls.get_node_types()
        if 'Milestone' not in types:
            types.append('Milestone')
            cls.set_node_types(types)
            cls.sync_shapes_to_types(types)

    @classmethod
    def get_name_formatting(cls) -> dict:
        val = cls._get_db_value("TITLECASE_LINTER")
        if val:
            try:
                saved = json.loads(val)
                if isinstance(saved, dict):
                    mode = saved.get('mode')
                    if mode not in NAME_FORMAT_MODES:
                        # Migrate the former enabled switch without requiring a
                        # database rewrite during a read.
                        mode = (NAME_FORMAT_TITLE if saved.get('enabled', True)
                                else NAME_FORMAT_NONE)
                    exclusions = saved.get('exclusions', DEFAULT_TITLECASE_EXCLUSIONS)
                    if not isinstance(exclusions, list):
                        exclusions = list(DEFAULT_TITLECASE_EXCLUSIONS)
                    return {
                        'mode': mode,
                        'enabled': mode != NAME_FORMAT_NONE,
                        'exclusions': list(exclusions),
                    }
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            **DEFAULT_TITLECASE_LINTER,
            'exclusions': list(DEFAULT_TITLECASE_EXCLUSIONS),
        }

    @classmethod
    def set_name_formatting(cls, settings: dict):
        mode = settings.get('mode')
        if mode not in NAME_FORMAT_MODES:
            mode = (NAME_FORMAT_TITLE if settings.get('enabled', True)
                    else NAME_FORMAT_NONE)
        exclusions = settings.get('exclusions', DEFAULT_TITLECASE_EXCLUSIONS)
        if not isinstance(exclusions, list):
            exclusions = list(DEFAULT_TITLECASE_EXCLUSIONS)
        cls._set_db_value("TITLECASE_LINTER", json.dumps({
            'mode': mode,
            'enabled': mode != NAME_FORMAT_NONE,
            'exclusions': exclusions,
        }))

    @classmethod
    def get_next_table_rows(cls) -> int:
        val = cls._get_db_value("NEXT_TABLE_ROWS")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return DEFAULT_NEXT_TABLE_ROWS

    @classmethod
    def set_next_table_rows(cls, count: int):
        cls._set_db_value("NEXT_TABLE_ROWS", str(count))

    @classmethod
    def get_now_node_cap(cls) -> int:
        val = cls._get_db_value("NOW_NODE_CAP")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return DEFAULT_NOW_NODE_CAP

    @classmethod
    def set_now_node_cap(cls, count: int):
        cls._set_db_value("NOW_NODE_CAP", str(count))

    @classmethod
    def get_unblocking_steps_per_now(cls) -> int:
        val = cls._get_db_value("UNBLOCKING_STEPS_PER_NOW")
        if val:
            try:
                return max(0, int(val))
            except ValueError:
                pass
        return DEFAULT_UNBLOCKING_STEPS_PER_NOW

    @classmethod
    def set_unblocking_steps_per_now(cls, count: int):
        cls._set_db_value("UNBLOCKING_STEPS_PER_NOW", str(count))

    @classmethod
    def get_show_scoring_perf(cls) -> bool:
        val = cls._get_db_value("SHOW_SCORING_PERF")
        if val is None:
            return DEFAULT_SHOW_SCORING_PERF
        return val == "1"

    @classmethod
    def set_show_scoring_perf(cls, enabled: bool):
        cls._set_db_value("SHOW_SCORING_PERF", "1" if enabled else "0")

    @classmethod
    def get_auto_backup(cls) -> bool:
        """Whether the app makes its once-a-day backup. On unless switched off."""
        return cls._get_db_value("AUTO_BACKUP") != "0"

    @classmethod
    def set_auto_backup(cls, enabled: bool):
        cls._set_db_value("AUTO_BACKUP", "1" if enabled else "0")

    @classmethod
    def get_backup_extra_dir(cls) -> str:
        """A second folder each new backup is also copied to, or ''.

        Typically a synced folder, so a copy survives the loss of the machine.
        """
        return cls._get_db_value("BACKUP_EXTRA_DIR") or ""

    @classmethod
    def set_backup_extra_dir(cls, path: str):
        cls._set_db_value("BACKUP_EXTRA_DIR", (path or "").strip())

    @classmethod
    def get_welcome_done(cls) -> bool:
        """Whether the first-launch welcome has been answered (onboarding.py)."""
        return cls._get_db_value("WELCOME_DONE") == "1"

    @classmethod
    def set_welcome_done(cls, done: bool):
        cls._set_db_value("WELCOME_DONE", "1" if done else "0")

    @classmethod
    def get_getting_started_progress(cls) -> list:
        """Getting Started steps already done, so they never un-tick."""
        raw = cls._get_db_value("GETTING_STARTED_PROGRESS")
        try:
            keys = json.loads(raw) if raw else []
        except ValueError:
            return []
        return [k for k in keys if isinstance(k, str)] if isinstance(keys, list) else []

    @classmethod
    def set_getting_started_progress(cls, keys):
        cls._set_db_value("GETTING_STARTED_PROGRESS", json.dumps(sorted(set(keys))))

    @classmethod
    def get_getting_started_dismissed(cls) -> bool:
        return cls._get_db_value("GETTING_STARTED_DISMISSED") == "1"

    @classmethod
    def set_getting_started_dismissed(cls, dismissed: bool):
        cls._set_db_value("GETTING_STARTED_DISMISSED", "1" if dismissed else "0")

    @classmethod
    def get_last_app_version(cls) -> Optional[str]:
        """The app version that most recently opened this database, if any."""
        return cls._get_db_value("LAST_APP_VERSION")

    @classmethod
    def set_last_app_version(cls, version: str):
        cls._set_db_value("LAST_APP_VERSION", version)

    @classmethod
    def get_time_calibration_enabled(cls) -> bool:
        """Whether to prompt for actual time spent when a node is marked Done."""
        val = cls._get_db_value("TIME_CALIBRATION_ENABLED")
        if val is None:
            return DEFAULT_TIME_CALIBRATION_ENABLED
        return val == "1"

    @classmethod
    def set_time_calibration_enabled(cls, enabled: bool):
        cls._set_db_value("TIME_CALIBRATION_ENABLED", "1" if enabled else "0")
