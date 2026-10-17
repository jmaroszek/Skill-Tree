/** Validate the whole time bracket on section exit, not between its inputs. */
(function () {
    'use strict';
    var pendingExit = null;

    function section() { return document.getElementById('section-time-estimates'); }
    function reveal(ready) {
        var root = section();
        var value = ready ? 'true' : 'false';
        if (!root || root.getAttribute('data-validation-ready') === value) return;
        // Hide immediately, including while an earlier validation request is
        // still returning. Keep the React prop in sync for later renders.
        root.setAttribute('data-validation-ready', value);
        window.dash_clientside.set_props(root.id, {'data-validation-ready': value});
    }
    document.addEventListener('focusin', function (event) {
        var root = section();
        if (!root || !root.contains(event.target)) return;
        clearTimeout(pendingExit);
        reveal(false);
    }, true);
    document.addEventListener('focusout', function (event) {
        var root = section();
        if (!root || !root.contains(event.target)) return;
        clearTimeout(pendingExit);
        pendingExit = setTimeout(function () {
            // relatedTarget can be null (including for native select menus).
            // Wait for the browser's final focus target before deciding.
            if (root.isConnected && !root.contains(document.activeElement)) reveal(true);
        }, 0);
    }, true);
    document.addEventListener('pointerdown', function (event) {
        var root = section();
        // Disabled Save buttons don't take focus. An explicit attempt to
        // leave the section still reveals why that save isn't available.
        if (!root) return;
        if (root.contains(event.target)) reveal(false);
        else if (root.contains(document.activeElement)) reveal(true);
    }, true);
    document.addEventListener('input', function (event) {
        var root = section();
        if (root && root.contains(event.target)) reveal(false);
    }, true);
})();
