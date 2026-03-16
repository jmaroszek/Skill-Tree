"""
Centralized constants for the Skill Tree application.
Single source of truth for all enumerations, styling maps, and default values.
"""

# --- Node Enumerations ---

NODE_TYPES = ["Goal", "Topic", "Skill", "Habit", "Resource"]

NODE_STATUSES = ["Open", "Blocked", "In Progress", "Done"]

CONTEXTS = ["None", "Mind", "Body", "Social", "Action"]

EFFORT_OPTIONS = [
    {"label": "Easy", "value": 1},
    {"label": "Medium", "value": 2},
    {"label": "Hard", "value": 3},
]

# --- Styling Maps ---

NODE_COLORS = {
    'Blocked': '#dc3545',      # Red
    'Open': '#0d6efd',         # Blue
    'In Progress': '#ffc107',  # Yellow
    'Done': '#198754',         # Green
}

NODE_SHAPES = {
    'Goal': 'star',
    'Topic': 'ellipse',
    'Skill': 'triangle',
    'Habit': 'diamond',
    'Resource': 'pentagon',
}

# --- Algorithm Defaults ---

DEFAULT_WN = 2.0  # Weight for blocked-node unlocks
DEFAULT_WH = 1.0  # Weight for synergistic Helps connections
