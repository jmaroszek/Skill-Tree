"""
Shared Cytoscape stylesheet definitions for Cytoscape graph components.
"""
from skilltree.domain.models import STATUS_BLOCKED
from skilltree.domain.models import STATUS_DONE
from skilltree.domain.models import STATUS_OPEN
from skilltree.domain.themes import THEME_ZEN, THEME_STEEL
from skilltree.store import settings

# Badge for nodes whose completion triggers an event: a gold lightning bolt in
# a dark circle. Served from assets/ — Dash exposes this at /assets/ automatically.
_TRIGGER_BADGE_SVG = "/assets/trigger_badge.svg"

# --- Main Cytoscape Stylesheet ---
# Cytoscape can't read a CSS variable, so what a theme changes is listed here.
_CANVAS_COLORS = {
    THEME_ZEN: {'accent': '#889eaa', 'canvas': '#212121', 'edge': '#6a6a6a', 'dormant': '#999999',
                    'synergy': '#889eaa', 'focus': '#889eaa', 'locate': '#d6b64c',
                    'chart': '#6d90aa'},
    THEME_STEEL: {'accent': '#5b86b3', 'canvas': '#1a1d21', 'edge': '#6c757d', 'dormant': '#adb5bd',
                  'synergy': '#5b86b3', 'focus': '#a8bdd3', 'locate': '#cba92b',
                  'chart': '#4a82c2'},
}


