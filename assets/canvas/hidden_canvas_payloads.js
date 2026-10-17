/** A hidden canvas keeps its newest payload until its tab is shown.
 *
 * The filters are shared, and Details and Events re-render on graph
 * refreshes from anywhere. Applying a payload to a hidden canvas runs its
 * layout on the page's one main thread, with nobody watching it. A Nodes
 * filter change laid out the hidden Details graph inside the Nodes
 * animation. Once the Nodes canvas had loaded, a filter change on Details
 * laid out all of Nodes, about 0.8 s of blocked page, before the Details
 * graph could start moving.
 *
 * So the pending-store bridge in callbacks.py hands a hidden canvas's
 * payload here. Only the newest payload is kept. A payload that arrives
 * while the canvas is shown drops the one held.
 *
 * When the tab is shown, the held payload is applied after the tab has
 * painted. Applied with the tab switch, a large layout ran before the
 * browser could draw the new tab, so the click seemed to do nothing for a
 * second. The layout then runs on the visible canvas, and the user sees the
 * graph move to its new state.
 *
 * Locate reads the held payload: it decides whether a node is on a canvas
 * before navigating there, and it waits for the held graph to settle before
 * it pulses a node.
 */
(function () {
    'use strict';
    var st = window.SkillTree = window.SkillTree || {};
    var held = {};
    var settling = {};
    // Bumped by every payload the canvas applies, so a held payload whose
    // turn comes after a newer one has landed is dropped.
    var generation = {};

    // A shown payload that starts no layout (its nodes and edges didn't
    // change) has nothing to wait for.
    var LAYOUT_START_GRACE_MS = 250;
    var SETTLE_DEADLINE_MS = 4000;
    // requestAnimationFrame doesn't run in a hidden window, and a canvas
    // can stay sizeless. The payload still lands, after this long.
    var SHOWN_DEADLINE_MS = 1000;

    function canvasBy(field, value) {
        return (st.canvases || []).find(function (canvas) {
            return canvas[field] === value;
        });
    }

    function liveCy(canvas) {
        return canvas && st.getCy ? st.getCy(document.getElementById(canvas.cytoscapeId)) : null;
    }

    // Runs `fn` once the canvas is on screen and a frame has painted it.
    // The tab's panel is displayed by a render after active_tab changes,
    // which can come after the next frame.
    function afterShown(canvas, fn) {
        var ran = false;
        var deadline = setTimeout(once, SHOWN_DEADLINE_MS);
        function once() {
            if (ran) return;
            ran = true;
            clearTimeout(deadline);
            fn();
        }
        function shown() {
            var el = document.getElementById(canvas.cytoscapeId);
            return Boolean(el && el.offsetWidth > 0 && el.offsetHeight > 0);
        }
        // A frame callback runs before that frame paints. A timeout queued
        // from it runs after.
        function frame() {
            if (ran) return;
            if (shown()) setTimeout(once, 0);
            else requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    function hasNodes(pending) {
        return pending.some(function (element) {
            var data = element && element.data;
            return data && data.source == null;
        });
    }

    // Holds `pending` when the canvas's tab isn't the active one. Returns
    // whether it did. A payload with no nodes has nothing to lay out, so it
    // lands at once. Held, its layout ran when the tab opened, and could
    // still be running when the user picked the first graph to show.
    st.holdHiddenPayload = function (key, pending, activeTab) {
        var canvas = canvasBy('key', key);
        if (!canvas || canvas.tabId === activeTab || !hasNodes(pending)) {
            delete held[key];
            generation[key] = (generation[key] || 0) + 1;
            return false;
        }
        held[key] = pending;
        return true;
    };

    // Once the canvas's tab is active, hands its held payload to `apply`
    // after the tab has painted. Returns whether there was one.
    st.showHeldPayload = function (key, activeTab, apply) {
        var canvas = canvasBy('key', key);
        if (!canvas || canvas.tabId !== activeTab || !held[key]) return false;
        var pending = held[key];
        delete held[key];
        var token = {};
        settling[key] = token;
        var gen = generation[key] = (generation[key] || 0) + 1;
        afterShown(canvas, function () {
            if (generation[key] !== gen) {
                if (settling[key] === token) delete settling[key];
                return;
            }
            watchSettle(canvas, token);
            apply(pending);
        });
        return true;
    };

    st.heldPayload = function (cytoscapeId) {
        var canvas = canvasBy('cytoscapeId', cytoscapeId);
        return (canvas && held[canvas.key]) || null;
    };

    // True while a payload is held for the canvas, or while one just shown
    // is landing and laying out.
    st.canvasPayloadPending = function (cytoscapeId) {
        var canvas = canvasBy('cytoscapeId', cytoscapeId);
        return Boolean(canvas && (held[canvas.key] || settling[canvas.key]));
    };

    function watchSettle(canvas, token) {
        var key = canvas.key;
        var started = false;
        var cy = liveCy(canvas);
        function done() {
            if (settling[key] === token) delete settling[key];
            if (cy) {
                cy.off('layoutstart', onStart);
                cy.off('layoutstop', done);
            }
        }
        function onStart() { started = true; }
        if (!cy) { done(); return; }
        // Listen before the payload lands: Nodes lays out new elements as
        // dash-cytoscape applies them.
        cy.on('layoutstart', onStart);
        cy.one('layoutstop', done);
        setTimeout(function () { if (!started) done(); }, LAYOUT_START_GRACE_MS);
        setTimeout(done, SETTLE_DEADLINE_MS);
    }
})();
