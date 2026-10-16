"""The Goals sidebar's layout."""
from dash import html
from skilltree.domain.models import STATUS_BLOCKED
from skilltree.domain.models import STATUS_DONE
from skilltree.domain.models import STATUS_OPEN
from skilltree.ui import tokens
from skilltree.ui.components.duration import format_time_friendly
from skilltree.ui.kit import goal_corner_badge
from skilltree.ui.styles import badge_style
from typing import Any
from typing import List
from typing import Optional
from skilltree.ui.components.list_toolbar import GOALS_SORT
from skilltree.ui.components.list_toolbar import SEARCH_STYLE
from skilltree.ui.components.list_toolbar import build_list_toolbar
from skilltree.ui.kit import add_button
from skilltree.ui.kit import panel_close_button
from skilltree.ui.styles import LOADING_SPINNER_STYLE
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED
from skilltree.ui.styles import SIDEBAR_WIDTH_PX
import dash_bootstrap_components as dbc


def build_goal_card(name: str, status: str, completion: dict, subtask_count: int, is_selected: bool = False, priority_rank: Optional[int] = None,
                    show_order_buttons: bool = False, is_first: bool = False, is_last: bool = False,
                    corner_text: Optional[str] = None, menu_attributes: Optional[dict] = None):
    """Builds a single goal card for the goal sidebar list.

    ``menu_attributes`` are the goal's ``node_menu_attributes``, which give the
    card the shared node context menu on right-click.
    """
    border_style = f"2px solid {tokens.ACCENT}" if is_selected else f"1px solid {tokens.BORDER_PANEL}"

    pct = completion.get("pct", 0)
    total = completion.get("total", 0)
    formatted_time = format_time_friendly(completion.get("remaining_time", 0))

    # A goal is effectively Done if its toggle is on OR all subtasks are complete
    if status == STATUS_DONE or (pct == 100 and total > 0):
        effective_status = STATUS_DONE
    elif completion.get("is_blocked", False):
        effective_status = STATUS_BLOCKED
    else:
        effective_status = STATUS_OPEN

    # status badge uses centralized BADGE_PALETTE (constructed inline below)

    # Drag handle (visible only for non-priority, manual-sort goals)
    drag_handle = html.Span(
        html.I(className="bi bi-list"), className="goal-drag-handle",
        style={"cursor": "grab", "color": tokens.TEXT_DIM, "fontSize": tokens.FS_MD,
               "marginRight": "8px", "userSelect": "none"},
    ) if show_order_buttons else None

    # Top-right indicator: a green "Done" badge for completed goals, otherwise
    # the sort-dependent corner text (priority score / manual rank). Open goals
    # carry no badge under sorts where order is arbitrary (alphabetical).
    _badge_cls = "badge ms-1" if priority_rank is not None else "badge"
    if effective_status == STATUS_DONE:
        corner_badge = html.Span(
            STATUS_DONE, className=_badge_cls,
            style={**badge_style(STATUS_DONE, font_size=tokens.FS_XS),
                   "width": "62px", "textAlign": "center", "display": "inline-block"})
    elif corner_text and priority_rank is None:
        corner_badge = goal_corner_badge(corner_text, STATUS_OPEN, _badge_cls)
    else:
        corner_badge = None

    children: List[Any] = [
        html.Div([
            html.Div([
                drag_handle,
                html.H6(name, className="mb-0", style={"fontWeight": "500"}),
            ], className="d-flex align-items-center"),
            html.Div([
                html.Span(
                    goal_corner_badge(str(priority_rank), "PriorityRank"),
                    className="goal-rank-trigger",
                    role="button", tabIndex=0,
                    **{"data-goal-name": name, "aria-label": f"Set priority for {name}"},
                ) if priority_rank is not None else None,
                corner_badge,
            ], className="d-flex align-items-center ms-2 gap-1"),
        # mb-0, not mb-1: the name and its stats line are one block, and the
        # Small below already carries its own leading. The extra 4px read as a
        # gap between two unrelated things.
        ], className="d-flex align-items-center justify-content-between mb-0"),
    ]

    # Stats line: progress as the share of estimated work done, so a Goal
    # with one big topic left doesn't look nearly finished; the remaining
    # time carries the sense of size.
    if total > 0:
        _sep = "\u00a0\u00a0\u00b7\u00a0\u00a0"
        stats_text = f"{pct}% done{_sep}{formatted_time} left"
    else:
        stats_text = "No subtasks yet"

    children.append(html.Small(stats_text, className="text-muted", style={"fontSize": tokens.FS_SM}))

    return html.Div(children, id={"type": "goal-card", "index": name},
       className="mb-2 goal-card rounded",
       role="button", tabIndex=0,
       **{"data-goal-name": name, **(menu_attributes or {})},
       style={
           "border": border_style,
           "backgroundColor": tokens.BG_RAISED if is_selected else tokens.BG_PANEL,
           "transition": "border-color 0.2s, background-color 0.2s",
           "padding": "10px 14px",
       })


# --- Goals sidebar (left) ---
def goal_list_cover():
    """What the Goals list shows while the sidebar is closed or still building.

    The cards are only mounted while the sidebar is open. Dash re-checks every
    mounted component on each store update, so a list of hidden cards slowed
    every interaction elsewhere, the Details graph's opening animation most
    of all.
    """
    return html.Div([
        dbc.Spinner(spinner_style=LOADING_SPINNER_STYLE),
        html.Div("Preparing your goals…", className="canvas-cover-label"),
    ], className="loading-cover", role="status",
        **{"aria-live": "polite"})  # type: ignore[reportArgumentType]


def build_goals_sidebar():
    """Container Div for the goals overlay (left, closed initially)."""
    return html.Div(
        id="details-goal-sidebar",
        children=[
            html.Div([
                html.Div([
                    html.H4("Goals", className="mb-0"),
                    add_button("btn-goals-sidebar-new", "New goal", large=True),
                ], className="d-flex align-items-center"),
                panel_close_button("btn-details-goals-close", "Close goals sidebar",
                                   large=True),
            ], className="d-flex justify-content-between align-items-center mb-2 mt-2 px-3"),

            build_list_toolbar(
                dbc.Input(id="details-goal-search", type="text",
                          placeholder="Search goals...", size="sm",
                          debounce=False, style=SEARCH_STYLE),
                GOALS_SORT,
            ),

            # The list is built once the open slide finishes and cleared once
            # the close slide does. The first open slides in over this cover;
            # later ones use the remembered list while it is current.
            html.Div(
                goal_list_cover(),
                id="details-goal-list-container",
                style={"overflowY": "auto", "flex": "1", "padding": "0 12px"}),
        ],
        style={
            "position": "absolute",
            "top": "0",
            "left": "0",
            "width": SIDEBAR_WIDTH_PX,
            "height": "100%",
            "zIndex": 100,
            "overflowX": "hidden",
            "overflowY": "auto",
            "borderRight": f"1px solid {tokens.BORDER_PANEL}",
            "transition": "transform 0.3s ease",
            "transform": SIDEBAR_TRANSLATE_CLOSED,
            "willChange": "transform",
            "backgroundColor": tokens.BG_PANEL,
            "display": "flex",
            "flexDirection": "column",
        }
    )
