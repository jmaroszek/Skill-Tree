"""Bounded simulation work/cache; browser requests can supersede older work."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import threading

import numpy as np

from config import ConfigManager
from models import STATUS_DONE
from simulation import simulate_task_chain, SimulationCancelled, bracket_diagnostics

MAX_TRIALS = 100_000
MAX_SAMPLE_WORK = 2_000_000
MAX_CACHED_RESULTS = 16
MAX_SESSIONS = 128


def effective_trials(requested, nodes, scenarios=1):
    tasks = sum(n.status != STATUS_DONE and n.time_mode != 'inherited'
                for n in nodes.values())
    return min(max(1, int(requested)), MAX_TRIALS,
               max(1, MAX_SAMPLE_WORK // max(1, tasks * scenarios)))


class SimulationService:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = OrderedDict()
        self._cache = OrderedDict()
        # Large calculations must not consume every Dash request thread/CPU.
        self._slots = threading.BoundedSemaphore(2)

    def begin(self, session, sequence):
        with self._lock:
            if sequence <= self._latest.get(session, -1):
                return False
            self._latest[session] = sequence
            self._latest.move_to_end(session)
            while len(self._latest) > MAX_SESSIONS:
                self._latest.popitem(last=False)
            return True

    def cancelled(self, session, sequence):
        with self._lock:
            return self._latest.get(session) != sequence

    def summarize(self, target, nodes, edges, include_soft, include_helps,
                  requested_trials, should_cancel=None):
        cancelled = should_cancel or (lambda: False)
        if cancelled():
            raise SimulationCancelled()
        correlation = ConfigManager.get_estimate_correlation()
        # Deliberately broad illustrative assumptions, not a calibrated range.
        correlations = sorted({0.0, correlation, 1.0})
        trials = effective_trials(requested_trials, nodes, len(correlations))
        # Cosmetic edits and unrelated graph changes do not change this key.
        key = (target, include_soft, include_helps, trials, correlation,
               tuple((name, n.status, n.time_mode, n.time_o, n.time_m, n.time_p)
                     for name, n in sorted(nodes.items())),
               tuple(sorted((e['source'], e['target'], e['type']) for e in edges)))
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return deepcopy(cached)
        while not self._slots.acquire(timeout=0.05):
            if cancelled():
                raise SimulationCancelled()
        try:
            if cancelled():
                raise SimulationCancelled()
            # A private generator avoids shared global RNG state across requests.
            # Stable inputs also reproduce the same result after cache eviction.
            seed = int.from_bytes(hashlib.sha256(repr(key).encode()).digest()[:8], 'big')
            result = simulate_task_chain(target, nodes, edges, include_soft, include_helps,
                                         trials, rng=np.random.default_rng(seed),
                                         should_cancel=cancelled,
                                         correlation=correlation)
            counts, bins = np.histogram(result['samples'], bins=50)
            summary = dict(stats=result['stats'], chain_size=result['chain_size'],
                           trials=trials, centers=((bins[:-1] + bins[1:]) / 2).tolist(),
                           counts=counts.tolist(), width=float(bins[1] - bins[0]))
            summary['correlation'] = correlation
            summary['mean_hours'] = sum(nodes[name].time for name in result['chain_nodes'])
            summary['diagnostics'] = bracket_diagnostics(
                nodes[name] for name in result['chain_nodes'])
            summary['sensitivity'] = []
            for rho in correlations:
                comparison = result if rho == correlation else simulate_task_chain(
                    target, nodes, edges, include_soft, include_helps, trials,
                    rng=np.random.default_rng(seed), should_cancel=cancelled,
                    correlation=rho)
                summary['sensitivity'].append(dict(
                    correlation=rho, p10=comparison['stats']['p10'],
                    p50=comparison['stats']['p50'], p90=comparison['stats']['p90']))
            if cancelled():
                raise SimulationCancelled()
            with self._lock:
                self._cache[key] = summary
                self._cache.move_to_end(key)
                while len(self._cache) > MAX_CACHED_RESULTS:
                    self._cache.popitem(last=False)
            return deepcopy(summary)
        finally:
            self._slots.release()


simulation_service = SimulationService()
