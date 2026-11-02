/**
 * Frame Focus: bring a route closer without losing the graph around it.
 *
 * Focus dims everything but a route or a subtree on the Nodes canvas. On a big
 * graph the whole-graph frame leaves a short route too small to read, and a
 * frame fit to the route alone hides what the route is connected to, which
 * Details already shows on its own. So the route takes about half the canvas,
 * and the rest stays for context.
 *
 * Clear Focus puts the viewport back where Focus found it.
 */
(function () {
    window.dash_clientside = window.dash_clientside || {};
    var SkillTree = window.SkillTree = window.SkillTree || {};

    var CANVAS_ID = 'cytoscape-graph';
    var ROUTE_SHARE = 0.55;   // of the canvas, along whichever side it fills first
    var MAX_ZOOM = 1;         // past natural size a frame only magnifies
    var DURATION_MS = 400;
    var SETTLE_MS = 150;      // a response's layout starts within this
    var LAYOUT_WATCH_MS = 8000;
    var WAIT_TRIES = 100;     // 10 s

    var framed = null;        // the focus the viewport is framed for
    var home = null;          // the viewport before Focus

    function route(cy, focus) {
        var names = Object.keys((focus.path_info && focus.path_info.node_rank) || {});
        if (!names.length) names = focus.subtree || [];
        if (!names.length && focus.node) names = [focus.node];
        var found = cy.collection();
        names.forEach(function (name) {
            found = found.union(cy.getElementById(name));
        });
        return found;
    }

    function zoomToFit(box, width, height) {
        return Math.min(width / Math.max(box.w, 1), height / Math.max(box.h, 1));
    }

    function viewportFor(cy, nodes) {
        var width = cy.width();
        var height = cy.height();
        var box = nodes.boundingBox({includeLabels: false});
        var whole = zoomToFit(cy.elements().boundingBox({includeLabels: false}), width, height);
        var zoom = zoomToFit(box, width, height) * ROUTE_SHARE;
        // A route as big as the graph stays at the whole-graph frame.
        zoom = Math.min(Math.max(zoom, Math.min(whole, MAX_ZOOM)), MAX_ZOOM);
        return {
            zoom: zoom,
            pan: {
                x: width / 2 - (box.x1 + box.w / 2) * zoom,
                y: height / 2 - (box.y1 + box.h / 2) * zoom,
            },
        };
    }

    function move(cy, viewport) {
        cy.stop();
        cy.animate(viewport, {duration: DURATION_MS});
    }

    function frameFocus(cy, focus, key) {
        if (framed !== key) return;
        var nodes = route(cy, focus);
        if (nodes.length) move(cy, viewportFor(cy, nodes));
    }

    // Clearing filters for Focus adds nodes, and the layout that follows moves
    // the route, so a layout under way waits and the frame follows it.
    function frameWhenSettled(cy, focus, key) {
        var laying = false;
        cy.off('.focusFrame');
        cy.on('layoutstart.focusFrame', function () { laying = true; });
        cy.on('layoutstop.focusFrame', function () {
            laying = false;
            frameFocus(cy, focus, key);
        });
        setTimeout(function () {
            if (!laying) frameFocus(cy, focus, key);
        }, SETTLE_MS);
        setTimeout(function () {
            if (framed === key) cy.off('.focusFrame');
        }, LAYOUT_WATCH_MS);
    }

    function ready(cy) {
        var paint = SkillTree.canvasFirstPaintDone;
        var pending = SkillTree.canvasPayloadPending;
        return (typeof paint !== 'function' || paint())
            && (typeof pending !== 'function' || !pending(CANVAS_ID))
            && cy.width() > 0 && cy.height() > 0;
    }

    function whenReady(then, attempt) {
        var cy = SkillTree.getCy(document.getElementById(CANVAS_ID));
        if (cy && ready(cy)) {
            then(cy);
        } else if ((attempt || 0) < WAIT_TRIES) {
            setTimeout(function () { whenReady(then, (attempt || 0) + 1); }, 100);
        }
    }

    window.dash_clientside.canvas_focus = {
        // Runs on the render that carries Focus's stylesheet, so its elements
        // are on the canvas by now. Every later render leaves the viewport
        // alone: the same focus is already framed.
        frame: function (_stylesheet, focus) {
            var no = window.dash_clientside.no_update;
            var key = focus ? JSON.stringify(focus) : null;
            if (key === framed) return no;
            framed = key;
            whenReady(function (cy) {
                if (framed !== key) return;
                if (key) {
                    if (!home) home = {zoom: cy.zoom(), pan: Object.assign({}, cy.pan())};
                    frameWhenSettled(cy, focus, key);
                } else {
                    cy.off('.focusFrame');
                    if (home) move(cy, home);
                    home = null;
                }
            });
            return no;
        },
    };
})();
