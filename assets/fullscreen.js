/**
 * Fullscreen toggle, scroll sensitivity, and right-click-to-pan for the Skill Tree canvas.
 *
 * Pure JS — no Dash callback needed.
 */
(function () {

    // --- Scroll sensitivity ---
    // Cytoscape's built-in zoom is disabled (userZoomingEnabled=False).
    // We handle wheel events ourselves with cy.zoom() for gradual control.
    var ZOOM_FACTOR = 1.1;  // per-tick multiplier (closer to 1 = slower)

    function initScrollSensitivity(selector) {
        var cyWrapper = document.querySelector(selector);
        if (!cyWrapper) {
            setTimeout(function() { initScrollSensitivity(selector); }, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        cyWrapper.addEventListener('wheel', function (e) {
            e.preventDefault();
            var cy = getCy();
            if (!cy) return;

            var rect = cyWrapper.getBoundingClientRect();
            var renderedPosition = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };

            var direction = e.deltaY > 0 ? -1 : 1;  // scroll down = zoom out
            var newZoom = cy.zoom() * Math.pow(ZOOM_FACTOR, direction);

            // Clamp to Cytoscape's min/max
            newZoom = Math.max(cy.minZoom(), Math.min(cy.maxZoom(), newZoom));

            cy.zoom({
                level: newZoom,
                renderedPosition: renderedPosition
            });
        }, { passive: false });
    }

    // --- Right-click panning ---
    // userPanningEnabled is set to False in Cytoscape config.
    // We manually pan on right-click drag on the canvas background.
    function initRightClickPan(selector) {
        var cyWrapper = document.querySelector(selector);
        if (!cyWrapper) {
            setTimeout(function() { initRightClickPan(selector); }, 300);
            return;
        }

        function getCy() {
            return (cyWrapper._cyreg && cyWrapper._cyreg.cy) ? cyWrapper._cyreg.cy : null;
        }

        cyWrapper.addEventListener('mousedown', function (e) {
            // Only handle right-click (button 2)
            if (e.button !== 2) return;
            if (!window.SkillTree || !window.SkillTree.drag) return;

            var cy = getCy();
            if (!cy) return;

            // Check if the mousedown is on a node — if so, don't pan (let context menu handle it)
            var rect = cyWrapper.getBoundingClientRect();
            var rendPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
            var modelPos = {
                x: (rendPos.x - cy.pan().x) / cy.zoom(),
                y: (rendPos.y - cy.pan().y) / cy.zoom()
            };
            var nearNode = cy.nodes().some(function (node) {
                var bb = node.boundingBox();
                return modelPos.x >= bb.x1 && modelPos.x <= bb.x2 &&
                       modelPos.y >= bb.y1 && modelPos.y <= bb.y2;
            });
            if (nearNode) return;

            var lastX = e.clientX;
            var lastY = e.clientY;
            cyWrapper.style.cursor = 'grabbing';
            e.preventDefault();

            window.SkillTree.drag.start({
                // Cursor is scoped to cyWrapper, not body; don't override body cursor.
                userSelect: false,
                onMove: function (ev) {
                    var c = getCy();
                    if (!c) return;
                    var dx = ev.clientX - lastX;
                    var dy = ev.clientY - lastY;
                    lastX = ev.clientX;
                    lastY = ev.clientY;
                    c.panBy({ x: dx, y: dy });
                },
                onEnd: function () {
                    cyWrapper.style.cursor = '';
                },
            });
        });
    }

    // --- Fullscreen toggle (generic, used by every canvas) ---
    function initCanvasFullscreen(btnId, containerId, cyId) {
        var btn = document.getElementById(btnId);
        var container = document.getElementById(containerId);

        if (!btn || !container) {
            setTimeout(function () { initCanvasFullscreen(btnId, containerId, cyId); }, 300);
            return;
        }

        function refit() {
            setTimeout(function () {
                var cy = document.getElementById(cyId);
                if (cy && cy._cyreg && cy._cyreg.cy) {
                    cy._cyreg.cy.resize();
                    cy._cyreg.cy.fit();
                }
            }, 50);
        }

        btn.addEventListener('click', function () {
            container.classList.toggle('canvas-fullscreen');
            refit();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && container.classList.contains('canvas-fullscreen')) {
                container.classList.remove('canvas-fullscreen');
                refit();
            }
        });
    }

    // --- Fit the graph the moment its canvas first has a size ---
    function centerGraph(selector) {
        var el = document.querySelector(selector);
        if (!el || !el._cyreg || !el._cyreg.cy) {
            return false;
        }
        el._cyreg.cy.resize();
        el._cyreg.cy.fit(null, 30);
        el._cyreg.cy.center();
        return true;
    }

    // The Nodes tab isn't the default, so this canvas mounts inside a
    // display:none subtree. Its layout still computes sensible positions, but
    // `fit: true` is a no-op at 0x0 — Cytoscape leaves zoom at 1 and pan at the
    // origin, which parks the whole graph in the canvas's top-left corner.
    // Nothing corrects that until something fits again, so opening the tab used
    // to show the graph crammed into the corner for about half a second and
    // then jump into place.
    //
    // Three independent triggers, all idempotent, first one wins:
    //   - a ResizeObserver on the canvas, whose callback runs before the browser
    //     paints the frame, so the fit lands in the same frame the tab is
    //     revealed and the corner state is never drawn;
    //   - a MutationObserver on the tab pane, for the same reveal;
    //   - a bounded poll, because both observers are delivered as part of the
    //     rendering lifecycle and a document that never composites gets neither.
    // The old version fitted on fixed 100 ms and 600 ms timers after the reveal,
    // which is exactly the delay that made the corner state visible.
    var POLL_INTERVAL_MS = 100;
    var POLL_MAX_TRIES = 6000;  // 10 minutes

    function fitWhenFirstVisible(cyId, paneId) {
        var el = document.getElementById(cyId);
        if (!el) {
            setTimeout(function () { fitWhenFirstVisible(cyId, paneId); }, 300);
            return;
        }

        var done = false;
        var cleanups = [];

        function attempt() {
            if (done) return true;
            // clientWidth forces the pending reflow, so this reads the size the
            // canvas has now rather than the one it had before the reveal.
            if (!el.clientWidth || !el.clientHeight) return false;
            // Cytoscape mounts long before the tab is opened, but never latch
            // on a canvas that has no instance yet.
            if (!centerGraph('#' + cyId)) return false;
            done = true;
            cleanups.forEach(function (fn) { fn(); });
            cleanups = [];
            return true;
        }

        if (typeof ResizeObserver !== 'undefined') {
            var ro = new ResizeObserver(attempt);
            ro.observe(el);
            cleanups.push(function () { ro.disconnect(); });
        }

        var pane = paneId && document.getElementById(paneId);
        if (pane && typeof MutationObserver !== 'undefined') {
            var mo = new MutationObserver(attempt);
            mo.observe(pane, { attributes: true, attributeFilter: ['style', 'class'] });
            cleanups.push(function () { mo.disconnect(); });
        }

        // The tab may be opened at any point in a session, so this backstop
        // has to outlive "shortly after load" — a short-lived one is expired
        // by the time it would be needed. The check is a single clientWidth
        // read; the cap only exists so it cannot leak forever.
        var tries = 0;
        var poll = setInterval(function () {
            if (attempt() || ++tries > POLL_MAX_TRIES) clearInterval(poll);
        }, POLL_INTERVAL_MS);
        cleanups.push(function () { clearInterval(poll); });

        attempt();
    }

    function initAll() {
        initScrollSensitivity('#cytoscape-graph');
        initScrollSensitivity('#goal-mini-graph');
        initScrollSensitivity('#details-mini-graph');
        initScrollSensitivity('#events-detail-graph');
        initCanvasFullscreen('btn-fullscreen', 'canvas-container', 'cytoscape-graph');
        initCanvasFullscreen('btn-details-graph-fullscreen', 'details-dep-graph-container', 'details-mini-graph');
        initCanvasFullscreen('btn-events-graph-fullscreen', 'events-detail-graph-container', 'events-detail-graph');
        initRightClickPan('#cytoscape-graph');
        initRightClickPan('#goal-mini-graph');
        initRightClickPan('#details-mini-graph');
        initRightClickPan('#events-detail-graph');
        fitWhenFirstVisible('cytoscape-graph', 'canvas-tab-content');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
