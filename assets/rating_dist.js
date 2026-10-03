/**
 * Behaviour for the Analyze tab's Ratings by Context grid: its hover
 * tooltip, the Expand all / Collapse all buttons in its corner, and the
 * toggle for the dashed guide at the mean of all nodes.
 *
 * The grid holds about 1,500 cells, so one delegated listener moves a single
 * floating box between them rather than giving each cell its own tooltip.
 * A cell's text is in data-tip, as three lines: the area, the count at that
 * rating, and the rating's definition. A mean tick and the work-left cell
 * use the same first-line-bold layout.
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

    function fill(text) {
        var lines = text.split('\n');
        var classes = ['rd-tip-head', '', 'rd-tip-def'];
        tip.replaceChildren.apply(tip, lines.filter(Boolean).map(function (line, i) {
            var d = document.createElement('div');
            if (classes[i]) d.className = classes[i];
            d.textContent = line;
            return d;
        }));
    }

    var current = null;
    document.addEventListener('pointermove', function (e) {
        var cell = e.target.closest && e.target.closest('.rating-dist .rd-cell, .rating-dist .rd-mean, .rating-dist .rd-work');
        if (!cell) {
            if (current) { tip.hidden = true; current = null; }
            return;
        }
        ensureTip();
        if (cell !== current) {
            current = cell;
            fill(cell.getAttribute('data-tip') || '');
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
        if (tip && current) { tip.hidden = true; current = null; }
    }, true);
})();
