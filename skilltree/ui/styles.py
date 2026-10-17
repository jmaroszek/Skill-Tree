"""
Shared Cytoscape stylesheet definitions for Cytoscape graph components.
"""
from skilltree.domain.models import STATUS_BLOCKED
from skilltree.domain.models import STATUS_DONE
from skilltree.domain.models import STATUS_OPEN
from skilltree.store import settings

# Badge for nodes whose completion triggers an event: a gold lightning bolt in
# a dark circle. Served from assets/ — Dash exposes this at /assets/ automatically.
_TRIGGER_BADGE_SVG = "/assets/trigger_badge.svg"

# --- Main Cytoscape Stylesheet ---
stylesheet = [
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'background-color': 'data(color)',
            'shape': 'data(shape)',
            'color': '#fff',
            'text-outline-width': 2,
            'text-outline-color': '#1a1d21',
            'width': 60,
            'height': 60,
            'text-max-width': '200px',
            'text-wrap': 'ellipsis',
        }
    },
    {
        # Now flag: nodes the user is currently working on. An amber ring
        # outside the node, parted from its fill by a gap in the canvas
        # color, so it reads on any fill: a yellow Goal took a border in
        # the same yellow as its own. Placed BEFORE :selected, whose white
        # border replaces the gap while the ring stays. The color is sourced
        # per-element via data(now_color) so the settings-modal color picker
        # can change it without restyling the canvas. The pulse animation is
        # driven separately by assets/now_pulse.js.
        'selector': '.now',
        'style': {
            'border-width': 3,
            'border-color': '#1a1d21',
            'border-opacity': 1,
            'outline-width': 5,
            'outline-color': 'data(now_color)',
            'outline-opacity': 1,
        }
    },
    {
        # Dormant: muted ghost effect with a high-contrast dashed border.
        # Keep this before :selected so a clicked dormant node receives the
        # same white selection outline as every other node. Reduced opacity
        # still reads as "asleep / not part of the live workspace".
        'selector': '.dormant',
        'style': {
            'border-width': 2,
            'border-color': '#adb5bd',
            'border-style': 'dashed',
            'outline-width': 0,
            'opacity': 0.6,
        }
    },
    {
        # Selection indicator: thick white border, no background override.
        # Previously used cyan #0dcaf0 as the bg, which clashed with the
        # Milestone type color (teal #17a2b8) — the two looked nearly
        # identical. A border-only indicator works regardless of the
        # node's underlying type color and avoids future clashes.
        'selector': 'node:selected',
        'style': {
            'border-width': 5,
            'border-color': '#ffffff',
            'border-style': 'solid',
            'border-opacity': 1,
        }
    },
    {
        'selector': 'node.keyboard-current',
        'style': {
            # Focus sits outside the node; the white selection border remains
            # independently visible when focus moves to another node.
            'overlay-color': '#0dcaf0',
            'overlay-opacity': 0.22,
            'overlay-padding': 10,
        },
    },
    {
        'selector': 'edge',
        'style': {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#666',
            'line-color': '#666',
            'width': 2
        }
    },
    {
        'selector': '[type = "Needs_Hard"]',
        'style': {
            'target-arrow-color': '#6c757d',
            'line-color': '#6c757d',
            'line-style': 'solid'
        }
    },
    {
        'selector': '[type = "Needs_Soft"]',
        'style': {
            'target-arrow-color': '#6c757d',
            'line-color': '#6c757d',
            'line-style': 'dashed'
        }
    },
    {
        'selector': '[type = "Helps"]',
        'style': {
            'source-arrow-shape': 'triangle',
            'source-arrow-color': '#0d6efd',
            'target-arrow-color': '#0d6efd',
            'line-color': '#0d6efd',
            'line-style': 'solid'
        }
    },
    {
        'selector': '.locate-pulse',
        'style': {
            'border-width': 8,
            'border-color': '#ffd000',
            'border-opacity': 1,
            'z-index': 9999,
        }
    },
    {
        'selector': '.trigger',
        'style': {
            'background-image': _TRIGGER_BADGE_SVG,
            'background-fit': 'none',
            'background-clip': 'none',
            'background-width': '32%',
            'background-height': '32%',
            'background-position-x': '100%',
            'background-position-y': '0%',
        }
    },
]

# --- Mini Graph Stylesheet (smaller nodes for embedded views) ---
# Derived from the main stylesheet with node/edge size overrides.

