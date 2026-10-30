/**
 * How every tooltip behaves, and the one tooltip for small marks.
 *
 * A tooltip shows after a delay and closes the moment the pointer leaves.
 * The delay lives in CSS (custom.css, Tooltips): a tooltip mounts at once and
 * fades in after --st-tooltip-show-delay, so dbc tooltips and the shared tip
 * below wait the same.
 *
 * - Only a pointer that moves opens one. When a dialog closes, a sidebar
 *   slides in or a list redraws under a still pointer, the browser reports a
 *   hover on whatever is now beneath it. That hover is held back until the
 *   pointer next moves, so a tooltip never opens on its own.
 * - A press closes: pressing an element closes its tooltip, and none opens
 *   again until the pointer has left it, so a click never leaves one up.
 * - The shared tip: an element with `data-hint` shows that text, and one with
 *   the `overflow-hint` class shows its own text only while it is cut off
 *   with an ellipsis. Rows can carry these by the hundred without a Dash
 *   tooltip component each, and they replace native `title` tooltips, which
 *   keep Chromium's own delay, look and click behaviour.
 */
(function () {
    var pressed = null;
    var tip = null, tipInner = null, tipArrow = null, tipTarget = null;
    var lastX = null, lastY = null;   // where the mouse last moved
    var held = null;                  // a hover the mouse didn't move into

    function readDelay() {
        var el = document.getElementById('tooltip-config');
        if (!el) return false;
        var show = parseInt(el.getAttribute('data-show'), 10);
        if (!isNaN(show) && show >= 0) {
            document.documentElement.style.setProperty(
                '--st-tooltip-show-delay', show + 'ms');
            return true;
        }
        return false;
    }

    function hintText(el) {
        if (el.hasAttribute('data-hint')) return el.getAttribute('data-hint');
        // overflow-hint: only a name the ellipsis cut short has more to say.
        if (el.scrollWidth > el.clientWidth + 1) return el.textContent.trim();
        return '';
    }

    function ensureTip() {
        if (tip) return;
        tip = document.createElement('div');
        tip.className = 'tooltip fade bs-tooltip-top hover-tip';
        tip.setAttribute('role', 'tooltip');
        tipArrow = document.createElement('div');
        tipArrow.className = 'tooltip-arrow';
        tipInner = document.createElement('div');
        tipInner.className = 'tooltip-inner';
        tip.append(tipArrow, tipInner);
    }

    function showTip(el, text) {
        ensureTip();
        tipTarget = el;
        tipInner.textContent = text;
        tip.classList.remove('show', 'bs-tooltip-bottom');
        tip.classList.add('bs-tooltip-top');
        document.body.appendChild(tip);
        var r = el.getBoundingClientRect();
        var w = tip.offsetWidth, h = tip.offsetHeight;
        var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2),
                            window.innerWidth - w - 8);
        var top = r.top - h - 2;
        if (top < 8) {
            top = r.bottom + 2;
            tip.classList.replace('bs-tooltip-top', 'bs-tooltip-bottom');
        }
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
        tipArrow.style.left = (r.left + r.width / 2 - left - tipArrow.offsetWidth / 2) + 'px';
        void tip.offsetWidth;   // so the fade-in starts from hidden
        tip.classList.add('show');
    }

    function hideTip() {
        if (!tip || !tipTarget) return;
        tipTarget = null;
        tip.classList.remove('show');
        if (tip.parentNode) tip.parentNode.removeChild(tip);
    }

    function init() {
        if (!document.body || !readDelay()) { setTimeout(init, 200); return; }

        document.addEventListener('pointerdown', function (e) {
            pressed = e.target;
            hideTip();
            if (window.SkillTree && window.SkillTree.tooltip) window.SkillTree.tooltip.hide();
            // dbc tooltips close on their target's mouseout. Only a target
            // under the pointer has one up, so this reaches it. relatedTarget
            // is the target itself, so React sees no enter or leave.
            if (document.querySelector('.tooltip')) {
                e.target.dispatchEvent(new MouseEvent('mouseout', {
                    bubbles: true, view: window, relatedTarget: e.target,
                }));
            }
        }, true);

        // pointermove runs before the mouseover of the same step, so leaving
        // what was pressed clears it before the next hover is weighed.
        document.addEventListener('pointermove', function (e) {
            if (pressed && (!pressed.isConnected || !pressed.contains(e.target))) pressed = null;
        }, true);

        document.addEventListener('mouseover', function (e) {
            var el = e.target.closest && e.target.closest('[data-hint], .overflow-hint');
            if (el === tipTarget) return;
            hideTip();
            if (!el || pressed) return;
            var text = hintText(el);
            if (text) showTip(el, text);
        });

        document.addEventListener('scroll', hideTip, true);
    }

    // The hover gate. Window capture runs before every other listener, dbc's
    // tooltips included. mouseover fires before the mousemove of the same
    // step, so a hover at the last move's position came from content moving.
    window.addEventListener('mouseover', function (e) {
        if (!e.isTrusted) return;
        // Still on what was pressed: no tooltip there until the pointer leaves.
        if (pressed && pressed.isConnected && pressed.contains(e.target)) {
            e.stopImmediatePropagation();
            return;
        }
        if (lastX === null || (e.clientX === lastX && e.clientY === lastY)) {
            held = { target: e.target, relatedTarget: e.relatedTarget };
            e.stopImmediatePropagation();
            if (tipTarget && !tipTarget.contains(e.target)) hideTip();
        } else {
            held = null;
        }
    }, true);
    window.addEventListener('mousemove', function (e) {
        if (e.clientX === lastX && e.clientY === lastY) return;
        lastX = e.clientX;
        lastY = e.clientY;
        if (!held) return;
        var h = held;
        held = null;
        // Still over what it was held on: let that hover through now.
        if (h.target.isConnected && h.target.contains(e.target)) {
            h.target.dispatchEvent(new MouseEvent('mouseover', {
                bubbles: true, cancelable: true, view: window,
                clientX: e.clientX, clientY: e.clientY, relatedTarget: h.relatedTarget,
            }));
        }
    }, true);

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
