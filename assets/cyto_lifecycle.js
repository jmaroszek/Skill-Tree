/**
 * Shared lifecycle hook for Cytoscape instances owned by Dash.
 *
 * Each callback file used to bind its handlers via a one-shot IIFE that
 * captured the initial `_cyreg.cy` reference. If Dash-Cytoscape ever
 * recreated that instance (element replacement / re-mount), the handlers
 * stayed bound to a detached cy — tooltip showed nothing, context menu
 * went dead, etc.
 *
 * Consumers call `window.SkillTree.onCytoReady(selector, fn)`. The helper:
 *   - locates the container by selector,
 *   - observes it for DOM mutations,
 *   - whenever a new `_cyreg.cy` appears, invokes `fn(cy)` so the
 *     consumer can re-bind its handlers on the fresh instance,
 *   - never re-invokes `fn` against the same cy instance.
 *
 * Safe to call multiple times for the same selector with different fns.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};
    if (window.SkillTree.onCytoReady) return;

    var _handlers = {};
    var _boundCy = {};
    var _observers = {};

    function findCy(selector) {
        var el = document.querySelector(selector);
        if (!el) return null;
        return (el._cyreg && el._cyreg.cy) ? el._cyreg.cy : null;
    }

    function invokeAll(selector, cy) {
        var fns = _handlers[selector] || [];
        for (var i = 0; i < fns.length; i++) {
            try { fns[i](cy); }
            catch (e) { console.error('[SkillTree/cyto] handler error on', selector, e); }
        }
    }

    function maybeRebind(selector) {
        var cy = findCy(selector);
        if (!cy) return;
        if (_boundCy[selector] === cy) return;
        _boundCy[selector] = cy;
        invokeAll(selector, cy);
    }

    function ensureObserver(selector) {
        if (_observers[selector]) return;
        var el = document.querySelector(selector);
        if (!el) {
            setTimeout(function () { ensureObserver(selector); }, 300);
            return;
        }
        maybeRebind(selector);
        var obs = new MutationObserver(function () { maybeRebind(selector); });
        obs.observe(el, { childList: true, subtree: true, attributes: true });
        _observers[selector] = obs;
    }

    window.SkillTree.onCytoReady = function (selector, fn) {
        if (!_handlers[selector]) _handlers[selector] = [];
        _handlers[selector].push(fn);
        ensureObserver(selector);
        var existing = _boundCy[selector];
        if (existing) {
            try { fn(existing); }
            catch (e) { console.error('[SkillTree/cyto] handler error on', selector, e); }
        }
    };
})();
