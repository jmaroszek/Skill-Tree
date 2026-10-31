"""When assets/components/hover_tips.js opens and closes a tooltip.

The script runs in Node against a small stand-in for the page: elements with
boxes, a hit test, and a clock the test moves by hand. Pointer events arrive
in the order Chromium sends them: leave, enter, then the move. A page that
changes under a still pointer sends nothing, as Chromium doesn't.
"""
import shutil
import subprocess

import pytest

from support.paths import asset_file

_PAGE = r'''
const assert = require('node:assert/strict');

// --- The clock ---------------------------------------------------------
let now = 0, nextTimer = 1;
const timers = new Map();
global.setTimeout = (fn, ms) => { timers.set(nextTimer, {fn, at: now + (ms || 0)}); return nextTimer++; };
global.setInterval = (fn, ms) => { timers.set(nextTimer, {fn, at: now + ms, every: ms}); return nextTimer++; };
global.clearTimeout = global.clearInterval = id => { timers.delete(id); };
Date.now = () => now;
const settle = () => new Promise(resolve => setImmediate(resolve));
async function wait(ms) {
    const end = now + ms;
    for (;;) {
        let due = null;
        for (const [id, t] of timers) if (t.at <= end && (!due || t.at < due[1].at)) due = [id, t];
        if (!due) break;
        const [id, t] = due;
        now = t.at;
        if (t.every) t.at += t.every; else timers.delete(id);
        t.fn();
        await settle();
    }
    now = end;
    await settle();
}

// --- The page ----------------------------------------------------------
class Text {
    constructor(data) { this.nodeType = 3; this.data = data; }
    get textContent() { return this.data; }
    cloneNode() { return new Text(this.data); }
}
class El {
    constructor(tag, attrs = {}, box = null) {
        this.tagName = tag.toUpperCase(); this.nodeType = 1;
        this.attrs = new Map(Object.entries(attrs)); this.childNodes = [];
        this.parentElement = null; this.box = box; this.style = {}; this.listeners = [];
        this.scrollWidth = 0; this.clientWidth = 0; this.clientHeight = 0;
        const el = this;
        this.classList = {
            contains: c => el.classes().includes(c),
            add: (...cs) => el.setAttribute('class', [...new Set([...el.classes(), ...cs])].join(' ')),
            remove: (...cs) => el.setAttribute('class', el.classes().filter(c => !cs.includes(c)).join(' ')),
        };
    }
    classes() { return (this.getAttribute('class') || '').split(/\s+/).filter(Boolean); }
    get id() { return this.getAttribute('id') || ''; }
    set className(v) { this.setAttribute('class', v); }
    get className() { return this.getAttribute('class') || ''; }
    hasAttribute(n) { return this.attrs.has(n); }
    getAttribute(n) { return this.attrs.has(n) ? this.attrs.get(n) : null; }
    setAttribute(n, v) { this.attrs.set(n, String(v)); }
    get parentNode() { return this.parentElement; }
    append(...nodes) { for (const n of nodes) this.appendChild(n); }
    appendChild(n) {
        if (n.parentElement) n.parentElement.removeChild(n);
        n.parentElement = this; this.childNodes.push(n); return n;
    }
    removeChild(n) { this.childNodes = this.childNodes.filter(c => c !== n); n.parentElement = null; return n; }
    remove() { if (this.parentElement) this.parentElement.removeChild(this); }
    replaceChildren(...nodes) { for (const c of this.childNodes) c.parentElement = null; this.childNodes = []; this.append(...nodes); }
    get textContent() { return this.childNodes.map(c => c.textContent).join(''); }
    set textContent(v) { this.replaceChildren(new Text(String(v))); }
    cloneNode() {
        const copy = new El(this.tagName, Object.fromEntries(this.attrs));
        copy.append(...this.childNodes.map(c => c.cloneNode(true)));
        return copy;
    }
    get isConnected() { let n = this; while (n.parentElement) n = n.parentElement; return n === html; }
    contains(other) { for (let n = other; n; n = n.parentElement) if (n === this) return true; return false; }
    getBoundingClientRect() {
        const b = this.box || {x: 0, y: 0, w: 0, h: 0};
        return {x: b.x, y: b.y, left: b.x, top: b.y, width: b.w, height: b.h, right: b.x + b.w, bottom: b.y + b.h};
    }
    get offsetWidth() { return this.box ? this.box.w : 0; }
    get offsetHeight() { return this.box ? this.box.h : 0; }
    addEventListener(type, fn, options) {
        this.listeners.push({type, fn, capture: options === true || !!(options && options.capture)});
    }
    fire(event, capture) {
        for (const l of this.listeners) if (l.type === event.type && l.capture === capture) l.fn(event);
    }
    // The topmost element with a box at (x, y): later siblings sit on top.
    hit(x, y) {
        if (this.hasAttribute('hidden')) return null;
        for (let i = this.childNodes.length - 1; i >= 0; i--) {
            const c = this.childNodes[i];
            const found = c.nodeType === 1 && c.hit(x, y);
            if (found) return found;
        }
        const b = this.box;
        return b && x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h ? this : null;
    }
    *all() { yield this; for (const c of this.childNodes) if (c.nodeType === 1) yield* c.all(); }
}

const html = new El('html');
html.clientWidth = 1000; html.clientHeight = 800;
const body = new El('body', {}, {x: 0, y: 0, w: 1000, h: 800});
html.appendChild(body);
const windowListeners = new El('window');
const documentListeners = new El('document');
global.window = {
    addEventListener: (...a) => windowListeners.addEventListener(...a),
    SkillTree: {tooltip: {hide: () => { cardHides += 1; }}},
};
global.document = {
    documentElement: html, body, hidden: false,
    addEventListener: (...a) => documentListeners.addEventListener(...a),
    createElement: tag => new El(tag),
    getElementById: id => [...html.all()].find(el => el.id === id) || null,
    getElementsByClassName: c => [...html.all()].filter(el => el.classList.contains(c)),
    elementFromPoint: (x, y) => html.hit(x, y),
};
let cardHides = 0;

function el(tag, attrs, box, text) {
    const e = new El(tag, attrs, box);
    if (text) e.textContent = text;
    return e;
}
const save = el('button', {id: 'save'}, {x: 100, y: 100, w: 40, h: 30});
const icon = el('i', {}, {x: 110, y: 105, w: 20, h: 20});
save.appendChild(icon);
const top = el('button', {id: 'top'}, {x: 300, y: 2, w: 40, h: 30});
const quiet = el('button', {id: 'quiet'}, {x: 200, y: 100, w: 40, h: 30});
const row = el('div', {'data-hint': 'Row hint'}, {x: 100, y: 300, w: 400, h: 20});
const name = el('span', {class: 'overflow-hint'}, {x: 100, y: 300, w: 100, h: 20}, 'A long name');
name.scrollWidth = 300; name.clientWidth = 100;
row.appendChild(name);
body.append(
    el('div', {id: 'tooltip-config', 'data-show': '700'}),
    save, top, quiet, row,
    el('div', {class: 'tooltip-source', hidden: '', 'data-tooltip-for': 'save', 'data-placement': 'bottom'}, null, 'Save the node'),
    el('div', {class: 'tooltip-source', hidden: '', 'data-tooltip-for': 'top', 'data-placement': 'top'}, null, 'At the top'),
    el('div', {class: 'tooltip-source', hidden: '', 'data-tooltip-for': 'quiet'}),
);

// --- The pointer, as Chromium reports it --------------------------------
const pointer = {x: null, y: null, over: null};
function dispatch(target, type, init = {}) {
    const event = Object.assign({type, target, relatedTarget: null, buttons: 0}, init);
    const path = [];
    for (let n = target; n; n = n.parentElement) path.push(n);
    for (const n of [windowListeners, documentListeners, ...path.slice().reverse()]) n.fire(event, true);
    for (const n of [...path, documentListeners, windowListeners]) n.fire(event, false);
}
function move(x, y) {
    const over = document.elementFromPoint(x, y);
    if (over !== pointer.over) {
        if (pointer.over) dispatch(pointer.over, 'mouseout', {clientX: x, clientY: y, relatedTarget: over});
        if (over) dispatch(over, 'mouseover', {clientX: x, clientY: y, relatedTarget: pointer.over});
    }
    Object.assign(pointer, {x, y, over});
    if (over) dispatch(over, 'mousemove', {clientX: x, clientY: y});
}
const middle = e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; };
const away = () => move(700, 600);
function tip() {
    const t = body.childNodes.find(c => c.classList && c.classList.contains('hover-tip'));
    return t && t.classList.contains('show') ? t : null;
}
const text = () => tip() && tip().textContent;
'''

