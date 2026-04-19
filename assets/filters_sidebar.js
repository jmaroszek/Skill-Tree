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
        right: "-320px",
        width: "320px",
        height: "100%",
        zIndex: 100,
        overflowX: "hidden",
        overflowY: "auto",
        borderLeft: "1px solid #495057",
        transition: "right 0.3s ease",
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

        if (trigger === "btn-filters-toggle") {
            style.right = (style.right || "-320px") === "0px" ? "-320px" : "0px";
        } else if (trigger === "btn-close-filters") {
            style.right = "-320px";
        } else {
            return NO;
        }

        return style;
    };
})();
