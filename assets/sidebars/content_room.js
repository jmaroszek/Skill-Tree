/**
 * The tab content makes room for an open sidebar instead of sitting under it.
 *
 * The content slides with a transform, on the compositor like the sidebar, so
 * a busy main thread can't make it stutter. Its box changes once: at the end of
 * an opening, where the sidebar has arrived, and at the start of a closing,
 * before it has left. A transform stays only for the slide, because a resting
 * one misplaces every position: fixed dropdown inside it.
 *
 * A graph never moves on screen. The page slides, and the graph's canvas slides
 * the other way inside its clipped container, so the two cancel. When the box
 * changes, the pan cancels that too. Nodes has nothing else in its pane, so it
 * doesn't slide at all. A graph can end up off centre, which is better than a
 * jump, and cy.width() stays the visible width for Locate, Focus and Fit.
 *
 * A chart redraws with the box change. Left to itself Plotly waits 100 ms and
 * more, which shows as a second jump after the first.
 *
 * Below ONE_PANEL_MIN the sidebars cover, as there is no room to give, except
 * the Events list, which is half of its tab. Below BOTH_PANELS_MIN a left panel
 * still pushes, and Filters covers beside it.
 */
window.SkillTree = window.SkillTree || {};

(function () {
    // NOTE: must match the 0.3s transition on .left-sidebar in theme.css.
    var SLIDE_MS = 300;
    var ONE_PANEL_MIN = 1250;
    var BOTH_PANELS_MIN = 1600;
    var NODES_PANE = 'canvas-tab-content';
    var EVENTS_PANE = 'events-tab-content';
    var EVENTS_SIDEBAR = 'events-sidebar-container';

    // What room the stage should give. `left` is the open left sidebar's id or
    // null: 'all' gives room on every tab, 'events' only on the Events tab.
    function roomFor(left, rightOpen, width) {
        var roomy = width >= ONE_PANEL_MIN;
        return {
            left: left && roomy ? 'all' : (left === EVENTS_SIDEBAR ? 'events' : ''),
            right: Boolean(rightOpen && roomy && (!left || width >= BOTH_PANELS_MIN))
        };
    }

    window.SkillTree.contentRoom = { roomFor: roomFor };

    if (typeof document === 'undefined') return;

    var stage = null;
    var panes = [];
    // What the stage says now, and where each side is heading.
    var committed = { left: '', right: false };
    var target = { left: '', right: false };
    var slide = null;
    var rightWait = null;
    // Each canvas's pane left when it last settled, so a hidden tab can catch up.
    var settledLeft = {};

    function reducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function wanted() {
        var left = stage.querySelector('.left-sidebar.is-open');
        var right = stage.querySelector('.right-sidebar.is-open');
        return roomFor(left ? left.id : null, Boolean(right), window.innerWidth);
    }

    function hasLeftRoom(value, pane) {
        return value === 'all' || (value === 'events' && pane.id === EVENTS_PANE);
    }

    function settleCanvas(canvas) {
        var el = document.getElementById(canvas.cytoscapeId);
        if (!el || !el.offsetParent) return;
        var cy = window.SkillTree.getCy(el);
        var pane = el.closest('.stage-pane');
        if (!cy || !pane) return;

        var left = pane.offsetLeft;
        var seenLeft = settledLeft[canvas.key];
        settledLeft[canvas.key] = left;
        if (el.clientWidth === cy.width() && left === seenLeft) return;

        cy.resize();
        // A tab's first reveal has nothing to hold: its layout frames it.
        if (seenLeft === undefined || seenLeft === left) return;
        window.SkillTree.adjustCanvasViewport(canvas.cytoscapeId, function () {
            cy.panBy({ x: seenLeft - left, y: 0 });
        });
    }

    function settlePlot(plot) {
        var layout = plot.layout;
        var drawn = plot._fullLayout;
        if (!plot.offsetParent || !layout || !drawn || (layout.width && layout.height)) return;
        if (Math.abs(drawn.width - plot.clientWidth) <= 1) return;
        window.Plotly.relayout(plot, { autosize: true });
    }

    function visiblePlots() {
        var plots = [];
        if (!window.Plotly) return plots;
        panes.forEach(function (pane) {
            if (!pane.offsetParent) return;
            Array.prototype.push.apply(plots, pane.querySelectorAll('.js-plotly-plot'));
        });
        return plots.filter(function (plot) { return plot.offsetParent; });
    }

    // At the start of a closing the slide's first frame waits for this task. One
    // chart is cheap enough to draw before it. Several wait for the frame after,
    // when the slide is on the compositor and a busy main thread can't hold it.
    function settle(slideStarting) {
        (window.SkillTree.canvases || []).forEach(settleCanvas);
        var plots = visiblePlots();
        if (!slideStarting || plots.length <= 1) {
            plots.forEach(settlePlot);
            return;
        }
        window.requestAnimationFrame(function () {
            window.requestAnimationFrame(function () { visiblePlots().forEach(settlePlot); });
        });
    }

    function commit(left, right, slideStarting) {
        committed = { left: left, right: right };
        if (left) stage.dataset.roomLeft = left;
        else delete stage.dataset.roomLeft;
        if (right) stage.dataset.roomRight = '1';
        else delete stage.dataset.roomRight;
        settle(slideStarting);
    }

    // Runs when the sidebar's own transition ends: one document timeline, and
    // no frame between the two.
    function afterSlide(run) {
        var wait = new Animation(new KeyframeEffect(stage, [], SLIDE_MS), document.timeline);
        wait.onfinish = run;
        wait.play();
        return wait;
    }

    function play(element, from, to) {
        return element.animate(
            [{ transform: 'translateX(' + from + 'px)' }, { transform: 'translateX(' + to + 'px)' }],
            { duration: SLIDE_MS, easing: 'ease', fill: 'both' });
    }

    // The canvas's box inside its clipped container, with what sits on it.
    function heldCanvases(pane) {
        var held = [];
        (window.SkillTree.canvases || []).forEach(function (canvas) {
            var container = document.getElementById(canvas.containerId);
            if (container && pane.contains(container) && container.firstElementChild) {
                held.push(container.firstElementChild);
            }
        });
        return held;
    }

    function moveLeft(next) {
        if (next === target.left) return;
        var previous = target.left;
        target.left = next;
        // Turned around mid-slide. The content reverses from where it is, and
        // the end of the slide commits whatever the target is by then.
        if (slide) {
            slide.forEach(function (animation) { animation.reverse(); });
            return;
        }
        var opening = !previous && next;
        var closing = previous && !next;
        if (!opening && !closing) {
            commit(next, committed.right);
            return;
        }
        var width = stage.querySelector('.left-sidebar').offsetWidth;
        var from = opening ? 0 : width;
        var to = opening ? width : 0;
        var moving = [];
        // Hidden panes slide too: the Events tab opens its sidebar on arrival,
        // and whichever pane is showing by then is already in step.
        panes.forEach(function (pane) {
            if (pane.id === NODES_PANE || !hasLeftRoom(previous || next, pane)) return;
            moving.push(play(pane, from, to));
            heldCanvases(pane).forEach(function (held) {
                moving.push(play(held, -from, -to));
            });
        });
        moving.push(afterSlide(function () {
            var finished = slide;
            slide = null;
            commit(target.left, committed.right);
            finished.forEach(function (animation) { animation.cancel(); });
        }));
        slide = moving;
        if (closing) commit('', committed.right, true);
    }

    function moveRight(next) {
        if (next === target.right) return;
        target.right = next;
        if (rightWait) rightWait.cancel();
        rightWait = null;
        if (!next) {
            commit(committed.left, false, true);
            return;
        }
        rightWait = afterSlide(function () {
            rightWait = null;
            commit(committed.left, true);
        });
    }

    function update() {
        var next = wanted();
        if (!reducedMotion()) {
            moveLeft(next.left);
            moveRight(next.right);
            return;
        }
        target = next;
        if (next.left !== committed.left || next.right !== committed.right) {
            commit(next.left, next.right);
        }
    }

    function mount() {
        stage = document.getElementById('tab-stage');
        if (!stage) return false;
        panes = Array.prototype.slice.call(stage.querySelectorAll(':scope > .stage-pane'));

        target = wanted();
        commit(target.left, target.right);

        // Same task as the class write, so the first frame has both.
        var sidebars = new MutationObserver(update);
        Array.prototype.forEach.call(stage.querySelectorAll('.left-sidebar, .right-sidebar'), function (el) {
            sidebars.observe(el, { attributes: true, attributeFilter: ['class'] });
        });
        // A tab revealed after a sidebar moved while it was hidden.
        var reveals = new MutationObserver(function () {
            window.requestAnimationFrame(function () { settle(false); });
        });
        panes.forEach(function (pane) {
            reveals.observe(pane, { attributes: true, attributeFilter: ['style'] });
        });
        window.addEventListener('resize', update);
        return true;
    }

    function whenMounted() {
        if (mount()) return;
        var watcher = new MutationObserver(function () {
            if (mount()) watcher.disconnect();
        });
        watcher.observe(document.body, { childList: true, subtree: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', whenMounted);
    else whenMounted();
})();
