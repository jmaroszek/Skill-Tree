/**
 * Put back the browser's own trim and number-parsing functions.
 *
 * Dash loads a core-js 2 polyfill before anything else. core-js treats U+180E
 * as whitespace and modern engines don't, so it calls their trim
 * non-compliant and replaces it: String.prototype.trim and its trimStart and
 * trimEnd, and parseFloat and parseInt, which it builds on its own trim. The
 * replacements run 13 to 60 times slower, and they hide it by reporting
 * "[native code]". Cytoscape parses numbers and trims strings constantly while
 * it reads styles, so this cost about 0.16 s of main-thread work on the Nodes
 * canvas's first load alone.
 *
 * A fresh iframe realm still has the native functions. They return plain
 * strings and numbers, so functions from the other realm are safe to install
 * here, and they keep working after the iframe is removed. Functions that
 * return arrays or objects are left alone: those would come back belonging to
 * the other realm.
 *
 * Asset scripts run after the polyfill. This also runs again once the page
 * has loaded, in case a later bundle polyfills again.
 */
(function () {
    'use strict';

    var NAMES = ['trim', 'trimStart', 'trimEnd', 'trimLeft', 'trimRight'];

    function install(target, name, native) {
        if (typeof native !== 'function' || target[name] === native) return;
        Object.defineProperty(target, name, {
            value: native, writable: true, configurable: true, enumerable: false,
        });
    }

    function restore() {
        var host = document.body || document.documentElement;
        if (!host || typeof document.createElement !== 'function') return;
        var frame = document.createElement('iframe');
        frame.style.display = 'none';
        host.appendChild(frame);
        try {
            var pristine = frame.contentWindow && frame.contentWindow.String
                && frame.contentWindow.String.prototype;
            if (!pristine) return;
            var win = frame.contentWindow;
            NAMES.forEach(function (name) {
                install(String.prototype, name, pristine[name]);
            });
            ['parseFloat', 'parseInt'].forEach(function (name) {
                install(window, name, win[name]);
                install(Number, name, win[name]);
            });
        } finally {
            frame.remove();
        }
    }

    restore();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restore);
    }
})();
