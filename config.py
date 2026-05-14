"""
Configuration and persistent settings.

The module holds:
  - Global defaults (DEFAULT_*) used when the DB has no stored value.
  - `ENVIRONMENT` — switched to "sandbox" by app.py when invoked with
    `--sandbox`; determines which SQLite file database.py opens.
  - `ConfigManager` — a classmethod-only gateway to the Settings table
    (a simple key/value JSON store), plus a few semantic helpers
    (rename propagation, hyperparameter profiles, time formatting).

ConfigManager is effectively a singleton: all state lives in SQLite,
so a single import is shared across all callback modules.
"""

import json
from pathlib import Path
from typing import Optional
from database import get_connection
from models import STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE

ENVIRONMENT = "production" # Options: sandbox, production (case sensitive!)

CANVAS_HEIGHT = 760  # Default pixel height of the node canvas area

# --- Tooltip timing (industry standard ~700ms) ---
TOOLTIP_SHOW_DELAY_MS = 700
TOOLTIP_HIDE_DELAY_MS = 100
TOOLTIP_NODE_HIDE_DELAY_MS = 300  # Cytoscape node cursor-tooltip lingers slightly longer to avoid flicker

# --- Toast / banner clear timing ---
TOAST_CLEAR_INTERVAL_MS = 3000
LOCATE_TOAST_CLEAR_INTERVAL_MS = 4000  # Locate-node banner lingers slightly longer

# --- Sidebar geometry ---
# Shared width for the editor (left), goals (left), events (left), and
# filters (right) sidebars. Keep them visually consistent with one knob.
# Anything in JS that closes a sidebar by transform/translate must keep its
# magic number in sync (see assets/editor_sidebar.js, filters_sidebar.js).
SIDEBAR_WIDTH = 350
SIDEBAR_WIDTH_PX = f"{SIDEBAR_WIDTH}px"
SIDEBAR_WIDTH_NEG_PX = f"-{SIDEBAR_WIDTH}px"
SIDEBAR_TRANSLATE_CLOSED = f"translateX(-{SIDEBAR_WIDTH}px)"

DEFAULT_OBSIDIAN_VAULT = r"C:\Users\jonah\Documents\Obsidian"

# Production DB filename. Sandbox mode prepends "sandbox_" at path-resolution time.
DB_FILENAME = "skilltree.db"

# --- Weekly backup script (backup.py, invoked by Windows Task Scheduler) ---
BACKUP_DIR = r'G:\My Drive\Code\Skill Tree'
# Relative to this file so the path stays valid if the project is moved or
# the username changes. Resolves to <project>/data/backup_log.log.
BACKUP_LOG_FILE = str(Path(__file__).parent / 'data' / 'backup_log.log')

DEFAULT_NODE_TYPES = ["Learn", "Action", "Resource"]
DEFAULT_CONTEXTS = [
    "Mind", "Body", "Social", "Life",
    "STEM", "Humanities", "Creation", "Money",
]
DEFAULT_SUBCONTEXTS = {
    "Mind":       ["Sensory", "Rational", "Judgment"],
    "Body":       ["Stress", "Rhythms", "Exercise", "Nutrition"],
    "Social":     ["Dating", "Morality", "Influence", "Relationships"],
    "Life":       ["Fun", "Life Skills", "Productivity", "Satisfaction"],
    "STEM":       ["Math", "Biology", "Physics", "Computers",
                   "Chemistry", "Psychology", "Engineering", "Data Science"],
    "Humanities": ["Art", "History", "Religion", "Literature"],
    "Creation":   ["Music", "Video", "Writing", "Software"],
    "Money":      ["Business", "Economics", "Personal Finance"],
}

# Sort modes for subcontext dropdown menus. 'definition' preserves the
# user-defined order from the Contexts settings textbox; the other modes
# re-order alphabetically or by length.
SUBCONTEXT_SORT_DEFINITION = 'definition'
SUBCONTEXT_SORT_LENGTH = 'length'
SUBCONTEXT_SORT_ALPHABETICAL = 'alphabetical'
SUBCONTEXT_SORT_MODES = (
    SUBCONTEXT_SORT_DEFINITION,
    SUBCONTEXT_SORT_LENGTH,
    SUBCONTEXT_SORT_ALPHABETICAL,
)
DEFAULT_SUBCONTEXT_SORT_MODE = SUBCONTEXT_SORT_DEFINITION

