/**
 * Keep an in-memory dcc.Store from reporting a change when it mounts.
 *
 * Each memory Store gets a fresh, empty backing store, so dcc.Store's mount
 * code always finds it "different" and calls setProps: with a timestamp when
 * the Store has data, and with `data: undefined` when it starts as None. The
 * data is the same either way. But each call is a Redux update, and on every
 * update dash-renderer re-checks all ~2,000 mounted components. A None Store
 * also wakes its listeners as if it had been written, prevent_initial_call or
 * not, which is how an arrival store used to "arrive" on page load.
 *
 * Measured on the 774-node sandbox, this removed 53 mount updates and five
 * startup callbacks, and the cover lifted about 0.35 s sooner.
 *
 * The replacement does only what the original's mount does for a memory
 * Store with nothing stored yet: it records the initial data. Every other
 * case (local or session storage, a remount that finds data) runs the
 * original. Later writes go through componentDidUpdate, which is unchanged.
 * If a Dash upgrade changes the component so the guards below no longer
 * hold, the original runs untouched.
 *
 * Asset scripts load before Dash's component bundles, so this waits for
 * DOMContentLoaded. The layout is fetched after that, so no Store has
 * mounted yet.
 */
(function () {
    'use strict';

    function patchStore() {
        var dcc = window.dash_core_components;
        var Store = dcc && dcc.Store;
        var proto = Store && Store.prototype;
        if (!proto || typeof proto.UNSAFE_componentWillMount !== 'function'
                || proto.__skillTreeQuietMount) {
            return;
        }
        var original = proto.UNSAFE_componentWillMount;
        proto.UNSAFE_componentWillMount = function () {
            var props = this.props || {};
            var backstore = this._backstore;
            if (props.storage_type !== 'memory' || !backstore
                    || typeof backstore.getItem !== 'function'
                    || typeof backstore.setItem !== 'function'
                    || backstore.getItem(props.id) !== undefined) {
                return original.apply(this, arguments);
            }
            if (props.data !== null && props.data !== undefined) {
                backstore.setItem(props.id, props.data);
            }
        };
        proto.__skillTreeQuietMount = true;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', patchStore);
    } else {
        patchStore();
    }
})();
