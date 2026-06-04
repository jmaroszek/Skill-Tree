// Custom window controls for the frameless native (pywebview) window.
//
// In a normal browser tab, window.pywebview is undefined: the controls stay
// hidden (display:none from the layout) and none of this runs, so the app
// behaves exactly as before. In the native window, pywebview injects its JS
// API; we then reveal the min/maximize/close buttons and wire them to the
// _WindowControls methods exposed from app.py.
(function () {
    "use strict";

    function wire() {
        var minBtn = document.getElementById("win-ctl-min");
        var maxBtn = document.getElementById("win-ctl-max");
        var closeBtn = document.getElementById("win-ctl-close");

        if (minBtn) minBtn.addEventListener("click", function () {
            window.pywebview.api.minimize();
        });
        if (maxBtn) maxBtn.addEventListener("click", function () {
            window.pywebview.api.toggle_maximize().then(function (maximized) {
                var icon = maxBtn.querySelector("i");
                if (icon) icon.className = maximized ? "bi bi-copy" : "bi bi-square";
            });
        });
        if (closeBtn) closeBtn.addEventListener("click", function () {
            window.pywebview.api.close();
        });

        // The whole top bar is the drag region (.pywebview-drag-region). Stop
        // mousedown on interactive elements from bubbling to it, so clicking a
        // tab or button never accidentally starts a window drag.
        var bar = document.getElementById("main-toolbar");
        if (bar) {
            bar.querySelectorAll("button, a, input, .nav-link").forEach(function (el) {
                el.addEventListener("mousedown", function (e) { e.stopPropagation(); });
            });
        }
    }

    function ready() {
        return window.pywebview && window.pywebview.api &&
               document.getElementById("window-controls");
    }

    // Dash builds the layout client-side after load, and pywebview injects its
    // API asynchronously, so poll until both exist — then reveal + wire once.
    var tries = 0;
    var timer = setInterval(function () {
        tries += 1;
        if (ready()) {
            clearInterval(timer);
            document.getElementById("window-controls").style.display = "flex";
            wire();
        } else if (tries > 100) {   // ~20s; give up quietly (e.g. browser mode)
            clearInterval(timer);
        }
    }, 200);
})();
