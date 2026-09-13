/**
 * Drag-and-drop reordering for event cards using SortableJS.
 *
 * Watches #events-list-container for mutations (Dash re-renders), then
 * (re-)initialises a Sortable instance per card group.  On drag-end the new order is
 * written to the hidden #event-drag-order-input so Dash can pick it up.
 */

/* ---------- Load SortableJS from CDN (shared with goal_sortable.js) ---------- */
(function () {
    if (window.Sortable) return;           // already loaded
    var s  = document.createElement('script');
    s.src  = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js';
    s.async = false;
    document.head.appendChild(s);
})();

/* ---------- Helper: set value via native setter so React/Dash sees it ---------- */
function _setNativeValueEvent(el, val) {
    var nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, val);
    el.dispatchEvent(new Event('input', { bubbles: true }));
}

/* ---------- Init / re-init Sortable on each card group ---------- */
// The list holds up to two groups: active events and, when shown, triggered
// events below their divider. Each group is its own Sortable so a card can't
// be dragged across the divider. The saved order still reads every card in
// the container, top to bottom.
var _eventSortableInstances = [];
var _eventIsDragging = false;

function _onEventDragEnd(container) {
    _eventIsDragging = false;

    // Read the new order from DOM data attributes
    var cards = container.querySelectorAll('[data-event-name]');
    var order = [];
    cards.forEach(function (c) {
        var name = c.getAttribute('data-event-name');
        if (name) order.push(name);
    });

    // Write to hidden input so Dash picks it up
    var input = document.getElementById('event-drag-order-input');
    if (input) {
        _setNativeValueEvent(input, JSON.stringify(order));
    }
}

function _initEventSortable() {
    var container = document.getElementById('events-list-container');
    if (!container) return;

    // Destroy previous instances if Dash re-rendered the container
    _eventSortableInstances.forEach(function (instance) {
        try { instance.destroy(); } catch (_) {}
    });
    _eventSortableInstances = [];

    // Only enable if SortableJS is loaded
    if (!window.Sortable) {
        setTimeout(_initEventSortable, 200);
        return;
    }

    container.querySelectorAll('.events-sort-group').forEach(function (group) {
        _eventSortableInstances.push(new Sortable(group, {
            animation: 150,
            handle: '.event-drag-handle',       // only drag via the handle
            ghostClass: 'event-sortable-ghost',
            chosenClass: 'event-sortable-chosen',
            dragClass: 'event-sortable-drag',
            onStart: function () {
                _eventIsDragging = true;
            },
            onEnd: function () {
                _onEventDragEnd(container);
            }
        }));
    });
}

/* ---------- MutationObserver: re-init after every Dash render ---------- */
var _eventObserver = new MutationObserver(function (mutations) {
    // Never destroy/recreate the Sortable instance mid-drag.
    if (_eventIsDragging) return;
    // Debounce: only re-init once per render cycle
    clearTimeout(_eventObserver._timer);
    _eventObserver._timer = setTimeout(_initEventSortable, 50);
});

function _startEventObserving() {
    var container = document.getElementById('events-list-container');
    if (container) {
        _eventObserver.observe(container, { childList: true, subtree: false });
        _initEventSortable();
    } else {
        setTimeout(_startEventObserving, 300);
    }
}

// Kick off once the DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startEventObserving);
} else {
    _startEventObserving();
}