# Sort modes for context dropdown menus. Same three modes as subcontexts.
CONTEXT_SORT_DEFINITION = 'definition'
CONTEXT_SORT_LENGTH = 'length'
CONTEXT_SORT_ALPHABETICAL = 'alphabetical'
CONTEXT_SORT_MODES = (
    CONTEXT_SORT_DEFINITION,
    CONTEXT_SORT_LENGTH,
    CONTEXT_SORT_ALPHABETICAL,
)
DEFAULT_CONTEXT_SORT_MODE = CONTEXT_SORT_DEFINITION


def sort_subcontexts(subs, mode=None):
    """Return a list of subcontexts sorted by the user's configured mode.

    `'definition'` preserves the input order. `'length'` is stable so equal
    lengths keep their definition order. `None` falls back to the live
    ConfigManager value.
    """
    if mode is None:
        mode = ConfigManager.get_subcontext_sort_mode()
    items = list(subs)
    if mode == SUBCONTEXT_SORT_LENGTH:
        return sorted(items, key=len)
    if mode == SUBCONTEXT_SORT_ALPHABETICAL:
        return sorted(items, key=lambda s: s.lower())
    return items


def sort_contexts(ctxs, mode=None):
    """Return a list of contexts sorted by the user's configured mode.

    Mirrors `sort_subcontexts`. `None` falls back to the live ConfigManager value.
    """
    if mode is None:
        mode = ConfigManager.get_context_sort_mode()
    items = list(ctxs)
    if mode == CONTEXT_SORT_LENGTH:
        # "Self" renders visibly narrower than other 4-char contexts (STEM, etc.)
        # in proportional fonts — pin it ahead of same-length peers so the visual
        # order matches a true shortest-first read of the user's actual contexts.
        return sorted(items, key=lambda s: (len(s), 0 if s == 'Self' else 1))
    if mode == CONTEXT_SORT_ALPHABETICAL:
        return sorted(items, key=lambda s: s.lower())
    return items

DEFAULT_DANGER_COLOR = '#c94c4c' # subtle red

DEFAULT_NODE_COLORS = {
    STATUS_BLOCKED: '#dc3545',
    STATUS_OPEN: '#0d6efd',
    STATUS_DONE: '#198754',
    'Goal': '#d3c41d',
    'Action': '#9047b8',
    'Learn': '#0d6efd',
    'Resource': '#17a2b8',
    'Milestone': '#fd7e14',
    'Override': '#e83e8c',
}

DEFAULT_NODE_SHAPES = {
    'Learn': 'ellipse',
    'Action': 'triangle',
    'Goal': 'star',
    'Resource': 'pentagon',
    'Milestone': 'diamond',
}

# Static palette for every non-canvas surface that needs a type/status/
# relationship color: Next-tab priority bars, Details info-pane badges,
# Editor priority strip, subtasks-table tiles. Each entry is (background,
# foreground).
#
# These colors are intentionally DECOUPLED from Settings → Type Colors
# (which drive the Cytoscape canvas). The canvas needs vivid hues to keep
# the network readable; the bars/badges need the same hue identity at a
# quieter register so a screen full of them doesn't fatigue the eye.
#
# Type-color values were tuned by hand from the user's saturated canvas
# palette using a per-hue HSL desaturation (orange and purple respond
# differently to the same delta), then frozen here so future-you doesn't
# have to remember the derivation. To change one: edit the literal hex.
# To re-derive after a canvas-palette swap: `git log -p` this block for
# the original deltas (Learn -25/-10, Action -30/-10, Resource -10/-4,
# Goal/Milestone/Override -20/-7).
#
# STYLE_GUIDE.md is the human-readable source of truth — keep it in sync
# when changing values here.
BADGE_PALETTE = {
    # Type badges — muted variants of the canvas Type Colors.
    'Learn':      ('#1d5cba', '#ffffff'),
    'Action':     ('#bb6823', '#ffffff'),
    'Resource':   ('#814d9e', '#ffffff'),
    'Goal':       ('#cdbe23', '#ffffff'),  # canvas yellow with -5 sat for badge use
    'Priority':   ('#cdbe23', '#ffffff'),  # Priority N suppresses Goal type — share its color
    'Milestone':  ('#2f909d', '#ffffff'),
    'Override':   ('#c516a5', '#ffffff'),
    # Status badges (Open / Done / Blocked) — tuned independently for the
    # subtasks-table status pills and node-info status indicators.
    STATUS_OPEN:       ('#3e61a0', '#ffffff'),
    STATUS_DONE:       ('#148a68', '#ffffff'),
    STATUS_BLOCKED:    ('#9e3838', '#ffffff'),
    # Relationship-priority badges — match the subtasks-table relationship tiles.
    'HardRelPri': ('#2a4d6e', '#d6e0ee'),
    'SoftRelPri': ('#414f5c', '#d0d6dc'),
    # Event-card badges. The three trigger-type labels (Manual, Scheduled,
    # Completion) deliberately share a single neutral pewter — they are
    # peer categories and the text inside the badge already carries the
    # type information, so color would only introduce false hierarchy.
    # EventTriggered shares STATUS_DONE's value so "fired / complete"
    # speaks one vocabulary across the app.
    'EventTrigger':   ('#56575a', '#dcdcdd'),
    'EventTriggered': ('#148a68', '#ffffff'),
}


