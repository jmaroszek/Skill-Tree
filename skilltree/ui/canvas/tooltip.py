"""The hover tooltip that follows the cursor over any canvas."""
from dash import html
from skilltree.ui import tokens


def build_hover_tooltip():
    return html.Div(
        id="hover-tooltip",
        className="border rounded shadow p-2",
        style={
            "position": "fixed",
            "zIndex": 9999,
            "display": "none",
            "pointerEvents": "none",
            "maxWidth": "280px",
            "fontSize": tokens.FS_BASE,
            "lineHeight": "1.5",
            "backgroundColor": tokens.BG_RAISED,
            "color": tokens.TEXT_PRIMARY,
            "borderColor": tokens.BORDER_PANEL
        }
    )
