"""The user's settings, stored in the Settings table.

Each stored setting is a Setting: its key in that key/value table and its
default. ``NOW_NODE_CAP.get()`` reads the stored value, or a copy of the
default when nothing usable is stored, and ``NOW_NODE_CAP.set(4)`` writes one
back. All state lives in SQLite, so every module shares it through one
import. The functions at the end combine settings: hyperparams(),
time_multiplier() and the like.
"""

import copy
import json
from skilltree.store import database
from typing import Optional
from skilltree.store.database import get_connection
from skilltree.store.graph.state import revisions
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
# settings tab (NOW_NODE_CAP below). Setting Now is refused
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


# --- Storage ------------------------------------------------------------------

# Every Setting, by its key in the Settings table.
SETTINGS = {}


def read_stored(key: str) -> Optional[str]:
    """The text stored under ``key``, or None. Reads the current operation's
    detached snapshot when there is one."""
    snapshot = database.current_snapshot()
    if snapshot is not None:
        return snapshot.settings.get(key)
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM Settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


def _changed(key):
    setting = SETTINGS.get(key)
    if setting is not None and setting.refreshes_graph:
        revisions.changed(scoring=False)


@database.atomic
def write_stored(key: str, text: str):
    """Store ``text`` under ``key``. Writing the same text again does nothing."""
    with get_connection() as conn:
        previous = conn.execute("SELECT value FROM Settings WHERE key=?", (key,)).fetchone()
        if previous and previous[0] == text:
            return
        conn.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, text))
        conn.commit()
    _changed(key)


@database.atomic
def clear_stored(key: str):
    """Drop what is stored under ``key``, so its default applies again."""
    with get_connection() as conn:
        removed = conn.execute("DELETE FROM Settings WHERE key=?", (key,)).rowcount
        conn.commit()
    if removed:
        _changed(key)


class Setting:
    """One stored setting: its key in the Settings table and its default.

    ``read`` turns the stored text into a value, and ``write`` a value into
    text. Both are JSON unless the setting says otherwise. A ``read`` that
    raises ValueError or TypeError marks the stored text unusable, and the
    default is read instead. ``merge_defaults`` fills in the keys a stored
    dict lacks from the default. ``refreshes_graph`` marks a setting that
    changes scores or how the canvas draws nodes: writing it bumps the graph
    revision, so every view redraws.
    """

    def __init__(self, key, default, *, read=json.loads, write=json.dumps,
                 merge_defaults=False, refreshes_graph=False):
        self.key = key
        self.default = default
        self.read = read
        self.write = write
        self.merge_defaults = merge_defaults
        self.refreshes_graph = refreshes_graph
        SETTINGS[key] = self

    def get(self):
        """The stored value, or a copy of the default when nothing usable is
        stored. A caller may change what it gets without changing the
        default for the rest of the process."""
        text = read_stored(self.key)
        if text:
            try:
                value = self.read(text)
                if self.merge_defaults:
                    value = {**copy.deepcopy(self.default), **value}
                return value
            except (ValueError, TypeError):
                pass
        return copy.deepcopy(self.default)

    def set(self, value):
        write_stored(self.key, self.write(value))

    def clear(self):
        clear_stored(self.key)

    def __repr__(self):
        return f"Setting({self.key!r})"


class NameList(Setting):
    """A setting that lists node or event names in order. A rename or a
    delete of what they name carries into it."""

    def rename(self, old_name, new_name):
        names = self.get()
        if old_name in names:
            self.set([new_name if name == old_name else name for name in names])

    def drop(self, name):
        """Take ``name`` out. The names after it move up."""
        names = self.get()
        if name in names:
            self.set([other for other in names if other != name])


def _list(text):
    value = json.loads(text)
    if not isinstance(value, list):
        raise TypeError(f"a list was expected, not {type(value).__name__}")
    return value


def _dict(text):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError(f"a dict was expected, not {type(value).__name__}")
    return value


def _is_on(text):
    return text == "1"


def _on_text(on):
    return "1" if on else "0"


def _one_of(choices, default):
    """``read`` and ``write`` for a setting stored as plain text, one of
    ``choices``. Anything else reads, and is written, as ``default``."""
    def read(text):
        if text not in choices:
            raise ValueError(f"{text!r} is not one of {sorted(choices)}")
        return text

    def write(value):
        return value if value in choices else default
    return {'read': read, 'write': write}


# --- Node types and contexts ----------------------------------------------------

