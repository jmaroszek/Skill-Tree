(function () {
    function init() {
        const btn = document.getElementById('btn-ratings-info');
        const closeBtn = document.getElementById('btn-ratings-close');
        const editBtn = document.getElementById('btn-ratings-edit');
        const popup = document.getElementById('ratings-popup');
        const header = document.getElementById('ratings-popup-header');
        if (!btn || !popup || !header || !closeBtn) return;

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            popup.style.display = popup.style.display === 'flex' ? 'none' : 'flex';
        });

        closeBtn.addEventListener('click', function () {
            popup.style.display = 'none';
        });

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
