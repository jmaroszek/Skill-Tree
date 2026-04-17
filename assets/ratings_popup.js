(function () {
    // Keep in sync with the inline style declared on #ratings-popup in layout.py.
    // These are reapplied each time the popup is opened so a prior drag/resize
    // doesn't persist across reopenings.
    var DEFAULT_WIDTH = '960px';
    var DEFAULT_HEIGHT = '710px';
    var DEFAULT_LEFT = '420px';
    var DEFAULT_TOP = '120px';

    function resetPopupGeometry(popup) {
        popup.style.width = DEFAULT_WIDTH;
        popup.style.height = DEFAULT_HEIGHT;
        popup.style.left = DEFAULT_LEFT;
        popup.style.top = DEFAULT_TOP;
    }

    function init() {
        const btn = document.getElementById('btn-ratings-info');
        const closeBtn = document.getElementById('btn-ratings-close');
        const editBtn = document.getElementById('btn-ratings-edit');
        const popup = document.getElementById('ratings-popup');
        const header = document.getElementById('ratings-popup-header');
        if (!btn || !popup || !header || !closeBtn) return;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (popup.style.display === 'flex') {
                popup.style.display = 'none';
            } else {
                resetPopupGeometry(popup);
                popup.style.display = 'flex';
            }
        });

        closeBtn.addEventListener('click', function () {
            popup.style.display = 'none';
        });

        if (editBtn) {
            editBtn.addEventListener('click', function () {
                popup.style.display = 'none';
            });
        }

        // Drag via header
        var dragging = false, startX, startY, origLeft, origTop;

        header.addEventListener('mousedown', function (e) {
            if (e.target === closeBtn || closeBtn.contains(e.target)) return;
            if (editBtn && (e.target === editBtn || editBtn.contains(e.target))) return;
            dragging = true;
            startX = e.clientX;
            startY = e.clientY;
            origLeft = popup.offsetLeft;
            origTop = popup.offsetTop;
            e.preventDefault();
        });

        document.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            popup.style.left = (origLeft + e.clientX - startX) + 'px';
            popup.style.top  = (origTop  + e.clientY - startY) + 'px';
        });

        document.addEventListener('mouseup', function () {
            dragging = false;
        });
    }

    // Dash renders components asynchronously — wait for the button to appear
    var obs = new MutationObserver(function () {
        if (document.getElementById('btn-ratings-info')) {
            obs.disconnect();
            init();
        }
    });
    obs.observe(document.body, { childList: true, subtree: true });
})();