NODE_TYPES = Setting("NODE_TYPES", DEFAULT_NODE_TYPES)
CONTEXTS = Setting("CONTEXTS", DEFAULT_CONTEXTS)


def _subcontexts(text):
    """The legacy list format, or text that isn't JSON, reads as no
    subcontexts at all, not as the defaults."""
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


SUBCONTEXTS = Setting("SUBCONTEXTS", DEFAULT_SUBCONTEXTS, read=_subcontexts)
CONTEXT_SORT_MODE = Setting("CONTEXT_SORT_MODE", DEFAULT_CONTEXT_SORT_MODE,
                            **_one_of(CONTEXT_SORT_MODES, DEFAULT_CONTEXT_SORT_MODE))
SUBCONTEXT_SORT_MODE = Setting("SUBCONTEXT_SORT_MODE", DEFAULT_SUBCONTEXT_SORT_MODE,
                               **_one_of(SUBCONTEXT_SORT_MODES, DEFAULT_SUBCONTEXT_SORT_MODE))
# A missing context weighs 1.
CONTEXT_WEIGHTS = Setting("CONTEXT_WEIGHTS", {}, refreshes_graph=True)


# --- Appearance -----------------------------------------------------------------

def _node_colors(text):
    colors = json.loads(text)
    # Legacy rename: 'Active' → 'Now'. Renamed as it is read, so a read
    # never writes.
    if 'Active' in colors and 'Now' not in colors:
        colors['Now'] = colors.pop('Active')
    return colors


NODE_COLORS = Setting("NODE_COLORS", DEFAULT_NODE_COLORS, read=_node_colors,
                      merge_defaults=True, refreshes_graph=True)
NODE_SHAPES = Setting("NODE_SHAPES", DEFAULT_NODE_SHAPES, refreshes_graph=True)
GRAPH_LAYOUT_DEFAULTS = Setting("GRAPH_LAYOUT_DEFAULTS", DEFAULT_GRAPH_LAYOUT)
DETAILS_GRAPH_LAYOUT_DEFAULTS = Setting("DETAILS_GRAPH_LAYOUT_DEFAULTS",
                                        DEFAULT_DETAILS_GRAPH_LAYOUT)
EVENTS_GRAPH_LAYOUT_DEFAULTS = Setting("EVENTS_GRAPH_LAYOUT_DEFAULTS",
                                       DEFAULT_EVENTS_GRAPH_LAYOUT)
SHOW_SCORING_PERF = Setting("SHOW_SCORING_PERF", DEFAULT_SHOW_SCORING_PERF,
                            read=_is_on, write=_on_text)


# --- Scoring --------------------------------------------------------------------

# Profiles have been renamed over time. A stored old name reads as the new
# one (PROFILE_ALIASES), so the dropdown stays filled and the profile keeps
# working.
HP_PROFILE = Setting("HP_PROFILE", "Sage", read=lambda name: PROFILE_ALIASES.get(name, name),
                     write=str, refreshes_graph=True)
# Scoring settings that override the profile's: see hyperparams().
HYPERPARAMS = Setting("HYPERPARAMS", None, read=_dict, refreshes_graph=True)
# The Goals ranked by priority, at most three.
PRIORITY_GOALS = NameList("PRIORITY_GOALS", [], write=lambda goals: json.dumps(goals[:3]),
                          refreshes_graph=True)


# --- Time -----------------------------------------------------------------------

# A stored value missing a key reads that key's default.
TIME_SETTINGS = Setting("TIME_SETTINGS", DEFAULT_TIME_SETTINGS, merge_defaults=True,
                        refreshes_graph=True)
TIME_CALIBRATION_ENABLED = Setting("TIME_CALIBRATION_ENABLED", DEFAULT_TIME_CALIBRATION_ENABLED,
                                   read=_is_on, write=_on_text)


# --- Ratings --------------------------------------------------------------------

RATINGS_DEFINITIONS = Setting("RATINGS_DEFINITIONS", DEFAULT_RATINGS_DEFINITIONS)
REFLECTION_RATINGS_DEFINITIONS = Setting("REFLECTION_RATINGS_DEFINITIONS",
                                         DEFAULT_REFLECTION_RATINGS_DEFINITIONS)


# --- Editing --------------------------------------------------------------------

