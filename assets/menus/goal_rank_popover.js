/**
 * Goal sidebar: the rank popover on a priority goal's rank badge.
 *
 * Left-clicking a .goal-rank-trigger opens #goal-rank-popover below the badge.
 * Its items write "<name>|<1|2|3|clear>|<ts>" to goal-priority-trigger-input,
 * the same input the node context menu's Set Priority submenu uses. A goal
 * card's right-click menu is the shared node menu (context_menu.js).
 * menus.js positions and closes the popover.
 */
(function () {
    var _activeGoalName = null;

    function init() {
        var menus = window.SkillTree && window.SkillTree.menus;
        if (!menus) {
            setTimeout(init, 100);
            return;
        }

        document.addEventListener('click', function (evt) {
            var trigger = evt.target.closest && evt.target.closest('.goal-rank-trigger');
            if (!trigger) return;
            var name = trigger.getAttribute('data-goal-name');
            var popover = document.getElementById('goal-rank-popover');
            if (!name || !popover) return;
            evt.stopPropagation();
            evt.preventDefault();
            _activeGoalName = name;
            var rect = trigger.getBoundingClientRect();
            menus.open(popover, rect.left, rect.bottom + 4);
        }, true);

        ['1', '2', '3', 'clear'].forEach(function (rank) {
            menus.onItem('goal-rank-' + rank, function () {
                if (!_activeGoalName) return;
                menus.send('goal-priority-trigger-input',
                    _activeGoalName + '|' + rank + '|' + Date.now());
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
