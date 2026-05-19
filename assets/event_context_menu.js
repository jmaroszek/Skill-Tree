/**
 * Events sidebar: right-click context menu (edit / trigger / delete).
 *
 * On right-click of an .event-card, opens #event-context-menu. Each item
 * writes "<event_name>|<action>|<ts>" to #event-ctx-action-input so the
 * Python callback can react.
 */
(function () {
    var _activeEventName = null;

    function setHiddenInput(inputId, value) {
        var input = document.getElementById(inputId);
        if (!input) return;
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function hideMenu() {
        var m = document.getElementById('event-context-menu');
        if (m) m.style.display = 'none';
    }

    function positionMenu(menu, x, y) {
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

    function bindMenuItem(itemId, action) {
        var el = document.getElementById(itemId);
        if (!el) return;
        el.addEventListener('click', function (evt) {
            evt.stopPropagation();
            var name = _activeEventName;
            hideMenu();
            if (!name) return;
            setHiddenInput('event-ctx-action-input',
                name + '|' + action + '|' + Date.now());
        });
    }

    function init() {
        var ctxMenu = document.getElementById('event-context-menu');
        if (!ctxMenu) {
            setTimeout(init, 300);
            return;
        }

        document.addEventListener('contextmenu', function (evt) {
            var card = evt.target.closest && evt.target.closest('.event-card');
            if (!card) return;
            var name = card.getAttribute('data-event-name');
            if (!name) return;
            evt.preventDefault();
            _activeEventName = name;
            hideMenu();
            positionMenu(ctxMenu, evt.clientX, evt.clientY);
        });

        document.addEventListener('click', function (evt) {
            if (!evt.target.closest('#event-context-menu')) hideMenu();
        }, true);

        document.addEventListener('keydown', function (evt) {
            if (evt.key === 'Escape') hideMenu();
        });
        window.addEventListener('blur', hideMenu);
        window.addEventListener('resize', hideMenu);

        bindMenuItem('event-ctx-edit', 'edit');
        bindMenuItem('event-ctx-trigger', 'trigger');
        bindMenuItem('event-ctx-delete', 'delete');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