def _resolved_badge_colors(name: str) -> tuple[str, str]:
    """Return (bg, fg) for a badge by direct lookup in BADGE_PALETTE.

    Unknown names fall back to a neutral gray. The palette is the single
    source of truth — there is no Settings → Type Colors override path.
    """
    return BADGE_PALETTE.get(name, ('#444', '#dee2e6'))


def badge_style(name: str, font_size: str = "0.75rem") -> dict:
    """Return an inline-style dict for a node-info badge with the given name.

    `name` should be a key in `BADGE_PALETTE` (e.g. 'Open', 'Goal',
    'HardRelPri'). Unknown names fall back to a neutral gray.
    """
    bg, fg = _resolved_badge_colors(name)
    return {"backgroundColor": bg, "color": fg, "fontSize": font_size}


# Info-strip rendering: a single rounded container holding multiple
# colored segments side-by-side, separated by subtle vertical dividers.
# Used by the Node Editor priority strip + the Details info pane stack.
# Reads as one compact metadata bar instead of a row of buttons.
INFO_STRIP_CONTAINER_STYLE = {
    "display": "inline-flex",
    "borderRadius": "4px",
    "overflow": "hidden",
    "alignItems": "center",
    "marginBottom": "8px",
}


def info_strip_segment_style(name: str, is_first: bool = False) -> dict:
    """Style dict for one segment of the connected info-strip.

    `name` should be a key in `BADGE_PALETTE`. `is_first=True` skips the
    left divider so the first segment isn't preceded by a vertical line.
    """
    bg, fg = _resolved_badge_colors(name)
    style = {
        "backgroundColor": bg,
        "color": fg,
        "padding": "2px 9px",
        "fontSize": "0.7rem",
        "fontWeight": "600",
        "lineHeight": "1.4",
        "whiteSpace": "nowrap",
    }
    if not is_first:
        style["borderLeft"] = "1px solid rgba(255, 255, 255, 0.18)"
    return style

DEFAULT_TIME_SETTINGS = {
    'hours_per_week': 20,
    'hours_per_month': 80
}

DEFAULT_TIME_ESTIMATE_DEFAULTS = {
    'optimistic': 2,
    'expected': 4,
    'pessimistic': 6,
    'unit': 'weeks',
}

DEFAULT_GRAPH_LAYOUT = {
    'edge_length': 100,
    'gravity': 5,
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
    'bottlenecks': 25,
    'goals': 75,
    'risk': 25,
    'time_sinks': 10,
    'deepest': 10,
    'connected': 10,
}

DEFAULT_RATINGS_DEFINITIONS = [
    {"rating": 1,
     "value": "None: obligatory; I wouldn't do this if I had the choice. No utility, growth, or payoff.",
     "interest": "Averse: I dread this task and have to force myself to start. Relieved when the session is over.",
     "effort": "Unconscious: purely reflexive and automatic. I can do it on autopilot without fatigue."},
    {"rating": 2,
     "value": "Fleeting: a small immediate benefit, but the payoff doesn't stick.",
     "interest": "Reluctant: I don't like this task, but the visceral disgust isn't as sharp as aversion.",
     "effort": "Simple: a light lift using familiar skills. No new learning, no obstacles."},
    {"rating": 3,
     "value": "Minor: slightly improves a small skill, habit, or interest. Limited in scope.",
     "interest": "Boring: monotonous and tedious. Requires discipline to endure, and I procrastinate on it often.",
     "effort": "Straightforward: multiple simple steps. I know what I need to do, I just have to do it."},
    {"rating": 4,
     "value": "Helpful: a meaningful contribution to something I care about. Worth doing if nothing more pressing is on my plate.",
     "interest": "Tolerable: I don't want to do it, but it's not actively painful once I start. Momentum carries me through.",
     "effort": "Moderate: a clear path at the start, but some steps require learning and exertion. Not too challenging."},
    {"rating": 5,
     "value": "Solid: a noticeable improvement to something important.",
     "interest": "Indifferent: no strong feelings either way.",
     "effort": "Involved: several unknowns that require me to learn and grow. A stretch, but within reach."},
    {"rating": 6,
     "value": "Significant: a major boost to a core competency, or a meaningful addition to a general one.",
     "interest": "Curious: the process holds my attention, provokes genuine thought, and is easy to keep going. Rewarding.",
     "effort": "Difficult: requires sustained focus and discipline. I'll succeed as long as I stay locked in and push past my comfort zone."},
    {"rating": 7,
     "value": "Strategic: a lever. Many future opportunities and compounding benefits depend on it.",
     "interest": "Excited: I look forward to the project and enjoy working on it, but I don't think about it much outside of work hours.",
     "effort": "Demanding: considerable overall load. The energy required makes other life areas harder to manage."},
    {"rating": 8,
     "value": "Fundamental: essential to a core pillar of my life. Supports my broader identity and stability.",
     "interest": "Engaged: I frequently choose this over leisure activities, and think about it casually throughout the day.",
     "effort": "Arduous: needs new approaches and considerable effort. May require cutting back elsewhere."},
    {"rating": 9,
     "value": "Transformative: expected to shift my worldview or capabilities entirely.",
     "interest": "Obsessed: I consistently look forward to it and think about it continually. Working on it is a blast. I'm upset when I have to stop.",
     "effort": "Daunting: a deep dive into an uncharted, complex landscape. Requires monumental development. Others would think I'm crazy for trying."},
    {"rating": 10,
     "value": "Spiritual: calls to my soul. Connected to my life's work, filling me with purpose, meaning, and fulfillment.",
     "interest": "Flow: the activity is its own reward. I would do it even if there were no external benefit. I love it, plain and simple.",
     "effort": "Herculean: a massive undertaking bridging multiple difficult domains. Requires immense stamina, adaptability, and sacrifice. Failure is the most probable outcome."},
]

