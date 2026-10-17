/* Clears a toast or banner a fixed time after its text last changed.
 *
 * Each message restarts the timer, so one that follows another still stays its
 * full time. A dcc.Interval can't do this: resetting its n_intervals doesn't
 * restart its clock, so a new message was cleared at the next tick of the old
 * rhythm, anywhere from 0 to the full time after it appeared.
 */
(function () {
    'use strict';
    var timers = {};

    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.toast_timer = {
        /* Arm (or re-arm) the timer for component `id`, then clear its
         * children after `ms` unless they changed again. */
        arm: function (id, ms, children) {
            clearTimeout(timers[id]);
            delete timers[id];
            if (!children) return;
            timers[id] = setTimeout(function () {
                delete timers[id];
                window.dash_clientside.set_props(id, {children: ''});
            }, ms);
            return;
        },
    };
})();
