/**
 * Clientside fast-path for the Node Editor toolbar toggle (btn-add).
 *
 * btn-add toggles the editor open/closed, preserving the loaded node (like the
 * Goals/Events toggles). This fast-path handles only the OPEN half: when the
 * editor is closed it kicks off the reveal transition before core_engine's
 * round-trip completes, so opening feels instant. core_engine computes the same
 * open-transform server-side, so the redundant write is a no-op after React
 * reconciles.
 *
 * The CLOSE half is deferred to the server: closing must run the same
 * unsaved-changes guard as btn-close-editor (toggle_unsaved_modal +
 * _compute_sidebar_styles), which the browser can't evaluate. So when the
 * editor is already open we return no_update and let core_engine decide.
 *
 * btn-editor-new, btn-new-node, btn-close-editor, btn-save-close, etc. stay
 * server-only — they need form state (unsaved-changes modal, validation,
 * pending nav).
 */
// NOTE: 350px must match config.SIDEBAR_WIDTH on the Python side. If you
// change the sidebar width, update both. Same applies to filters_sidebar.js.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.editor = window.dash_clientside.editor || {};

(function () {
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        left: "0",
        width: "350px",
        minWidth: "350px",
        height: "100%",
        zIndex: 1000,
        overflowX: "hidden",
        overflowY: "auto",
        borderRight: "1px solid #495057",
        transition: "transform 0.3s ease",
        transform: "translateX(-350px)",
        willChange: "transform",
        backgroundColor: "#212529"
    };

    window.dash_clientside.editor.open_on_add = function (
        _addN, currentStyle, goalStyle, eventsStyle
    ) {
        var NO = window.dash_clientside.no_update;

        // Already open → this click is a toggle-close. Defer to the server so the
        // unsaved-changes guard can run; don't touch styles here.
        if (currentStyle && currentStyle.transform === "translateX(0px)") {
            return [NO, NO, NO];
        }

        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        style.transform = "translateX(0px)";

        var nextGoal = NO;
        var nextEvents = NO;
        if (goalStyle && (goalStyle.left || "-350px") === "0px") {
            nextGoal = Object.assign({}, goalStyle, { left: "-350px" });
        }
        if (eventsStyle && (eventsStyle.left || "-350px") === "0px") {
            nextEvents = Object.assign({}, eventsStyle, { left: "-350px" });
        }

        return [style, nextGoal, nextEvents];
    };
})();
