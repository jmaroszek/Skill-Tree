/* Match simulation results to the current browser selection, not arrival order. */
(function () {
    var session = window.crypto.randomUUID();
    var sequence = 0;
    var displayed = -1;
    var pendingNode = null;

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
                           settledToken, activeTab, freezeOn) {
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
                hideBlocked: hideBlocked, timeUnit: timeUnit
            };
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
            if (result.error) return [no, hidden, hidden, result.error];
            return [result.figure, result.resultsStyle, result.emptyStyle, result.caption];
        }
    };
})();
