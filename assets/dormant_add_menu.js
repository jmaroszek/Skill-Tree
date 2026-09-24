/**
 * Events tab: the menu behind the Dormant Nodes "+".
 *
 * Clicking the "+" opens #dormant-add-menu under it. "New node" opens the
 * node editor on a new node already dormant under the selected event;
 * "Existing nodes…" opens the Add to Event picker. Either writes
 * "<new|existing>|<ms>" to dormant-add-choice-input, which event_callbacks.py
 * reads. Clicking the "+" again closes the menu. menus.js positions and
 * closes it.
 */
(function () {
    var BUTTON_ID = 'btn-add-dormant-node';
    var MENU_ID = 'dormant-add-menu';
    var INPUT_ID = 'dormant-add-choice-input';
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
            menus.onItem('dormant-add-' + choice, function () {
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
