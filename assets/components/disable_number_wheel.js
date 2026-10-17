/**
 * Disable scroll-wheel value changes on <input type="number">.
 *
 * Browser default: a focused number input increments/decrements its value
 * when the mousewheel scrolls over it. That clobbers time estimates (and
 * other numeric fields) when the user is just trying to scroll the editor.
 *
 * Fix: blur any number input that receives a wheel event. The wheel then
 * propagates as a normal page scroll, and the input value is left alone.
 */
document.addEventListener('wheel', function (e) {
    var t = e.target;
    if (t && t.tagName === 'INPUT' && t.type === 'number' && document.activeElement === t) {
        t.blur();
    }
}, { passive: true });
