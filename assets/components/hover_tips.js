/**
 * Every hover tooltip in the app: when it opens, where it sits, and when it
 * closes.
 *
 * Three kinds of element have one:
 * - the target of a `ui_kit.Tooltip`. The tooltip's content waits in a
 *   hidden `.tooltip-source` that names its target in `data-tooltip-for`.
 *   Callbacks can rewrite it, and an empty one shows nothing.
 * - an element with `data-hint` (`ui_kit.hint`), which shows that text.
 * - an element with the `overflow-hint` class, which shows its own text only
 *   while an ellipsis cuts it off.
 * The innermost one under the pointer wins. Rows can carry hints by the
 * hundred, and none of them is a component of its own.
 *
 * One tooltip shows at a time:
 * - It opens after TOOLTIP_SHOW_DELAY_MS, only for a pointer that moved onto
 *   its target. A dialog closing, a sidebar sliding in or a list redrawing
 *   under a still pointer opens nothing until the pointer next moves.
 * - It closes the moment the pointer leaves its target or the window.
 * - A press, a key, the wheel or the window losing focus closes it, and none
 *   opens on that target again until the pointer has left it.
 * - The browser reports nothing when a target disappears, or slides or is
 *   covered out from under a still pointer. While a tooltip waits or shows,
 *   it checks what is under the pointer, and closes once its target isn't.
 * - In the desktop window the toolbar is the title bar. The OS takes the
 *   pointer over its drag area and window buttons without telling the page,
 *   so that check also asks the shell where the cursor really is.
 *
 * dbc.Tooltip decided all this itself, and lost the pointer's leave when it
 * came before React had re-rendered the tooltip open: the tooltip then stayed
 * up wherever the pointer went. Each open and close also went through Dash's
 * store. Here a hover never touches Dash.
 */
