/**
 * Drag-and-drop reordering for Now cards in the Next tab.
 *
 * Follows the same pattern as event_sortable.js.  Watches a stable
 * ancestor for mutations (Dash re-renders), then (re-)initialises a
 * Sortable instance on #now-cards-container.  On drag-end the new
 * order is written to the hidden #now-drag-order-input so Dash can
 * pick it up.
 */

/* ---------- Helper: set value via native setter so React/Dash sees it ---------- */
function _setNativeValueNow(el, val) {
    var nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
}

/* ---------- Cleanup helper ---------- */
var _nowDragClasses = ['now-sortable-ghost', 'now-sortable-chosen', 'now-sortable-drag', 'now-sortable-fallback'];

function _clearNowDragClasses() {
    var cards = document.querySelectorAll('#now-cards-container .now-card');
    cards.forEach(function (c) {
        c.classList.remove.apply(c.classList, _nowDragClasses);
    });
    // Remove orphaned fallback clones that forceFallback appends to <body>.
    var orphans = document.querySelectorAll('body > .now-sortable-fallback');
    orphans.forEach(function (el) { el.remove(); });
}

/* ---------- Init / re-init Sortable on the container ---------- */
var _nowSortableInstance = null;
var _nowIsDragging = false;
// Track the DOM element the current Sortable is bound to, so we can
// detect when React replaces it with a new element of the same id.
var _nowBoundContainer = null;

function _initNowSortable() {
    var container = document.getElementById('now-cards-container');
    if (!container) {
        _nowSortableInstance = null;
        _nowBoundContainer = null;
        return;
    }

    // If the container element hasn't changed and we already have an
    // instance, there's nothing to do — avoid destroying a working Sortable.
    if (container === _nowBoundContainer && _nowSortableInstance) return;

    // Reset in case a previous drag was in-flight when the DOM changed.
    _nowIsDragging = false;
    _clearNowDragClasses();

    // Destroy previous instance if it exists
    if (_nowSortableInstance) {
        try { _nowSortableInstance.destroy(); } catch (_) {}
        _nowSortableInstance = null;
    }

    if (!window.Sortable) {
        setTimeout(_initNowSortable, 200);
        return;
    }

    _nowBoundContainer = container;

    _nowSortableInstance = new Sortable(container, {
        animation: 150,
        direction: 'horizontal',
        swapThreshold: 0.5,
        // Bypass the native HTML5 drag-and-drop API.  Native drag relies
        // on dragover events for swap detection, which fire inconsistently
        // during slow movements.  Fallback mode uses mousemove instead.
        forceFallback: true,
        fallbackOnBody: true,
        fallbackClass: 'now-sortable-fallback',
        fallbackTolerance: 1,
        ghostClass: 'now-sortable-ghost',
        chosenClass: 'now-sortable-chosen',
        dragClass: 'now-sortable-drag',
        onStart: function () {
            _nowIsDragging = true;
        },
        onEnd: function () {
            _nowIsDragging = false;
            _clearNowDragClasses();

            // Read the new order from DOM data attributes
            var cards = container.querySelectorAll('.now-card[data-node-name]');
            var order = [];
            cards.forEach(function (c) {
                var name = c.getAttribute('data-node-name');
                if (name) order.push(name);
            });

            // Write to hidden input so Dash picks it up
            var input = document.getElementById('now-drag-order-input');
            if (input) {
                _setNativeValueNow(input, JSON.stringify(order));
            }
        }
    });
}

/* ---------- MutationObserver on a stable ancestor ---------- */
// Observing #now-cards-container directly is fragile: when Dash
// re-renders the entire Next tab, React replaces the container element
// itself — the observer ends up watching a detached node and never
// fires again.  Instead, observe the Dash app root (which is never
// replaced) with subtree, and debounce heavily.
var _nowObserver = new MutationObserver(function () {
    if (_nowIsDragging) return;
    clearTimeout(_nowObserver._timer);
    _nowObserver._timer = setTimeout(_initNowSortable, 80);
});

function _startNowObserving() {
    // _app-entry is Dash's outermost stable wrapper div.
    var root = document.getElementById('_dash-app-content')
            || document.getElementById('react-entry-point')
            || document.body;
    _nowObserver.observe(root, { childList: true, subtree: true });
    _initNowSortable();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startNowObserving);
} else {
    _startNowObserving();
}
