"""The app's color themes. Settings > Appearance picks one.

The name is the value of ``data-theme`` on the page's root element. Each theme's
CSS values are in assets/css: tokens.css holds Minimal, theme_steel.css the rest.
"""

THEME_MINIMAL = "minimal"
THEME_STEEL = "steel"
THEMES = (THEME_MINIMAL, THEME_STEEL)
DEFAULT_THEME = THEME_MINIMAL
