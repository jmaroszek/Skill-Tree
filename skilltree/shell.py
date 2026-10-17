"""
Layout definitions for the Skill Tree Dash application.
Contains all UI component definitions and the Cytoscape stylesheet.
"""

from skilltree.store import database

from dash import html, dcc
import dash_bootstrap_components as dbc
from skilltree.store import settings
from skilltree.ui.styles import LOADING_SPINNER_STYLE
from skilltree.ui.timing import (
    TOOLTIP_SHOW_DELAY_MS, TOOLTIP_HIDE_DELAY_MS, TOOLTIP_NODE_HIDE_DELAY_MS,
    TOAST_CLEAR_INTERVAL_MS,
)
from skilltree.ui.styles import CANVAS_HEIGHT
from skilltree.features.events.layout import build_events_tab_content, build_add_to_event_modal
from skilltree.features.details.layout import build_details_tab_content
from skilltree.features.settings.layout import build_settings_modal
from skilltree.features.review.layout import build_review_hub_modal
from skilltree.features.analyze.layout import build_analyze_tab_content
from skilltree.features.links.layout import build_bridge_modal
from skilltree.features.home.view import initial_next_view, perf_stats_text
from skilltree.ui.components.context_picker import build_context_picker_support
from skilltree.ui.components.list_toolbar import SORT_MENUS, sort_menu_items
from skilltree.ui import tokens
from skilltree.store.resources import MAX_SECTIONS
from skilltree.ui.kit import (Tooltip)
from skilltree.ui.components.menus import (
    floating_menu, menu_divider,
    menu_heading, menu_item,
    priority_items,
)
from skilltree.features.nodes.layout import create_graph_view
from skilltree.features.home.layout import build_next_view
from skilltree.features.settings.migration import build_migration_modal
from skilltree.features.onboarding.layout import build_welcome_modal
from skilltree.features.editor.layout import (
    build_delete_confirm_modal, build_editor_reopen_confirm_modal,
    build_ratings_editor_modal, build_ratings_popup, build_unsaved_changes_modal,
)
from skilltree.engine.layout import (
    build_auto_done_suggestion_modal, build_group_delete_confirm_modal,
    build_undo_done_confirm_modal,
)
from skilltree.features.links.layout import build_link_reopen_confirm_modal
from skilltree.features.review.layout import (
    build_calibration_review_toast, build_reflection_ratings_editor_modal,
    build_reflection_ratings_popup, build_time_calibration_modal,
)
from skilltree.ui.canvas.tooltip import build_hover_tooltip
from skilltree.features.editor.layout import build_node_editor_sidebar
from skilltree.features.events.layout import build_events_sidebar
from skilltree.features.filters.layout import build_filters_sidebar
from skilltree.features.goals.layout import build_goals_sidebar


# --- Graph View (Canvas only) ---


# --- Next View ---


# --- Migration Modal ---


def build_error_modal():
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Validation Error", className="text-danger")),
        dbc.ModalBody(id="error-modal-body", style={"color": tokens.TEXT_PRIMARY}),
        dbc.ModalFooter(dbc.Button("Close", id="btn-close-error", color="secondary"))
    ], id="modal-error", size="sm", is_open=False, centered=True)


def build_app_error_modal():
    """What the user sees when a callback fails unexpectedly.

    app.report_callback_error opens it. Without it the failed action simply
    didn't happen, with nothing on screen to say so.
    """
    return dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Something went wrong", className="text-danger")),
        dbc.ModalBody(id="app-error-body", style={"color": tokens.TEXT_PRIMARY}),
        dbc.ModalFooter(dbc.Button("Close", id="btn-close-app-error", color="secondary")),
    ], id="modal-app-error", size="sm", is_open=False, centered=True)


# --- Floating Tooltip ---


# --- Floating menus ---
# Every right-click menu and popover is built from these, so a row, divider
# or destructive item can't look different from one menu to the next.
# assets/menus/menus.js gives them the same behavior.


