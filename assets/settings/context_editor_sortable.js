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
 * derived from its structure (features/settings/contexts._structure_key), so the render
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
// Served from assets/vendor, not a CDN, so drag-to-reorder works offline.
(function () {
    var src = '/assets/vendor/sortablejs/Sortable.min.js';
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

/* ---------- Chips hug their text ---------- */
// The server sets a first guess in `ch` (the width of a "0", wider than most
// letters). Here each input is measured in its own font, and re-measured as
// the user types, so the pill never runs long or clips.
var _ctxMeasure = null;

function _ctxFitChip(input) {
    if (!_ctxMeasure) _ctxMeasure = document.createElement('canvas').getContext('2d');
    var cs = getComputedStyle(input);
    _ctxMeasure.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
    var text = input.value || input.placeholder || '';
    var px = Math.ceil(_ctxMeasure.measureText(text).width) + 3;  // room for the caret
    var want = Math.max(px, 24) + 'px';
    if (input.style.width !== want) input.style.width = want;
}

function _ctxFitAllChips() {
    document.querySelectorAll('.ctx-chip-input').forEach(_ctxFitChip);
}

// A re-render mounts chips at the server's rough width. Fitting them in the
// debounced bind below would paint that width first, so chips wrap onto the
// wrong rows and the modal jumps before snapping back. Mutation observers run
// before the next paint, so this one fits new chips ahead of it.
new MutationObserver(function (records) {
    for (var i = 0; i < records.length; i++) {
        if (records[i].addedNodes.length) { _ctxFitAllChips(); return; }
    }
}).observe(document.body, { childList: true, subtree: true });

document.addEventListener('input', function (e) {
    if (e.target && e.target.matches && e.target.matches('.ctx-chip-input')) {
        _ctxFitChip(e.target);
    }
});

/* ---------- Enter finishes a field ---------- */
// Delegated from document because the rows remount on every structural edit.
// Values already reach Dash on each keystroke, so leaving the field is enough.
// A chip hands focus to its row's "+ add", so the next Tab or Enter continues
// from where the user was instead of restarting at the modal header.
document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.isComposing) return;
    var field = e.target;
    if (!field || !field.matches ||
        !field.matches('.ctx-row-name, .ctx-chip-input, .ctx-row-weight')) return;
    e.preventDefault();
    var add = field.matches('.ctx-chip-input')
        ? field.closest('.ctx-row') && field.closest('.ctx-row').querySelector('.ctx-chip-add')
        : null;
    if (add) add.focus(); else field.blur();
});

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