(function () {
    var CHECK_MS = 100;   // how often a waiting or open tooltip checks its target
    var GAP = 6;          // between the target and the tooltip: Bootstrap's offset
    var EDGE = 8;         // kept clear of the window's edges
    var SLACK = 4;        // how far off its target the shell's cursor may be
    var SIDES = { top: 'top', bottom: 'bottom', left: 'start', right: 'end' };
    var FLIP = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };
    var MODIFIERS = { Shift: 1, Control: 1, Alt: 1, Meta: 1 };

    var tip = null, inner = null, arrow = null;
    var lastX = null, lastY = null;   // where the pointer last moved
    var under = null;                 // what it moved over
    var current = null;               // the target waiting or showing: {target, timer, open}
    var blocked = null;               // closed by a press or key, until the pointer leaves it
    var watch = null, asking = false;

    function showDelay() {
        var el = document.getElementById('tooltip-config');
        var ms = el ? parseInt(el.getAttribute('data-show'), 10) : NaN;
        return ms >= 0 ? ms : 700;
    }

    // The tooltip source for each target id. Dash adds and removes sources as
    // it renders, so this is read fresh, from a collection the browser keeps.
    function sources() {
        var map = new Map();
        var list = document.getElementsByClassName('tooltip-source');
        for (var i = 0; i < list.length; i++) {
            var id = list[i].getAttribute('data-tooltip-for');
            if (id && !map.has(id)) map.set(id, list[i]);
        }
        return map;
    }

    function cutOff(el) {
        return el.scrollWidth > el.clientWidth + 1;
    }

    // The innermost element at or above `node` that has a tooltip.
    function targetOf(node) {
        var map = null;
        for (var el = node; el && el.nodeType === 1; el = el.parentElement) {
            if (el.hasAttribute('data-hint')) return el;
            if (el.classList.contains('overflow-hint') && cutOff(el)) return el;
            if (el.id) {
                map = map || sources();
                if (map.has(el.id)) return el;
            }
        }
        return null;
    }

    function sameTarget(a, b) {
        return !!a && !!b && (a === b || (!!a.id && a.id === b.id));
    }

    // Whether the pointer, where it last moved, is over `target`. A target
    // that is gone, hidden or covered is not.
    function hovered(target) {
        if (lastX === null || !target.isConnected) return false;
        var hit = document.elementFromPoint(lastX, lastY);
        return !!hit && target.contains(hit);
    }

    function ensureTip() {
        if (tip) return;
        tip = document.createElement('div');
        tip.setAttribute('role', 'tooltip');
        arrow = document.createElement('div');
        arrow.className = 'tooltip-arrow';
        inner = document.createElement('div');
        inner.className = 'tooltip-inner';
        tip.append(arrow, inner);
    }

    // Copies the target's tooltip into the tip. Returns its placement, or
    // null when it has nothing to say.
    function fill(target) {
        ensureTip();
        var placement = 'top', classes = 'tooltip fade hover-tip';
        if (target.hasAttribute('data-hint') || target.classList.contains('overflow-hint')) {
            inner.textContent = target.hasAttribute('data-hint')
                ? target.getAttribute('data-hint') : target.textContent.trim();
            classes += ' is-text';
        } else {
            var source = sources().get(target.id);
            if (!source) return null;
            inner.replaceChildren.apply(inner, Array.prototype.map.call(
                source.childNodes, function (n) { return n.cloneNode(true); }));
            placement = source.getAttribute('data-placement') || placement;
            classes += ' ' + (source.getAttribute('data-tooltip-class') || '');
        }
        tip.className = classes.trim();
        return inner.textContent.trim() ? placement : null;
    }

    function clamp(value, low, high) {
        return Math.max(low, Math.min(value, high));
    }

    function fits(side, r, w, h, vw, vh) {
        if (side === 'top') return r.top - GAP - h >= EDGE;
        if (side === 'bottom') return r.bottom + GAP + h <= vh - EDGE;
        if (side === 'left') return r.left - GAP - w >= EDGE;
        return r.right + GAP + w <= vw - EDGE;
    }

    // Beside the target on the side asked for, or the opposite one when only
    // that has room, with the arrow at the target's middle.
    function place(target, placement) {
        var side = SIDES[placement] ? placement : 'top';
        tip.style.left = '0px';   // measured unsqueezed by the window's edge
        tip.style.top = '0px';
        var r = target.getBoundingClientRect();
        var w = tip.offsetWidth, h = tip.offsetHeight;
        var vw = document.documentElement.clientWidth;
        var vh = document.documentElement.clientHeight;
        if (!fits(side, r, w, h, vw, vh) && fits(FLIP[side], r, w, h, vw, vh)) side = FLIP[side];
        tip.classList.add('bs-tooltip-' + SIDES[side]);
        var left, top;
        if (side === 'top' || side === 'bottom') {
            left = clamp(r.left + r.width / 2 - w / 2, EDGE, vw - w - EDGE);
            top = side === 'top' ? r.top - GAP - h : r.bottom + GAP;
            arrow.style.top = '';
            arrow.style.left = clamp(r.left + r.width / 2 - left - arrow.offsetWidth / 2,
                                     4, w - arrow.offsetWidth - 4) + 'px';
        } else {
            top = clamp(r.top + r.height / 2 - h / 2, EDGE, vh - h - EDGE);
            left = side === 'left' ? r.left - GAP - w : r.right + GAP;
            arrow.style.left = '';
            arrow.style.top = clamp(r.top + r.height / 2 - top - arrow.offsetHeight / 2,
                                    4, h - arrow.offsetHeight - 4) + 'px';
        }
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }

    function close() {
        if (!current) return;
        clearTimeout(current.timer);
        current = null;
        clearInterval(watch);
        watch = null;
        if (tip && tip.parentNode) {
            tip.classList.remove('show');
            tip.parentNode.removeChild(tip);
        }
    }

    // Closes the tooltip, and keeps one from opening on that target again
    // until the pointer has left it. `node` is what was pressed, if anything.
    function dismiss(node) {
        var target = (node && targetOf(node)) || (current && current.target) || targetOf(under);
        close();
        if (target) blocked = target;
        if (window.SkillTree && window.SkillTree.tooltip) window.SkillTree.tooltip.hide();
    }

    // The page has lost track of the pointer: decide afresh on its next move.
    function lost() {
        close();
        under = null;
    }

    // Desktop only: resolves true unless the shell puts the cursor off `target`.
    function cursorOn(target) {
        var desktop = window.skillTreeDesktop;
        if (!desktop || !desktop.cursorPoint) return Promise.resolve(true);
        return desktop.cursorPoint().then(function (p) {
            var r = target.getBoundingClientRect();
            if (!p || (!r.width && !r.height)) return true;
            return p.x >= r.left - SLACK && p.x <= r.right + SLACK &&
                   p.y >= r.top - SLACK && p.y <= r.bottom + SLACK;
        }, function () { return true; });
    }

    function open(entry) {
        if (current !== entry || entry.open) return;
        if (!hovered(entry.target)) { lost(); return; }
        var placement = fill(entry.target);
        if (!placement) return;
        document.body.appendChild(tip);
        place(entry.target, placement);
        void tip.offsetWidth;   // so the fade-in starts from hidden
        tip.classList.add('show');
        entry.open = true;
    }

    function check() {
        var entry = current;
        if (!entry) return;
        if (!hovered(entry.target)) { lost(); return; }
        if (asking) return;
        asking = true;
        cursorOn(entry.target).then(function (on) {
            asking = false;
            if (!on && current === entry) lost();
        });
    }

    function arm(target) {
        var entry = { target: target, open: false, timer: null };
        current = entry;
        entry.timer = setTimeout(function () {
            cursorOn(target).then(function (on) {
                if (on) open(entry);
                else if (current === entry) lost();
            });
        }, showDelay());
        watch = setInterval(check, CHECK_MS);
    }

    // A move is the only thing that opens a tooltip. Chromium can repeat a
    // move at the same spot when the page changes; that is not the pointer.
    window.addEventListener('mousemove', function (e) {
        if (e.clientX === lastX && e.clientY === lastY) return;
        lastX = e.clientX;
        lastY = e.clientY;
        if (e.target === under) return;
        under = e.target;
        var target = targetOf(under);
        if (!sameTarget(target, blocked)) blocked = null;
        if (current && current.target === target) return;
        close();
        // No tooltip mid-drag, or on what was just pressed or closed.
        if (target && !blocked && !e.buttons) arm(target);
    }, true);

    // A hover the pointer didn't move into: the page changed under it. It
    // closes a tooltip whose target is no longer under the pointer, and opens
    // none.
    window.addEventListener('mouseover', function (e) {
        if (current && !current.target.contains(e.target)) close();
    }, true);

    window.addEventListener('mouseout', function (e) {
        if (!e.relatedTarget) lost();   // off the window
    }, true);

    window.addEventListener('pointerdown', function (e) { dismiss(e.target); }, true);
    window.addEventListener('keydown', function (e) {
        if (!MODIFIERS[e.key]) dismiss(null);
    }, true);
    window.addEventListener('wheel', function () { dismiss(null); },
                            { capture: true, passive: true });
    window.addEventListener('blur', function () { dismiss(null); });
    window.addEventListener('resize', lost);
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) dismiss(null);
    });
    // A scroll that carries the target away, like a list scrolled by code.
    document.addEventListener('scroll', function (e) {
        var box = e.target;
        if (current && (box === document || (box.contains && box.contains(current.target)))) lost();
    }, true);
})();
