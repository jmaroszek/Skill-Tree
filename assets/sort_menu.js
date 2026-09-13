/**
 * Goals and Events sidebars: the sort menu behind the ⇅ button.
 *
 * Clicking a .sort-menu-button opens the menu named by its data-sort-menu,
 * right-aligned under the button. Clicking the button again closes it. A menu
 * item writes its sort value to the hidden input named by data-sort-input;
 * list_toolbar.py copies it into the sort store and moves the check mark.
 * menus.js positions and closes the menu.
 */
(function () {
    var GAP_PX = 4;
    // The menu that was open when the pointer went down on its own button.
    // menus.js closes every menu on that press, so the click that follows
    // must not reopen it.
    var closingMenuId = null;

    function init() {
        var menus = window.SkillTree && window.SkillTree.menus;
        if (!menus) {
            setTimeout(init, 100);
            return;
        }

        // Window capture runs before menus.js's document-level close.
        window.addEventListener('mousedown', function (evt) {
            var button = evt.target.closest && evt.target.closest('.sort-menu-button');
            var menu = button && document.getElementById(button.getAttribute('data-sort-menu'));
            closingMenuId = (menu && menu.style.display === 'block') ? menu.id : null;
        }, true);

        document.addEventListener('click', function (evt) {
            var button = evt.target.closest && evt.target.closest('.sort-menu-button');
            if (!button) return;
            var menuId = button.getAttribute('data-sort-menu');
            var inputId = button.getAttribute('data-sort-input');
            var menu = document.getElementById(menuId);
            if (!menu) return;
            if (closingMenuId === menuId) {
                closingMenuId = null;
                return;
            }

            menu.querySelectorAll('.ctx-menu-item[id]').forEach(function (item) {
                var value = item.id.slice(menuId.length + 1);
                menus.onItem(item.id, function () {
                    menus.send(inputId, value);
                });
            });

            var rect = button.getBoundingClientRect();
            menus.open(menu, rect.left, rect.bottom + GAP_PX);
            menu.style.left = Math.max(0, rect.right - menu.offsetWidth) + 'px';
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
