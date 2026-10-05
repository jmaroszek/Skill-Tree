/** Drop Dash's empty callback-bookkeeping dispatches before they reach React.
 *
 * dash-renderer's requested-callbacks observer runs asynchronously, once per
 * change to its queues. When a burst of callbacks finishes, the queued runs
 * resolve afterwards, each finding nothing to do, and each still dispatches a
 * `Callbacks.Aggregate` action whose every entry is null. The reducer returns
 * the state unchanged for that, but the dispatch alone makes every mounted
 * component re-check the store, about 2 ms apiece here. After a Details
 * selection about ten of them landed in a row in the graph's first frames.
 *
 * Only that exact no-op is dropped. Dash's observers read `store.dispatch`
 * when they run, so wrapping the property reaches them. The store doesn't
 * exist yet when assets load, so the wrapper is installed as Dash assigns
 * `window.store`.
 */
(function () {
    'use strict';

    function isEmptyAggregate(action) {
        if (!action || action.type !== 'Callbacks.Aggregate') return false;
        var payload = action.payload;
        if (!Array.isArray(payload)) return false;
        for (var i = 0; i < payload.length; i++) {
            if (payload[i] !== null) return false;
        }
        return true;
    }

    function wrap(store) {
        if (!store || typeof store.dispatch !== 'function' || store._skillTreeNoopFilter) {
            return store;
        }
        var dispatch = store.dispatch;
        store.dispatch = function (action) {
            if (isEmptyAggregate(action)) return action;
            return dispatch.apply(this, arguments);
        };
        store._skillTreeNoopFilter = true;
        return store;
    }

    var current = wrap(window.store);
    try {
        Object.defineProperty(window, 'store', {
            configurable: true,
            enumerable: true,
            get: function () { return current; },
            set: function (store) { current = wrap(store); }
        });
    } catch (e) {
        // A non-configurable property: leave Dash's store as it is.
    }

    window.SkillTree = window.SkillTree || {};
    window.SkillTree.isEmptyDashAggregate = isEmptyAggregate;
})();
