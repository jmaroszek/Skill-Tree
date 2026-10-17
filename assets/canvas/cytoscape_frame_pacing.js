/**
 * Pace Cytoscape's animation frames on every canvas.
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
 *
 * Those slow draws get two savings instead. The tick between two draws used
 * to step every animation, and Cytoscape's texture queue then recomputed the
 * geometry of everything the step had moved. The next tick stepped again
 * before drawing, so nobody saw that work. Now that tick leaves the animations
 * alone and asks the next tick to draw. And before a slow draw, every node's
 * bounds are measured. Cytoscape draws edges first, and an edge with a moved
 * endpoint recomputed its own bounds on each of the five lookups its draw
 * makes, because the endpoint's bounds stayed stale until the node itself was
 * drawn. A Settle of the 567-node sandbox graph went from about 20 drawn frames
 * a second to 27 with both.
 *
 * Animations also step on a fresh clock. Chrome stamps a frame with the time
 * it was scheduled, and after a long task the stamp can be hundreds of
 * milliseconds old. Cytoscape steps by that stamp, so a tween that starts
 * after its layout's computation started its clock that far back. A Settle
 * of the sandbox graph lost its first 0.3 s that way. Its first frame drew
 * the start, and its next frame jumped a third of the way. A stamp more than
 * two frames older than the tick is moved up to that limit.
 */
(function () {
    'use strict';
    var SkillTree = window.SkillTree = window.SkillTree || {};

    // Ticks further apart than this are a pause, not a frame.
    var MAX_FRAME_MS = 100;
    // A frame stamp older than this many frames is stale.
    var STALE_FRAMES = 2;
    // Assumed until the ticks have been measured.
    var DEFAULT_FRAME_MS = 1000 / 60;

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
        var stepping = false;
        var stepAsked = false;
        var lastStepMoved = false;

        // Unknown until the ticks and a draw have been measured.
        function slow() {
            return frameMs !== null && r.averageRedrawTime >= frameMs / 2;
        }

        function fast() {
            return frameMs !== null && r.averageRedrawTime < frameMs / 2;
        }

        // Elements with animations to step, or a viewport animation. Without
        // Cytoscape's pool of animating elements, only the viewport counts.
        function animating() {
            var pool = cy._private && cy._private.aniEles;
            if (pool && pool.length) return true;
            return typeof cy.animated === 'function' && Boolean(cy.animated());
        }

        // Ahead of every other tick callback, so it sees the animation step's
        // request. It runs on ticks that won't draw too, and resets there.
        var priorities = r.beforeRenderPriorities || {};
        var levels = Object.keys(priorities).map(function (key) {
            return priorities[key];
        });
        var first = Math.max.apply(null, levels.concat([0])) + 100;
        var last = Math.min.apply(null, levels.concat([100])) - 100;
        r.beforeRender(function (willDraw, now) {
            preparing = true;
            requested = false;
            if (lastTick !== null && now - lastTick > 0 && now - lastTick < MAX_FRAME_MS) {
                var delta = now - lastTick;
                frameMs = frameMs === null ? delta : frameMs * 0.8 + delta * 0.2;
            }
            lastTick = now;
        }, first);

        // Cytoscape steps its animations from this callback.
        var animations = (r.beforeRenderCallbacks || []).filter(function (callback) {
            return callback.priority === priorities.animations;
        })[0];
        if (animations && typeof animations.fn === 'function') {
            var step = animations.fn;
            animations.fn = function (willDraw, now) {
                // The previous step moved something that is still moving, so
                // this one would move it too, and the next tick would move it
                // again before drawing.
                if (!willDraw && lastStepMoved && slow() && animating()) {
                    r.redraw();
                    return undefined;
                }
                var floor = performance.now() - STALE_FRAMES * (frameMs || DEFAULT_FRAME_MS);
                stepping = true;
                stepAsked = false;
                try {
                    return step.call(this, willDraw, now < floor ? floor : now);
                } finally {
                    stepping = false;
                    lastStepMoved = stepAsked;
                }
            };
        }

        // After every other tick callback, so the nodes have their new
        // positions and rendered styles.
        r.beforeRender(function (willDraw) {
            if (!willDraw || !slow()) return;
            var nodes = cy.nodes();
            for (var i = 0; i < nodes.length; i++) nodes[i].boundingBox();
        }, last);

        var redraw = r.redraw;
        r.redraw = function () {
            if (preparing) requested = true;
            if (stepping) stepAsked = true;
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
                    if (!r.destroyed && fast()) r.redraw();
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
