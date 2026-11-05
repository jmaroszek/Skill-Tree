/* The chevron on a native select (dbc.Select), drawn by a CSS paint worklet so
 * it can turn over like every other chevron in the app.
 *
 * A select has no box of its own to rotate: Electron's Chromium paints nothing
 * for ::picker-icon or ::after on one, and a background image can't turn. A
 * paint worklet can, because it redraws from a custom property that CSS can
 * transition (--select-chevron-turn, dropdowns.css). The glyph is the same V as
 * the other chevrons: path "m2 5 6 6 6-6" in a 16-unit box, stroke 2.
 *
 * Dash loads this file as a page script, and the worklet loads it again. The
 * page's copy registers the worklet; the worklet's copy registers the painter.
 */
(function () {
    if (typeof registerPaint === 'function') {
        registerPaint('select-chevron', class {
            static get inputProperties() {
                return ['--select-chevron-turn', '--st-chevron'];
            }
            paint(ctx, size, props) {
                var turn = parseFloat(String(props.get('--select-chevron-turn'))) || 0;
                var scale = Math.min(size.width, size.height) / 16;
                ctx.translate(size.width / 2, size.height / 2);
                ctx.rotate(turn * Math.PI / 180);
                ctx.scale(scale, scale);
                ctx.strokeStyle = String(props.get('--st-chevron')).trim() || '#999999';
                ctx.lineWidth = 2;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.beginPath();
                ctx.moveTo(-6, -3);
                ctx.lineTo(0, 3);
                ctx.lineTo(6, -3);
                ctx.stroke();
            }
        });
        return;
    }
    if (typeof CSS !== 'undefined' && CSS.paintWorklet && document.currentScript) {
        CSS.paintWorklet.addModule(document.currentScript.src);
    }
})();
