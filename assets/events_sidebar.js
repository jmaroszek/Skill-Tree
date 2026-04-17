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
 *   - toggle_sidebar: responds to the three events-sidebar buttons; also
 *     closes editor/goals sidebars when opening (mutex).
 *   - adjust_tab_inner: reflows the events-tab-inner wrapper so content
 *     shifts right when the sidebar is open.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.events = window.dash_clientside.events || {};

(function () {
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        left: "-380px",
        width: "380px",
        height: "100%",
        zIndex: 100,
        overflowX: "hidden",
        overflowY: "auto",
        borderRight: "1px solid #495057",
        transition: "left 0.3s ease",
        backgroundColor: "#212529",
        display: "flex",
        flexDirection: "column"
    };

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

    window.dash_clientside.events.toggle_sidebar = function (
        _toggleN, _closeN, _openN,
        currentStyle, editorStyle, goalStyle, refresh
    ) {
        var NO = window.dash_clientside.no_update;
        var trigger = triggerId();
        if (!trigger) return [NO, NO, NO, NO];

        // Merge BASE with currentStyle so the returned dict is never partial.
        // currentStyle wins where present; BASE fills any missing property.
        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        var nextRefresh = NO;
        var nextEditor = NO;
        var nextGoal = NO;

        function doOpen() {
            style.left = "0px";
            nextRefresh = (refresh || 0) + 1;
            if (editorStyle && editorStyle.transform === "translateX(0px)") {
                nextEditor = Object.assign({}, editorStyle, { transform: "translateX(-380px)" });
            }
            if (goalStyle && (goalStyle.left || "-380px") === "0px") {
                nextGoal = Object.assign({}, goalStyle, { left: "-380px" });
            }
        }

        if (trigger === "btn-events-sidebar-toggle") {
            if ((style.left || "-380px") === "0px") {
                style.left = "-380px";
            } else {
                doOpen();
            }
        } else if (trigger === "btn-open-events-sidebar") {
            doOpen();
        } else if (trigger === "btn-events-sidebar-close") {
            style.left = "-380px";
        } else {
            return [NO, NO, NO, NO];
        }

        return [style, nextRefresh, nextEditor, nextGoal];
    };

    window.dash_clientside.events.adjust_tab_inner = function (sidebarStyle) {
        var isOpen = sidebarStyle && (sidebarStyle.left || "-380px") === "0px";
        return {
            display: "flex",
            flexDirection: "row",
            height: "100%",
            width: isOpen ? "calc(100% - 380px)" : "100%",
            marginLeft: isOpen ? "380px" : "0",
            transition: "margin-left 0.3s ease, width 0.3s ease"
        };
    };
})();
