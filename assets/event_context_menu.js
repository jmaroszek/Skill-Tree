/**
 * Events sidebar: right-click context menu (edit / trigger / delete).
 *
 * On right-click of an .event-card, opens #event-context-menu. Each item
 * writes "<event_name>|<action>|<ts>" to #event-ctx-action-input so the
 * Python callback can react. menus.js positions and closes the menu.
 */
(function () {
    var _activeEventName = null;

    function init() {
        var menus = window.SkillTree && window.SkillTree.menus;
        if (!menus) {
            setTimeout(init, 100);
            return;
        }

        document.addEventListener('contextmenu', function (evt) {
            var card = evt.target.closest && evt.target.closest('.event-card');
            if (!card) return;
            var name = card.getAttribute('data-event-name');
            var menu = document.getElementById('event-context-menu');
            if (!name || !menu) return;
            evt.preventDefault();
            _activeEventName = name;

            // A triggered event has nothing left to wake.
            var canTrigger = card.getAttribute('data-event-status') !== 'Triggered';
            ['event-ctx-trigger', 'event-ctx-trigger-divider'].forEach(function (id) {
                var el = document.getElementById(id);
                if (el) el.style.display = canTrigger ? '' : 'none';
            });

            menus.open(menu, evt.clientX, evt.clientY);
        });

        ['edit', 'trigger', 'delete'].forEach(function (action) {
            menus.onItem('event-ctx-' + action, function () {
                if (!_activeEventName) return;
                menus.send('event-ctx-action-input',
                    _activeEventName + '|' + action + '|' + Date.now());
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
