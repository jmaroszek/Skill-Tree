/** Coalesce Cytoscape's read-only viewport metadata while it is moving.
 *
 * dash-cytoscape reports `extent` five milliseconds after each viewport event.
 * During a pan/zoom tween that dispatches a Dash/React store update per frame
 * across every mounted tab. The graph renders directly from its live viewport;
 * none of our callbacks consume extent. Relay its latest value after 150 ms of
 * quiet, and forward every other prop immediately.
 *
 * Dash loads the component bundles before assets. This React facade preserves
 * the component's public props and DOM; it changes only its setProps relay.
 */
(function () {
    'use strict';
    var components = window.dash_cytoscape, React = window.React;
    if (!components || !components.Cytoscape || !React) return;
    var Cytoscape = components.Cytoscape;

    function SettledExtentCytoscape(props) {
        var send = React.useRef(props.setProps);
        send.current = props.setProps;
        var timer = React.useRef(null);
        var pending = React.useRef(null);
        var mounted = React.useRef(true);
        var relay = React.useCallback(function (changes) {
            if (!mounted.current) return;
            if (Object.prototype.hasOwnProperty.call(changes, 'extent')) {
                pending.current = changes.extent;
                clearTimeout(timer.current);
                timer.current = setTimeout(function () {
                    timer.current = null;
                    send.current({extent: pending.current});
                }, 150);
            }
            var immediate = Object.assign({}, changes);
            delete immediate.extent;
            if (Object.keys(immediate).length) send.current(immediate);
        }, []);
        React.useEffect(function () {
            mounted.current = true;
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