_SCENARIOS = r'''
(async () => {
    require(process.argv[1]);

    // It opens after the delay, below the target as asked, and closes the
    // moment the pointer leaves.
    away(); move(...middle(save));
    await wait(600);
    assert.equal(tip(), null, 'not before the delay');
    await wait(150);
    assert.equal(text(), 'Save the node');
    assert.ok(tip().classList.contains('bs-tooltip-bottom'));
    away();
    assert.equal(tip(), null, 'closed the moment the pointer left');

    // A pointer that passes through opens nothing.
    await wait(1000);
    move(...middle(save)); await wait(40); away();
    await wait(1000);
    assert.equal(tip(), null, 'a pass opens nothing');

    // A press closes it, and nothing opens there until the pointer has left.
    move(...middle(save)); await wait(750);
    assert.ok(tip());
    dispatch(icon, 'pointerdown', {clientX: pointer.x, clientY: pointer.y});
    assert.equal(tip(), null, 'a press closes it');
    move(103, 102); await wait(1000);
    assert.equal(tip(), null, 'still nothing anywhere on what was pressed');
    away(); move(...middle(save)); await wait(750);
    assert.equal(text(), 'Save the node', 'opens again after leaving');

    // A key closes it; a modifier held to click or read doesn't.
    dispatch(body, 'keydown', {key: 'Shift'});
    assert.ok(tip(), 'Shift leaves it');
    const hidesBefore = cardHides;
    dispatch(body, 'keydown', {key: 'a'});
    assert.equal(tip(), null, 'a key closes it');
    assert.equal(cardHides, hidesBefore + 1, 'and the node card');

    // Off the window closes it.
    away(); move(...middle(save)); await wait(750);
    dispatch(save, 'mouseout', {clientX: pointer.x, clientY: pointer.y, relatedTarget: null});
    pointer.over = null;
    assert.equal(tip(), null, 'off the window');

    // A target that slides in under a still pointer opens nothing until the
    // pointer moves. Chromium reports no hover for it.
    away(); await wait(1000);
    save.box = {x: 680, y: 585, w: 40, h: 30};
    await wait(1000);
    assert.equal(tip(), null, 'nothing under a still pointer');
    move(pointer.x + 1, pointer.y); await wait(750);
    assert.equal(text(), 'Save the node', 'opens once the pointer moves');

    // Chromium can report a hover with no move after a scroll or a redraw.
    // It opens nothing either.
    save.box = {x: 100, y: 100, w: 40, h: 30};
    away(); await wait(1000);
    save.box = {x: 680, y: 585, w: 40, h: 30};
    dispatch(save, 'mouseover', {clientX: pointer.x, clientY: pointer.y, relatedTarget: null});
    dispatch(save, 'mousemove', {clientX: pointer.x, clientY: pointer.y});
    pointer.over = save;
    await wait(1000);
    assert.equal(tip(), null, 'a hover with no move opens nothing');
    move(pointer.x, pointer.y + 1); await wait(750);
    assert.equal(text(), 'Save the node');

    // A target that slides away, is covered or vanishes closes its tooltip
    // within a check, though no event says so.
    save.box = {x: 100, y: 100, w: 40, h: 30};
    await wait(100);
    assert.equal(tip(), null, 'slid out from under the pointer');
    move(...middle(save)); await wait(750);
    assert.ok(tip());
    const cover = el('div', {}, {x: 0, y: 0, w: 1000, h: 800});
    body.appendChild(cover);
    await wait(100);
    assert.equal(tip(), null, 'covered');
    cover.remove();
    move(pointer.x + 1, pointer.y); await wait(750);
    assert.ok(tip());
    save.remove();
    await wait(100);
    assert.equal(tip(), null, 'gone');
    body.appendChild(save);

    // An empty tooltip shows nothing.
    away(); move(...middle(quiet)); await wait(1000);
    assert.equal(tip(), null, 'empty');

    // A tooltip with no room on its side takes the other one.
    away(); move(...middle(top)); await wait(750);
    assert.equal(text(), 'At the top');
    assert.ok(tip().classList.contains('bs-tooltip-bottom'), 'flipped below');

    // data-hint shows its text; overflow-hint its own, only while cut off.
    away(); move(450, 310); await wait(750);
    assert.equal(text(), 'Row hint');
    away(); move(...middle(name)); await wait(750);
    assert.equal(text(), 'A long name');
    name.scrollWidth = 100;
    away(); move(...middle(name)); await wait(750);
    assert.equal(text(), 'Row hint', 'a name that fits defers to its row');

    // Warm handoff: right after one tooltip, the next opens almost at once.
    away(); await wait(1000);
    move(...middle(save)); await wait(750);
    assert.ok(tip());
    away(); await wait(200);
    move(...middle(top)); await wait(60);
    assert.equal(text(), 'At the top', 'handed off');
    // A pass is still a pass, warm or not.
    away(); move(...middle(save)); await wait(20);
    assert.equal(tip(), null, 'a warm pass shows nothing on the way');
    away(); await wait(1000);
    assert.equal(tip(), null, 'a warm pass opens nothing');
    // A target the pointer only waited on warms nothing.
    move(...middle(save)); await wait(300); away();
    move(...middle(top)); await wait(100);
    assert.equal(tip(), null, 'waiting warms nothing');
    away(); await wait(1000);
    // Waiting on a target doesn't keep it warm: warmth runs out.
    move(...middle(save)); await wait(750);
    away(); await wait(600);
    move(...middle(top)); await wait(100);
    assert.equal(tip(), null, 'cold again');
    await wait(650);
    assert.ok(tip());
    // A tooltip closed on purpose hands nothing off.
    dispatch(body, 'keydown', {key: 'a'});
    away(); move(...middle(save)); await wait(100);
    assert.equal(tip(), null, 'no handoff after a key');

    // In the desktop window, the shell's cursor off the target closes it:
    // the OS took the pointer into the title bar without telling the page.
    let cursor = {x: 120, y: 115};
    window.skillTreeDesktop = {cursorPoint: () => Promise.resolve(cursor)};
    away(); move(...middle(save)); await wait(750);
    assert.equal(text(), 'Save the node', 'the cursor is on it');
    cursor = {x: 120, y: 20};
    await wait(100);
    assert.equal(tip(), null, 'escaped into the title bar');
    away(); move(...middle(save)); await wait(750);
    assert.equal(tip(), null, 'never opens while the cursor is elsewhere');
})().catch(error => { console.error(error); process.exit(1); });
'''


def test_tooltips_open_on_a_deliberate_hover_and_close_whenever_it_ends():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to run hover_tips.js")
    result = subprocess.run(
        [node, "-e", _PAGE + _SCENARIOS, str(asset_file("hover_tips.js"))],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
