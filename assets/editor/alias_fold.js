/**
 * The editor's alias rows open and close with a slide that a busy page can't
 * stall.
 *
 * Bootstrap's collapse tweens `height`, which is laid out on the main thread
 * every frame. A node load starts that tween in the same answer that fills the
 * whole form, and a dozen follow-on callbacks run during it, so the slide
 * showed in a handful of frames. On a clear the rows were also redrawn blank,
 * and with several aliases the box dropped to one row before it started.
 *
 * Instead the box changes once, at once (theme.css turns the tween off), and
 * transforms play the motion on the compositor:
 *   - what follows the rows slides from where it was to where it now is;
 *   - opening, the rows are revealed from the top: the box's clip moves down
 *     while the rows inside stay put;
 *   - closing, a copy of the rows as they last looked is covered the same way
 *     in reverse. The form has already reset them, so the copy is what shows.
 * Like content_room.js, a transform stays only for the slide.
 */
window.SkillTree = window.SkillTree || {};

(function () {
    // NOTE: matches Bootstrap's .collapsing transition (0.35s ease).
    var SLIDE_MS = 350;
    var EASING = 'ease';
    var FOLD_ID = 'collapse-aliases';
    var GHOST_HOST_ID = 'aliases-fold-ghost';
    var SCROLLER_ID = 'sidebar-editor-container';

    // What a change of the box's height plays. `follow` is how far what comes
    // after starts from where it now is. `reveal` uncovers the new rows, and
    // `cover` hides the old ones' copy; each is the clip's travel.
    function plan(fromHeight, toHeight) {
        var change = toHeight - fromHeight;
        if (!change) return null;
        return {
            follow: -change,
            reveal: change > 0 ? change : 0,
            cover: toHeight === 0 ? fromHeight : 0
        };
    }

    window.SkillTree.aliasFold = { plan: plan };

    if (typeof document === 'undefined' || typeof MutationObserver === 'undefined') return;

    var fold = null;
    var lastHeight = 0;
    var lastLook = null;
    var running = [];
    var ghost = null;

    function reducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function slide(element, from, to) {
        return element.animate(
            [{ transform: 'translateY(' + from + 'px)' }, { transform: 'translateY(' + to + 'px)' }],
            { duration: SLIDE_MS, easing: EASING });
    }

    // A clip box moving by `from`..`to`, with what is inside held still.
    function clipSlide(box, inner, from, to) {
        // overflow is its own animation: one that isn't a transform would
        // keep the transform off the compositor.
        running.push(box.animate([{ overflow: 'clip' }, { overflow: 'clip' }], { duration: SLIDE_MS }));
        running.push(slide(box, from, to));
        if (inner) running.push(slide(inner, -from, -to));
    }

    // Everything laid out after the rows, up to the editor's scroll box. A
    // `display: contents` wrapper has no box to move, so its children move.
    // The sticky Save bar stays where it is.
    function following(start) {
        var scroller = document.getElementById(SCROLLER_ID);
        var out = [];
        function add(element) {
            var style = window.getComputedStyle(element);
            if (style.display === 'none' || style.position === 'sticky' || style.position === 'fixed') return;
            if (style.display === 'contents') {
                Array.prototype.forEach.call(element.children, add);
                return;
            }
            out.push(element);
        }
        for (var at = start; at && at !== scroller; at = at.parentElement) {
            for (var next = at.nextElementSibling; next; next = next.nextElementSibling) add(next);
        }
        return out;
    }

    // The rows as they look now, with what was typed, and nothing a lookup
    // or a click could reach.
    function snapshot() {
        var inner = fold.firstElementChild;
        if (!inner) return null;
        var copy = inner.cloneNode(true);
        var from = inner.querySelectorAll('input');
        var to = copy.querySelectorAll('input');
        for (var i = 0; i < to.length && i < from.length; i++) to[i].value = from[i].value;
        copy.removeAttribute('id');
        Array.prototype.forEach.call(copy.querySelectorAll('[id]'), function (el) { el.removeAttribute('id'); });
        return copy;
    }

    function stop() {
        running.forEach(function (animation) { animation.cancel(); });
        running = [];
        if (ghost) {
            ghost.remove();
            ghost = null;
        }
    }

    function play(step) {
        stop();
        following(document.getElementById(GHOST_HOST_ID) || fold).forEach(function (element) {
            running.push(slide(element, step.follow, 0));
        });
        if (step.reveal) clipSlide(fold, fold.firstElementChild, -step.reveal, 0);
        var host = document.getElementById(GHOST_HOST_ID);
        if (step.cover && lastLook && host) {
            ghost = document.createElement('div');
            ghost.className = 'alias-fold-ghost';
            ghost.setAttribute('aria-hidden', 'true');
            ghost.inert = true;
            ghost.style.height = step.cover + 'px';
            ghost.appendChild(lastLook);
            host.appendChild(ghost);
            clipSlide(ghost, lastLook, 0, -step.cover);
            lastLook = null;
        }
        var last = running[running.length - 1];
        if (last) {
            last.onfinish = function () {
                if (running[running.length - 1] === last) stop();
            };
        }
    }

    // Runs after each change Dash or Bootstrap makes to the rows, before the
    // frame paints, so the slide's first frame is the one the change shows.
    function check() {
        var height = fold.offsetHeight;
        var step = plan(lastHeight, height);
        lastHeight = height;
        // A hidden editor has nothing to show.
        var scroller = document.getElementById(SCROLLER_ID);
        if (step && scroller && scroller.getClientRects().length && !reducedMotion()) play(step);
        if (height) lastLook = snapshot();
    }

    function attach() {
        fold = document.getElementById(FOLD_ID);
        if (!fold) return false;
        lastHeight = fold.offsetHeight;
        if (lastHeight) lastLook = snapshot();
        new MutationObserver(check).observe(fold, {
            attributes: true, childList: true, subtree: true, characterData: true
        });
        // Typing changes an input's value without changing the page.
        fold.addEventListener('input', function () { if (fold.offsetHeight) lastLook = snapshot(); });
        return true;
    }

    // The editor is in the first layout, but Dash mounts it after this runs.
    if (!attach()) {
        var wait = new MutationObserver(function () {
            if (attach()) wait.disconnect();
        });
        wait.observe(document.documentElement, { childList: true, subtree: true });
    }
})();