def _name_formatting(saved):
    """Name formatting as it is read and written: a mode, the 'enabled'
    switch it replaced, and the words Title Case leaves alone."""
    if not isinstance(saved, dict):
        raise TypeError(f"a dict was expected, not {type(saved).__name__}")
    mode = saved.get('mode')
    if mode not in NAME_FORMAT_MODES:
        # The former enabled switch, read without rewriting the database.
        mode = NAME_FORMAT_TITLE if saved.get('enabled', True) else NAME_FORMAT_NONE
    exclusions = saved.get('exclusions', DEFAULT_TITLECASE_EXCLUSIONS)
    if not isinstance(exclusions, list):
        exclusions = DEFAULT_TITLECASE_EXCLUSIONS
    return {'mode': mode, 'enabled': mode != NAME_FORMAT_NONE,
            'exclusions': list(exclusions)}


NAME_FORMATTING = Setting(
    "TITLECASE_LINTER",
    {**DEFAULT_TITLECASE_LINTER, 'exclusions': list(DEFAULT_TITLECASE_EXCLUSIONS)},
    read=lambda text: _name_formatting(json.loads(text)),
    write=lambda formatting: json.dumps(_name_formatting(formatting)))


# --- Lists ----------------------------------------------------------------------

# The Goals and Events lists' manual (drag) orders.
GOAL_ORDER = NameList("GOAL_ORDER", [])
EVENT_ORDER = NameList("EVENT_ORDER", [], read=_list)
# Each sidebar list's sort, by the list's store id: see list_sort().
LIST_SORTS = Setting("LIST_SORTS", {}, read=_dict,
                     write=lambda sorts: json.dumps(sorts, sort_keys=True))

# The settings that store node names. A node's rename or delete carries into them.
NODE_NAME_SETTINGS = (PRIORITY_GOALS, GOAL_ORDER)


# --- Home -----------------------------------------------------------------------

NEXT_TABLE_ROWS = Setting("NEXT_TABLE_ROWS", DEFAULT_NEXT_TABLE_ROWS, read=int, write=str)
NOW_NODE_CAP = Setting("NOW_NODE_CAP", DEFAULT_NOW_NODE_CAP, read=int, write=str)
UNBLOCKING_STEPS_PER_NOW = Setting("UNBLOCKING_STEPS_PER_NOW", DEFAULT_UNBLOCKING_STEPS_PER_NOW,
                                   read=lambda text: max(0, int(text)), write=str)
# The Events Triggered announcement's queue: see add_event_notification().
PENDING_EVENT_NOTIFICATIONS = Setting("PENDING_EVENT_NOTIFICATIONS", [])


# --- Analyze --------------------------------------------------------------------

# A stored value missing a key reads that key's default.
ANALYZE_LIMITS = Setting("ANALYZE_LIMITS", DEFAULT_ANALYZE_LIMITS, merge_defaults=True)


# --- Backups --------------------------------------------------------------------

# The once-a-day backup. On unless switched off.
AUTO_BACKUP = Setting("AUTO_BACKUP", True, read=lambda text: text != "0", write=_on_text)
# A second folder each new backup is also copied to, or ''. Typically a
# synced folder, so a copy survives the loss of the machine.
BACKUP_EXTRA_DIR = Setting("BACKUP_EXTRA_DIR", "", read=str,
                           write=lambda path: (path or "").strip())


# --- Onboarding and the app -----------------------------------------------------

# Whether the first-launch welcome has been answered (features/onboarding).
WELCOME_DONE = Setting("WELCOME_DONE", False, read=_is_on, write=_on_text)
# Getting Started steps already done, so they never un-tick.
GETTING_STARTED_PROGRESS = Setting(
    "GETTING_STARTED_PROGRESS", [],
    read=lambda text: [key for key in _list(text) if isinstance(key, str)],
    write=lambda keys: json.dumps(sorted(set(keys))))
GETTING_STARTED_DISMISSED = Setting("GETTING_STARTED_DISMISSED", False,
                                    read=_is_on, write=_on_text)
# The app version that most recently opened this database, if any.
LAST_APP_VERSION = Setting("LAST_APP_VERSION", None, read=str, write=str)


# --- Combined settings ----------------------------------------------------------

def hyperparams():
    """The scoring settings: the chosen profile, as the code defines it now.

    Settings stores only the profile's name, so a retune reaches every
    install. A bundle written with set_hyperparams overrides it. A row
    from before is a snapshot an older Settings save took of its profile,
    and is ignored (see HYPERPARAMS_SCHEMA_VERSION).
    """
    merged = dict(DEFAULT_HYPERPARAMS)
    merged.update(PROFILES.get(HP_PROFILE.get(), DEFAULT_HYPERPARAMS))
    stored = HYPERPARAMS.get()
    if stored and stored.get('_schema', 1) >= 5:
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


