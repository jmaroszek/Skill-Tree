/**
 * Behaviour for the Analyze tab's Ratings by Context grid: its hover
 * tooltip, the Expand all / Collapse all buttons in its corner, and the
 * toggle for the dashed guide at the mean of all nodes. The Goals rows'
 * bars share the tooltip, and so do the History charts: their HTML marks
 * carry data-tip, and the two Plotly ones (the estimation scatter and box
 * plot) pass each point's text as customdata, shown here on plotly_hover.
 *
 * The grid holds about 1,500 cells, so one delegated listener moves a single
 * floating box between them rather than giving each cell its own tooltip.
 * A cell's text is in data-tip, as three lines: the area, the count at that
 * rating, and the rating's definition. A mean tick, the work-left cell and
 * a Goal's bar use the same first-line-bold layout.
 *
 * The guide toggle is a class on <html>, so it applies before the grid
 * renders and survives every re-render. It starts off on every load and
 * is not remembered: the guide is for a quick comparison, not a standing
 * view.
 */
(function () {
    var tip = null;
    var root = document.documentElement;

    function syncPressed(btn) {
        btn.setAttribute('aria-pressed',
                         String(root.classList.contains('rd-guides-on')));
    }

    function ensureTip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.className = 'rd-tip';
        tip.setAttribute('role', 'tooltip');
        tip.hidden = true;
        document.body.appendChild(tip);
        return tip;
    }

    function position(x, y) {
        var offset = 14;
        var w = tip.offsetWidth, h = tip.offsetHeight;
        var left = x + offset + w > window.innerWidth ? x - w - offset : x + offset;
        var top = y + offset + h > window.innerHeight ? y - h - offset : y + offset;
        tip.style.left = Math.max(8, left) + 'px';
        tip.style.top = Math.max(8, top) + 'px';
    }

    // The first line is the area, in bold. A rating cell's or mean tick's
    // third line is a definition or a comparison, set soft. The Work left
    // and Goals tooltips are data on every line.
    function fill(text, softThird) {
        var lines = text.split('\n');
        tip.replaceChildren.apply(tip, lines.filter(Boolean).map(function (line, i) {
            var d = document.createElement('div');
            if (i === 0) d.className = 'rd-tip-head';
            else if (i === 2 && softThird) d.className = 'rd-tip-def';
            d.textContent = line;
            return d;
        }));
    }

    var current = null;
    var plotShown = false;   // a Plotly point's tooltip is up
    document.addEventListener('pointermove', function (e) {
        var cell = e.target.closest && e.target.closest(
            '.rating-dist .rd-cell, .rating-dist .rd-mean, .rating-dist .rd-work, '
            + '.goal-progress .gp-bar, .hist-chart [data-tip]');
        if (!cell) {
            if (current) { tip.hidden = true; current = null; }
            if (plotShown) position(e.clientX, e.clientY);
            return;
        }
        ensureTip();
        if (cell !== current) {
            current = cell;
            fill(cell.getAttribute('data-tip') || '',
                 cell.matches('.rd-cell, .rd-mean'));
            tip.hidden = false;
        }
        position(e.clientX, e.clientY);
    });
    // The contexts fold with native <details>, so opening them all is a
    // property flip. A server callback would redraw the grid for nothing.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest(
            '#rating-dist-expand-all, #rating-dist-collapse-all, #rating-dist-guide-toggle');
        if (!btn) return;
        if (btn.id === 'rating-dist-guide-toggle') {
            root.classList.toggle('rd-guides-on');
            syncPressed(btn);
            return;
        }
        var open = btn.id === 'rating-dist-expand-all';
        document.querySelectorAll('.rating-dist details.rd-group')
            .forEach(function (d) { d.open = open; });
    });

    // The button renders after this script runs, and Dash can replace it, so
    // its pressed state is filled in when it is first reached.
    ['pointerover', 'focusin'].forEach(function (type) {
        document.addEventListener(type, function (e) {
            var btn = e.target.closest && e.target.closest('#rating-dist-guide-toggle');
            if (btn) syncPressed(btn);
        });
    });

    // A tab switch or scroll can pull the grid out from under a still cursor.
    document.addEventListener('scroll', function () {
        if (tip && (current || plotShown)) {
            tip.hidden = true; current = null; plotShown = false;
        }
    }, true);

    // Plotly charts. Their traces use hoverinfo 'none', which draws no box
    // but still fires these events. The box is placed by the pointermove
    // handler above once it is up, so it follows the cursor like the rest.
    function bindPlot(gd) {
        gd.on('plotly_hover', function (d) {
            var pt = d.points && d.points[0];
            var text = pt && (pt.customdata || pt.text || pt.hovertext);
            if (!text) return;
            ensureTip();
            fill(String(text), false);
            tip.hidden = false;
            current = null;
            plotShown = true;
            position(d.event.clientX, d.event.clientY);
        });
        gd.on('plotly_unhover', function () {
            if (tip) tip.hidden = true;
            plotShown = false;
        });
    }

    // A scatter's legend is HTML, so Plotly's own click-to-hide does not
    // apply. Each entry names its trace in data-trace; a click flips that
    // trace between shown and legend-only, as Plotly's legend does. The
    // graph is the legend's sibling in the card. A new figure redraws both,
    // so the two never disagree.
    function toggleTrace(item) {
        var card = item.closest('.gp-legend').parentElement;
        var gd = card && card.querySelector('.js-plotly-plot');
        if (!gd || !window.Plotly || !gd.data) return;
        var name = item.getAttribute('data-trace');
        var shown = item.getAttribute('aria-pressed') !== 'false';
        var idx = [];
        gd.data.forEach(function (t, i) { if (t.name === name) idx.push(i); });
        if (!idx.length) return;
        window.Plotly.restyle(gd, {visible: shown ? 'legendonly' : true}, idx);
        item.setAttribute('aria-pressed', String(!shown));
    }
    document.addEventListener('click', function (e) {
        var item = e.target.closest && e.target.closest('.gp-legend-item[data-trace]');
        if (item) toggleTrace(item);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var item = e.target.closest && e.target.closest('.gp-legend-item[data-trace]');
        if (!item) return;
        e.preventDefault();
        toggleTrace(item);
    });

    // Dash draws a graph after this script runs and can replace it, so each
    // new one is found by watching the Analyze tab. A plot is bound once.
    var bindQueued = false;
    function bindPlots() {
        bindQueued = false;
        document.querySelectorAll('.analyze-plot .js-plotly-plot').forEach(function (gd) {
            if (gd._stTip || typeof gd.on !== 'function') return;
            gd._stTip = true;
            bindPlot(gd);
        });
    }
    function watchAnalyze(pane) {
        new MutationObserver(function () {
            if (bindQueued) return;
            bindQueued = true;
            requestAnimationFrame(bindPlots);
        }).observe(pane, {childList: true, subtree: true});
        bindPlots();
    }
    function waitForAnalyze() {
        var pane = document.getElementById('analyze-tab-content');
        if (pane) { watchAnalyze(pane); return; }
        var waiter = new MutationObserver(function () {
            var mounted = document.getElementById('analyze-tab-content');
            if (!mounted) return;
            waiter.disconnect();
            watchAnalyze(mounted);
        });
        waiter.observe(document.documentElement, {childList: true, subtree: true});
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', waitForAnalyze, {once: true});
    } else {
        waitForAnalyze();
    }
})();
