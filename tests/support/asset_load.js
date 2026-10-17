// Run the app's asset scripts in the order Dash loads them, against a stand-in
// for the browser, and report any that throw while loading.
//
// Usage: node asset_load.js <order.json>
// order.json: {"canvases": [...], "scripts": [path, ...]}
//
// Everything the page provides is a permissive stub, so a script can touch
// the DOM, observers and timers freely. window.SkillTree is a real object,
// holding only what the page's inline script gives it (the canvases) and
// what earlier scripts added. A script that reads a SkillTree name before
// the script defining it has loaded throws, and is reported.
'use strict';
const fs = require('node:fs');

const {canvases, scripts} = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

function stub() {
    const fn = function () { return stub(); };
    return new Proxy(fn, {
        get(target, key) {
            if (key === Symbol.toPrimitive) return () => '';
            if (key === 'then') return undefined;  // not a promise
            if (key === Symbol.iterator) return function* () {};
            if (key in target) return target[key];
            return stub();
        },
        apply() { return stub(); },
        construct() { return stub(); },
    });
}

// Node has these too, but a page script must not run them: a timer would keep
// the process alive, and nothing here is a real browser to talk to.
const BROWSER_ONLY = new Set([
    'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'setImmediate',
    'queueMicrotask', 'requestAnimationFrame', 'fetch', 'navigator', 'localStorage',
    'sessionStorage', 'location', 'BroadcastChannel', 'MessageChannel', 'WebSocket',
]);

// The page's globals: real for SkillTree and the JavaScript builtins, a stub
// for anything else a script names.
const page = {SkillTree: {canvases}};
const scope = new Proxy(page, {
    has(target, key) {
        return typeof key === 'string' && (!(key in globalThis) || BROWSER_ONLY.has(key));
    },
    get(target, key) {
        if (key === Symbol.unscopables) return undefined;
        if (key in target) return target[key];
        if (key === 'window' || key === 'self' || key === 'globalThis') return scope;
        return stub();
    },
    set(target, key, value) {
        target[key] = value;
        return true;
    },
});

const failures = [];
for (const path of scripts) {
    if (process.env.ASSET_LOAD_TRACE) process.stderr.write(path + '\n');
    const source = fs.readFileSync(path, 'utf8');
    try {
        new Function('__scope', 'with (__scope) {\n' + source + '\n}')(scope);
    } catch (error) {
        failures.push(`${path}: ${error && error.stack ? error.stack.split('\n')[0] : error}`);
    }
}
console.log(JSON.stringify(failures));
process.exit(0);
