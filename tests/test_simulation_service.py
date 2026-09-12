"""Simulation budget, cancellation, deterministic reuse, and UI response order."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

import simulation_service as service_module
from simulation import simulate_task_chain, SimulationCancelled, _sample_node
from simulation_service import SimulationService, effective_trials, MAX_SAMPLE_WORK
from test_atomic_saves import node


def data(count=3):
    nodes = {'Goal': node('Goal', type='Goal')}
    nodes.update({f'N{i}': node(f'N{i}') for i in range(count)})
    edges = [dict(source=n, target='Goal', type='Needs_Hard') for n in nodes if n != 'Goal']
    return nodes, edges


def test_service_reuses_relevant_inputs_and_returns_detached_results(monkeypatch):
    service = SimulationService()
    nodes, edges = data()
    calls = []
    original = service_module.simulate_task_chain
    def tracked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(service_module, 'simulate_task_chain', tracked)
    first = service.summarize('Goal', nodes, edges, True, False, 1000)
    nodes['N0'].description = 'Cosmetic edit'
    again = service.summarize('Goal', nodes, edges, True, False, 1000)
    assert first == again and len(calls) == 1
    again['counts'][0] = -100
    assert service.summarize('Goal', nodes, edges, True, False, 1000) == first
    nodes['N0'].time_p = 8
    service.summarize('Goal', nodes, edges, True, False, 1000)
    assert len(calls) == 2
    nodes['N0'].status = 'Done'
    service.summarize('Goal', nodes, edges, True, False, 1000)
    assert len(calls) == 3


def test_private_rng_reproduces_results_without_changing_global_rng():
    nodes, edges = data()
    np.random.seed(123)
    expected = np.random.random(5)
    np.random.seed(123)
    a = SimulationService().summarize('Goal', nodes, edges, True, False, 1000)
    assert np.array_equal(np.random.random(5), expected)
    b = SimulationService().summarize('Goal', nodes, edges, True, False, 1000)
    assert a == b


def test_trial_budget_is_enforced_on_server():
    nodes, _ = data(500)
    assert effective_trials(10_000, nodes) == 4000
    assert effective_trials(10**12, nodes) * 500 <= MAX_SAMPLE_WORK
    assert effective_trials(10**12, {'N': node('N')}) == 100_000


def test_superseded_and_out_of_order_requests_are_cancelled():
    service = SimulationService()
    assert service.begin('browser', 2)
    assert not service.begin('browser', 1)
    assert service.begin('browser', 3)
    assert service.cancelled('browser', 2)
    nodes, edges = data()
    with pytest.raises(SimulationCancelled):
        service.summarize('Goal', nodes, edges, True, False, 1000,
                          lambda: service.cancelled('browser', 2))
    assert not service._cache


def test_engine_checks_cancellation_during_chunks():
    nodes, edges = data()
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 10
    with pytest.raises(SimulationCancelled):
        simulate_task_chain('Goal', nodes, edges, n_simulations=100_000,
                            should_cancel=cancelled)
    assert calls == 10


def test_streaming_sum_matches_independent_node_draws():
    nodes, edges = data(4)
    actual = simulate_task_chain('Goal', nodes, edges, n_simulations=1000,
                                 rng=np.random.default_rng(42))['samples']
    rng = np.random.default_rng(42)
    expected = sum((_sample_node(nodes[name], 1000, rng=rng)
                    for name in sorted(nodes) if name != 'Goal'), np.zeros(1000))
    assert np.array_equal(actual, expected)


def test_result_and_session_caches_are_bounded():
    service = SimulationService()
    for i in range(150):
        service.begin(f'browser{i}', 1)
    assert len(service._latest) == 128
    assert service.cancelled('browser0', 1)
    for i in range(20):
        nodes = {'N': node('N', time_o=i+1, time_m=i+1, time_p=i+1)}
        service.summarize('N', nodes, [], True, False, 100)
    assert len(service._cache) == 16
    assert all('samples' not in result for result in service._cache.values())


def test_browser_ignores_old_results_after_and_before_current_result():
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the browser response-order contract')
    asset = Path(__file__).resolve().parents[1] / 'assets' / 'simulation_requests.js'
    script = r'''
const assert = require('node:assert/strict');
global.window = {
    crypto: require('node:crypto'),
    dash_clientside: {no_update: 'NO', callback_context: {triggered: []}}
};
require(process.argv[1]);
const ui = window.dash_clientside.skillTreeSimulation;
function request(name, triggerId, settledRoot = null, frozen = false) {
    window.dash_clientside.callback_context.triggered = triggerId ? [{
        prop_id: `${triggerId}.data`
    }] : [];
    const args = Array(20).fill(null);
    args[0] = name;
    args[17] = settledRoot ? JSON.stringify({root: settledRoot}) : '';
    args[18] = 'tab-details';
    args[19] = frozen;
    return ui.request(...args);
}
const waitingA = request('A', 'details-selected-node-store');
assert.equal(waitingA.node, null);
assert.equal(waitingA.waitingForLayout, true);
assert.deepEqual(ui.render(null, waitingA), [
    'NO', {display: 'none'}, {display: 'none'}, 'Calculating…'
]);

const old = request('A', 'details-simulation-settled-trigger-input', 'A');
assert.equal(old.node, 'A');
assert.equal(old.waitingForLayout, false);
const waitingB = request('B', 'details-selected-node-store', 'A');
assert.equal(waitingB.node, null);
const latest = request('B', 'details-simulation-settled-trigger-input', 'B');
assert.equal(latest.node, 'B');
const staleResult = {...old, figure: 'A'};
assert.equal(ui.render(staleResult, latest)[3], 'Calculating…');
const result = {...latest, figure: 'B', resultsStyle: {display:'flex'}, emptyStyle: {}, caption:'100 trials'};
assert.equal(ui.render(result, latest)[0], 'B');
assert.deepEqual(ui.render(staleResult, latest), ['NO','NO','NO','NO']);

// An old settled token cannot release a same-root re-selection. Further
// layout-affecting inputs stay gated until a new layoutstop signal arrives.
const reselected = request('B', 'details-selected-node-store', 'B');
assert.equal(reselected.node, null);
assert.equal(request('B', 'filter-context', 'B').node, null);
assert.equal(request('B', 'details-simulation-settled-trigger-input', 'B').node, 'B');

// Every settled layout emits that signal, including the ones a graph-settings
// slider starts. With nothing pending, it must not issue a request of its own.
assert.equal(request('B', 'details-simulation-settled-trigger-input', 'B'), 'NO');

// Frozen canvases intentionally emit no layout events, so selection is ready.
const frozen = request('C', 'details-selected-node-store', null, true);
assert.equal(frozen.node, 'C');
assert.equal(frozen.waitingForLayout, false);

assert.equal(ui.render(result, request(null, 'details-selected-node-store'))[1].display, 'none');
assert(latest.sequence > old.sequence);
'''
    result = subprocess.run([node_binary, '-e', script, str(asset)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
