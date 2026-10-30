"""How long tooltips wait to show and hide, and how long toasts stay."""

# Tooltip timing (industry standard ~700ms). The show delay reaches
# assets/components/hover_tips.js through #tooltip-config. A tooltip closes
# the moment the pointer leaves.
TOOLTIP_SHOW_DELAY_MS = 700
# The Cytoscape node cursor tooltip lingers slightly longer to avoid flicker.
TOOLTIP_NODE_HIDE_DELAY_MS = 300

# How long a toast or banner stays before it clears.
TOAST_CLEAR_INTERVAL_MS = 3000
# The Locate banner lingers slightly longer.
LOCATE_TOAST_CLEAR_INTERVAL_MS = 4000
