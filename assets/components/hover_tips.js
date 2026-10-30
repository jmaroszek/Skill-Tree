/**
 * How every tooltip behaves, and the one tooltip for small marks.
 *
 * Timing lives in CSS (custom.css, Tooltips): a tooltip mounts at once and
 * fades in after --st-tooltip-show-delay. This script only flips classes on
 * <body>, so dbc tooltips and the shared tip below follow the same rules.
 *
 * - A press cancels: `tooltips-suppressed` hides every tooltip until the
 *   pointer moves off the element it pressed. A tooltip whose hover timer
 *   was still running when you clicked never appears.
 * - Warm handoff: once a tooltip has shown, `tooltips-warm` lets the next
 *   one show at once, until WARM_MS pass with none showing.
 * - The shared tip: an element with `data-hint` shows that text, and one with
 *   the `overflow-hint` class shows its own text only while it is cut off
 *   with an ellipsis. Rows can carry these by the hundred without a Dash
 *   tooltip component each, and they replace native `title` tooltips, which
 *   keep Chromium's own delay, look and click behaviour.
 */
(function () {
    var WARM_MS = 500;
    var body = null;
    var pressed = null;
    var coolTimer = null;
    var tip = null, tipInner = null, tipArrow = null, tipTarget = null;

    function cls(name, on) { if (body) body.classList.toggle(name, on); }

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
        startCooling();
    }

    function anyShowing() {
        return Array.prototype.some.call(document.querySelectorAll('.tooltip.show'),
            function (t) { return parseFloat(getComputedStyle(t).opacity) > 0; });
    }

    // Warmth lasts WARM_MS past the last tooltip on screen.
    function startCooling() {
        clearTimeout(coolTimer);
        coolTimer = setTimeout(function cool() {
            if (anyShowing()) coolTimer = setTimeout(cool, WARM_MS);
            else cls('tooltips-warm', false);
        }, WARM_MS);
    }

    function init() {
        body = document.body;
        if (!body || !readDelay()) { setTimeout(init, 200); return; }

        document.addEventListener('pointerdown', function (e) {
            pressed = e.target;
            cls('tooltips-suppressed', true);
            hideTip();
            if (window.SkillTree && window.SkillTree.tooltip) window.SkillTree.tooltip.hide();
        }, true);

        document.addEventListener('pointermove', function (e) {
            if (pressed && (!pressed.isConnected || !pressed.contains(e.target))) {
                pressed = null;
                cls('tooltips-suppressed', false);
            }
        }, true);

        document.addEventListener('pointerover', function (e) {
            var el = e.target.closest && e.target.closest('[data-hint], .overflow-hint');
            if (el === tipTarget) return;
            hideTip();
            if (!el || pressed) return;
            var text = hintText(el);
            if (text) showTip(el, text);
        });

        document.addEventListener('scroll', hideTip, true);

        // transitionstart fires once the show delay has passed: the tooltip is
        // really appearing, unless a press is hiding it.
        document.addEventListener('transitionstart', function (e) {
            var t = e.target;
            if (e.propertyName !== 'opacity' || !t.classList || !t.classList.contains('tooltip')) return;
            if (t.classList.contains('show') && !body.classList.contains('tooltips-suppressed')) {
                clearTimeout(coolTimer);
                cls('tooltips-warm', true);
            }
        });
        // Leaving any element may be leaving the last tooltip: start the clock.
        document.addEventListener('mouseout', function () {
            if (body.classList.contains('tooltips-warm')) startCooling();
        }, true);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
