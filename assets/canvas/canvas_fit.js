/**
 * Frame a canvas's graph even when its layout ran while the tab was hidden.
 *
 * Every layout request asks Cytoscape to fit the graph to the canvas. It fits
 * against the canvas size it has cached, and at 0x0 the fit silently does
 * nothing: zoom stays at 1, the pan stays at the origin, and the graph draws
 * in the canvas's top-left corner. Two things left Details and Events there.
 *
 *   - The tab had just opened. Cytoscape refreshes its cached size 100 ms
 *     after the canvas resizes. View Details opens the tab and selects the
 *     node in one step, so the layout could start inside that window and fit
 *     against the 0x0 the hidden tab left behind.
 *   - The tab was still hidden. Details lays out a new selection from any tab,
 *     as Explain Priority does from Next, and later opens on a graph that was
 *     never framed.
 *
 * So each layout first refreshes the cached size. A layout that still finds
 * no size owes its fit. The debt is paid once the canvas has a size and that
 * layout has stopped, in the same task that reveals the tab, before it paints.
 * A later layout that finds a size cancels the debt, because its own fit
 * lands. Nothing else moves the viewport, so a tab you come back to keeps the
 * pan and zoom you left it with.
 *
 * canvas_first_paint.js also frames the Nodes canvas behind its cover on the
 * first load. Both fit the whole graph, so it doesn't matter which runs first.
 */
(function () {
    var SkillTree = window.SkillTree = window.SkillTree || {};

    // A fit scales the graph to fill the canvas, so two nodes would fill it
    // too and draw at many times their size. Past natural size a fit stops
    // helping; it only magnifies. Zoom in beyond this by hand.
    var MAX_FIT_ZOOM = 1;

    function hasSize(cy) {
        var container = cy.container();
        return Boolean(container && container.clientWidth && container.clientHeight);
    }

    // Pull a fit that overshot back to MAX_FIT_ZOOM about the canvas's center,
    // where the fit has just put the graph.
    function capZoom(cy) {
        if (typeof cy.zoom !== 'function' || !hasSize(cy) || cy.zoom() <= MAX_FIT_ZOOM) return;
        var container = cy.container();
        cy.zoom({
            level: MAX_FIT_ZOOM,
            renderedPosition: { x: container.clientWidth / 2, y: container.clientHeight / 2 }
        });
    }
    SkillTree.capFitZoom = capZoom;

    function track(cy) {
        if (cy._skillTreeFit) return;
        var state = cy._skillTreeFit = { debt: null, observers: [] };

        function unwatch() {
            state.observers.forEach(function (observer) { observer.disconnect(); });
            state.observers = [];
        }

        function pay() {
            var debt = state.debt;
            if (!debt || !debt.stopped || !hasSize(cy)) return;
            state.debt = null;
            unwatch();
            cy.resize();
            cy.fit(undefined, debt.padding);
            capZoom(cy);
        }

        // A tab is revealed by an inline style or class on some ancestor, and
        // a MutationObserver hears that in the revealing task. The
        // ResizeObserver covers any other way the canvas gains a size.
        function watch() {
            if (state.observers.length) return;
            var container = cy.container();
            if (!container) return;
            if (typeof MutationObserver !== 'undefined') {
                var mutations = new MutationObserver(pay);
                for (var el = container; el && el !== document.body; el = el.parentElement) {
                    mutations.observe(el, { attributes: true, attributeFilter: ['style', 'class'] });
                }
                state.observers.push(mutations);
            }
            if (typeof ResizeObserver !== 'undefined') {
                var resizes = new ResizeObserver(pay);
                resizes.observe(container);
                state.observers.push(resizes);
            }
        }

        // An animated layout frames the graph with an animation of the viewport
        // toward its final fit, so capping once the layout stops would show the
        // whole zoom-in and then snap back. Cap the animation's target instead.
        var animation = cy.animation;
        if (typeof animation === 'function') {
            cy.animation = function (props) {
                var rest = Array.prototype.slice.call(arguments, 1);
                var fit = props && props.fit;
                var container = cy.container();
                if (fit && fit.boundingBox && hasSize(cy) && typeof cy.getFitViewport === 'function') {
                    var view = cy.getFitViewport(fit.boundingBox, fit.padding);
                    if (view && view.zoom > MAX_FIT_ZOOM) {
                        var box = fit.boundingBox;
                        props = Object.assign({}, props, {
                            zoom: MAX_FIT_ZOOM,
                            pan: {
                                x: container.clientWidth / 2 - MAX_FIT_ZOOM * (box.x1 + box.x2) / 2,
                                y: container.clientHeight / 2 - MAX_FIT_ZOOM * (box.y1 + box.y2) / 2
                            }
                        });
                        delete props.fit;
                    }
                }
                return animation.apply(cy, [props].concat(rest));
            };
        }

        window.SkillTree.wrapLayout(cy, 'fit', function (next, options) {
            cy.resize();
            var run = next(options);
            if (!options || options.fit === false) return run;
            if (hasSize(cy)) {
                state.debt = null;
                unwatch();
                run.one('layoutstop', function () { capZoom(cy); });
                return run;
            }
            var debt = state.debt = { padding: options.padding || 0, stopped: false };
            run.one('layoutstop', function () {
                debt.stopped = true;
                pay();
            });
            watch();
            return run;
        });
    }

    function watchCanvases() {
        if (!SkillTree.onCytoReady) return;
        window.SkillTree.canvases.forEach(function (canvas) {
            SkillTree.onCytoReady('#' + canvas.cytoscapeId, track);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchCanvases);
    } else {
        watchCanvases();
    }
})();
