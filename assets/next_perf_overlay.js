/**
 * Hide the Home tab's "737 nodes · 1126 edges · 34ms" caption when it would
 * sit on top of the page.
 *
 * The caption is pinned to the bottom-right corner of the viewport. On a tall
 * window that corner is empty. In a short or narrow one the list scrolls
 * beneath it and the caption lands on a row's bars and dots. It is a nicety,
 * so it gives way: whenever visible content (text, bars, icons) falls under
 * it, it is hidden, and it comes back once the corner is clear again.
 *
 * The check runs when the page scrolls, the window resizes, or the content
 * changes, at most once a frame.
 */
(function () {
    'use strict';

    var CAPTION_ID = 'next-perf-stats';
    var GAP = 8;   // How close content may come before the caption leaves.
    var frame = null;

    function intersects(a, b) {
        return a.left < b.right + GAP && a.right + GAP > b.left
            && a.top < b.bottom + GAP && a.bottom + GAP > b.top;
    }

    // Elements that are drawn without text of their own showing them: bars,
    // dots and icons. Text is checked by its own rectangles, which are tighter
    // than the box of the element holding it.
    function paints(el) {
        if (el.children.length) return false;
        var tag = el.tagName.toLowerCase();
        if (tag === 'svg' || tag === 'img' || tag === 'canvas') return true;
        var color = window.getComputedStyle(el).backgroundColor;
        return Boolean(color) && color !== 'transparent' && color !== 'rgba(0, 0, 0, 0)';
    }

    // Whether anything in `root` is drawn where the caption is.
    function covers(root, caption) {
        var box = caption.getBoundingClientRect();
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        var range = document.createRange();
        for (var node = walker.nextNode(); node; node = walker.nextNode()) {
            if (node.nodeType === Node.TEXT_NODE) {
                if (!node.nodeValue.trim()) continue;
                range.selectNodeContents(node);
                var lines = range.getClientRects();
                for (var i = 0; i < lines.length; i++) {
                    if (lines[i].width && intersects(box, lines[i])) return true;
                }
            } else if (paints(node)) {
                var rect = node.getBoundingClientRect();
                if (rect.width && rect.height && intersects(box, rect)) return true;
            }
        }
        return false;
    }

    function update() {
        frame = null;
        var caption = document.getElementById(CAPTION_ID);
        if (!caption) return;
        var tab = caption.parentElement;
        watch(tab);
        if (!caption.offsetParent) return;   // Home is hidden.
        var scroller = tab.firstElementChild;
        watch(scroller);
        if (covers(scroller, caption)) caption.setAttribute('data-crowded', '');
        else caption.removeAttribute('data-crowded');
    }

    function schedule() {
        if (frame === null) frame = window.requestAnimationFrame(update);
    }

    // Dash builds the layout after load and may rebuild the scrolling column,
    // so each element is looked up when needed and watched once.
    var watched = new WeakSet();
    function watch(el) {
        if (watched.has(el)) return;
        watched.add(el);
        el.addEventListener('scroll', schedule, {passive: true});
        // The tab's style is how Home is shown and hidden; its subtree is
        // the list and the Description beside it.
        var options = {childList: true, subtree: true, characterData: true};
        if (el.id === 'next-tab-content') {
            options.attributes = true;
            options.attributeFilter = ['style'];
        }
        new MutationObserver(schedule).observe(el, options);
    }

    window.addEventListener('resize', schedule);
    // The caption is created by Dash after load; look for it until it is there.
    var arrival = new MutationObserver(function () {
        if (!document.getElementById(CAPTION_ID)) return;
        arrival.disconnect();
        schedule();
    });
    arrival.observe(document.documentElement, {childList: true, subtree: true});
})();