def set_hyperparams(params: dict):
    """Override the profile's scoring settings, for tests and tools.
    Settings never calls this: it stores the profile's name only."""
    stamped = dict(params)
    stamped.pop('alpha', None)
    effective = dict(DEFAULT_HYPERPARAMS)
    effective.update(PROFILES.get(HP_PROFILE.get(), DEFAULT_HYPERPARAMS))
    effective.update(stamped)
    strength, _, _ = synergy_parameters(effective['d_Syn_pair'],
        effective['d_Syn_mul'], effective['cross_context_mult'])
    if strength != effective['d_Syn_mul']:
        stamped['d_Syn_mul'] = strength
    stamped['_schema'] = HYPERPARAMS_SCHEMA_VERSION
    HYPERPARAMS.set(stamped)


def clear_hyperparams():
    """Drop any stored scoring settings, so the profile alone decides."""
    HYPERPARAMS.clear()


def monte_carlo_trials() -> int:
    """Number of Monte Carlo trials for the Time Simulation panel."""
    try:
        n = int(TIME_SETTINGS.get().get('monte_carlo_trials', DEFAULT_MONTE_CARLO_TRIALS))
    except (TypeError, ValueError):
        return DEFAULT_MONTE_CARLO_TRIALS
    return n if n > 0 else DEFAULT_MONTE_CARLO_TRIALS


def estimate_correlation() -> float:
    """Shared-bias fraction used by the Time Simulation panel."""
    try:
        rho = float(TIME_SETTINGS.get().get('estimate_correlation', DEFAULT_ESTIMATE_CORRELATION))
    except (TypeError, ValueError):
        return DEFAULT_ESTIMATE_CORRELATION
    if not 0.0 <= rho <= 1.0:
        return DEFAULT_ESTIMATE_CORRELATION
    return rho


def hours_per_year() -> float:
    return HOURS_PER_YEAR_MULT * TIME_SETTINGS.get()['hours_per_month']


def hours_per_day() -> float:
    return TIME_SETTINGS.get()['hours_per_week'] / DAYS_PER_WEEK


def time_multiplier(unit: str) -> float:
    """Hours in one `unit` ('hours', 'days', 'weeks', 'months' or 'years'),
    for converting a time input to hours."""
    return hours_per_unit(unit, TIME_SETTINGS.get())


def list_sort(list_id: str, default: str) -> str:
    """The saved sort of one sidebar list, keyed by its store id."""
    value = LIST_SORTS.get().get(list_id)
    return value if isinstance(value, str) else default


def set_list_sort(list_id: str, value: str):
    LIST_SORTS.set({**LIST_SORTS.get(), list_id: value})


# Types that always keep their shape even if not in the user's type list.
# Goal and Milestone are referenced by literal string in scoring.py and
# the canvas hover tooltip, so their visual identity must persist even
# if a user removes them from the editable type list.
_PERMANENT_SHAPE_TYPES = {'Goal', 'Milestone'}


def sync_shapes_to_types(new_types: list):
    """Prune shapes for removed types and add defaults for new types."""
    shapes = {name: shape for name, shape in NODE_SHAPES.get().items()
              if name in new_types or name in _PERMANENT_SHAPE_TYPES}
    for node_type in new_types:
        if node_type not in shapes:
            shapes[node_type] = DEFAULT_NODE_SHAPES.get(node_type, 'rectangle')
    NODE_SHAPES.set(shapes)


def ensure_node_type(node_type: str):
    """Add ``node_type`` to the stored node types, with its default shape,
    if it is missing: databases from before the type existed lack it."""
    types = NODE_TYPES.get()
    if node_type not in types:
        types.append(node_type)
        NODE_TYPES.set(types)
        sync_shapes_to_types(types)


def add_event_notification(entry: dict):
    """Queue an entry for the next Events Triggered announcement."""
    PENDING_EVENT_NOTIFICATIONS.set(PENDING_EVENT_NOTIFICATIONS.get() + [entry])


@database.atomic
def remove_event_notifications(shown: list):
    """Drop the notifications the announcement showed, and only those.
    One queued while it was open waits for the next announcement."""
    entries = PENDING_EVENT_NOTIFICATIONS.get()
    remaining = [entry for entry in entries if entry not in (shown or [])]
    if len(remaining) != len(entries):
        PENDING_EVENT_NOTIFICATIONS.set(remaining)
