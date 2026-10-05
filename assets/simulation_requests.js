/* Match simulation results to the current browser selection, not arrival order.
 *
 * Every request goes to the chart (details-sim-request). Only requests the
 * server has work in goes to it (details-sim-server-request): one that names
 * a node, or a node-less one while an earlier simulation may still be
 * running, which it cancels. A selection sends a node-less request while its
 * layout animates. With nothing to cancel, its round trip did nothing but
 * compete with the animation for frames.
 */
(function () {
    var session = window.crypto.randomUUID();
    var sequence = 0;
    var displayed = -1;
    var pendingNode = null;
    // The sequence of the newest node request the server hasn't answered.
    // A cancelled one is never answered, so this stays set until a
    // forwarded request supersedes it.
    var inFlight = null;

    function forward(request) {
        var no = window.dash_clientside.no_update;
        if (!request || request === no) return no;
        if (request.node) {
            inFlight = request.sequence;
            return request;
        }
        if (inFlight === null) return no;
        inFlight = null;
        return request;
    }

    var layoutInputs = new Set([
        'details-selected-node-store',
        'details-include-soft-needs',
        'details-include-synergies',
        'details-max-depth',
        'filter-context',
        'filter-subcontext',
        'filter-done',
        'filter-value',
        'filter-interest',
        'filter-time',
        'filter-time-min',
        'filter-difficulty',
        'filter-node-type',
        'filter-dormant',
        'details-hide-blocked',
        'graph-version-store'
    ]);

    function triggeredIds() {
        var context = window.dash_clientside.callback_context;
        var triggered = context && context.triggered ? context.triggered : [];
        return triggered.map(function (item) {
            return String(item.prop_id || '').split('.')[0];
        });
    }

    function settledRoot(token) {
        try {
            return JSON.parse(token || '{}').root || null;
        } catch (error) {
            return null;
        }
    }

    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.skillTreeSimulation = {
        request: function (node, soft, helps, depth, context, subcontext, done,
                           value, interest, time, difficulty, types, dormant,
                           hideBlocked, timeUnit, version, settings,
                           settledToken, activeTab, timeMin, freezeOn) {
            var activeNode = activeTab === 'tab-details' ? node : null;
            var triggered = triggeredIds();
            var layoutChanged = triggered.some(function (id) {
                return layoutInputs.has(id);
            });
            var settledChanged = triggered.indexOf(
                'details-simulation-settled-trigger-input'
            ) !== -1;
            var wasPending = pendingNode === activeNode;

            // Every settled layout emits this signal, including the ones a
            // graph-settings slider starts — and nothing was waiting on those.
            // Issuing a request anyway would bump the sequence, orphan the
            // result already on screen and flash "Calculating…" for numbers
            // that cannot have changed.
            if (settledChanged && !layoutChanged && activeNode && !wasPending) {
                return window.dash_clientside.no_update;
            }

            if (!activeNode) {
                pendingNode = null;
            } else if (freezeOn) {
                pendingNode = null;
            } else {
                if (layoutChanged) pendingNode = activeNode;
                if (settledChanged && settledRoot(settledToken) === activeNode) {
                    pendingNode = null;
                }
            }

            var waitingForLayout = Boolean(
                activeNode && !freezeOn && pendingNode === activeNode
            );
            return {
                session: session, sequence: ++sequence,
                node: waitingForLayout ? null : activeNode,
                waitingForLayout: waitingForLayout,
                soft: soft, helps: helps, depth: depth,
                context: context, subcontext: subcontext, done: done,
                value: value, interest: interest, time: time,
                difficulty: difficulty, types: types, dormant: dormant,
                hideBlocked: hideBlocked, timeUnit: timeUnit, timeMin: timeMin
            };
        },
        // The registered callback: the chart's request, and the server's.
        requestAndForward: function () {
            var request = window.dash_clientside.skillTreeSimulation.request
                .apply(null, arguments);
            return [request, forward(request)];
        },
        render: function (result, request) {
            var no = window.dash_clientside.no_update;
            var hidden = {display: 'none'};
            var visible = {display: 'block'};
            if (request && request.waitingForLayout) {
                return [no, hidden, hidden, 'Calculating…'];
            }
            if (!request || !request.node) return [no, hidden, visible, ''];
            var matches = result && result.session === request.session &&
                result.sequence === request.sequence;
            if (!matches) {
                // An older response arriving after the latest one must not
                // hide an already-correct chart or re-enable a loading state.
                if (displayed === request.sequence) return [no, no, no, no];
                return [no, hidden, hidden, 'Calculating…'];
            }
            displayed = request.sequence;
            if (inFlight !== null && result.sequence >= inFlight) inFlight = null;
            if (result.error) return [no, hidden, hidden, result.error];
            return [result.figure, result.resultsStyle, result.emptyStyle, result.caption];
        }
    };
})();
