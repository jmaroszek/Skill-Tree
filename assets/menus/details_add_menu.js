/**
 * Details tab: the menu behind the Subtasks "+".
 *
 * "New node" opens the shared editor with Supports > Hard prefilled;
 * "Existing node…" opens the focused linking modal. The choice is written
 * to details-add-choice-input for Dash callbacks. Clicking the "+" again closes the menu. menus.js positions and
 * closes it.
 */
(function () {
    var BUTTON_ID = 'btn-details-add-node';
    var MENU_ID = 'details-add-menu';
    var INPUT_ID = 'details-add-choice-input';
    var GAP_PX = 4;
    // True when the menu was open as the pointer went down on the "+".
    // menus.js closes every menu on that press, so the click that follows
    // must not reopen it.
    var closing = false;

    function init() {
        var menus = window.SkillTree && window.SkillTree.menus;
        if (!menus) {
            setTimeout(init, 100);
            return;
        }

        // Window capture runs before menus.js's document-level close.
        window.addEventListener('mousedown', function (evt) {
            var button = evt.target.closest && evt.target.closest('#' + BUTTON_ID);
            var menu = document.getElementById(MENU_ID);
            closing = Boolean(button && menu && menu.style.display === 'block');
        }, true);

        document.addEventListener('click', function (evt) {
            var button = evt.target.closest && evt.target.closest('#' + BUTTON_ID);
            if (!button) return;
            var menu = document.getElementById(MENU_ID);
            if (!menu) return;
            if (closing) {
                closing = false;
                return;
            }
            var rect = button.getBoundingClientRect();
            menus.open(menu, rect.left, rect.bottom + GAP_PX);
        });

        ['new', 'existing'].forEach(function (choice) {
            menus.onItem('details-add-' + choice, function () {
                menus.send(INPUT_ID, choice + '|' + Date.now());
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
