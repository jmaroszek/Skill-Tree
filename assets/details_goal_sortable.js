/**
 * Drag-and-drop reordering for goal cards in the Details tab sidebar.
 *
 * Watches #details-goal-list-container for mutations (Dash re-renders),
 * then (re-)initialises a Sortable instance.  On drag-end the new order
 * is written to #details-goal-drag-order-input so Dash can pick it up.
 */

/* ---------- Init / re-init Sortable on the container ---------- */
var _detailsSortableInstance = null;
var _detailsIsDragging = false;

function _initDetailsGoalSortable() {
    var container = document.getElementById('details-goal-list-container');
    if (!container) return;

    // Destroy previous instance if Dash re-rendered the container
    if (_detailsSortableInstance) {
        try { _detailsSortableInstance.destroy(); } catch (_) {}
        _detailsSortableInstance = null;
    }

    // Only enable if SortableJS is loaded
    if (!window.Sortable) {
        setTimeout(_initDetailsGoalSortable, 200);
        return;
    }

    _detailsSortableInstance = new Sortable(container, {
        animation: 150,
        handle: '.goal-drag-handle',       // only drag via the handle
        ghostClass: 'goal-sortable-ghost',
        chosenClass: 'goal-sortable-chosen',
        dragClass: 'goal-sortable-drag',
        onStart: function () {
            _detailsIsDragging = true;
        },
        onEnd: function () {
            _detailsIsDragging = false;

            // Read the new order from DOM data attributes
            var cards = container.querySelectorAll('[data-goal-name]');
            var order = [];
            cards.forEach(function (c) {
                var name = c.getAttribute('data-goal-name');
                if (name) order.push(name);
            });

            // Write to hidden input so Dash picks it up
            var input = document.getElementById('details-goal-drag-order-input');
            if (input) {
                var nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(input, JSON.stringify(order));
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
    });
}

/* ---------- MutationObserver: re-init after every Dash render ---------- */
var _detailsObserver = new MutationObserver(function (mutations) {
    if (_detailsIsDragging) return;
    clearTimeout(_detailsObserver._timer);
    _detailsObserver._timer = setTimeout(_initDetailsGoalSortable, 50);
});

function _startDetailsObserving() {
    var container = document.getElementById('details-goal-list-container');
    if (container) {
        _detailsObserver.observe(container, { childList: true, subtree: false });
        _initDetailsGoalSortable();
    } else {
        setTimeout(_startDetailsObserving, 300);
    }
}

// Kick off once the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startDetailsObserving);
} else {
    _startDetailsObserving();
}
