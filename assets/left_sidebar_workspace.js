/**
 * Projection for the desktop workspace beside the mutually-exclusive left
 * sidebars. The sidebar callbacks own which panel is open; this module owns
 * only how much room that visible panel reserves for tab content.
 *
 * Keeping the projection separate makes a handoff safe: an opening callback
 * puts its incoming sidebar in view before (or alongside) closing its peer,
 * so this function never releases the workspace during a sidebar-to-sidebar
 * transition.
 */
// NOTE: 350px must match config.SIDEBAR_WIDTH and the inline sidebar styles.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.leftSidebar = window.dash_clientside.leftSidebar || {};

(function () {
    var OPEN = "translateX(0px)";
    var WIDTH = "350px";

    function isOpen(style) {
        return Boolean(style) && style.transform === OPEN;
    }

    function workspaceStyle(reserved) {
        return {
            position: "relative",
            height: "100%",
            width: reserved ? "calc(100% - 350px)" : "100%",
            marginLeft: reserved ? WIDTH : "0",
            overflow: "hidden",
            transition: "margin-left 0.3s ease, width 0.3s ease",
            willChange: "margin-left, width"
        };
    }

    window.dash_clientside.leftSidebar.workspace_style = function (
        editorStyle, goalStyle, eventsStyle
    ) {
        return workspaceStyle(
            isOpen(editorStyle) || isOpen(goalStyle) || isOpen(eventsStyle)
        );
    };
})();
