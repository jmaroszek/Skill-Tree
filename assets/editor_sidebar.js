/**
 * Clientside fast-path for opening the Node Editor sidebar on btn-add.
 *
 * core_engine still runs server-side to clear the form, refresh suggestions,
 * and handle close/save/new-node flows. This just kicks off the CSS transform
 * transition before that round-trip completes, making the sidebar feel
 * instant. Both callbacks compute the same open-transform value, so the
 * redundant server write is a no-op after React reconciles.
 *
 * Only listens to btn-add (the unconditional "open + clear form" button).
 * btn-new-node, btn-close-editor, btn-save-close, etc. stay server-only —
 * they need form state (unsaved-changes modal, validation, pending nav).
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.editor = window.dash_clientside.editor || {};

(function () {
    var BASE_SIDEBAR_STYLE = {
        position: "absolute",
        top: "0",
        left: "0",
        width: "380px",
        minWidth: "380px",
        height: "100%",
        zIndex: 1000,
        overflowX: "hidden",
        overflowY: "auto",
        borderRight: "1px solid #495057",
        transition: "transform 0.3s ease",
        transform: "translateX(-380px)",
        willChange: "transform",
        backgroundColor: "#212529"
    };

    window.dash_clientside.editor.open_on_add = function (
        _addN, currentStyle, goalStyle, eventsStyle
    ) {
        var NO = window.dash_clientside.no_update;
        var style = Object.assign({}, BASE_SIDEBAR_STYLE, currentStyle || {});
        style.transform = "translateX(0px)";

        var nextGoal = NO;
        var nextEvents = NO;
        if (goalStyle && (goalStyle.left || "-380px") === "0px") {
            nextGoal = Object.assign({}, goalStyle, { left: "-380px" });
        }
        if (eventsStyle && (eventsStyle.left || "-380px") === "0px") {
            nextEvents = Object.assign({}, eventsStyle, { left: "-380px" });
        }

        return [style, nextGoal, nextEvents];
    };
})();
