/**
 * The Events list follows the left panel (assets/sidebars/left_panel.js).
 *
 * The list refresh after opening waits for the slide to finish, so the main
 * thread is free to glide the Events tab content alongside it.
 */
// NOTE: SLIDE_MS must match the 0.3s transition on .left-sidebar in theme.css.
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.events = window.dash_clientside.events || {};

(function () {
    var SLIDE_MS = 300;
    var open = false;
    var pendingRefresh = null;

    window.dash_clientside.events.follow_left_panel = function (panel) {
        var nowOpen = panel === 'events';
        if (nowOpen === open) return;
        open = nowOpen;
        clearTimeout(pendingRefresh);
        pendingRefresh = null;
        if (!open) return;
        pendingRefresh = setTimeout(function () {
            pendingRefresh = null;
            window.dash_clientside.set_props("events-ui-refresh-trigger", { data: Date.now() });
        }, SLIDE_MS);
    };

    // The graph panel glides with the rest of the tab, but Cytoscape draws
    // into a fixed-size canvas and nothing watches a container that only
    // changes width. Left alone it keeps rendering at whatever width it had
    // when the tab was last laid out. Settle it once the glide is over:
    // resizing per frame would put a full graph redraw inside the transition,
    // which is the main-thread work the transform-based slide exists to
    // avoid. During the glide the canvas is simply clipped.
    //
    // Delegated to the document because Dash renders its layout after
    // DOMContentLoaded, so #events-tab-inner does not exist at load time.
    // transitionend bubbles, so one listener catches it whenever it appears.
    function refitEventsCanvas() {
        (window.SkillTree.canvases || []).forEach(function (canvas) {
            if (canvas.tabId !== "tab-events") return;
            var el = document.getElementById(canvas.cytoscapeId);
            if (!el || !el.offsetParent) return;
            var cy = window.SkillTree.getCy(el);
            if (cy) cy.resize();
        });
    }

    if (typeof document !== "undefined") {
        document.addEventListener("transitionend", function (evt) {
            if (evt.propertyName !== "width") return;
            if (!evt.target || evt.target.id !== "events-tab-inner") return;
            refitEventsCanvas();
        });
    }
})();
