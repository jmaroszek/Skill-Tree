/**
 * Drag-and-drop for the Settings ▸ Contexts row editor.
 *
 * Two kinds of list: the context rows, and each row's subcontext chips. Each
 * chip list is its own SortableJS instance with no shared group, so a chip
 * reorders within its row and cannot be dragged into another context.
 *
 * On drop the whole layout is read back from the DOM and written to the
 * hidden #ctx-editor-drag-input as
 *     {"rows": [rid, ...], "subs": {rid: [sid, ...]}, "t": <nonce>}
 * for context_rules.apply_drag_order to fold into the store.
 *
 * SortableJS moves DOM nodes itself. The editor's root carries a React key
 * derived from its structure (callback_helpers._structure_key), so the render
 * that follows a drop remounts the editor instead of reconciling against the
 * rearranged DOM. The nonce makes every drop produce that render.
 *
 * SortableJS runs in its forced-fallback mode, as the Now cards do: native
 * HTML5 drag detects the drop position from dragover events, which arrive
 * too unevenly to place a row reliably. The fallback clone follows the
 * pointer on <body>, outside the modal, so .ctx-sortable-fallback lifts it
 * above the modal on its own z-index layer.
 */

/* ---------- Load SortableJS (shared with the event and goal sortables) ---------- */
(function () {
    var src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js';
    if (window.Sortable || document.querySelector('script[src="' + src + '"]')) return;
    var s = document.createElement('script');
    s.src = src;
    s.async = false;
    document.head.appendChild(s);
})();

var _ctxSortables = [];
var _ctxBoundRoot = null;
var _ctxDragging = false;

function _ctxLayoutFromDom(root) {
    var rows = [];
    var subs = {};
    root.querySelectorAll('.ctx-row-list > .ctx-row[data-ctx-row]').forEach(function (row) {
        var rid = row.getAttribute('data-ctx-row');
        rows.push(rid);
        var list = row.querySelector('.ctx-chips[data-ctx-subs]');
        if (!list) return;
        subs[rid] = [];
        list.querySelectorAll('.ctx-chip[data-ctx-sub]').forEach(function (chip) {
            subs[rid].push(chip.getAttribute('data-ctx-sub'));
        });
    });
    return { rows: rows, subs: subs, t: Date.now() };
}

function _ctxOnEnd() {
    _ctxDragging = false;
    document.body.classList.remove('ctx-dragging');
    var root = document.getElementById('ctx-editor-rows');
    var input = document.getElementById('ctx-editor-drag-input');
    if (!root || !input) return;
    window.SkillTree.setInputValue(input, JSON.stringify(_ctxLayoutFromDom(root)));
}

function _ctxOnStart() {
    _ctxDragging = true;
    document.body.classList.add('ctx-dragging');
}

function _ctxDestroy() {
    _ctxSortables.forEach(function (instance) {
        try { instance.destroy(); } catch (_) {}
    });
    _ctxSortables = [];
    _ctxBoundRoot = null;
}

function _initCtxSortable() {
    var root = document.getElementById('ctx-editor-rows');
    if (!root) {
        if (_ctxBoundRoot) _ctxDestroy();
        return;
    }
    // Same element as last time: its lists are already bound. A structural
    // change remounts the root (see the header), so identity is the signal.
    if (root === _ctxBoundRoot) return;

    if (!window.Sortable) {
        setTimeout(_initCtxSortable, 200);
        return;
    }

    _ctxDestroy();
    _ctxBoundRoot = root;

    var rowList = root.querySelector('.ctx-row-list');
    if (rowList) {
        _ctxSortables.push(new Sortable(rowList, {
            animation: 150,
            draggable: '.ctx-row',
            handle: '.ctx-drag-handle',
            ghostClass: 'ctx-sortable-ghost',
            chosenClass: 'ctx-sortable-chosen',
            forceFallback: true,
            fallbackOnBody: true,
            fallbackClass: 'ctx-sortable-fallback',
            fallbackTolerance: 3,
            onStart: _ctxOnStart,
            onEnd: _ctxOnEnd,
        }));
    }

    root.querySelectorAll('.ctx-chips[data-ctx-subs]').forEach(function (list) {
        _ctxSortables.push(new Sortable(list, {
            animation: 150,
            draggable: '.ctx-chip',
            handle: '.ctx-chip-grip',
            ghostClass: 'ctx-sortable-ghost',
            chosenClass: 'ctx-sortable-chosen',
            forceFallback: true,
            fallbackOnBody: true,
            fallbackClass: 'ctx-sortable-fallback',
            fallbackTolerance: 3,
            onStart: _ctxOnStart,
            onEnd: _ctxOnEnd,
        }));
    });
}

/* ---------- Re-bind after every render ---------- */
// The Settings modal renders into a portal on <body>, outside the Dash app
// root, so the observer watches <body>. It only resets a timer; the bind
// itself bails out early unless the editor root was remounted.
var _ctxObserver = new MutationObserver(function () {
    if (_ctxDragging) return;
    clearTimeout(_ctxObserver._timer);
    _ctxObserver._timer = setTimeout(_initCtxSortable, 60);
});

function _startCtxObserving() {
    _ctxObserver.observe(document.body, { childList: true, subtree: true });
    _initCtxSortable();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startCtxObserving);
} else {
    _startCtxObserving();
}