def _build_stylesheet(c):
    return [
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
                'text-outline-color': c['canvas'],
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
            # driven separately by assets/canvas/now_pulse.js.
            'selector': '.now',
            'style': {
                'border-width': 3,
                'border-color': c['canvas'],
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
                'border-color': c['dormant'],
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
                'overlay-color': c['focus'],
                'overlay-opacity': 0.22,
                'overlay-padding': 10,
            },
        },
        {
            'selector': 'edge',
            'style': {
                'curve-style': 'bezier',
                'target-arrow-shape': 'triangle',
                'target-arrow-color': c['edge'],
                'line-color': c['edge'],
                'width': 2
            }
        },
        {
            'selector': '[type = "Needs_Hard"]',
            'style': {
                'target-arrow-color': c['edge'],
                'line-color': c['edge'],
                'line-style': 'solid'
            }
        },
        {
            'selector': '[type = "Needs_Soft"]',
            'style': {
                'target-arrow-color': c['edge'],
                'line-color': c['edge'],
                'line-style': 'dashed'
            }
        },
        {
            'selector': '[type = "Helps"]',
            'style': {
                'source-arrow-shape': 'triangle',
                'source-arrow-color': c['synergy'],
                'target-arrow-color': c['synergy'],
                'line-color': c['synergy'],
                'line-style': 'solid'
            }
        },
        {
            'selector': '.locate-pulse',
            'style': {
                'border-width': 8,
                'border-color': c['locate'],
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

# --- Mini Graph Stylesheet
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


def stylesheet():
    """The canvases' stylesheet, in the current theme's colors."""
    return _build_stylesheet(_CANVAS_COLORS[settings.THEME.get()])


def mini_stylesheet():
    """A smaller-node stylesheet, derived from the main one."""
    mini = stylesheet()
    for rule in mini:
        overrides = _MINI_OVERRIDES.get(rule['selector'])
        if overrides:
            rule['style'].update(overrides)
    return mini


# The paths a focus view draws. Bright on purpose, against the dimmed graph.
_FOCUS_PATH_COLORS = {
    THEME_ZEN: {1: '#f63f54', 2: '#41dfb3', 3: '#cc46f2', 4: '#f67b20', 5: '#ef3d70'},
    THEME_STEEL: {1: '#ff1744', 2: '#1de9b6', 3: '#d500f9', 4: '#ff6d00', 5: '#f50057'},
}


def accent_color():
    """The theme's accent as a real color, for what can't read a CSS variable."""
    return _CANVAS_COLORS[settings.THEME.get()]['accent']


def chart_accent_color():
    """The second accent as a real color: the simulation histogram's bars."""
    return _CANVAS_COLORS[settings.THEME.get()]['chart']


def focus_path_colors():
    return _FOCUS_PATH_COLORS[settings.THEME.get()]


# --- Loading spinner ---
# The one spinner every loading cover shows (Nodes canvas, Analyze, Goals sidebar).
LOADING_SPINNER_STYLE = {"width": "2rem", "height": "2rem", "color": "var(--st-spinner)"}


# Colors with no node color behind them: rank numbers, relationships, edges and
# event triggers. Each entry is (background, foreground), and each theme has its
# own. Types and statuses aren't here: bars and badges use the node colors
# (_SETTING_FOR_COLOR), so a color means one thing everywhere.
#
# STYLE_GUIDE.md is the human-readable source of truth. Keep it in sync when
# changing values here.
BADGE_PALETTE = {
    'PriorityRank': ('#b98332', '#ffffff'),
    'PriorityScore': ('#3467a9', '#ffffff'),
    'Unblocking': ('#985984', '#ffffff'),
    'HardRelPri': ('#305170', '#d8e0e8'),
    'SoftRelPri': ('#44515b', '#d4d8da'),
    'EventTrigger':   ('#4d4d4d', '#d1d1d1'),
    'EdgeHard':    ('#305170', '#d8e0e8'),
    'EdgeSoft':    ('#585f67', '#dcdfe1'),
    'EdgeSynergy': ('#476c78', '#d8e4e6'),
    'EdgeSelf':    ('#685f53', '#e4ddd4'),
}

_STEEL_BADGE_PALETTE = {
    # The bare rank number on Goals-sidebar cards and Details suggestions.
    # Darkly's warning orange, deliberately warmer than the Goal yellow.
    'PriorityRank': ('#ca872d', '#ffffff'),
    'PriorityScore': ('#2961bf', '#ffffff'),
    'Unblocking': ('#a73e8e', '#ffffff'),  # steps pinned toward a blocked Now node
    # Relationship-priority badges.
    'HardRelPri': ('#2a4d6e', '#d6e0ee'),
    'SoftRelPri': ('#414f5c', '#d0d6dc'),
    # Event-card badges. The three trigger-type labels (Manual, Scheduled,
    # Completion) deliberately share a single neutral pewter — they are
    # peer categories and the text inside the badge already carries the
    # type information, so color would only introduce false hierarchy.
    'EventTrigger':   ('#56575a', '#dcdcdd'),
    # Edge-relationship colors — the explain modal's contributor chart and
    # its legend. All three sit at similar lightness and are told apart by
    # hue alone. EdgeHard shares HardRelPri's value so the same
    # blue means the same thing app-wide: related to a priority goal via a
    # Hard edge. 'EdgeSelf' is the node itself, off the edge axis entirely.
    'EdgeHard':    ('#2a4d6e', '#d6e0ee'),
    'EdgeSoft':    ('#576068', '#dde0e5'),
    'EdgeSynergy': ('#466a78', '#d8e6e9'),
    'EdgeSelf':    ('#685e52', '#e4ddd4'),  # warm sand
}


_BADGE_PALETTES = {THEME_ZEN: BADGE_PALETTE, THEME_STEEL: _STEEL_BADGE_PALETTE}


def badge_palette():
    """The current theme's palette."""
    return _BADGE_PALETTES[settings.THEME.get()]


# The names that take a node color, and which one. 'Priority' suppresses the Goal
# type, so it shares Goal's. A fired event speaks the same vocabulary as Done.
_SETTING_FOR_COLOR = {
    **{name: name for name in ('Goal', 'Action', 'Learn', 'Resource', 'Milestone', 'Now',
                               STATUS_OPEN, STATUS_DONE, STATUS_BLOCKED)},
    'Priority': 'Goal',
    'EventTriggered': STATUS_DONE,
}


def palette_color(name: str, fallback: str = '#444') -> str:
    """The color of a bar or badge: its node color, or its BADGE_PALETTE value."""
    key = _SETTING_FOR_COLOR.get(name)
    if key is not None:
        return settings.NODE_COLORS.get()[key]
    entry = badge_palette().get(name)
    return entry[0] if entry else fallback


def _resolved_badge_colors(name: str) -> tuple[str, str]:
    """Return (bg, fg) for a badge. Unknown names fall back to a neutral gray.

    The text on a node color is white, whatever the color.
    """
    if name in _SETTING_FOR_COLOR:
        return palette_color(name), '#ffffff'
    return badge_palette().get(name, ('#444', '#d1d1d1'))


def badge_style(name: str, font_size: str = "0.75rem") -> dict:
    """Return an inline-style dict for a node-info badge with the given name.

    `name` is a node type or status, or a key in `BADGE_PALETTE` (e.g. 'Open',
    'Goal', 'HardRelPri'). Unknown names fall back to a neutral gray.
    """
    bg, fg = _resolved_badge_colors(name)
    return {"backgroundColor": bg, "color": fg, "fontSize": font_size}


CANVAS_HEIGHT = 760  # Default pixel height of the node canvas area


# --- Sidebar geometry ---
# Shared width for the editor (left), goals (left), events (left), and
# filters (right) sidebars. Keep them visually consistent with one knob.
# Anything in JS that opens or closes a sidebar must keep its magic number in
# sync (see assets/sidebars/editor_sidebar.js, goals_sidebar.js, events_sidebar.js,
# filters_sidebar.js).
SIDEBAR_WIDTH_PX = "var(--st-sidebar-width)"
