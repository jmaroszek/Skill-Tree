/**
 * Shared behavior for every floating menu: the node context menu, the Events
 * sidebar menu and the goal rank popover.
 *
 * All of them are `.ctx-menu` elements built by the same helpers in layout.py,
 * so they look alike. This module makes them behave alike. A menu module
 * decides which items to show and what each one does; this one opens the menu
 * at a point, keeps it on screen, runs its submenus, and closes every menu on
 * an outside press, Escape, scroll, blur or resize.
 *
 * Items are dispatched from one delegated click listener, so a module can
 * register its handlers before Dash has rendered the menus.
 */
(function () {
    var SkillTree = window.SkillTree = window.SkillTree || {};
    if (SkillTree.menus) return;

    // How long a submenu stays open after the pointer leaves its row, so a
    // diagonal move toward the submenu doesn't close it on the way.
    var SUBMENU_CLOSE_MS = 150;
    var EDGE_GAP_PX = 4;

    var handlers = Object.create(null);

    function hideAll() {
        document.querySelectorAll('.ctx-menu').forEach(function (menu) {
            menu.style.display = 'none';
        });
        document.querySelectorAll('.ctx-menu-submenu-open').forEach(function (row) {
            row.classList.remove('ctx-menu-submenu-open');
        });
    }

    function bindSubmenu(row) {
        var submenu = row.querySelector('.ctx-menu-submenu');
        if (!submenu || row._skillTreeSubmenu) return;
        row._skillTreeSubmenu = true;
        var closeTimer = null;

        function cancelClose() {
            if (closeTimer) clearTimeout(closeTimer);
            closeTimer = null;
        }

        // The submenu is a child of its row, so moving into it never leaves
        // the row. Only a move out to the rest of the menu does.
        row.addEventListener('mouseenter', function () {
            cancelClose();
            row.classList.remove('ctx-menu-submenu-flip');
            submenu.style.top = '';
            row.classList.add('ctx-menu-submenu-open');
            var rowRect = row.getBoundingClientRect();
            var rect = submenu.getBoundingClientRect();
            if (rowRect.right + rect.width > window.innerWidth - EDGE_GAP_PX) {
                row.classList.add('ctx-menu-submenu-flip');
            }
            var overflow = rect.bottom - (window.innerHeight - EDGE_GAP_PX);
            if (overflow > 0) {
                submenu.style.top = (submenu.offsetTop - overflow) + 'px';
            }
        });
        row.addEventListener('mouseleave', function () {
            cancelClose();
            closeTimer = setTimeout(function () {
                row.classList.remove('ctx-menu-submenu-open');
                closeTimer = null;
            }, SUBMENU_CLOSE_MS);
        });
    }

    /**
     * Show `menu` with its top-left corner at the pointer. A menu that would
     * run past the right or bottom edge opens to the left of or above the
     * pointer instead. Show or hide items before calling this, since that
     * changes the size being measured.
     */
    function open(menu, x, y) {
        hideAll();
        menu.querySelectorAll('.ctx-menu-submenu-parent').forEach(bindSubmenu);
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        menu.style.display = 'block';
        var rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) x -= rect.width;
        if (rect.bottom > window.innerHeight) y -= rect.height;
        menu.style.left = Math.max(0, x) + 'px';
        menu.style.top = Math.max(0, y) + 'px';
    }

    /** Run `fn` when the item is clicked, after every menu has closed. */
    function onItem(itemId, fn) {
        handlers[itemId] = fn;
    }

    /**
     * Write `value` to a hidden Dash input. React ignores a plain
     * `input.value = ...`, so this goes through the native setter and then
     * raises the `input` event React listens for.
     */
    function send(inputId, value) {
        var input = document.getElementById(inputId);
        if (!input) return;
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function insideMenu(target) {
        return Boolean(target && target.closest && target.closest('.ctx-menu'));
    }

    document.addEventListener('click', function (evt) {
        var item = evt.target.closest && evt.target.closest('.ctx-menu-item[id]');
        if (!item || !handlers[item.id]) return;
        evt.stopPropagation();
        hideAll();
        handlers[item.id]();
    });

    // A press rather than a click, so the click that opens another menu, such
    // as the goal rank popover, lands after this has closed the old one.
    document.addEventListener('mousedown', function (evt) {
        if (!insideMenu(evt.target)) hideAll();
    }, true);
    // Capturing, because scrolls inside a sidebar or list don't bubble.
    document.addEventListener('scroll', function (evt) {
        if (!insideMenu(evt.target)) hideAll();
    }, true);
    document.addEventListener('keydown', function (evt) {
        if (evt.key === 'Escape') hideAll();
    });
    window.addEventListener('blur', hideAll);
    window.addEventListener('resize', hideAll);

    SkillTree.menus = { open: open, hideAll: hideAll, onItem: onItem, send: send };
})();
