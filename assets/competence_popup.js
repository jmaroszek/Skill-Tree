(function () {
    // Keep in sync with the inline style declared on #competence-popup in layout.py.
    // These are reapplied each time the popup is opened so a prior drag/resize
    // doesn't persist across reopenings.
    var DEFAULT_WIDTH = '720px';
    var DEFAULT_HEIGHT = '560px';
    var DEFAULT_LEFT = '460px';
    var DEFAULT_TOP = '140px';

    // Three sites trigger the same popup: main node editor, Add Subtask modal
    // (Details tab), and Dormant Node editor (Events tab). Some of these render
    // lazily, so we watch continuously and wire up each button as it appears.
    var TRIGGER_IDS = [
        'btn-competence-info',
        'btn-details-competence-info',
        'btn-dormant-competence-info',
    ];

    var attached = {};
    var popup = null;
    var header = null;
    var closeBtn = null;
    var editBtn = null;

    function resetPopupGeometry(p) {
        p.style.width = DEFAULT_WIDTH;
        p.style.height = DEFAULT_HEIGHT;
        p.style.left = DEFAULT_LEFT;
        p.style.top = DEFAULT_TOP;
    }

    function onTriggerClick(e) {
        e.stopPropagation();
        if (!popup) return;
        if (popup.style.display === 'flex') {
            popup.style.display = 'none';
        } else {
            resetPopupGeometry(popup);
            popup.style.display = 'flex';
        }
    }

    function tryAttachTrigger(id) {
        if (attached[id]) return;
        var btn = document.getElementById(id);
        if (!btn) return;
        btn.addEventListener('click', onTriggerClick);
        attached[id] = true;
    }

    function attachShared() {
        if (!popup) popup = document.getElementById('competence-popup');
        if (!header) header = document.getElementById('competence-popup-header');
        if (!closeBtn) {
            closeBtn = document.getElementById('btn-competence-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', function () {
                    if (popup) popup.style.display = 'none';
                });
            }
        }
        if (!editBtn) {
            editBtn = document.getElementById('btn-competence-edit');
            if (editBtn) {
                editBtn.addEventListener('click', function () {
                    if (popup) popup.style.display = 'none';
                });
            }
        }
        if (!popup || !header || header.__dragWired) return;
        header.__dragWired = true;

        header.addEventListener('mousedown', function (e) {
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
        attachShared();
        TRIGGER_IDS.forEach(tryAttachTrigger);
    }

    // Dash renders components asynchronously — keep watching and wire up new
    // buttons as they appear (the two modal-based triggers mount lazily).
    var obs = new MutationObserver(wireAll);
    obs.observe(document.body, { childList: true, subtree: true });
    wireAll();
})();