# --- Page template: the startup cover ---
# Dash's default page template, plus a cover that is part of the very first
# paint. The Home tab arrives with the layout, seconds before the app can act
# on it: until the startup callbacks settle, a click could wait behind them or
# be dropped, and the Node Editor's search opened empty. The cover holds all of
# that back, and assets/startup_cover.js lifts it once the app can respond. It
# lives here rather than in the layout so it is on screen before Dash renders
# anything, and so React never re-renders it.
_INDEX_TEMPLATE = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <script>
        (function () {
            var params = new URLSearchParams(location.search);
            var launchToken = params.get('token');
            if (launchToken) {
                sessionStorage.setItem('skilltree_launch_token', launchToken);
                history.replaceState(null, '', location.pathname + location.hash);
            }
            var token = sessionStorage.getItem('skilltree_launch_token');
            if (!token) return;
            var headerName = 'X-Skill-Tree-Token';
            var originalFetch = window.fetch;
            if (originalFetch) {
                window.fetch = function (input, init) {
                    var target = input instanceof Request ? input.url : String(input);
                    if (new URL(target, location.href).origin === location.origin) {
                        var request = new Request(input, init);
                        request.headers.set(headerName, token);
                        return originalFetch.call(this, request);
                    }
                    return originalFetch.apply(this, arguments);
                };
            }
            var originalOpen = XMLHttpRequest.prototype.open;
            var originalSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function (method, url) {
                this._skillTreeOwnOrigin = new URL(url, location.href).origin === location.origin;
                return originalOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function () {
                if (this._skillTreeOwnOrigin) this.setRequestHeader(headerName, token);
                return originalSend.apply(this, arguments);
            };
        })();
        </script>
        {%favicon%}
        {%css%}
    </head>
    <body>
        <div id="startup-cover" class="startup-cover" role="status" aria-live="polite">
            <div class="spinner-border" style="__SPINNER_STYLE__"></div>
            <div class="canvas-cover-label">Getting ready&hellip;</div>
        </div>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


def build_index_string():
    """The page template, with the startup cover drawn like every other cover.

    The spinner takes LOADING_SPINNER_STYLE, as dbc.Spinner does in the canvas
    and panel covers, so a change to it reaches this one too.
    """
    def css_name(prop):
        return "".join(f"-{c.lower()}" if c.isupper() else c for c in prop)

    spinner_style = "; ".join(f"{css_name(prop)}: {value}"
                              for prop, value in LOADING_SPINNER_STYLE.items())
    return _INDEX_TEMPLATE.replace("__SPINNER_STYLE__", spinner_style)


@database.snapshot_read
def build_app_layout(graph, env="production"):
    """Assembles the full application layout with pure Flexbox (Push behavior)."""
    sidebars = build_all_sidebars()
    initial_next = initial_next_view(graph, build_next_view(), sidebars)
    
    edit_trigger = html.Button(id="btn-edit-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})
    toggle_trigger = html.Button(id="btn-toggle-done-node", style={"visibility": "hidden", "width": 0, "height": 0, "position": "absolute"})

    # --- Node context menu: every canvas, Next rows, Now cards, goal cards ---
    # Grouped by intent: Edit; inspection; Set Priority; workflow state;
    # Create Bridge; external links; Delete on its own. context_menu.js
    # relabels the toggles for the node and hides the sections that don't
    # apply: links that aren't set, Set Priority for anything but a single
    # Goal, and Create Bridge for anything but two nodes. So a Goal's menu is
    # every other node's menu plus one section.
    context_menu = floating_menu("node-context-menu", [
        menu_item("Edit", "ctx-menu-edit", icon="pencil"),
        menu_divider(),
        menu_item("View Details", "ctx-menu-details", icon="file-text"),
        menu_item("Explain Priority", "ctx-menu-explain", icon="lightbulb"),
        menu_divider("ctx-menu-priority-divider"),
        html.Div(
            [
                html.I(className="bi bi-flag ctx-menu-icon", **{"aria-hidden": "true"}),
                html.Span("Set Priority", className="ctx-menu-label"),
                html.I(className="bi bi-chevron-right ctx-menu-caret"),
                html.Div(priority_items("ctx-menu-priority"),
                         className="ctx-menu-submenu"),
            ],
            id="ctx-menu-priority",
            className="ctx-menu-item ctx-menu-submenu-parent",
            role="menuitem", tabIndex=-1,
            **{"aria-haspopup": "menu", "aria-expanded": "false"},
        ),
        menu_divider(),
        menu_item("Add to Now", "ctx-menu-toggle-now", icon="play-circle"),
        menu_item("Add to Event…", "ctx-menu-add-to-event", icon="calendar-event"),
        menu_item("Mark Done", "ctx-menu-toggle-done", icon="check-circle"),
        # Shown, with its divider, only when the menu acts on two nodes.
        menu_divider("ctx-menu-bridge-divider"),
        menu_item("Create Bridge…", "ctx-menu-bridge", icon="share"),
        menu_divider("ctx-menu-links-divider"),
        # One slot per possible Resource section; context_menu.js names each
        # after its section and shows only those the node has a link in.
        *[menu_item("Open Resource", f"ctx-menu-resource-{i}", icon="box-arrow-up-right")
          for i in range(MAX_SECTIONS)],
        menu_divider(),
        menu_item("Delete…", "ctx-menu-delete", danger=True, icon="trash3"),
    ])

    # --- Edge context menu: a link on any canvas ---
    # context_menu.js relabels the type toggle and its arrow (Make Soft on a
    # Hard link, Make Hard on a Soft one) and hides it and Reverse on a Synergy, which has
    # neither a strength nor a direction to change.
    edge_context_menu = floating_menu("edge-context-menu", [
        menu_item("Insert Node Here…", "ctx-menu-edge-bridge", icon="share"),
        menu_divider("ctx-menu-edge-change-divider"),
        menu_item("Make Soft", "ctx-menu-edge-type", icon="arrow-down-circle"),
        menu_item("Reverse Direction", "ctx-menu-edge-reverse", icon="arrow-left-right"),
        menu_divider(),
        menu_item("Remove Link", "ctx-menu-edge-remove", danger=True, icon="trash3"),
    ])

    # --- Goal sidebar: rank popover (click a priority goal's rank badge) ---
    goal_rank_popover = floating_menu(
        "goal-rank-popover", priority_items("goal-rank"))

    # --- Events sidebar: right-click context menu ---
    # Same grouping as the node menu. event_context_menu.js hides Trigger Now
    # and its divider for an event that has already triggered.
    event_context_menu = floating_menu("event-context-menu", [
        menu_item("Edit", "event-ctx-edit", icon="pencil"),
        menu_divider("event-ctx-trigger-divider"),
        menu_item("Trigger Now…", "event-ctx-trigger", icon="lightning-charge"),
        menu_divider(),
        menu_item("Delete…", "event-ctx-delete", danger=True, icon="trash3"),
    ])

    # --- Events tab: the Dormant Nodes "+" ---
    # dormant_add_menu.js opens it under the button and writes the choice to
    # dormant-add-choice-input.
    dormant_add_menu = floating_menu("dormant-add-menu", [
        menu_heading("Add to this event"),
        menu_item("New node", "dormant-add-new", icon="plus-lg"),
        menu_item("Existing nodes…", "dormant-add-existing", icon="box-arrow-in-down"),
    ])

    details_add_menu = floating_menu("details-add-menu", [
        menu_heading("Add subtask"),
        menu_item("New node", "details-add-new", icon="plus-lg"),
        menu_item("Existing node…", "details-add-existing", icon="box-arrow-in-down"),
    ])

    # --- Goals / Events sidebars: sort menus (the ⇅ button beside search) ---
    # sort_menu.js opens each under its button and writes the choice to the
    # hidden input; list_toolbar.py moves it into the sort store.
    sort_menus = []
    for sort in SORT_MENUS:
        sort_menus.append(floating_menu(sort.menu_id, [
            menu_heading("Sort by"),
            *[menu_item(label, item_id) for label, item_id in sort_menu_items(sort)],
        ]))
        sort_menus.append(dcc.Input(id=sort.input_id, type='text', value='',
                                    style={'display': 'none'}))

    # --- Tab Navigation (toolbar: left buttons | centered tabs | right buttons) ---
    main_tabs = html.Div([
        # LEFT: Node Editor + Goals + Events (open left-side sidebars)
        html.Div([
            dbc.Button([html.I(className="bi bi-node-plus", **{"aria-hidden": "true"}),
                        html.Span("Node editor", className="visually-hidden")],
                       id="btn-add", color="secondary", size="sm", className="me-2"),
            Tooltip("Node editor", target="btn-add", placement="bottom"),
            dbc.Button([html.I(className="bi bi-star", **{"aria-hidden": "true"}),
                        html.Span("Goals", className="visually-hidden")],
                       id="btn-goals-toggle", color="secondary", size="sm", className="me-2"),
            Tooltip("Goals", target="btn-goals-toggle", placement="bottom"),
            dbc.Button([html.I(className="bi bi-calendar-event", **{"aria-hidden": "true"}),
                        html.Span("Events", className="visually-hidden")],
                       id="btn-events-sidebar-toggle", color="secondary", size="sm"),
            Tooltip("Events", target="btn-events-sidebar-toggle", placement="bottom"),
        ], className="d-flex align-items-center ps-3",
           style={"flex": "0 0 auto"}),

        # CENTER: Tabs
        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-next",
            children=[
                dbc.Tab(label="Home", tab_id="tab-next"),
                dbc.Tab(label="Nodes", tab_id="tab-canvas"),
                dbc.Tab(label="Details", tab_id="tab-details"),
                dbc.Tab(label="Events", tab_id="tab-events"),
                # The class lets assets/analyze/analyze_prewarm.js find the tab.
                dbc.Tab(label="Analyze", tab_id="tab-analyze",
                        label_class_name="analyze-tab-link"),
            ],
            className="px-3 pt-1 justify-content-center",
            style={"flex": "1", "backgroundColor": tokens.BG_CANVAS, "borderBottom": "none"}
        ),

        # RIGHT: Clear Focus + Filters (open right-side sidebar)
        html.Div([
            dbc.Button("Clear Focus", id="btn-clear-focus", color="warning", size="sm",
                       className="me-2", style={"display": "none"}),
            dbc.Button([html.I(className="bi bi-funnel", id="btn-filters-icon",
                               **{"aria-hidden": "true"}),
                        html.Span("Filters", className="visually-hidden")],
                       id="btn-filters-toggle", color="secondary", size="sm"),
            Tooltip("Filters", target="btn-filters-toggle", placement="bottom"),
            dbc.Button([html.I(className="bi bi-journal-text", **{"aria-hidden": "true"}),
                        html.Span("Reflection", className="visually-hidden")], id="btn-calibration-review",
                       color="secondary", size="sm", className="ms-2",
                       style={"display": "none"}),
            Tooltip("Reflection", target="btn-calibration-review", placement="bottom"),
            dbc.Button([html.I(className="bi bi-gear", **{"aria-hidden": "true"}),
                        html.Span("Settings", className="visually-hidden")],
                       id="btn-settings-toggle", color="secondary", size="sm", className="ms-2"),
            Tooltip("Settings", target="btn-settings-toggle", placement="bottom"),
        ], className="main-toolbar-actions d-flex align-items-center pe-3",
           style={"flex": "0 0 auto"}),
    ], id="main-toolbar", className="d-flex align-items-center",
       style={"borderBottom": f"1px solid {tokens.BORDER_PANEL}", "backgroundColor": tokens.BG_CANVAS})

    # --- Canvas Tab Content (existing layout, unchanged) ---
    canvas_tab_content = html.Div(
        id="canvas-tab-content",
        children=[
            # --- MAIN CENTER CONTENT ---
            html.Div(
                style={
                    "flex": "1",
                    "display": "flex",
                    "flexDirection": "column",
                    "minWidth": "0",
                },
                children=[
                    # Canvas Container
                    html.Div(
                        [create_graph_view()],
                        className="flex-grow-1",
                        style={
                            "minHeight": "200px",
                            "position": "relative",
                            "overflow": "hidden"
                        }
                    ),
                ]
            ),

        ],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Events Tab Content (hidden by default) ---
    events_tab_content = html.Div(
        id="events-tab-content",
        children=[build_events_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Home Tab Content (hidden by default) ---
    # The scrollable content lives in its own flex child (minHeight: 0 lets it
    # shrink and own the scrollbar) so next-tab-content itself never scrolls.
    # That keeps its box the fixed size of the viewport, which is what the
    # bottom-right/bottom-left overlays are positioned against — otherwise
    # scrolling the (taller) content also scrolls the overlays out of the
    # visible corner.
    next_tab_content = html.Div(
        id="next-tab-content",
        children=[
            html.Div([
                html.Div([initial_next], className="px-4 pt-3 pb-4"),
            ], style={"flex": "1", "minHeight": "0", "overflowY": "auto"}),
            # Filled here, like the table: the table no longer re-renders on
            # load, and that re-render was this caption's first update.
            html.Div(perf_stats_text(graph), id="next-perf-stats",
                     className="next-perf-overlay"),
        ],
        style={"display": "flex", "width": "100%", "height": "100%", "overflow": "hidden",
               "position": "absolute", "top": "0", "left": "0", "flexDirection": "column",
               "visibility": "visible"}
    )

    # --- Details Tab Content (hidden by default) ---
    details_tab_content = html.Div(
        id="details-tab-content",
        children=[build_details_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%",
               "position": "absolute", "top": "0", "left": "0"}
    )

    # --- Analyze Tab Content (hidden by default) ---
    analyze_tab_content = html.Div(
        id="analyze-tab-content",
        children=[build_analyze_tab_content()],
        style={"display": "none", "width": "100%", "height": "100%", "overflow": "auto",
               "position": "absolute", "top": "0", "left": "0"}
    )

    return html.Div([
        build_hover_tooltip(),
        build_ratings_popup(),
        build_reflection_ratings_popup(),
        edit_trigger,
        toggle_trigger,
        context_menu,
        edge_context_menu,
        goal_rank_popover,
        event_context_menu,
        dormant_add_menu,
        details_add_menu,
        *sort_menus,
        dcc.Input(id='event-ctx-action-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='ctx-obsidian-path-store', data=None),
        dcc.Store(id='ctx-drive-path-store', data=None),
        dcc.Input(id='group-delete-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='group-delete-request-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='group-delete-pending-store', data=None),
        dcc.Input(id='edit-trigger-input', type='text', value='', style={'display': 'none'}),
        # Written by context_menu.js with the two nodes of a bridge (or the
        # edge to insert a node into). bridge_callbacks opens the dialog.
        dcc.Input(id='bridge-open-input', type='text', value='', style={'display': 'none'}),
        # Written by the link menu: an action and the link it applies to.
        # link_menu_callbacks applies it.
        dcc.Input(id='link-action-input', type='text', value='', style={'display': 'none'}),
        # A link menu request waiting on the reopen confirmation.
        dcc.Store(id='link-action-pending-store', data=None),
        # The Save button a save that reopens Done nodes waits to finish with.
        dcc.Store(id='editor-reopen-pending-store', data=None),
        # The dialog's Start and End.
        dcc.Store(id='bridge-modal-store', data=None),
        # The bridge the editor was opened with. populate_editor writes it,
        # and the save that creates the bridge node reads it to remove the
        # link the bridge replaces. Anything that loads the editor clears it.
        dcc.Store(id='bridge-pending-store', data=None),
        dcc.Input(id='toggle-done-trigger-input', type='text', value='', style={'display': 'none'}),
        # Written by dispatch_now_toggle after a direct DB flip of the
        # `now` flag — feeds core_engine so the canvas re-renders to show
        # the new amber border.
        dcc.Input(id='node-now-trigger-input', type='text', value='', style={'display': 'none'}),
        # Written by context-menu "Now" items (canvas + goal sidebar)
        # carrying a JSON list of node names + timestamp. A dedicated callback
        # flips Now for each named node and re-bumps node-now-trigger-
        # input to refresh the canvas.
        dcc.Input(id='toggle-now-trigger-input', type='text', value='', style={'display': 'none'}),
        # Bumped by both the editor dispatcher and the context-menu handler
        # whenever setting Now is refused for hitting the Now cap.
        # show_now_cap_toast listens and pops a transient warning toast.
        dcc.Input(id='now-cap-refused-trigger', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='now-drag-order-input', type='text', value='', style={'display': 'none'}),
        # Transient "Now cap reached" toast — auto-dismisses after 5s.
        # Fixed top-right, anchored just below the tab bar (the row holding
        # the Filters / Calibration / Settings icons sits at ~48px tall, so
        # top:60px clears it with a touch of breathing room). zIndex above
        # context menus (10000–10002).
        dbc.Toast(
            f"{settings.NOW_NODE_CAP.get()} Now nodes is the cap. Clear one to make room.",
            id="now-cap-toast",
            header="Now Cap Reached",
            is_open=False,
            duration=5000,
            dismissable=True,
            icon="warning",
            style={
                "position": "fixed",
                "top": "60px",
                "right": "20px",
                "minWidth": "320px",
                "zIndex": 10010,
            },
        ),
        dcc.Input(id='background-click-input', type='text', value='', style={'display': 'none'}),
        dcc.Store(id='pending-navigation-store', data=None),
        # Written by core_engine only when an editor save commits.
        dcc.Store(id='editor-save-result-store', data=None),
        # A saved link that needs a yes before it opens (resource_links.NeedsConfirmation).
        dcc.ConfirmDialog(id='confirm-open-link', message=''),
        dcc.Store(id='pending-open-link', data=None),
        dcc.Input(id='details-navigate-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='details-explain-trigger-input', type='text', value='', style={'display': 'none'}),
        # Set by context_menu.js when "Add to event…" is clicked. Carries a
        # JSON-encoded list of selected node IDs plus a "|<timestamp>" suffix.
        dcc.Input(id='dormant-existing-trigger-input', type='text', value='', style={'display': 'none'}),
        dcc.Input(id='dormant-add-choice-input', type='text', value='', style={'display': 'none'}),
        html.Div(id='canvas-height-config', style={'display': 'none'}, **{'data-height': str(CANVAS_HEIGHT)}),  # type: ignore[reportArgumentType]
        html.Div(id='tooltip-config', style={'display': 'none'}, **{  # type: ignore[reportArgumentType]
            'data-show': str(TOOLTIP_SHOW_DELAY_MS),
            'data-hide': str(TOOLTIP_HIDE_DELAY_MS),
            'data-node-hide': str(TOOLTIP_NODE_HIDE_DELAY_MS),
        }),
        *build_context_picker_support(),
        build_migration_modal(),
        build_error_modal(),
        build_app_error_modal(),
        build_welcome_modal(),
        build_unsaved_changes_modal(),
        build_bridge_modal(),
        build_delete_confirm_modal(),
        build_undo_done_confirm_modal(),
        build_link_reopen_confirm_modal(),
        build_editor_reopen_confirm_modal(),
        build_add_to_event_modal(),
        build_auto_done_suggestion_modal(),
        build_time_calibration_modal(),
        build_calibration_review_toast(),
        build_review_hub_modal(),
        build_group_delete_confirm_modal(),
        build_ratings_editor_modal(),
        build_reflection_ratings_editor_modal(),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Events Triggered")),
            dbc.ModalBody(id="event-announcements-body"),
            dbc.ModalFooter(dbc.Button("Dismiss", id="btn-event-announcements-dismiss",
                                       color="primary")),
        ], id="modal-event-announcements", is_open=False, centered=True, size="lg"),
        # The notifications the announcement is showing, so closing it drops
        # those and not one queued meanwhile.
        dcc.Store(id="event-announcements-shown", data=None),
        build_settings_modal(),
        dcc.Interval(id='app-load-interval', interval=500, n_intervals=0, max_intervals=1),

        dcc.Store(id='pending-settings-store', data=None),
        dcc.Store(id='migration-mapping-store', data=None),
        dcc.Store(id='freeze-rerender-store', data=False),
        # Intermediate hop for cytoscape elements — core_engine writes here,
        # a clientside callback either applies the delta directly to the cy
        # instance (during freeze) or forwards it to cytoscape-graph.elements
        # (normal operation). See assets/canvas/freeze_positions.js. Details and
        # Events tabs each have their own pending store + freeze store.
        dcc.Store(id='elements-pending-store', data=None),
        dcc.Store(id='details-elements-pending-store', data=None),
        dcc.Store(id='events-elements-pending-store', data=None),
        dcc.Store(id='details-freeze-rerender-store', data=False),
        dcc.Store(id='events-freeze-rerender-store', data=False),
        # Bumped by the bridge callback only when the graph revision
        # advances (i.e. a real node/edge mutation, not a cosmetic filter change).
        # Downstream listeners use this instead of cytoscape-graph.elements to
        # avoid re-firing on cosmetic updates (filter, depth, highlight).
        dcc.Store(id='graph-version-store', data=0),
        # Holds the names the user is about to un-Done while the confirmation
        # modal is open. Read by the modal-confirm callback to perform the
        # actual toggle once the user has acknowledged the downstream impact.
        dcc.Store(id='pending-undo-done-store', data=None),
        # Holds the name of the node awaiting time-calibration input while the
        # modal is open. Read by handle_time_calibration on Submit.
        dcc.Store(id='time-calibration-pending-store', data=None),
        # Queue of Goal/Milestone names whose hard prereqs just became all
        # Done. Drained from the graph manager's auto-Done queue whenever the
        # graph version bumps, then surfaced one at a time by the auto-Done
        # suggestion modal. Persists across modal interactions so chained
        # candidates (parent container becoming ready after the child Goal
        # is marked Done) are queued naturally.
        dcc.Store(id='auto-done-candidates-store', data=[]),
        # A stamp of each Nodes render, written by the clientside bridge that
        # also reports it to the first-paint and startup covers: whether the
        # canvas has loaded, its node count, and when. Server callbacks listen
        # to it instead of the canvas's elements. See callbacks.py.
        dcc.Store(id='canvas-payload-stamp', data=None),
        # Whether a filter narrows the Nodes canvas. Its count overlay and
        # Next's indicator read it.
        dcc.Store(id='canvas-filters-active-store', data=False),
        # Bumped by a clientside filter only when the user opens the Analyze
        # tab. refresh_analyze_tab listens to this instead of main-tabs
        # directly, so switching to any other tab makes no request at all.
        dcc.Store(id='analyze-active-store', data=None),
        # Bumped when the pointer or focus reaches the Analyze tab, so its
        # first render starts before the click. See assets/analyze/analyze_prewarm.js.
        dcc.Store(id='analyze-prewarm-store', data=None),
        # What the rendered Analyze charts were computed from. An arrival that
        # finds it current skips the recompute. See _analyze_signature.
        dcc.Store(id='analyze-rendered-store', data=None),
        dcc.Interval(id='settings-clear-interval', interval=TOAST_CLEAR_INTERVAL_MS, n_intervals=0, disabled=True),

        main_tabs,
        # Tab content wrapper — only one tab visible at a time
        html.Div([
            next_tab_content,
            canvas_tab_content,
            details_tab_content,
            events_tab_content,
            analyze_tab_content,
            # --- Cross-tab sidebar overlays (editor / goals / events / filters) ---
            *sidebars
        ], style={"flex": "1", "overflow": "hidden", "position": "relative"}),
    ], style={"width": "100vw", "height": "100vh", "overflow": "hidden",
              "display": "flex", "flexDirection": "column"})


def build_all_sidebars():
    """The four sidebars that float above every tab, in order: the node
    editor, Goals and Events on the left, Filters on the right.

    The three left sidebars share one slot: opening one closes the others
    (engine/sidebars.py decides). Filters is independent. A tab's own filter
    panel, such as the Details graph's, lives with that tab.
    """
    return [
        build_node_editor_sidebar(),
        build_goals_sidebar(),
        build_events_sidebar(),
        build_filters_sidebar(),
    ]