DEFAULT_TITLECASE_EXCLUSIONS = ["a", "an", "or", "not", "with", "the", "but", "and", "vs", "vs.", "at", "of", "are", "as", "is", "in"]

DEFAULT_TITLECASE_LINTER = {
    'enabled': True,
    'exclusions': DEFAULT_TITLECASE_EXCLUSIONS,
}

DEFAULT_SHOW_SCORING_PERF = True

DEFAULT_HYPERPARAMS = {
    'w_v': 1.00,
    'w_i': 1.00,
    'd_H': 0.60,
    'd_S': 0.40,
    'd_Syn_pair': 0.10,
    'd_Syn_mul': 0.40,
    'cross_context_mult': 1.00,
    'w_e': 2.50,
    'w_t': 1.00,
    'beta': 0.85,
    'goal_boost': 1.50,
    'alpha': 0.30,
}

PROFILES = {
    'Sage': DEFAULT_HYPERPARAMS,
    'Explorer': {
        'w_v': 1.00, 'w_i': 1.50, 'd_H': 0.60, 'd_S': 0.40,
        'd_Syn_pair': 0.15, 'd_Syn_mul': 0.60,
        'cross_context_mult': 1.50,
        'w_e': 2.50, 'w_t': 1.00, 'beta': 0.85,
        'goal_boost': 1.50, 'alpha': 0.30,
    },
    'Compounder': {
        'w_v': 1.00, 'w_i': 1.00, 'd_H': 0.80, 'd_S': 0.50,
        'd_Syn_pair': 0.10, 'd_Syn_mul': 0.40,
        'cross_context_mult': 1.00,
        'w_e': 1.50, 'w_t': 0.85, 'beta': 0.70,
        'goal_boost': 1.50, 'alpha': 0.20,
    },
    'Pragmatist': {
        'w_v': 1.50, 'w_i': 1.00, 'd_H': 0.65, 'd_S': 0.20,
        'd_Syn_pair': 0.05, 'd_Syn_mul': 0.25,
        'cross_context_mult': 1.00,
        'w_e': 2.50, 'w_t': 1.50, 'beta': 0.85,
        'goal_boost': 2.50, 'alpha': 0.20,
    },
    'Creator': {
        'w_v': 1.00, 'w_i': 1.00, 'd_H': 0.60, 'd_S': 0.40,
        'd_Syn_pair': 0.25, 'd_Syn_mul': 0.80,
        'cross_context_mult': 2.00,
        'w_e': 2.50, 'w_t': 1.00, 'beta': 0.85,
        'goal_boost': 1.50, 'alpha': 0.30,
    },
    'Glider': {
        'w_v': 1.00, 'w_i': 1.00, 'd_H': 0.45, 'd_S': 0.30,
        'd_Syn_pair': 0.05, 'd_Syn_mul': 0.20,
        'cross_context_mult': 1.00,
        'w_e': 3.50, 'w_t': 4.00, 'beta': 0.95,
        'goal_boost': 1.50, 'alpha': 0.30,
    },
}

