/**
 * Goal sidebar: rank popover + right-click context menu.
 *
 * Two floating panels live in the document (defined in layout.py):
 *   - #goal-rank-popover : opens on left-click of a .goal-rank-trigger
 *   - #goal-context-menu : opens on right-click anywhere on a .goal-card
 *
 * Both write to hidden inputs that Dash callbacks pick up:
 *   - goal-priority-trigger-input  : "<name>|<1|2|3|clear>|<ts>"
 *   - goal-details-trigger-input   : "<name>|<ts>"
 *   - details-edit-trigger-input   : "<name>"        (reused from canvas menu)
 *   - toggle-done-trigger-input    : "[<name>]|<ts>" (reused from canvas menu)
 */
(function () {
    var _activeGoalName = null;

    function setHiddenInput(inputId, value) {
        var input = document.getElementById(inputId);
        if (!input) return;
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function hideAll() {
        var p = document.getElementById('goal-rank-popover');
        var m = document.getElementById('goal-context-menu');
        if (p) p.style.display = 'none';
        if (m) m.style.display = 'none';
    }

    function positionMenu(menu, x, y) {
        // Show first so we can measure
        menu.style.display = 'block';
        menu.style.left = '0px';
        menu.style.top = '0px';
        var rect = menu.getBoundingClientRect();
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var px = x;
        var py = y;
        if (px + rect.width > vw) px = Math.max(0, vw - rect.width - 4);
        if (py + rect.height > vh) py = Math.max(0, vh - rect.height - 4);
        menu.style.left = px + 'px';
        menu.style.top = py + 'px';
    }

    function showRankPopover(x, y, goalName) {
        var menu = document.getElementById('goal-rank-popover');
        if (!menu) return;
        _activeGoalName = goalName;
        positionMenu(menu, x, y);
    }

    function showContextMenu(x, y, goalName) {
        var menu = document.getElementById('goal-context-menu');
        if (!menu) return;
        _activeGoalName = goalName;
        positionMenu(menu, x, y);
    }

    function bindMenuItem(itemId, handler) {
        var el = document.getElementById(itemId);
        if (!el) return;
        el.addEventListener('click', function (evt) {
            evt.stopPropagation();
            var name = _activeGoalName;
            hideAll();
            if (!name) return;
            handler(name);
        });
    }

    function init() {
        var rankPopover = document.getElementById('goal-rank-popover');
        var ctxMenu = document.getElementById('goal-context-menu');
        if (!rankPopover || !ctxMenu) {
            setTimeout(init, 300);
            return;
        }

        // --- Rank popover (left-click on .goal-rank-trigger) ---
        document.addEventListener('click', function (evt) {
            var trigger = evt.target.closest && evt.target.closest('.goal-rank-trigger');
            if (trigger) {
                evt.stopPropagation();
                evt.preventDefault();
                hideAll();
                var name = trigger.getAttribute('data-goal-name');
                if (!name) return;
                var rect = trigger.getBoundingClientRect();
                showRankPopover(rect.left, rect.bottom + 4, name);
                return;
            }
            // Background click — hide both menus
            if (!evt.target.closest('#goal-rank-popover') &&
                !evt.target.closest('#goal-context-menu')) {
                hideAll();
            }
        }, true);

        // --- Context menu (right-click on .goal-card) ---
        document.addEventListener('contextmenu', function (evt) {
            var card = evt.target.closest && evt.target.closest('.goal-card');
            if (!card) return;
            var name = card.getAttribute('data-goal-name');
            if (!name) return;
            evt.preventDefault();
            hideAll();
            showContextMenu(evt.clientX, evt.clientY, name);
        });

        // Hide on Escape, scroll, or window blur
        document.addEventListener('keydown', function (evt) {
            if (evt.key === 'Escape') hideAll();
        });
        window.addEventListener('blur', hideAll);
        window.addEventListener('resize', hideAll);

        // --- Rank popover items ---
        function setPriority(rank) {
            return function (name) {
                setHiddenInput('goal-priority-trigger-input',
                    name + '|' + rank + '|' + Date.now());
            };
        }
        bindMenuItem('goal-rank-set-1', setPriority('1'));
        bindMenuItem('goal-rank-set-2', setPriority('2'));
        bindMenuItem('goal-rank-set-3', setPriority('3'));
        bindMenuItem('goal-rank-clear', setPriority('clear'));

        // --- Context menu items ---
        bindMenuItem('goal-ctx-edit', function (name) {
            // Use details-edit-trigger-input from any tab: it opens the editor
            // sidebar in place WITHOUT switching tabs (edit-trigger-input would
            // switch to the canvas tab via handle_edit_trigger in callbacks.py).
            setHiddenInput('details-edit-trigger-input', name + '|' + Date.now());
        });
        bindMenuItem('goal-ctx-details', function (name) {
            setHiddenInput('goal-details-trigger-input', name + '|' + Date.now());
        });
        bindMenuItem('goal-ctx-toggle-done', function (name) {
            setHiddenInput('toggle-done-trigger-input',
                JSON.stringify([name]) + '|' + Date.now());
        });
        bindMenuItem('goal-ctx-set-1', setPriority('1'));
        bindMenuItem('goal-ctx-set-2', setPriority('2'));
        bindMenuItem('goal-ctx-set-3', setPriority('3'));
        bindMenuItem('goal-ctx-clear', setPriority('clear'));
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
