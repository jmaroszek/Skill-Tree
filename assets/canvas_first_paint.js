/**
 * First paint of the Nodes canvas: keep it covered until the graph is both
 * laid out and framed, and say so while it isn't.
 *
 * The Nodes tab isn't the default, so this canvas mounts inside a display:none
 * subtree, and two things follow from that. Elements reach Cytoscape well
 * before any layout runs — React has to ingest ~750 KB of them first, and the
 * layout call waits behind that on the main thread — and until the layout runs
 * every position-less node sits stacked at the origin. Meanwhile `fit` is a
 * no-op at 0x0, so the layout's own fit leaves zoom at 1 and pan at the origin.
 *
 * Opening the tab inside that window therefore drew the whole graph piled into
 * the canvas's top-left corner, and then it jumped into place when the layout
 * landed. Measured on the 568-node sandbox graph: elements at 3.6 s, layout at
 * 5.2 s — 1.6 s of corner state. Kicking the layout early doesn't help; it is
 * queued behind the same blocked main thread, and it only adds a second
 * randomized pass that reshuffles the graph a second time.
 *
 * So the canvas waits behind an opaque cover until both halves are true:
 *   - its layout has settled — `layoutstop` on a graph with nodes, positions
 *     away from the origin, or an element payload with no nodes to lay out;
 *   - the canvas has a real size, so the graph can actually be framed.
 * Only then does the fit run and the cover lift.
 *
 * The caption goes up in the same task that reveals the tab, never on a timer.
 * It used to wait 400 ms so a nearly-ready graph wouldn't flash a spinner, but
 * the wait it explains is main-thread work, and a timer can't fire during it.
 * Measured: due 400 ms after the reveal, it fired at 915 ms. Arriving just
 * before the payload was ingested pushed it past the layout, so the cover
 * lifted before the caption ever painted and the tab just sat blank. A graph
 * that is already laid out still shows nothing, because the reveal lifts the
 * cover before that frame is painted.
 *
 * The fit itself used to live in fullscreen.js, which fitted the moment the
 * canvas first had a size — correct framing, but nothing held back the frames
 * before it.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};

    var CY_ID = 'cytoscape-graph';
    var PANE_ID = 'canvas-tab-content';
    var COVER_ID = 'canvas-first-paint-cover';

    var LIFT_MS = 200;             // keep in sync with .canvas-cover in theme.css
    var POLL_INTERVAL_MS = 100;
    var POLL_MAX_TRIES = 6000;     // 10 minutes; only so the poll can't leak
    // Nothing may strand the canvas behind the cover. Timed from the reveal,
    // not from page load: a tab nobody opened is a tab nobody is waiting on.
    var GIVE_UP_MS = 15000;

    var laidOut = false;       // a layout settled, or there was nothing to lay out
    var captionShown = false;
    var paneWasOpen = false;   // as of the previous attempt
    var done = false;
    var cleanups = [];
    var timers = [];

    function cyFor(el) {
        return (el && el._cyreg && el._cyreg.cy) ? el._cyreg.cy : null;
    }

    // Cytoscape stacks every position-less node at (0,0), so anything sitting
    // away from the origin means a layout has run. This backs up the
    // `layoutstop` event rather than replacing it: a one-node graph can
    // legitimately settle at the origin, and only the event catches that.
    function looksLaidOut(cy) {
        return cy.nodes().some(function (node) {
            var p = node.position();
            return Math.abs(p.x) > 1 || Math.abs(p.y) > 1;
        });
    }

    // toggle_tab_content (event_callbacks.py) owns this inline display, and
    // sets it on every tab switch including the first.
    function paneIsOpen() {
        var pane = document.getElementById(PANE_ID);
        return Boolean(pane) && pane.style.display !== 'none';
    }

    function frame(cy) {
        cy.resize();
        cy.fit(null, 30);
        cy.center();
    }

    // The layout prop describes a transition, because that is what every run
    // after the first one is: a filter change adds or removes nodes, and the
    // graph should keep its shape, gliding when Smooth is on. A run that starts
    // with every node stacked at the origin is the exception. There is no shape
    // to keep, so it has to randomize — incremental from that pile, fCoSE left
    // 547 of 568 sandbox nodes within 12 px of a neighbor. And while the cover
    // is still up nobody can watch it glide, so animating would only hold the
    // cover up for another second. dash-cytoscape starts every layout through
    // cy.layout(), so this is the one place that sees them all; Settle passes
    // through untouched, because its graph is already laid out.
    function guardColdStart(cy) {
        if (cy._skillTreeColdStartGuard) return;
        cy._skillTreeColdStartGuard = true;
        var layout = cy.layout;
        cy.layout = function (options) {
            if (options && cy.nodes().length && !looksLaidOut(cy)) {
                options = Object.assign({}, options, { randomize: true });
                if (!done) options.animate = false;
            }
            return layout.call(cy, options);
        };
    }

    function showCaption() {
        if (captionShown) return;
        captionShown = true;
        var cover = document.getElementById(COVER_ID);
        if (cover) cover.classList.add('is-waiting');
        timers.push(setTimeout(giveUp, GIVE_UP_MS));
    }

    // Whatever went wrong — a layout that never ran, a canvas that never got a
    // size — a stranded cover is worse than an unframed graph.
    function giveUp() {
        if (done) return;
        var el = document.getElementById(CY_ID);
        var cy = cyFor(el);
        if (cy && el.clientWidth && el.clientHeight) frame(cy);
        finish(paneIsOpen());
    }

    function finish(onScreen) {
        done = true;
        timers.forEach(function (timer) { clearTimeout(timer); });
        timers = [];

        var cover = document.getElementById(COVER_ID);
        if (cover) {
            // Only cross-fade a cover that has actually been on screen. When the
            // graph is ready before the tab opens, the observers below run in
            // the reveal task and the cover is gone before anything is painted.
            if (onScreen) {
                cover.classList.add('is-lifting');
                setTimeout(function () { cover.classList.add('is-lifted'); }, LIFT_MS);
            } else {
                cover.classList.add('is-lifted');
            }
        }

        cleanups.forEach(function (fn) { fn(); });
        cleanups = [];
    }

    function attempt() {
        if (done) return true;
        var el = document.getElementById(CY_ID);
        if (!el) return false;

        var cy = cyFor(el);
        if (cy) guardColdStart(cy);
        if (!laidOut && cy && looksLaidOut(cy)) laidOut = true;

        // A pane that was closed at the previous attempt has painted nothing of
        // this reveal yet.
        var paneOpen = paneIsOpen();
        var onScreen = paneOpen && paneWasOpen;
        paneWasOpen = paneOpen;

        // clientWidth forces the pending reflow, so this reads the size the
        // canvas has now rather than the one it had before the reveal.
        if (laidOut && cy && el.clientWidth && el.clientHeight) {
            frame(cy);
            finish(onScreen);
            return true;
        }

        if (paneOpen) showCaption();
        return false;
    }

    // Called from the clientside bridge in callbacks.py with each element
    // payload. A graph with no nodes has no layout to wait for, so no
    // `layoutstop` is ever coming — nothing else would release the cover.
    window.SkillTree.notifyCanvasElements = function (elements) {
        if (done || laidOut || !Array.isArray(elements)) return;
        var hasNodes = elements.some(function (element) {
            return element && element.data && element.data.source == null;
        });
        if (!hasNodes) {
            laidOut = true;
            attempt();
        }
    };

    var watching = false;

    // Dash renders its layout after this script runs, so the canvas usually
    // isn't there yet. Wait for it with an observer rather than a timer: a
    // timer retry is starved by the same startup work as everything else, and
    // a tab opened before it fires goes unwatched, leaving the caption to the
    // poll.
    function waitForCanvas() {
        if (typeof MutationObserver === 'undefined') {
            setTimeout(watch, 300);
            return;
        }
        var waiter = new MutationObserver(function () {
            if (!document.getElementById(CY_ID)) return;
            waiter.disconnect();
            watch();
        });
        waiter.observe(document.documentElement, { childList: true, subtree: true });
    }

    // Three independent triggers, all idempotent, first one wins: a
    // MutationObserver on the tab pane, delivered in the same task that
    // reveals it; a ResizeObserver on the canvas, delivered before that frame
    // paints; and a bounded poll — because both observers are part of the
    // rendering lifecycle and a document that never composites gets neither.
    function watch() {
        if (watching) return;
        var el = document.getElementById(CY_ID);
        if (!el) {
            waitForCanvas();
            return;
        }
        watching = true;

        var pane = document.getElementById(PANE_ID);
        if (pane && typeof MutationObserver !== 'undefined') {
            var mo = new MutationObserver(function () { attempt(); });
            mo.observe(pane, { attributes: true, attributeFilter: ['style', 'class'] });
            cleanups.push(function () { mo.disconnect(); });
        }

        if (typeof ResizeObserver !== 'undefined') {
            var ro = new ResizeObserver(function () { attempt(); });
            ro.observe(el);
            cleanups.push(function () { ro.disconnect(); });
        }

        var tries = 0;
        var poll = setInterval(function () {
            if (attempt() || ++tries > POLL_MAX_TRIES) clearInterval(poll);
        }, POLL_INTERVAL_MS);
        cleanups.push(function () { clearInterval(poll); });

        if (window.SkillTree.onCytoReady) {
            window.SkillTree.onCytoReady('#' + CY_ID, function (cy) {
                guardColdStart(cy);
                cy.on('layoutstop', function () {
                    // The mount-time layout runs over an empty graph before any
                    // payload exists and says nothing about one. An empty
                    // payload is reported through notifyCanvasElements instead.
                    if (!cy.nodes().length) return;
                    laidOut = true;
                    attempt();
                });
            });
        }

        attempt();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watch);
    } else {
        watch();
    }
})();
