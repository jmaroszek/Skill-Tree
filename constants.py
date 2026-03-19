"""
Centralized constants for the Skill Tree application.
"""

# --- Node Enumerations ---

NODE_TYPES = ["Goal", "Topic", "Skill", "Habit", "Resource"]
NODE_STATUSES = ["Open", "Blocked", "Done"]
CONTEXTS = ["None", "Mind", "Body", "Social"]

# I think that these might be being ignored by the main script. I saw hardcoded values that did not use these. 
EFFORT_OPTIONS = [
    {"label": "Easy", "value": 1},
    {"label": "Medium", "value": 2},
    {"label": "Hard", "value": 3},
]

# --- Styling Maps ---
NODE_COLORS = {
    'Blocked': '#dc3545',      # Red
    'Open': '#0d6efd',         # Blue
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
# These are fallback values for the algorithm if there is nothing written to the database
# Change the hyperparameters through the UI. The values below are not used if the database has values.
DEFAULT_WN = 5  # Weight for blocked-node unlocks
DEFAULT_WH = 3  # Weight for synergistic Helps connections
