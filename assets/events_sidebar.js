/**
 * Clientside logic for the global Events sidebar.
 *
 * Replaces a Python callback that repeatedly misbehaved after "open -> select
 * event -> close -> reopen". Running the toggle entirely in the browser
 * eliminates server round-trips as a failure mode and removes the class of
 * bugs caused by state sync between Dash's callback manager and React's
 * reconciliation of the tab-bar button.
 *
 * Two functions:
 *   - toggle_sidebar: responds to the Events sidebar controls and opens
 *     on arrival to the Events tab when its true empty state is visible,
 *     closes on departure from that tab, and closes editor/goals sidebars
 *     when opening (mutex).
 *   - adjust_tab_inner: reflows the events-tab-inner wrapper so content
 *     shifts right when the sidebar is open.
 *
 * The sidebar slides with `transform`, which the browser animates off the
 * main thread. The list refresh after opening waits for the slide to finish,
 * so the main thread is free to glide the Events tab content alongside it.
 */
// NOTE: 350px must match config.SIDEBAR_WIDTH, and SLIDE_MS the 0.3s
// transition in sidebars_layout.py.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.events = window.dash_clientside.events || {};

(function () {
    var OPEN = "translateX(0px)";
    var CLOSED = "translateX(-350px)";
    var SLIDE_MS = 300;
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        left: "0",
        width: "350px",
        height: "100%",
        zIndex: 100,
        overflowX: "hidden",
        overflowY: "auto",
        borderRight: "1px solid #495057",
        transition: "transform 0.3s ease",
        transform: CLOSED,
        willChange: "transform",
        backgroundColor: "#212529",
        display: "flex",
        flexDirection: "column"
    };
    var pendingRefresh = null;
    var lastActiveTab = null;

    function triggerId() {
        // Prefer triggered_id (Dash >= 2.4); fall back to parsing prop_id.
        var cb = window.dash_clientside && window.dash_clientside.callback_context;
        if (!cb) return null;
        if (cb.triggered_id) return cb.triggered_id;
        var t = cb.triggered;
        if (t && t.length > 0 && t[0].prop_id) {
            return t[0].prop_id.split('.')[0];
        }
        return null;
    }

    function isOpen(style) {
        return Boolean(style) && style.transform === OPEN;
    }

    function cancelRefresh() {
        clearTimeout(pendingRefresh);
        pendingRefresh = null;
    }

    // The Events tab content glides aside in step with the sidebar. The
    // detail panel has a fixed width, so each frame only re-lays out the
    // graph panel, which is cheap enough to animate.
    function tabInnerStyle(open) {
        return {
            display: "flex",
            flexDirection: "row",
            height: "100%",
            width: open ? "calc(100% - 350px)" : "100%",
            marginLeft: open ? "350px" : "0",
            transition: "margin-left 0.3s ease, width 0.3s ease"
        };
    }

    window.dash_clientside.events.toggle_sidebar = function (
        _toggleN, _closeN, activeTab,
        currentStyle, editorStyle, goalStyle, refresh, selectedEvent, emptyStyle
    ) {
        var NO = window.dash_clientside.no_update;
        var trigger = triggerId();
        if (!trigger) return [NO, NO, NO, NO];

        // Remember the tab associated with every sidebar interaction. This
        // lets a main-tabs callback distinguish Events -> another tab from an
        // unrelated tab change while preserving the sidebar as a global
        // launcher when the user explicitly opens it elsewhere.
        var previousActiveTab = lastActiveTab;
        lastActiveTab = activeTab;

        // Merge BASE with currentStyle so the returned dict is never partial.
        // currentStyle wins where present; BASE fills any missing property.
        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        var nextEditor = NO;
        var nextGoal = NO;

        function doOpen() {
            style.transform = OPEN;
            cancelRefresh();
            var nextRefresh = (refresh || 0) + 1;
            pendingRefresh = setTimeout(function () {
                pendingRefresh = null;
                window.dash_clientside.set_props("events-ui-refresh-trigger", { data: nextRefresh });
            }, SLIDE_MS);
            if (isOpen(editorStyle)) {
                nextEditor = Object.assign({}, editorStyle, { transform: CLOSED });
            }
            if (isOpen(goalStyle)) {
                nextGoal = Object.assign({}, goalStyle, { transform: CLOSED });
            }
        }

        function doClose() {
            style.transform = CLOSED;
            cancelRefresh();
        }

        if (trigger === "btn-events-sidebar-toggle") {
            if (isOpen(style)) {
                doClose();
            } else {
                doOpen();
            }
        } else if (trigger === "btn-events-sidebar-close") {
            doClose();
        } else if (trigger === "main-tabs") {
            if (previousActiveTab === "tab-events" && activeTab !== "tab-events") {
                if (!isOpen(style)) return [NO, NO, NO, NO];
                doClose();
                return [style, tabInnerStyle(false), nextEditor, nextGoal];
            }

            // selectedEvent is also null while composing a new event, so use
            // the visible empty state to distinguish that draft from a tab
            // that genuinely has nothing useful to show yet.
            var emptyStateVisible = !emptyStyle || emptyStyle.display !== "none";
            if (activeTab !== "tab-events" || selectedEvent || !emptyStateVisible ||
                    isOpen(style)) {
                return [NO, NO, NO, NO];
            }
            doOpen();
        } else {
            return [NO, NO, NO, NO];
        }

        // The tab content is returned here, not left to adjust_tab_inner, so
        // both transitions start in the same frame and the content's edge
        // stays against the sidebar's for the whole glide.
        return [style, tabInnerStyle(isOpen(style)), nextEditor, nextGoal];
    };

    // Follows every other writer of the sidebar style, like the Goals and
    // editor toggles closing it. For this file's own toggle it repeats the
    // style already returned, which changes nothing.
    window.dash_clientside.events.adjust_tab_inner = function (sidebarStyle) {
        return tabInnerStyle(isOpen(sidebarStyle));
    };
})();
