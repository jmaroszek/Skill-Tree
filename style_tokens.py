"""Design tokens for Python-built components.

Every name here is a CSS ``var(--st-*)`` *reference*, not a copy of a value.
The values live in ``assets/tokens.css``, which is the single source of truth;
Dash passes ``var(...)`` strings through to the DOM unchanged, so an inline
style dict referencing one of these resolves to exactly what the stylesheets
use. That is the whole point: a color can no longer be "almost" right.

Do not add literal hex or rem values to this module. If a new value is needed,
declare it in ``assets/tokens.css`` and export the reference here.

Badge and tile colors are deliberately NOT here — they live in
``config.BADGE_PALETTE`` and are reached through ``config.badge_style()``.
That palette is user-adjacent (Settings recolors the canvas) and already
served as the app's one working token system; this module is its counterpart
for structural color and typography.
"""

# --- Surfaces: dark chrome layer -------------------------------------------
BG_CANVAS = "var(--st-bg-canvas)"
BG_PANEL = "var(--st-bg-panel)"
BG_RAISED = "var(--st-bg-raised)"
BG_SUNKEN = "var(--st-bg-sunken)"

BORDER_PANEL = "var(--st-border-panel)"
BORDER_SUBTLE = "var(--st-border-subtle)"

# --- Surfaces: light form layer --------------------------------------------
FIELD_BG = "var(--st-field-bg)"
FIELD_FG = "var(--st-field-fg)"
MENU_BG = "var(--st-menu-bg)"
MENU_FG = "var(--st-menu-fg)"
MENU_BORDER = "var(--st-menu-border)"

# --- Text -------------------------------------------------------------------
# TEXT_SECONDARY is what Bootstrap's `.text-muted` class actually resolves to
# under DARKLY. The two are interchangeable by design — prefer the class in
# component code, and this token only where an inline dict is unavoidable.
TEXT_PRIMARY = "var(--st-text-primary)"
TEXT_SECONDARY = "var(--st-text-secondary)"
TEXT_STRONG = "var(--st-text-strong)"
TEXT_SOFT = "var(--st-text-soft)"
TEXT_DIM = "var(--st-text-dim)"
TEXT_FAINT = "var(--st-text-faint)"
TEXT_PLACEHOLDER = "var(--st-text-placeholder)"
TEXT_ON_FIELD = "var(--st-text-on-field)"

# --- Accents ----------------------------------------------------------------
ACCENT = "var(--st-accent)"
DANGER = "var(--st-danger)"
DANGER_TEXT = "var(--st-danger-text)"

# --- Type scale -------------------------------------------------------------
FS_XS = "var(--st-fs-xs)"
FS_SM = "var(--st-fs-sm)"
FS_CAP = "var(--st-fs-cap)"
FS_BASE = "var(--st-fs-base)"
FS_MD = "var(--st-fs-md)"
FS_LG = "var(--st-fs-lg)"
FS_XL = "var(--st-fs-xl)"
FS_2XL = "var(--st-fs-2xl)"

FONT_MONO = "var(--st-font-mono)"

# --- Spacing ----------------------------------------------------------------
# Bootstrap utility classes carry almost all spacing. These two name the
# deliberate off-grid gaps in the Details header; see assets/tokens.css.
SPACE_BLOCK = "var(--st-space-block)"
SPACE_SECTION = "var(--st-space-section)"


# --- Geometry ---------------------------------------------------------------
RADIUS_SM = "var(--st-radius-sm)"
RADIUS = "var(--st-radius)"
SHADOW_PANEL = "var(--st-shadow-panel)"

# --- Inline validation messages ---------------------------------------------
# A field-level error under an input. This exact dict was written out at ten
# call sites (including inside clientside-callback JavaScript strings) with
# stock Bootstrap red, #dc3545 -- brighter than the tamed #c94c4c the app uses
# for every danger button and badge, and than the #ee6666 its own .text-danger
# class defines. Error text now speaks the same red as everything else.
ERROR_TEXT_HIDDEN = {"display": "none", "color": DANGER_TEXT, "fontSize": FS_BASE}
ERROR_TEXT_VISIBLE = {"display": "block", "color": DANGER_TEXT, "fontSize": FS_BASE}

#: The same pair for clientside callbacks, which build style objects in JS.
#: CSS variables resolve in JS-assigned inline styles exactly as they do in a
#: stylesheet, so the JS and Python paths cannot drift.
ERROR_TEXT_JS_HIDDEN = (
    '{display: "none", color: "var(--st-danger-text)", '
    'fontSize: "var(--st-fs-base)"}'
)
ERROR_TEXT_JS_VISIBLE = (
    '{display: "block", color: "var(--st-danger-text)", '
    'fontSize: "var(--st-fs-base)"}'
)


# --- Shared composite styles ------------------------------------------------
# These were module-local constants that each surface re-declared. Promoted so
# the tables/headings that are meant to match actually do.

#: A table cell carrying primary (full-contrast) content.
CELL_PRIMARY = {"verticalAlign": "middle"}

#: A table cell carrying secondary content. Matches `.text-muted`, so a cell
#: using this and a sibling using the class render identically — the bug that
#: made one column of the Events dormant table darker than its neighbours.
CELL_MUTED = {"verticalAlign": "middle", "color": TEXT_SECONDARY}

#: Every data table in the app. One font size, one background treatment.
#: `--bs-table-bg: transparent` drops DARKLY's per-cell tint so the table reads
#: against whatever panel or modal surface it sits on.
TABLE_STYLE = {"fontSize": FS_BASE, "--bs-table-bg": "transparent"}
TABLE_CLASS = "text-light"
TABLE_PROPS = {"bordered": False, "hover": True, "responsive": True, "size": "sm"}

#: Section title used by the Home-tab renderers and the node-editor panels.
SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}

#: Hover tooltip surface. Plotly hoverlabels take the same three colors.
TOOLTIP_STYLE = {
    "position": "fixed",
    "zIndex": 9999,
    "maxWidth": "280px",
    "fontSize": FS_BASE,
    "lineHeight": "1.5",
    "backgroundColor": BG_RAISED,
    "color": TEXT_PRIMARY,
    "borderColor": BORDER_PANEL,
}

#: Standard card surface. `selected=True` swaps to the raised background and
#: the accent border.
def card_style(selected: bool = False) -> dict:
    """Return the standard clickable-card style dict."""
    return {
        "padding": "10px 14px",
        "borderRadius": RADIUS,
        "border": f"2px solid {ACCENT}" if selected else f"1px solid {BORDER_PANEL}",
        "backgroundColor": BG_RAISED if selected else BG_PANEL,
        "cursor": "pointer",
        "transition": "background-color 0.2s",
    }
