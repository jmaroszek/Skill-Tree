/**
 * Clientside toggle for the Filters sidebar.
 *
 * Moved off the server to eliminate the 500ms-2s round-trip that was
 * blocking the CSS transition start. The filters sidebar lives on the
 * right edge and does not overlap the left-side sidebars, so no
 * peer-sidebar mutex is required.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.filters = window.dash_clientside.filters || {};

(function () {
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        right: "0px",
        transform: "translateX(100%)",
        width: "350px",
        height: "100%",
        zIndex: 100,
        overflowX: "hidden",
        overflowY: "auto",
        borderLeft: "1px solid #495057",
        transition: "transform 0.3s ease",
        willChange: "transform",
        backgroundColor: "#212529"
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

    window.dash_clientside.filters.toggle_sidebar = function (_toggleN, _closeN, currentStyle) {
        var NO = window.dash_clientside.no_update;
        var trigger = triggerId();
        if (!trigger) return NO;

        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        var open = currentStyle && (currentStyle.transform
            ? currentStyle.transform === "translateX(0px)" : currentStyle.right === "0px");
        // A refreshed asset can receive the older server's right-based style.
        style.right = BASE_SIDEBAR_STYLE.right;
        style.transition = BASE_SIDEBAR_STYLE.transition;
        style.willChange = BASE_SIDEBAR_STYLE.willChange;

        if (trigger === "btn-filters-toggle") {
            style.transform = open ? "translateX(100%)" : "translateX(0px)";
        } else if (trigger === "btn-close-filters") {
            style.transform = "translateX(100%)";
        } else {
            return NO;
        }

        return style;
    };
})();
