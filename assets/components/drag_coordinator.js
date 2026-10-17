/**
 * Shared drag coordinator for Skill Tree.
 *
 * Every drag context (panel resize, detail splits, popup move, canvas pan)
 * used to register its own pair of document-level mousemove + mouseup
 * listeners and a local `dragging` flag. Each listener had to guard with
 * `if (!dragging) return;` so that mouse events not intended for its drag
 * didn't cause interference. The pattern works but is fragile: new drag
 * features must remember the guard, and there's no central invariant that
 * only one drag can be active at a time.
 *
 * This module installs ONE pair of document-level listeners and exposes
 * window.SkillTree.drag.start({ cursor, onMove, onEnd }) for consumers.
 * - At most one drag is active; starting a new one cancels the prior.
 * - Cursor + user-select cleanup happens centrally.
 * - Consumers never touch `document.addEventListener` for drag handling.
 */
(function () {
    if (!window.SkillTree) window.SkillTree = {};
    if (window.SkillTree.drag) return;

    var _active = null;

    function cleanup() {
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        _active = null;
    }

    function endActive(ev, cancelled) {
        var a = _active;
        if (!a) return;
        _active = null; // clear before calling onEnd to allow onEnd to start a new drag if needed
        try {
            if (a.onEnd) a.onEnd({ event: ev, cancelled: !!cancelled });
        } catch (e) {
            console.error('[SkillTree/drag] onEnd error:', e);
        }
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }

    document.addEventListener('mousemove', function (e) {
        if (!_active || !_active.onMove) return;
        try { _active.onMove(e); }
        catch (err) { console.error('[SkillTree/drag] onMove error:', err); }
    });

    document.addEventListener('mouseup', function (e) {
        if (!_active) return;
        endActive(e, false);
    });

    window.SkillTree.drag = {
        start: function (handlers) {
            if (!handlers || typeof handlers !== 'object') return;
            if (_active) endActive(null, true);
            _active = handlers;
            if (handlers.cursor) document.body.style.cursor = handlers.cursor;
            if (handlers.userSelect !== false) document.body.style.userSelect = 'none';
        },
        isActive: function () { return _active !== null; },
        cancel: function () {
            if (_active) endActive(null, true);
            cleanup();
        },
    };
})();
