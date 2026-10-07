/**
 * Draw an animating canvas on every frame, not every other one.
 *
 * Cytoscape runs one loop per canvas on requestAnimationFrame. Each tick it
 * draws only if a redraw was requested before the tick began. Then it steps
 * the running animations, and the step requests the next redraw. On a tick
 * that draws, the loop clears that request once the draw finishes. The next
 * tick finds no request and only steps. So a moving graph was drawn on every
 * other tick.
 *
 * Traced in the Electron window on a 240 Hz screen, the Details opening
 * animation of a small view showed 120 new frames a second. The main thread
 * sat nearly idle.
 *
 * This module keeps the redraw a step asks for. A request made while a tick
 * prepares its draw is renewed after the draw, so the next tick draws too.
 * Requests made at any other time already survive, and a graph that stops
 * moving stops asking.
 *
 * A draw that takes more than half a frame keeps Cytoscape's pacing. Drawing
 * a large graph twice as often could starve everything else on the page, and
 * the skipped ticks are what leave it room. A frame is measured from the
 * ticks, because it is 4 ms on a 240 Hz screen and 17 ms on a 60 Hz one.
 */
(function () {
    'use strict';
    var SkillTree = window.SkillTree = window.SkillTree || {};

    // Ticks further apart than this are a pause, not a frame.
    var MAX_FRAME_MS = 100;

    function pace(cy) {
        var r = cy && typeof cy.renderer === 'function' ? cy.renderer() : null;
        if (!r || r._skillTreeFramePacing) return;
        if (typeof r.render !== 'function' || typeof r.redraw !== 'function'
                || typeof r.beforeRender !== 'function') return;
        r._skillTreeFramePacing = true;

        var preparing = false;
        var requested = false;
        var lastTick = null;
        var frameMs = null;

        // Ahead of every other tick callback, so it sees the animation step's
        // request. It runs on ticks that won't draw too, and resets there.
        var priorities = r.beforeRenderPriorities || {};
        var first = Math.max.apply(null, Object.keys(priorities).map(function (key) {
            return priorities[key];
        }).concat([0])) + 100;
        r.beforeRender(function (willDraw, now) {
            preparing = true;
            requested = false;
            if (lastTick !== null && now - lastTick > 0 && now - lastTick < MAX_FRAME_MS) {
                var delta = now - lastTick;
                frameMs = frameMs === null ? delta : frameMs * 0.8 + delta * 0.2;
            }
            lastTick = now;
        }, first);

        var redraw = r.redraw;
        r.redraw = function () {
            if (preparing) requested = true;
            return redraw.apply(this, arguments);
        };

        var render = r.render;
        r.render = function () {
            var renew = preparing && requested;
            preparing = false;
            requested = false;
            var result = render.apply(this, arguments);
            // The loop clears its request after this returns. A microtask
            // runs after that, and before the next tick.
            if (renew) {
                queueMicrotask(function () {
                    if (r.destroyed || frameMs === null) return;
                    if (r.averageRedrawTime < frameMs / 2) r.redraw();
                });
            }
            return result;
        };
    }

    SkillTree.paceCanvasFrames = pace;

    function watchCanvases() {
        if (!SkillTree.onCytoReady) return;
        (SkillTree.canvases || []).forEach(function (canvas) {
            SkillTree.onCytoReady('#' + canvas.cytoscapeId, pace);
        });
    }

    // cyto_lifecycle.js may not have run yet.
    if (typeof document !== 'undefined' && document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchCanvases);
    } else {
        watchCanvases();
    }
})();
