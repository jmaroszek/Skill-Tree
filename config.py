import json
from typing import Optional
from database import get_connection

ENVIRONMENT = "production" # Options: sandbox, production (case sensitive!)

CANVAS_HEIGHT = 760  # Default pixel height of the node canvas area

DEFAULT_OBSIDIAN_VAULT = r"C:\Users\jonah\Documents\Obsidian"

DEFAULT_NODE_TYPES = ["Learn", "Action", "Resource"]
DEFAULT_CONTEXTS = ["Mind", "Body", "Social"]
DEFAULT_SUBCONTEXTS = {}

DEFAULT_DANGER_COLOR = '#c94c4c' # subtle red

DEFAULT_NODE_COLORS = {
    'Blocked': '#dc3545',
    'Open': '#0d6efd',
    'Done': '#198754',
    'Goal': '#ffc107',
    'Action': '#fd7e14',
    'Learn': '#0d6efd',
    'Resource': '#9047b8',
    'Override': '#e83e8c',
}

DEFAULT_NODE_SHAPES = {
    'Learn': 'ellipse',
    'Action': 'triangle',
    'Goal': 'star',
    'Resource': 'pentagon',
    
}

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

DEFAULT_HYPERPARAMS = {
    'w_v': 1.00,
    'w_i': 1.00,
    'd_H': 0.60,
    'd_S': 0.25,
    'd_Syn': 0.35,
    'w_e': 2.50,
    'w_t': 1.00,
    'beta': 0.85,
    'goal_boost': 1.50,
}

PROFILES = {
    'Default': DEFAULT_HYPERPARAMS,
    'Curious': {
        'w_v': 1.00, 'w_i': 1.50, 'd_H': 0.75, 'd_S': 0.35,
        'd_Syn': 0.50, 'w_e': 1.00, 'w_t': 2.50, 'beta': 0.50,
        'goal_boost': 1.50,
    },
    'Industrious': {
        'w_v': 1.50, 'w_i': 1.00, 'd_H': 0.50, 'd_S': 0.15,
        'd_Syn': 0.25, 'w_e': 4.00, 'w_t': 3.00, 'beta': 0.70,
        'goal_boost': 2.00,
    }
}

class ConfigManager:
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

    @classmethod
    def get_time_multiplier(cls, unit: str) -> float:
        """Returns the hours-per-unit multiplier for time input conversion.

        Args:
            unit: 'hours', 'weeks', or 'months'

        Returns:
            Multiplier to convert from the given unit to hours.
        """
        if unit == 'weeks':
            return cls.get_time_settings().get('hours_per_week', 40.0)
        elif unit == 'months':
            return cls.get_time_settings().get('hours_per_month', 160.0)
        return 1.0

    @classmethod
    def format_time_friendly(cls, hours: float | None) -> str:
        """Format an hour based on user configured time bounds"""
        if hours is None or hours <= 0:
            return "0h"
        
        settings = cls.get_time_settings()
        hw = settings.get('hours_per_week', 40)
        hm = settings.get('hours_per_month', 160)
        
        if hm > 0 and hours >= hm:
            months = round(hours / hm, 1)
            if months.is_integer(): months = int(months)
            return f"{months}m"
        elif hw > 0 and hours >= hw:
            weeks = round(hours / hw, 1)
            if weeks.is_integer(): weeks = int(weeks)
            return f"{weeks}w"
        else:
            h = round(hours, 1)
            if h.is_integer(): h = int(h)
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

        if hm > 0 and hours >= hm:
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
        return val if val else "Default"

    @classmethod
    def set_hp_profile(cls, profile: str):
        cls._set_db_value("HP_PROFILE", profile)

    # Types that always keep their shape even if not in the user's type list
    _PERMANENT_SHAPE_TYPES = {'Goal'}

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
                if node and node.status != "Done":
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