class ConfigManager:
    """Classmethod-only facade over the Settings key/value table.

    Every `get_*` reads from SQLite (falling back to a DEFAULT_* constant
    on first run) and every `set_*` writes back. No in-process cache —
    values are round-tripped through the DB on each access, which keeps
    multiple callback modules consistent without coordination.
    """

    @staticmethod
    def _get_db_value(key: str) -> Optional[str]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM Settings WHERE key=?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    def _set_db_value(key: str, value: str):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    @classmethod
    def get_node_types(cls):
        val = cls._get_db_value("NODE_TYPES")
        return json.loads(val) if val else DEFAULT_NODE_TYPES

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
        return json.loads(val) if val else DEFAULT_CONTEXTS

    @classmethod
    def set_contexts(cls, contexts: list):
        cls._set_db_value("CONTEXTS", json.dumps(contexts))

    @classmethod
    def get_subcontexts(cls):
        val = cls._get_db_value("SUBCONTEXTS")
        if not val:
            return DEFAULT_SUBCONTEXTS
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
            return {**DEFAULT_NODE_COLORS, **json.loads(val)}
        return DEFAULT_NODE_COLORS

    @classmethod
    def set_node_colors(cls, colors: dict):
        cls._set_db_value("NODE_COLORS", json.dumps(colors))

    @classmethod
    def get_node_shapes(cls):
        val = cls._get_db_value("NODE_SHAPES")
        return json.loads(val) if val else DEFAULT_NODE_SHAPES

    @classmethod
    def set_node_shapes(cls, shapes: dict):
        cls._set_db_value("NODE_SHAPES", json.dumps(shapes))

    @classmethod
    def get_hyperparams(cls):
        val = cls._get_db_value("HYPERPARAMS")
        return json.loads(val) if val else DEFAULT_HYPERPARAMS

    @classmethod
    def set_hyperparams(cls, params: dict):
        cls._set_db_value("HYPERPARAMS", json.dumps(params))

    @classmethod
    def get_graph_layout_defaults(cls):
        val = cls._get_db_value("GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else DEFAULT_GRAPH_LAYOUT

    @classmethod
    def set_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_details_graph_layout_defaults(cls):
        val = cls._get_db_value("DETAILS_GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else DEFAULT_DETAILS_GRAPH_LAYOUT

    @classmethod
    def set_details_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("DETAILS_GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_events_graph_layout_defaults(cls):
        val = cls._get_db_value("EVENTS_GRAPH_LAYOUT_DEFAULTS")
        return json.loads(val) if val else DEFAULT_EVENTS_GRAPH_LAYOUT

    @classmethod
    def set_events_graph_layout_defaults(cls, params: dict):
        cls._set_db_value("EVENTS_GRAPH_LAYOUT_DEFAULTS", json.dumps(params))

    @classmethod
    def get_analyze_limits(cls):
        val = cls._get_db_value("ANALYZE_LIMITS")
        return json.loads(val) if val else DEFAULT_ANALYZE_LIMITS

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
    def get_time_settings(cls):
        val = cls._get_db_value("TIME_SETTINGS")
        return json.loads(val) if val else DEFAULT_TIME_SETTINGS

    @classmethod
    def set_time_settings(cls, params: dict):
        cls._set_db_value("TIME_SETTINGS", json.dumps(params))

    @classmethod
    def get_time_estimate_defaults(cls):
        val = cls._get_db_value("TIME_ESTIMATE_DEFAULTS")
        return json.loads(val) if val else DEFAULT_TIME_ESTIMATE_DEFAULTS

    @classmethod
    def set_time_estimate_defaults(cls, params: dict):
        cls._set_db_value("TIME_ESTIMATE_DEFAULTS", json.dumps(params))

    @classmethod
    def get_goal_order(cls):
        val = cls._get_db_value("GOAL_ORDER")
        return json.loads(val) if val else []

    @classmethod
    def set_goal_order(cls, order: list):
        cls._set_db_value("GOAL_ORDER", json.dumps(order))

    # One year of productivity = 13 months (≈ 52 weeks) by definition. Built
    # off hours_per_month so a user-tuned monthly rate flows through to years
    # consistently. Not a stored setting — derived on demand.
    HOURS_PER_YEAR_MULT = 13  # × hours_per_month

    @classmethod
    def get_hours_per_year(cls) -> float:
        return cls.HOURS_PER_YEAR_MULT * cls.get_time_settings().get('hours_per_month', 160)

    @classmethod
    def get_time_multiplier(cls, unit: str) -> float:
        """Returns the hours-per-unit multiplier for time input conversion.

        Args:
            unit: 'hours', 'weeks', 'months', or 'years'

        Returns:
            Multiplier to convert from the given unit to hours.
        """
        if unit == 'weeks':
            return cls.get_time_settings().get('hours_per_week', 40.0)
        elif unit == 'months':
            return cls.get_time_settings().get('hours_per_month', 160.0)
        elif unit == 'years':
            return cls.get_hours_per_year()
        return 1.0

    @classmethod
    def format_time_friendly(cls, hours: float | None,
                             force_one_decimal: bool = False) -> str:
        """Format an hour based on user configured time bounds.

        By default, integer values display without a decimal ("1w", "8h").
        Pass `force_one_decimal=True` for tabular displays where decimal
        alignment matters — every value gets exactly one decimal place
        ("1.0w", "8.0h", "0.0h").
        """
        if hours is None or hours <= 0:
            return "0.0h" if force_one_decimal else "0h"

        settings = cls.get_time_settings()
        hw = settings.get('hours_per_week', 40)
        hm = settings.get('hours_per_month', 160)
        hy = cls.HOURS_PER_YEAR_MULT * hm

        if hy > 0 and hours >= hy:
            years = round(hours / hy, 1)
            if years.is_integer() and not force_one_decimal:
                years = int(years)
            return f"{years}y"
        elif hm > 0 and hours >= hm:
            months = round(hours / hm, 1)
            if months.is_integer() and not force_one_decimal:
                months = int(months)
            return f"{months}m"
        elif hw > 0 and hours >= hw:
            weeks = round(hours / hw, 1)
            if weeks.is_integer() and not force_one_decimal:
                weeks = int(weeks)
            return f"{weeks}w"
        else:
            h = round(hours, 1)
            if h.is_integer() and not force_one_decimal:
                h = int(h)
            return f"{h}h"

    @classmethod
    def hours_to_friendly_unit(cls, hours: float) -> tuple:
        """Convert hours to the most logical display unit.

        Returns:
            (converted_value, unit_string) e.g. (2.0, 'weeks')
        """
        if hours is None or hours <= 0:
            return (0, 'hours')
        settings = cls.get_time_settings()
        hw = settings.get('hours_per_week', 40)
        hm = settings.get('hours_per_month', 160)
        hy = cls.HOURS_PER_YEAR_MULT * hm

        if hy > 0 and hours >= hy:
            val = round(hours / hy, 2)
            return (val, 'years')
        elif hm > 0 and hours >= hm:
            val = round(hours / hm, 2)
            return (val, 'months')
        elif hw > 0 and hours >= hw:
            val = round(hours / hw, 2)
            return (val, 'weeks')
        else:
            return (round(hours, 2), 'hours')

    @classmethod
    def get_obsidian_vault(cls, default: Optional[str] = None):
        val = cls._get_db_value("OBSIDIAN_VAULT")
        return val if val else (default or DEFAULT_OBSIDIAN_VAULT)

    @classmethod
    def set_obsidian_vault(cls, path: str):
        cls._set_db_value("OBSIDIAN_VAULT", path)

    @classmethod
    def get_gdrive_path(cls, default: Optional[str] = None):
        val = cls._get_db_value("GDRIVE_ROOT_PATH")
        return val if val else (default or "")

    @classmethod
    def set_gdrive_path(cls, path: str):
        cls._set_db_value("GDRIVE_ROOT_PATH", path)

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
        if val == "Industrious" or val == "Pragmatic":
            cls._set_db_value("HP_PROFILE", "Pragmatist")
            return "Pragmatist"
        if val == "Default":
            cls._set_db_value("HP_PROFILE", "Sage")
            return "Sage"
        if val == "Curious":
            cls._set_db_value("HP_PROFILE", "Explorer")
            return "Explorer"
        if val == "Sprinter":
            cls._set_db_value("HP_PROFILE", "Glider")
            return "Glider"
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

    # --- Filter persistence ---

    # Defaults mirror the clear_filters() callback so persisted state and a
    # fresh "Clear Filters" press converge on the same baseline.
    _FILTER_DEFAULTS = {
        "node_type": [],
        "context": [],
        "subcontext": [],
        "community_method": "components",
        "community": "All",
        "value": 1,
        "interest": 1,
        "difficulty": 10,
        "time": "",
        "time_unit": "hours",
        # Default off (empty list) means done is hidden — opt in via the
        # "Show Done" switch to reveal it. Symmetric with show_dormant below.
        "done": [],
        # When ["show_dormant"], reveal dormant nodes on the main canvas + any
        # surface that runs through filter_nodes (Details tab, etc.). Default
        # empty (off). The events tab graph ignores this filter and always
        # shows its event's dormant nodes.
        "show_dormant": [],
    }

    @classmethod
    def get_remember_filters(cls) -> bool:
        val = cls._get_db_value("REMEMBER_FILTERS")
        if val is None:
            # Default off so a fresh session starts with every filter switch
            # off — consistent with the opt-in framing of "Show Done" /
            # "Show Dormant". User can flip Memory on to retain filters.
            return False
        return val == "1"

    @classmethod
    def set_remember_filters(cls, enabled: bool):
        cls._set_db_value("REMEMBER_FILTERS", "1" if enabled else "0")

    @classmethod
    def get_filters(cls) -> dict:
        val = cls._get_db_value("FILTERS")
        merged = dict(cls._FILTER_DEFAULTS)
        if val:
            try:
                stored = json.loads(val)
                if isinstance(stored, dict):
                    # Migrate legacy "hide_done" persistence to the new
                    # "show_done" semantics. Old: ["hide_done"] = hide done,
                    # [] = show done. New: [] = hide done (default),
                    # ["show_done"] = show done. Strip any legacy "hide_done"
                    # entries — they collapse to [] (the new default), which
                    # preserves the legacy hidden-by-default behavior. Users
                    # who previously had done shown (legacy []) will need to
                    # re-flip the new switch on; the visual default still
                    # matches the most common case.
                    if "done" in stored and isinstance(stored["done"], list):
                        stored["done"] = [v for v in stored["done"] if v == "show_done"]
                    merged.update({k: v for k, v in stored.items() if k in cls._FILTER_DEFAULTS})
            except (ValueError, TypeError):
                pass
        return merged

    @classmethod
    def set_filters(cls, filters: dict):
        merged = dict(cls._FILTER_DEFAULTS)
        merged.update({k: v for k, v in (filters or {}).items() if k in cls._FILTER_DEFAULTS})
        cls._set_db_value("FILTERS", json.dumps(merged))

    # --- Manual Priority Override ---

    @classmethod
    def get_override(cls):
        val = cls._get_db_value("OVERRIDE")
        return json.loads(val) if val else {"parent": None, "mode": "hard"}

    @classmethod
    def set_override(cls, override: dict):
        cls._set_db_value("OVERRIDE", json.dumps(override))

    @classmethod
    def clear_override(cls):
        cls.set_override({"parent": None, "mode": "hard"})

    @classmethod
    def get_override_node_set(cls, manager) -> set:
        """Compute the full set of overridden node names from override parent + mode,
        unioned with any event-override nodes pinned by manual-override event triggers."""
        from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
        override = cls.get_override()
        parent = override.get("parent")
        base: set = set()
        if parent and manager.get_node(parent):
            mode = override.get("mode", "hard")
            if mode == "node_only":
                base = {parent}
            elif mode == "hard":
                base = {parent} | manager.get_goal_subtree(parent, edge_types=(EDGE_NEEDS_HARD,))
            elif mode == "soft":
                base = {parent} | manager.get_goal_subtree(parent, edge_types=(EDGE_NEEDS_SOFT,))
            else:  # "all"
                base = {parent} | manager.get_goal_subtree(parent)
        event_nodes = cls.get_event_override_nodes()
        if event_nodes:
            live = set()
            stale = False
            for n_name in event_nodes:
                node = manager.get_node(n_name)
                if node and node.status != STATUS_DONE:
                    live.add(n_name)
                else:
                    stale = True
            if stale:
                cls.set_event_override_nodes(sorted(live))
            base = base | live
        return base

    # --- Event Override Nodes (pinned by manual-override event triggers) ---

    @classmethod
    def get_event_override_nodes(cls) -> list:
        val = cls._get_db_value("EVENT_OVERRIDE_NODES")
        return json.loads(val) if val else []

    @classmethod
    def set_event_override_nodes(cls, names: list):
        cls._set_db_value("EVENT_OVERRIDE_NODES", json.dumps(list(names)))

    @classmethod
    def add_event_override_nodes(cls, names: list):
        existing = set(cls.get_event_override_nodes())
        existing.update(names)
        cls.set_event_override_nodes(sorted(existing))

    @classmethod
    def clear_event_override_nodes(cls):
        cls.set_event_override_nodes([])

    @classmethod
    def atomic_set_event_override(cls, candidates: list, replace: bool = False) -> None:
        """Atomically clear the parent override and pin event_override_nodes.

        Override parent and event_override_nodes form a single invariant
        ("what's currently pinned"). Writing them as two separate
        _set_db_value calls leaves a window where a crash / disk error
        can produce half-committed state — parent gone but no event pins,
        or stale pins alongside new ones. This method performs both writes
        in one DB transaction.

        replace=False: merge candidates with existing pins (union).
        replace=True: drop existing pins, use only the new candidates.
        """
        if replace:
            new_nodes = sorted(set(candidates))
        else:
            existing = set(cls.get_event_override_nodes())
            existing.update(candidates)
            new_nodes = sorted(existing)

        cleared_override = json.dumps({"parent": None, "mode": "hard"})
        new_event_nodes = json.dumps(list(new_nodes))
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)",
                ("OVERRIDE", cleared_override),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)",
                ("EVENT_OVERRIDE_NODES", new_event_nodes),
            )
            conn.commit()

    @classmethod
    def rename_node_references(cls, old_name: str, new_name: str) -> None:
        """Propagate a node rename to every config entry that stores a node name.

        Called from GraphManager.rename_node so callers don't have to remember
        which config keys hold names — the failure mode when they forget is a
        silent drop (lazy cleanup treats the old name as a deleted node).
        """
        if not old_name or not new_name or old_name == new_name:
            return

        override = cls.get_override()
        if override.get("parent") == old_name:
            override["parent"] = new_name
            cls.set_override(override)

        event_nodes = cls.get_event_override_nodes()
        if old_name in event_nodes:
            updated = [new_name if n == old_name else n for n in event_nodes]
            cls.set_event_override_nodes(updated)

        pg = cls.get_priority_goals()
        if old_name in pg:
            cls.set_priority_goals([new_name if g == old_name else g for g in pg])

    @classmethod
    def delete_node_references(cls, name: str) -> None:
        """Prune every config entry that stores a node name.

        Symmetric to `rename_node_references`. Called from
        GraphManager.delete_node so callers don't each have to remember which
        config keys hold names. Without this, deletes leave dangling
        references that fail silently (priority_goals waste a rank slot,
        override boost applies to nothing, etc.).
        """
        if not name:
            return

        pg = cls.get_priority_goals()
        if name in pg:
            cls.set_priority_goals([g for g in pg if g != name])

        if cls.get_override().get("parent") == name:
            cls.clear_override()

        eon = cls.get_event_override_nodes()
        if name in eon:
            cls.set_event_override_nodes([n for n in eon if n != name])

    @classmethod
    def clear_override_if_parent(cls, name: str) -> bool:
        """Clear the override iff `name` is the current System A parent.

        Returns True if cleared. Used by GraphManager.update_node when a node
        flips to Done so the boost stops applying to its (now-irrelevant)
        dependents.
        """
        if not name:
            return False
        if cls.get_override().get("parent") == name:
            cls.clear_override()
            return True
        return False

    @classmethod
    def has_any_override_active(cls) -> bool:
        """True if System A parent is set OR System B list is non-empty.

        Used to gate conflict prompts: only ONE override set may be active globally,
        so any code path that would introduce a new set must check this first.
        """
        if cls.get_override().get("parent"):
            return True
        return bool(cls.get_event_override_nodes())

    # --- Pending Event Notifications (shown on next app load) ---

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
    def pop_next_override_conflict(cls) -> Optional[dict]:
        """Remove and return the first override_conflict entry, if any."""
        entries = cls.get_pending_event_notifications()
        for i, e in enumerate(entries):
            if e.get("kind") == "override_conflict":
                remaining = entries[:i] + entries[i+1:]
                cls.set_pending_event_notifications(remaining)
                return e
        return None

    @classmethod
    def clear_pending_announcements_only(cls):
        """Remove every informational pending notification, keeping override_conflict entries."""
        entries = cls.get_pending_event_notifications()
        kept = [e for e in entries if e.get("kind") == "override_conflict"]
        cls.set_pending_event_notifications(kept)

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
    def get_danger_color(cls):
        """Returns the tamed danger/red color."""
        return DEFAULT_DANGER_COLOR

    @classmethod
    def get_titlecase_linter(cls) -> dict:
        val = cls._get_db_value("TITLECASE_LINTER")
        if val:
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        return DEFAULT_TITLECASE_LINTER.copy()

    @classmethod
    def set_titlecase_linter(cls, linter: dict):
        cls._set_db_value("TITLECASE_LINTER", json.dumps(linter))

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
    def apply_titlecase_linter(cls, name: str) -> str:
        """Apply titlecase linting to a node name if the linter is enabled."""
        linter = cls.get_titlecase_linter()
        if not linter.get('enabled', True):
            return name
        exclusions = {w.lower() for w in linter.get('exclusions', [])}
        words = name.split()
        result = []
        for i, word in enumerate(words):
            if i == 0:
                result.append(word[0].upper() + word[1:] if word else word)
            elif word.lower() in exclusions:
                result.append(word.lower())
            else:
                result.append(word[0].upper() + word[1:] if word else word)
        return ' '.join(result)

