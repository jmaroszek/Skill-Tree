(function () {
    var CLOSED = 'ratings-popup';
    var OPEN = 'ratings-popup is-open';

    // Two independent rubrics share this behavior. The estimation popup is
    // triggered from the node editor; the reflection popup is triggered from
    // the Reflection modal.
    // Each entry maps a trigger button to the popup/header/close/edit ids it
    // controls. Modals render lazily, so we watch continuously and wire up each
    // element as it appears.
    var POPUPS = [
        {
            popupId: 'ratings-popup',
            headerId: 'ratings-popup-header',
            closeId: 'btn-ratings-close',
            editId: 'btn-ratings-edit',
            triggerIds: ['btn-ratings-info'],
        },
        {
            popupId: 'reflection-ratings-popup',
            headerId: 'reflection-ratings-popup-header',
            closeId: 'btn-reflection-ratings-close',
            editId: 'btn-reflection-ratings-edit',
            triggerIds: ['btn-reflection-ratings-info'],
            modalId: 'modal-time-calibration',
        },
    ];

    POPUPS.forEach(function (cfg) {
        window.SkillTree.keyboardFocus.register({id: cfg.popupId,
            triggerId: cfg.triggerIds[0], closeId: cfg.closeId, initial: '#' + cfg.closeId,
            modalId: cfg.modalId, flow: true,
            hideWhenClosed: true, isOpen: function (el) { return el.classList.contains('is-open'); }});
    });

    // Through Dash, which owns the element. A drag or resize writes the popup's
    // geometry directly while it runs, and opening clears it.
    function setOpen(popup, open) {
        if (open) {
            ['width', 'height', 'left', 'top'].forEach(function (key) {
                popup.style[key] = '';
            });
        }
        window.dash_clientside.set_props(popup.id, {className: open ? OPEN : CLOSED});
    }

    function makeTriggerHandler(popupId) {
        return function (e) {
            e.stopPropagation();
            var popup = document.getElementById(popupId);
            if (!popup) return;
            setOpen(popup, !popup.classList.contains('is-open'));
        };
    }

    function tryAttachTrigger(id, popupId) {
        var btn = document.getElementById(id);
        if (!btn || btn.__ratingsWired) return;
        btn.addEventListener('click', makeTriggerHandler(popupId));
        btn.__ratingsWired = true;
    }

    function attachShared(cfg) {
        var popup = document.getElementById(cfg.popupId);
        var header = document.getElementById(cfg.headerId);

        var closeBtn = document.getElementById(cfg.closeId);
        if (closeBtn && !closeBtn.__ratingsWired) {
            closeBtn.addEventListener('click', function () {
                if (popup) setOpen(popup, false);
            });
            closeBtn.__ratingsWired = true;
        }

        var editBtn = document.getElementById(cfg.editId);
        if (editBtn && !editBtn.__ratingsWired) {
            // It steps aside for the edit table, and comes back when that
            // closes (reopen_after_edit).
            editBtn.addEventListener('click', function () {
                if (!popup) return;
                setOpen(popup, false);
                popup.__reopenAfterEdit = true;
            });
            editBtn.__ratingsWired = true;
        }

        if (!popup || !header || header.__dragWired) return;
        header.__dragWired = true;

        header.addEventListener('mousedown', function (e) {
            var closeBtn = document.getElementById(cfg.closeId);
            var editBtn = document.getElementById(cfg.editId);
            if (closeBtn && (e.target === closeBtn || closeBtn.contains(e.target))) return;
            if (editBtn && (e.target === editBtn || editBtn.contains(e.target))) return;
            if (!window.SkillTree || !window.SkillTree.drag) return;
            var startX = e.clientX;
            var startY = e.clientY;
            var origLeft = popup.offsetLeft;
            var origTop = popup.offsetTop;
            e.preventDefault();

            window.SkillTree.drag.start({
                onMove: function (ev) {
                    popup.style.left = (origLeft + ev.clientX - startX) + 'px';
                    popup.style.top  = (origTop  + ev.clientY - startY) + 'px';
                },
            });
        });
    }

    function wireAll() {
        POPUPS.forEach(function (cfg) {
            attachShared(cfg);
            cfg.triggerIds.forEach(function (id) {
                tryAttachTrigger(id, cfg.popupId);
            });
        });
    }

    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.ratings_popup = {
        reopen_after_edit: function (isOpen, popupId) {
            var popup = document.getElementById(popupId);
            if (!isOpen && popup && popup.__reopenAfterEdit) {
                popup.__reopenAfterEdit = false;
                setOpen(popup, true);
            }
            return window.dash_clientside.no_update;
        },
    };

    var obs = new MutationObserver(wireAll);
    obs.observe(document.body, { childList: true, subtree: true });
    wireAll();
})();
