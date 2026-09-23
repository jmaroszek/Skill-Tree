/**
 * Start the Analyze render when the user heads for its tab.
 *
 * Analyze no longer renders at startup. Its charts cost the browser about
 * 0.6 s of main-thread work, and the startup cover waited for them. It
 * renders on the first visit instead. The pointer reaching the tab, or
 * keyboard focus landing on it, is a good sign a visit is coming, so that
 * writes analyze-prewarm-store and the render starts before the click.
 *
 * refresh_analyze_tab skips a render that is still current, so a repeat
 * hover costs one small request. Hovers are throttled, and none are sent
 * while Analyze is already the open tab.
 */
(function () {
    'use strict';

    var LINK_SELECTOR = '#main-tabs .analyze-tab-link';
    var PANE_ID = 'analyze-tab-content';
    var THROTTLE_MS = 2000;
    var lastSent = 0;

    function paneIsOpen() {
        var pane = document.getElementById(PANE_ID);
        return Boolean(pane && pane.style.display !== 'none');
    }

    function onIntent(event) {
        var target = event.target;
        if (!target || typeof target.closest !== 'function') return;
        if (!target.closest(LINK_SELECTOR)) return;
        var now = Date.now();
        if (now - lastSent < THROTTLE_MS || paneIsOpen()) return;
        var clientside = window.dash_clientside;
        if (!clientside || typeof clientside.set_props !== 'function') return;
        lastSent = now;
        clientside.set_props('analyze-prewarm-store', { data: now });
    }

    document.addEventListener('pointerover', onIntent, true);
    document.addEventListener('focusin', onIntent, true);
})();
