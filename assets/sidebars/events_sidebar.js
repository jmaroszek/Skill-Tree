/**
 * The Events list follows the left panel (assets/sidebars/left_panel.js).
 *
 * The list refresh after opening waits for the slide to finish, so the main
 * thread is free while the sidebar moves.
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
})();
