/**
 * Clientside toggle for the Goals sidebar.
 *
 * Moved off the server to eliminate the ~50-150ms round-trip on each
 * open/close. Mirrors the events_sidebar.js pattern: on open, closes
 * peer left-side sidebars (editor, events) via the sidebar mutex, and
 * bumps details-refresh-trigger so render_goal_list rebuilds the card list.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.goals = window.dash_clientside.goals || {};

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
        var cb = window.dash_clientside && window.dash_clientside.callback_context;
        if (!cb) return null;
        if (cb.triggered_id) return cb.triggered_id;
        var t = cb.triggered;
        if (t && t.length > 0 && t[0].prop_id) {
            return t[0].prop_id.split('.')[0];
        }
        return null;
    }

    window.dash_clientside.goals.toggle_sidebar = function (
        _toggleN, _closeN,
        currentStyle, editorStyle, eventsStyle, refresh
    ) {
        var NO = window.dash_clientside.no_update;
        var trigger = triggerId();
        if (!trigger) return [NO, NO, NO, NO];

        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        var nextRefresh = NO;
        var nextEditor = NO;
        var nextEvents = NO;

        function doOpen() {
            style.left = "0px";
            nextRefresh = (refresh || 0) + 1;
            if (editorStyle && editorStyle.transform === "translateX(0px)") {
                nextEditor = Object.assign({}, editorStyle, { transform: "translateX(-380px)" });
            }
            if (eventsStyle && (eventsStyle.left || "-380px") === "0px") {
                nextEvents = Object.assign({}, eventsStyle, { left: "-380px" });
            }
        }

        if (trigger === "btn-goals-toggle") {
            if ((style.left || "-380px") === "0px") {
                style.left = "-380px";
            } else {
                doOpen();
            }
        } else if (trigger === "btn-details-goals-close") {
            style.left = "-380px";
        } else {
            return [NO, NO, NO, NO];
        }

        return [style, nextRefresh, nextEditor, nextEvents];
    };
})();