_MINI_OVERRIDES = {
    'node': {
        'text-outline-width': 1,
        'font-size': 10,
        'width': 40,
        'height': 40,
    },
    'node:selected': {
        'border-width': 3,
    },
    'edge': {
        'width': 1.5,
    },
}


def _build_mini_stylesheet():
    """Derive a smaller-node stylesheet from the main stylesheet."""
    import copy
    mini = copy.deepcopy(stylesheet)
    for rule in mini:
        overrides = _MINI_OVERRIDES.get(rule['selector'])
        if overrides:
            rule['style'].update(overrides)
    return mini


mini_stylesheet = _build_mini_stylesheet()

# --- Event graph stylesheet ---
# The .dormant rule now lives on the base stylesheet so all canvases
# (main, details, events) render dormant nodes consistently. Kept as a
# separate alias for any future events-only style overrides.
events_graph_stylesheet = stylesheet


# --- Loading spinner ---
# The one spinner every loading cover shows (Nodes canvas, Analyze, Goals sidebar).
LOADING_SPINNER_STYLE = {"width": "2rem", "height": "2rem", "color": "#1e90ff"}


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
# Goal/Milestone/Unblocking -20/-7).
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
    # The bare rank number on Goals-sidebar cards and Details suggestions.
    # Darkly's warning orange, deliberately warmer than the Goal yellow.
    'PriorityRank': ('#f39c12', '#ffffff'),
    'Milestone':  ('#2f909d', '#ffffff'),
    'Unblocking': ('#c516a5', '#ffffff'),  # steps pinned toward a blocked Now node
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
    # Edge-relationship tiles — the subtasks-table relationship column and the
    # explain modal's contributor chart. All three sit at similar lightness and
    # are told apart by hue alone. EdgeHard shares HardRelPri's value so the
    # same blue means the same thing app-wide: related to a priority goal via a
    # Hard edge. 'EdgeSelf' is the node itself, off the edge axis entirely.
    #
    # These were previously duplicated as details_layout._REL_BADGE_STYLES and
    # details/explain._VIA_COLORS, kept in sync by comments alone.
    'EdgeHard':    ('#2a4d6e', '#d6e0ee'),
    'EdgeSoft':    ('#576068', '#dde0e5'),
    'EdgeSynergy': ('#466a78', '#d8e6e9'),
    'EdgeSelf':    ('#685e52', '#e4ddd4'),  # warm sand
}


def _resolved_badge_colors(name: str) -> tuple[str, str]:
    """Return (bg, fg) for a badge by direct lookup in BADGE_PALETTE.

    Unknown names fall back to a neutral gray. The palette is the single
    source of truth for all badges EXCEPT 'Now' — that one is
    intentionally coupled to the user-configurable canvas color so the
    border on the canvas and the badge in the Details panel stay visually
    consistent under a custom color choice.
    """
    if name == 'Now':
        bg = settings.NODE_COLORS.get().get('Now', '#ffd000')
        return (bg, '#ffffff')
    return BADGE_PALETTE.get(name, ('#444', '#dee2e6'))


def badge_style(name: str, font_size: str = "0.75rem") -> dict:
    """Return an inline-style dict for a node-info badge with the given name.

    `name` should be a key in `BADGE_PALETTE` (e.g. 'Open', 'Goal',
    'HardRelPri'). Unknown names fall back to a neutral gray.
    """
    bg, fg = _resolved_badge_colors(name)
    return {"backgroundColor": bg, "color": fg, "fontSize": font_size}


CANVAS_HEIGHT = 760  # Default pixel height of the node canvas area


# --- Sidebar geometry ---
# Shared width for the editor (left), goals (left), events (left), and
# filters (right) sidebars. Keep them visually consistent with one knob.
# Anything in JS that opens or closes a sidebar must keep its magic number in
# sync (see assets/editor_sidebar.js, goals_sidebar.js, events_sidebar.js,
# filters_sidebar.js).
SIDEBAR_WIDTH = 350
SIDEBAR_WIDTH_PX = f"{SIDEBAR_WIDTH}px"


# The left sidebars (editor, goals, events) slide with `transform` rather than
# `left`. The browser runs a transform animation off the main thread, so the
# slide stays smooth while the page is busy mounting the sidebar's contents.
SIDEBAR_TRANSLATE_CLOSED = f"translateX(-{SIDEBAR_WIDTH}px)"
