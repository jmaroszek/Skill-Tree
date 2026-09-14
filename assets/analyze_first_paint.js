/**
 * Size prewarmed Analyze charts before their first visible paint.
 *
 * Analyze renders in the background so it is ready when the user opens it.
 * Its tab is display:none during that render, though, so Plotly falls back to
 * a 700 px SVG. `responsive=true` corrects the width after the tab opens, but
 * without a gate the fallback SVG gets one visible frame and then jumps.
 *
 * The tab's inline display style is owned by toggle_tab_content. A
 * MutationObserver receives that style change before the browser paints it.
 * We hide only the graph drawings (their fixed-height wrappers still hold the
 * page layout), resize every Plotly root against the now-visible pane, and
 * reveal the drawings on the following animation frame.
 *
 * The child-list path covers the less common case where the user reaches
 * Analyze before the background render finishes: newly mounted graphs are
 * held until Plotly has created their SVGs and they can be sized. A bounded
 * frame wait means a broken or missing Plotly root cannot hide a graph
 * forever.
 */
(function () {
    'use strict';

    var PANE_ID = 'analyze-tab-content';
    var SIZING_CLASS = 'analyze-is-sizing';
    var MAX_READY_FRAMES = 120;
    var generation = 0;

    function paneIsOpen(pane) {
        return Boolean(pane && pane.style.display !== 'none' && pane.clientWidth);
    }

    function graphWrappers(pane) {
        return Array.prototype.slice.call(pane.querySelectorAll('.dash-graph'));
    }

    function plotRoots(pane) {
        return Array.prototype.slice.call(pane.querySelectorAll('.js-plotly-plot'));
    }

    function plotsAreReady(wrappers, plots) {
        return Boolean(
            wrappers.length
            && wrappers.length === plots.length
            && plots.every(function (plot) {
                return Boolean(plot.querySelector('.main-svg'));
            })
            && window.Plotly
            && window.Plotly.Plots
            && typeof window.Plotly.Plots.resize === 'function'
        );
    }

    function revealOnNextFrame(pane, token) {
        requestAnimationFrame(function () {
            if (token !== generation) return;
            pane.classList.remove(SIZING_CLASS);
        });
    }

    function resizeAndReveal(pane, token, readyFrames) {
        if (token !== generation) return;
        if (!paneIsOpen(pane)) {
            pane.classList.remove(SIZING_CLASS);
            return;
        }

        var wrappers = graphWrappers(pane);
        var plots = plotRoots(pane);

        // No Graph components means this render contains only empty-state
        // cards. There is nothing to size or hold back.
        if (!wrappers.length) {
            pane.classList.remove(SIZING_CLASS);
            return;
        }

        if (!plotsAreReady(wrappers, plots) && readyFrames < MAX_READY_FRAMES) {
            requestAnimationFrame(function () {
                resizeAndReveal(pane, token, readyFrames + 1);
            });
            return;
        }

        var jobs = [];
        if (window.Plotly && window.Plotly.Plots
                && typeof window.Plotly.Plots.resize === 'function') {
            plots.forEach(function (plot) {
                try {
                    jobs.push(window.Plotly.Plots.resize(plot));
                } catch (_) {
                    // Reveal below rather than strand a chart because one
                    // Plotly root disappeared during a Dash reconciliation.
                }
            });
        }

        Promise.all(jobs.map(function (job) { return Promise.resolve(job); }))
            .then(function () { revealOnNextFrame(pane, token); })
            .catch(function () { revealOnNextFrame(pane, token); });
    }

    function beginSizing(pane) {
        if (!paneIsOpen(pane)) return;

        var wrappers = graphWrappers(pane);
        if (!wrappers.length) return;

        pane.classList.add(SIZING_CLASS);
        var token = ++generation;
        requestAnimationFrame(function () {
            resizeAndReveal(pane, token, 0);
        });
    }

    function addedGraph(mutation) {
        if (mutation.type !== 'childList') return false;
        return Array.prototype.some.call(mutation.addedNodes, function (node) {
            return node.nodeType === 1 && (
                node.matches('.dash-graph')
                || Boolean(node.querySelector('.dash-graph'))
            );
        });
    }

    function watchPane(pane) {
        var observer = new MutationObserver(function (mutations) {
            if (!paneIsOpen(pane)) {
                generation += 1;
                pane.classList.remove(SIZING_CLASS);
                return;
            }

            var revealed = mutations.some(function (mutation) {
                return mutation.type === 'attributes' && mutation.target === pane;
            });
            if (revealed || mutations.some(addedGraph)) beginSizing(pane);
        });

        observer.observe(pane, {
            attributes: true,
            attributeFilter: ['style'],
            childList: true,
            subtree: true,
        });

        // Covers a script loaded after the pane became visible.
        beginSizing(pane);
    }

    function watch() {
        var pane = document.getElementById(PANE_ID);
        if (pane) {
            watchPane(pane);
            return;
        }

        // Dash mounts its layout after assets execute. Attach to the pane in
        // the same mutation turn that inserts it, before it can be revealed.
        var waiter = new MutationObserver(function () {
            var mountedPane = document.getElementById(PANE_ID);
            if (!mountedPane) return;
            waiter.disconnect();
            watchPane(mountedPane);
        });
        waiter.observe(document.documentElement, {childList: true, subtree: true});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watch, {once: true});
    } else {
        watch();
    }
})();
