/**
 * Startup cover: keep the app covered until it can act on what it shows.
 *
 * The Home tab is part of the initial layout, so it paints about half a
 * second after load. Nothing behind it is ready yet. On the ~780-node graph,
 * startup is a cascade of about 80 callbacks that keeps Dash busy for four to
 * five seconds. The core engine's payload arrives two and a half seconds in,
 * Cytoscape spends most of the next second ingesting it, and the Goals and
 * Analyze prewarms finish last. Inside that window a click on a Home row
 * waited behind the cascade, or was dropped when the table it landed on was
 * rebuilt. The Node Editor's search opened empty, because its options arrive
 * with the core engine's payload. The UI looked ready and wasn't.
 *
 * So the page template (layout.build_index_string) paints a cover first, and
 * this module lifts it once two things are true:
 *   - the core engine's first payload has reached the Nodes canvas. Dash
 *     applies every output of a response together, so the search options and
 *     every other dropdown that response fills are in place;
 *   - Dash then has nothing pending for QUIET_MS, confirmed once the browser
 *     is idle. The ingest that follows the payload, and the prewarms it
 *     starts, are then behind the user's first click rather than ahead of it.
 * Until then the app underneath is inert, so the keyboard can't reach what
 * the pointer can't.
 *
 * Dash renders `._dash-loading-callback` as a child of the entry point while
 * any callback is requested, blocked or in flight, and removes it when none
 * is. That marker is the whole busy signal. It is also absent before the
 * layout has loaded, which is why the payload has to arrive first.
 *
 * A backstop lifts the cover regardless. A startup that fails should still
 * end with the UI on screen, not with a spinner.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};

    var COVER_ID = 'startup-cover';
    var APP_ID = 'react-entry-point';
    var BUSY_SELECTOR = '._dash-loading-callback';

    var LIFT_MS = 200;          // keep in sync with .startup-cover in theme.css
    // Dash hands one batch of callbacks to the next without a gap. Measured
    // on the ~780-node graph, it stayed busy without a break from the layout
    // until the end. A chain that continues through a timer could still leave
    // one: dash-cytoscape echoes its elements about 100 ms after ingesting
    // them. So wait out a gap that long.
    var QUIET_MS = 150;
    var IDLE_TIMEOUT_MS = 1000;
    // Measured from page load. The whole cascade takes four to five seconds.
    var GIVE_UP_MS = 20000;

    var payloadLanded = false;
    var lifted = false;
    var watching = false;
    // Bumped on every change in Dash's busy state, so a quiet window that a
    // new callback interrupted can't lift the cover when it expires.
    var generation = 0;
    var observer = null;
    var giveUpTimer = null;

    function dashBusy() {
        return Boolean(document.querySelector(BUSY_SELECTOR));
    }

    function whenIdle(fn) {
        if (typeof window.requestIdleCallback === 'function') {
            window.requestIdleCallback(fn, { timeout: IDLE_TIMEOUT_MS });
        } else {
            setTimeout(fn, 0);
        }
    }

    function lift() {
        if (lifted) return;
        lifted = true;
        generation++;
        if (observer) observer.disconnect();
        clearTimeout(giveUpTimer);

        var app = document.getElementById(APP_ID);
        if (app) app.removeAttribute('inert');

        var cover = document.getElementById(COVER_ID);
        if (cover) {
            // A page loaded in the background has painted none of the cover.
            if (document.visibilityState === 'hidden') {
                cover.classList.add('is-lifted');
            } else {
                cover.classList.add('is-lifting');
                setTimeout(function () { cover.classList.add('is-lifted'); }, LIFT_MS);
            }
        }
        // Marks the moment startup settled on DevTools' performance timeline.
        if (window.performance && typeof window.performance.mark === 'function') {
            window.performance.mark('skill-tree-ready');
        }
    }

    // Runs whenever the busy marker comes or goes, and once when the payload
    // lands. Each call restarts the quiet window from scratch.
    function settle() {
        if (lifted || !payloadLanded) return;
        var token = ++generation;
        if (dashBusy()) {
            // The observer calls back when the marker clears. Without one,
            // look again.
            if (!observer) setTimeout(settle, QUIET_MS);
            return;
        }
        setTimeout(function () {
            if (token !== generation) return;
            whenIdle(function () {
                if (token !== generation || dashBusy()) return;
                lift();
            });
        }, QUIET_MS);
    }

    // Called by the clientside bridge in callbacks.py with every element
    // payload. Only the first one matters. A dcc.Store whose data starts as
    // None reports itself changed when it mounts, so the bridge also runs
    // once with no payload at all; that doesn't count.
    window.SkillTree.notifyStartupPayload = function (elements) {
        if (payloadLanded || !Array.isArray(elements)) return;
        payloadLanded = true;
        settle();
    };

    function watch() {
        if (watching) return;
        var cover = document.getElementById(COVER_ID);
        var app = document.getElementById(APP_ID);
        if (!cover || !app) return;
        watching = true;

        app.setAttribute('inert', '');
        if (typeof MutationObserver !== 'undefined') {
            // The marker is a direct child of the entry point, so the
            // children list is all there is to watch.
            observer = new MutationObserver(settle);
            observer.observe(app, { childList: true });
        }
        giveUpTimer = setTimeout(lift, GIVE_UP_MS);
    }

    // The cover and the entry point both come before the scripts in the page
    // template, so they already exist when this runs.
    if (document.readyState === 'loading'
            && !document.getElementById(APP_ID)) {
        document.addEventListener('DOMContentLoaded', watch);
    } else {
        watch();
    }
})();
