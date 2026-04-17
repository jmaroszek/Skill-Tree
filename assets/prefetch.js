/**
 * Idle-time background prefetch for the Nodes and Analyze tabs.
 *
 * Fired once when the app-load-interval ticks. Uses requestIdleCallback so
 * prefetch never contends with first-paint or user-driven work; writes
 * sentinel values into the hidden `prefetch-tab-trigger` input so Dash's
 * populate_tab_content callback builds each tab's subtree silently. The
 * parent Div remains display:none until the user activates the tab for real.
 */
(function () {
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.prefetch = {
        scheduleIdlePrefetch: function (n_intervals) {
            if (!n_intervals || n_intervals < 1) {
                return window.dash_clientside.no_update;
            }

            function writeTrigger(value) {
                var input = document.getElementById('prefetch-tab-trigger');
                if (!input) return;
                var nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(input, value);
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }

            var scheduleIdle = window.requestIdleCallback || function (fn) {
                return setTimeout(fn, 300);
            };

            scheduleIdle(function () {
                writeTrigger('prefetch-canvas');
                scheduleIdle(function () {
                    writeTrigger('prefetch-analyze');
                }, { timeout: 1500 });
            }, { timeout: 1500 });

            return window.dash_clientside.no_update;
        }
    };
})();
