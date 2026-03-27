import json
from database import get_connection

ENVIRONMENT = "production" # Options: sandbox, production (case sensitive!)

CANVAS_HEIGHT = 760  # Default pixel height of the node canvas area

DEFAULT_OBSIDIAN_VAULT = r"C:\Users\jonah\Documents\Obsidian"

DEFAULT_NODE_TYPES = ["Learn", "Goal", "Habit", "Resource", "Action"]
DEFAULT_CONTEXTS = ["Mind", "Body", "Social"]
DEFAULT_SUBCONTEXTS = {}

DEFAULT_DANGER_COLOR = '#c94c4c' # Tamed red for a calmer dark mode

DEFAULT_NODE_COLORS = {
    'Blocked': '#dc3545',
    'Open': '#0d6efd',
    'Done': '#198754',
}

DEFAULT_NODE_SHAPES = {
    'Learn': 'ellipse',
    'Action': 'triangle',
    'Goal': 'star',
    'Resource': 'pentagon',
    
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
    def _get_db_value(key: str) -> str:
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
        return json.loads(val) if val else DEFAULT_NODE_COLORS

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
    def get_obsidian_vault(cls, default: str = None):
        val = cls._get_db_value("OBSIDIAN_VAULT")
        return val if val else (default or DEFAULT_OBSIDIAN_VAULT)

    @classmethod
    def set_obsidian_vault(cls, path: str):
        cls._set_db_value("OBSIDIAN_VAULT", path)

    @classmethod
    def sync_shapes_to_types(cls, new_types: list):
        """Prune shapes for removed types and add defaults for new types."""
        shapes = cls.get_node_shapes()
        # Remove shapes for types that no longer exist
        shapes = {k: v for k, v in shapes.items() if k in new_types}
        # Add default shape for new types
        for t in new_types:
            if t not in shapes:
                shapes[t] = 'rectangle'
        cls.set_node_shapes(shapes)

    @classmethod
    def get_priority_goals(cls):
        val = cls._get_db_value("PRIORITY_GOALS")
        return json.loads(val) if val else []

    @classmethod
    def set_priority_goals(cls, goals: list):
        cls._set_db_value("PRIORITY_GOALS", json.dumps(goals[:3]))

    @classmethod
    def ensure_action_type(cls):
        """Ensure 'Action' type exists in stored node types (migration for existing DBs)."""
        types = cls.get_node_types()
        if 'Action' not in types:
            types.append('Action')
            cls.set_node_types(types)
            cls.sync_shapes_to_types(types)

    @classmethod
    def get_danger_color(cls):
        """Returns the tamed danger/red color."""
        return DEFAULT_DANGER_COLOR

