/** Ambient Now borders, without animating Cytoscape's full graph renderer.
 *
 * The static border stays on the node. A transparent SVG behind the graph
 * pulses its outer edge; node fills and labels still paint above the pulse.
 * Follow Cytoscape renders for pan, zoom, dragging and layouts, and scan for
 * class/style changes. Nothing here starts or stops a node animation.
 */
(function () {
    'use strict';
    var ST = window.SkillTree;
    var NS = 'http://www.w3.org/2000/svg';
    var layers = new Map();
    var POLYGONS = {triangle: 3, rectangle: 4, pentagon: 5, hexagon: 6, octagon: 8};

    function attr(el, name, value) {
        value = String(value);
        if (el.getAttribute(name) !== value) el.setAttribute(name, value);
    }

    // The ten shapes offered by Settings, using Cytoscape's normalized
    // polygon geometry. Unknown/custom shapes retain their static border.
    function polygon(shape) {
        if (shape === 'diamond') return [[0, 1], [1, 0], [0, -1], [-1, 0]];
        if (shape === 'vee') return [[-1, -1], [0, -0.333], [1, -1], [0, 1]];
        var sides = POLYGONS[shape] || (shape === 'star' ? 5 : 0);
        if (!sides) return null;
        var points = [], step = 2 * Math.PI / sides;
        var start = Math.PI / 2 + (sides % 2 === 0 ? step / 2 : 0);
        var inner = 0.5 * (3 - Math.sqrt(5)) * 1.57;
        for (var i = 0; i < sides; i++) {
            var angle = start + i * step;
            points.push([Math.cos(angle), -Math.sin(angle)]);
            if (shape === 'star') points.push([
                inner * Math.cos(angle + step / 2), -inner * Math.sin(angle + step / 2)
            ]);
        }
        var xs = points.map(function (p) { return p[0]; });
        var ys = points.map(function (p) { return p[1]; });
        var sx = 2 / (Math.max.apply(null, xs) - Math.min.apply(null, xs));
        var sy = 2 / (Math.max.apply(null, ys) - Math.min.apply(null, ys));
        var top = Math.min.apply(null, ys) * sy;
        return points.map(function (p) { return [p[0] * sx, p[1] * sy - 1 - top]; });
    }

    function outline(shape, width, height) {
        var x = width / 2, y = height / 2;
        if (shape === 'ellipse') return 'M ' + -x + ' 0 A ' + x + ' ' + y +
            ' 0 1 0 ' + x + ' 0 A ' + x + ' ' + y + ' 0 1 0 ' + -x + ' 0 Z';
        if (shape === 'round-rectangle') {
            var r = Math.min(width / 4, height / 4, 8);
            return 'M ' + (-x + r) + ' ' + -y + ' H ' + (x - r) +
                ' A ' + r + ' ' + r + ' 0 0 1 ' + x + ' ' + (-y + r) + ' V ' + (y - r) +
                ' A ' + r + ' ' + r + ' 0 0 1 ' + (x - r) + ' ' + y + ' H ' + (-x + r) +
                ' A ' + r + ' ' + r + ' 0 0 1 ' + -x + ' ' + (y - r) + ' V ' + (-y + r) +
                ' A ' + r + ' ' + r + ' 0 0 1 ' + (-x + r) + ' ' + -y + ' Z';
        }
        var points = polygon(shape);
        return points && points.map(function (p, i) {
            return (i ? 'L ' : 'M ') + p[0] * x + ' ' + p[1] * y;
        }).join(' ') + ' Z';
    }

    function visible(wrapper) {
        return !document.hidden && wrapper.getClientRects().length > 0;
    }

    function sync(layer) {
        var cy = layer.cy, wrapper = layer.wrapper;
        var show = visible(wrapper);
        attr(layer.svg, 'visibility', show ? 'visible' : 'hidden');
        // display:none also suspends the SVG animation when switching tabs.
        if (!show) {
            if (layer.svg.style.display !== 'none') layer.svg.style.display = 'none';
            return;
        }
        var pan = cy.pan(), zoom = cy.zoom();
        attr(layer.group, 'transform', 'translate(' + pan.x + ' ' + pan.y + ') scale(' + zoom + ')');
        var live = new Set();
        cy.nodes('.now').forEach(function (node) {
            if (!node.visible() || node.hasClass('locate-pulse') || node.hasClass('dormant')) return;
            var path = outline(node.style('shape'), node.width(), node.height());
            if (!path) return;
            var id = node.id(), el = layer.nodes.get(id);
            live.add(id);
            if (!el) {
                el = document.createElementNS(NS, 'path');
                attr(el, 'data-node-id', id);
                layer.group.appendChild(el);
                layer.nodes.set(id, el);
            }
            var pos = node.position();
            attr(el, 'd', path);
            attr(el, 'transform', 'translate(' + pos.x + ' ' + pos.y + ')');
            attr(el, 'stroke', node.style('border-color'));
            attr(el, 'opacity', node.style('opacity'));
        });
        layer.nodes.forEach(function (el, id) {
            if (!live.has(id)) { el.remove(); layer.nodes.delete(id); }
        });
        var display = layer.nodes.size ? '' : 'none';
        if (layer.svg.style.display !== display) layer.svg.style.display = display;
    }

    function remove(layer) {
        layer.cy.off('render', layer.render);
        layer.svg.remove();
    }

    function scan(canvas) {
        var wrapper = document.getElementById(canvas.cytoscapeId);
        var cy = ST.getCy(wrapper), layer = layers.get(canvas.cytoscapeId);
        if (cy && cy.destroyed()) cy = null;
        if (layer && (layer.cy !== cy || layer.wrapper !== wrapper || !layer.svg.isConnected)) {
            remove(layer);
            layers.delete(canvas.cytoscapeId);
            layer = null;
        }
        if (!cy) return;
        if (!layer) {
            wrapper.classList.add('now-pulse-host');
            var svg = document.createElementNS(NS, 'svg');
            attr(svg, 'class', 'now-pulse-layer');
            attr(svg, 'aria-hidden', 'true');
            attr(svg, 'focusable', 'false');
            var group = document.createElementNS(NS, 'g');
            svg.appendChild(group);
            // Below Cytoscape's own drawing layers, above the wrapper's bg.
            wrapper.insertBefore(svg, wrapper.firstChild);
            layer = {cy: cy, wrapper: wrapper, svg: svg, group: group, nodes: new Map()};
            layer.render = function () { sync(layer); };
            cy.on('render', layer.render);
            layers.set(canvas.cytoscapeId, layer);
        }
        sync(layer);
    }

    function scanAll() { window.SkillTree.canvases.forEach(scan); }
    document.addEventListener('visibilitychange', scanAll);
    setInterval(scanAll, 250);
})();
