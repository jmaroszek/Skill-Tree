/* Match simulation results to the current browser selection, not arrival order. */
(function () {
    var session = window.crypto.randomUUID();
    var sequence = 0;
    var displayed = -1;
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.skillTreeSimulation = {
        request: function (node, soft, helps, depth, context, subcontext, done,
                           value, interest, time, difficulty, types, dormant,
                           hideBlocked, timeUnit, version, settings, activeTab) {
            return {
                session: session, sequence: ++sequence,
                node: activeTab === 'tab-details' ? node : null,
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
