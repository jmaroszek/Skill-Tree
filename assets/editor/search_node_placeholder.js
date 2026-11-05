/**
 * The node editor's Search list says what it matches once it opens.
 *
 * The closed field has no hint (the box reads as a plain control). Dash writes
 * its own word, "Search", into the input at the top of the open menu. This
 * swaps that word for the names-and-aliases hint, so the menu says aliases
 * count too. The menu is portaled to the end of <body>, so it is found by the
 * id the trigger points at (aria-controls), not by where it sits in the tree.
 */
(function () {
    var TRIGGER_ID = 'search-node';
    var HINT = 'Search by names and aliases...';

    function sweep() {
        var trigger = document.getElementById(TRIGGER_ID);
        if (!trigger) return;
        var menuId = trigger.getAttribute('aria-controls');
        if (!menuId) return;
        var menu = document.getElementById(menuId);
        if (!menu) return;
        var input = menu.querySelector('.dash-dropdown-search');
        if (input && input.getAttribute('placeholder') !== HINT) {
            input.setAttribute('placeholder', HINT);
        }
    }

    var scheduled = false;
    function scheduleSweep() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(function () {
            scheduled = false;
            sweep();
        });
    }

    // Opening the menu adds it to <body>, and Dash re-renders the input as it
    // filters, so watch for both rather than the one open event.
    document.addEventListener('click', scheduleSweep, true);
    document.addEventListener('keydown', scheduleSweep, true);
    new MutationObserver(scheduleSweep).observe(document.body, { childList: true, subtree: true });
})();
