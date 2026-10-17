/**
 * Stamp each Nodes render, and tell both covers it arrived.
 * engine/callbacks.py registers it.
 */
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.canvas_payload = window.dash_clientside.canvas_payload || {};

// `loaded` stays true once the canvas has had elements.
window.dash_clientside.canvas_payload.stamp = function (pending, previous) {
    if (window.SkillTree && window.SkillTree.notifyCanvasElements) {
        window.SkillTree.notifyCanvasElements(pending);
    }
    if (window.SkillTree && window.SkillTree.notifyStartupPayload) {
        window.SkillTree.notifyStartupPayload(pending);
    }
    var loaded = Boolean(previous && previous.loaded);
    var nodes = previous ? previous.nodes : null;
    if (Array.isArray(pending)) {
        loaded = true;
        nodes = pending.filter(function (element) {
            return element && element.data && element.data.source == null;
        }).length;
    }
    return {loaded: loaded, nodes: nodes, at: Date.now()};
};
