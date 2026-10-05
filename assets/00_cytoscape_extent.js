/** Keep Cytoscape's read-only reports out of Dash while the graph is moving.
 *
 * dash-cytoscape reports `extent` five milliseconds after each viewport event.
 * During a pan/zoom tween that dispatches a Dash/React store update per frame
 * across every mounted tab. The graph renders directly from its live viewport;
 * none of our callbacks consume extent. Relay its latest value after 150 ms of
 * quiet.
 *
 * It also writes its live `elements`, now carrying positions, back to Dash
 * 100 ms after nodes are added or removed. That lands inside the layout those
 * nodes started: a store update carrying the whole graph, a React re-render
 * that diffs every element, and the callbacks that listen to the prop, all
 * competing with the animation for frames. layout_requests.js already ignores
 * this echo, so hold it until the canvas's layouts have stopped and relay the
 * latest one then, with the positions the layout settled on. Every other prop
 * is forwarded immediately.
 *
 * Dash loads the component bundles before assets. This React facade preserves
 * the component's public props and DOM; it changes only its setProps relay.
 */
(function () {
    'use strict';
    var components = window.dash_cytoscape, React = window.React;
    if (!components || !components.Cytoscape || !React) return;
    var Cytoscape = components.Cytoscape;

    // A layout whose stop never arrives must not strand the echo. The
    // longest animation is 1 s, after any synchronous layout work.
    var ELEMENTS_DEADLINE_MS = 4000;

    // Running layouts per Cytoscape instance, counted from its own events.
    function runningLayouts(cy) {
        if (!cy._skillTreeRunningLayouts) {
            cy._skillTreeRunningLayouts = {count: 0, waiting: []};
            cy.on('layoutstart', function () {
                cy._skillTreeRunningLayouts.count += 1;
            });
            cy.on('layoutstop', function () {
                var state = cy._skillTreeRunningLayouts;
                state.count = Math.max(0, state.count - 1);
                if (state.count) return;
                var waiting = state.waiting;
                state.waiting = [];
                waiting.forEach(function (fn) { fn(); });
            });
        }
        return cy._skillTreeRunningLayouts;
    }

    // A held echo carries the positions from when it was taken, early in the
    // layout. Relaying those would move every node back there, so it goes
    // out with the positions the nodes have now.
    function withLivePositions(cy, elements) {
        if (!cy || !Array.isArray(elements)) return elements;
        return elements.map(function (element) {
            var data = element && element.data;
            if (!data || data.source !== undefined || element.position === undefined) {
                return element;
            }
            var node = cy.getElementById(data.id);
            if (!node || !node.length) return element;
            var position = node.position();
            return Object.assign({}, element, {position: {x: position.x, y: position.y}});
        });
    }

    function liveCy(id) {
        var getCy = window.SkillTree && window.SkillTree.getCy;
        return id && getCy ? getCy(document.getElementById(id)) : null;
    }

    function SettledExtentCytoscape(props) {
        var send = React.useRef(props.setProps);
        send.current = props.setProps;
        var id = React.useRef(props.id);
        id.current = props.id;
        var timer = React.useRef(null);
        var pending = React.useRef(null);
        var held = React.useRef(null);
        var queued = React.useRef(false);
        var mounted = React.useRef(true);
        // New elements from Dash make a held echo stale: relaying it would
        // put the previous graph back. The new graph's own echo replaces it.
        var lastElements = React.useRef(props.elements);
        if (props.elements !== lastElements.current) {
            lastElements.current = props.elements;
            held.current = null;
        }
        var relay = React.useCallback(function (changes) {
            if (!mounted.current) return;
            var immediate = Object.assign({}, changes);
            if (Object.prototype.hasOwnProperty.call(changes, 'extent')) {
                pending.current = changes.extent;
                clearTimeout(timer.current);
                timer.current = setTimeout(function () {
                    timer.current = null;
                    send.current({extent: pending.current});
                }, 150);
                delete immediate.extent;
            }
            if (Object.prototype.hasOwnProperty.call(changes, 'elements')) {
                var cy = liveCy(id.current);
                var layouts = cy ? runningLayouts(cy) : null;
                if (layouts && layouts.count) {
                    held.current = {elements: changes.elements};
                    if (!queued.current) {
                        queued.current = true;
                        // Runs once: from the last layoutstop or the deadline.
                        var flushed = false;
                        var flush = function () {
                            if (flushed) return;
                            flushed = true;
                            clearTimeout(deadline);
                            queued.current = false;
                            var latest = held.current;
                            held.current = null;
                            if (!latest || !mounted.current) return;
                            send.current({elements: withLivePositions(
                                liveCy(id.current), latest.elements)});
                        };
                        var deadline = setTimeout(flush, ELEMENTS_DEADLINE_MS);
                        layouts.waiting.push(flush);
                    }
                    delete immediate.elements;
                } else if (held.current) {
                    // A newer report supersedes the held one.
                    held.current.elements = changes.elements;
                    delete immediate.elements;
                }
            }
            if (Object.keys(immediate).length) send.current(immediate);
        }, []);
        React.useEffect(function () {
            mounted.current = true;
            // Count from the start, so the first layout's echo is held too.
            var cy = liveCy(id.current);
            if (cy) runningLayouts(cy);
            return function () { mounted.current = false; clearTimeout(timer.current); };
        }, []);
        return React.createElement(Cytoscape, Object.assign({}, props, {setProps: relay}));
    }

    SettledExtentCytoscape.displayName = 'SettledExtentCytoscape';
    SettledExtentCytoscape.propTypes = Cytoscape.propTypes;
    SettledExtentCytoscape.defaultProps = Cytoscape.defaultProps;
    // Bundle exports can be read-only getters. Replace the namespace rather
    // than assigning to its Cytoscape property.
    window.dash_cytoscape = Object.assign({}, components, {Cytoscape: SettledExtentCytoscape});
})();
