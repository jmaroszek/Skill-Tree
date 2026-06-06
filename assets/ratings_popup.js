(function () {
    // Keep in sync with the inline style declared on the popups in layout.py.
    // These are reapplied each time a popup is opened so a prior drag/resize
    // doesn't persist across reopenings.
    var DEFAULT_WIDTH = '960px';
    var DEFAULT_HEIGHT = 'auto';
    var DEFAULT_LEFT = '420px';
    var DEFAULT_TOP = '120px';

    // Two independent rubrics share this behavior. The estimation popup is
    // triggered from the main node editor and the Add Subtask modal (Details
    // tab); the reflection popup is triggered only from the Reflection modal.
    // Each entry maps a trigger button to the popup/header/close/edit ids it
    // controls. Modals render lazily, so we watch continuously and wire up each
    // element as it appears.
    var POPUPS = [
        {
            popupId: 'ratings-popup',
            headerId: 'ratings-popup-header',
            closeId: 'btn-ratings-close',
            editId: 'btn-ratings-edit',
            triggerIds: ['btn-ratings-info', 'btn-details-ratings-info'],
        },
        {
            popupId: 'reflection-ratings-popup',
            headerId: 'reflection-ratings-popup-header',
            closeId: 'btn-reflection-ratings-close',
            editId: 'btn-reflection-ratings-edit',
            triggerIds: ['btn-reflection-ratings-info'],
        },
    ];

    var attached = {};

    function resetPopupGeometry(p) {
        p.style.width = DEFAULT_WIDTH;
        p.style.height = DEFAULT_HEIGHT;
        p.style.left = DEFAULT_LEFT;
        p.style.top = DEFAULT_TOP;
    }

    function makeTriggerHandler(popupId) {
        return function (e) {
            e.stopPropagation();
            var popup = document.getElementById(popupId);
            if (!popup) return;
            if (popup.style.display === 'flex') {
                popup.style.display = 'none';
            } else {
                resetPopupGeometry(popup);
                popup.style.display = 'flex';
            }
        };
    }

    function tryAttachTrigger(id, popupId) {
        if (attached[id]) return;
        var btn = document.getElementById(id);
        if (!btn) return;
        btn.addEventListener('click', makeTriggerHandler(popupId));
        attached[id] = true;
    }

    function attachShared(cfg) {
        var popup = document.getElementById(cfg.popupId);
        var header = document.getElementById(cfg.headerId);

        var closeKey = '__close_' + cfg.closeId;
        if (!attached[closeKey]) {
            var closeBtn = document.getElementById(cfg.closeId);
            if (closeBtn) {
                closeBtn.addEventListener('click', function () {
                    if (popup) popup.style.display = 'none';
                });
                attached[closeKey] = true;
            }
        }

        var editKey = '__edit_' + cfg.editId;
        if (!attached[editKey]) {
            var editBtn = document.getElementById(cfg.editId);
            if (editBtn) {
                editBtn.addEventListener('click', function () {
                    if (popup) popup.style.display = 'none';
                });
                attached[editKey] = true;
            }
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

    var obs = new MutationObserver(wireAll);
    obs.observe(document.body, { childList: true, subtree: true });
    wireAll();
})();
