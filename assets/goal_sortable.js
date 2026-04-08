/**
 * Drag-and-drop reordering for goal cards using SortableJS.
 *
 * Watches #goals-list-container for mutations (Dash re-renders), then
 * (re-)initialises a Sortable instance.  On drag-end the new order is
 * written to the hidden #goal-drag-order-input so Dash can pick it up.
 */

/* ---------- Load SortableJS from CDN ---------- */
(function () {
    if (window.Sortable) return;           // already loaded
    var s  = document.createElement('script');
    s.src  = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js';
    s.async = false;
    document.head.appendChild(s);
})();

/* ---------- Helper: set value via native setter so React/Dash sees it ---------- */
function _setNativeValue(el, val) {
    var nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
}

/* ---------- Init / re-init Sortable on the container ---------- */
var _sortableInstance = null;

function _initGoalSortable() {
    var container = document.getElementById('goals-list-container');
    if (!container) return;

    // Destroy previous instance if Dash re-rendered the container
    if (_sortableInstance) {
        try { _sortableInstance.destroy(); } catch (_) {}
        _sortableInstance = null;
    }

    // Only enable if SortableJS is loaded
    if (!window.Sortable) {
        setTimeout(_initGoalSortable, 200);
        return;
    }

    _sortableInstance = new Sortable(container, {
        animation: 150,
        handle: '.goal-drag-handle',       // only drag via the handle
        ghostClass: 'goal-sortable-ghost',
        chosenClass: 'goal-sortable-chosen',
        dragClass: 'goal-sortable-drag',
        onEnd: function () {
            // Read the new order from DOM data attributes
            var cards = container.querySelectorAll('[data-goal-name]');
            var order = [];
            cards.forEach(function (c) {
                var name = c.getAttribute('data-goal-name');
                if (name) order.push(name);
            });

            // Write to hidden input so Dash picks it up
            var input = document.getElementById('goal-drag-order-input');
            if (input) {
                _setNativeValue(input, JSON.stringify(order));
            }
        }
    });
}

/* ---------- MutationObserver: re-init after every Dash render ---------- */
var _observer = new MutationObserver(function (mutations) {
    // Debounce: only re-init once per render cycle
    clearTimeout(_observer._timer);
    _observer._timer = setTimeout(_initGoalSortable, 50);
});

function _startObserving() {
    var container = document.getElementById('goals-list-container');
    if (container) {
        _observer.observe(container, { childList: true, subtree: false });
        _initGoalSortable();
    } else {
        setTimeout(_startObserving, 300);
    }
}

// Kick off once the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startObserving);
} else {
    _startObserving();
}
