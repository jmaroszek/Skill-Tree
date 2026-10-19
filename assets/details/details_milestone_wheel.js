/**
 * Mouse wheel over the Details Milestones strip scrolls it sideways, eased.
 * The strip sits inside the Subtasks section, which scrolls vertically, so one
 * wheel event must go to exactly one of them. Each event is decided on its own,
 * in one synchronous step: while the strip can still move in the wheel's
 * direction it takes the event (preventDefault stops the section scrolling);
 * at either end, or when nothing overflows, the event is left alone and the
 * section scrolls as usual. Horizontal gestures (trackpad, shift+wheel) already
 * scroll the strip natively and are left alone.
 *
 * Wheel ticks move a target, and a frame loop eases scrollLeft toward it. The
 * easing is by elapsed time, so it feels the same at any refresh rate.
 */
(function () {
    var SETTLE_MS = 70;   // time constant of the ease: smaller is snappier
    var target = 0;
    var animating = false;
    var lastFrame = 0;

    function step(now) {
        var strip = document.getElementById('details-milestones-tiles');
        if (!strip) { animating = false; return; }
        var dt = Math.min(now - lastFrame, 50);
        lastFrame = now;
        var gap = target - strip.scrollLeft;
        if (Math.abs(gap) < 0.5) {
            strip.scrollLeft = target;
            animating = false;
            return;
        }
        strip.scrollLeft += gap * (1 - Math.exp(-dt / SETTLE_MS));
        requestAnimationFrame(step);
    }

    document.addEventListener('wheel', function (event) {
        if (event.ctrlKey || event.shiftKey || event.defaultPrevented) return;
        if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
        var strip = event.target.closest && event.target.closest('#details-milestones-tiles');
        if (!strip) return;
        var max = strip.scrollWidth - strip.clientWidth;
        if (max <= 0) return;
        // Wheel ticks arrive in lines on some devices; a line is ~16px.
        var delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
        // Idle: start from where the strip is, in case it moved by other means.
        var from = animating ? target : strip.scrollLeft;
        var next = Math.min(max, Math.max(0, from + delta));
        if (next === from) return;
        target = next;
        event.preventDefault();
        if (!animating) {
            animating = true;
            lastFrame = performance.now();
            requestAnimationFrame(step);
        }
    // Non-passive: preventDefault is needed to keep the section from scrolling.
    }, {passive: false});
})();
