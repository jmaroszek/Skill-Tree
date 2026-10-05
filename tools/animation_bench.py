"""Measure animation work in sandbox Chromium over a synthetic graph.

    python tools/animation_bench.py --rate 4 --repeats 5 --output audit.json

PLAYWRIGHT_CHROMIUM can point at an installed Chrome. --app-root uses another
source checkout for a matched comparison; data always stays in a temporary
SKILLTREE_HOME. Results include main-thread rAF gaps, long tasks, layouts,
transitions and trace totals. rAF gaps do not measure compositor presentation.
Trace FunctionCall durations overlap and are not total CPU time.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from local_server import Server
from playwright.sync_api import sync_playwright

INSTRUMENT = r'''
window.animationAudit = {result: null};
window.animationAudit.arm = function(selector, duration) {
  const audit = this;
  audit.result = null;
  const intervals = [], tasks = [], transitions = [], layouts = [];
  let start = null, previous = null, frame, stopped = false;
  const observer = new PerformanceObserver(list => {
    list.getEntries().forEach(e => tasks.push({start: e.startTime, duration: e.duration}));
  });
  observer.observe({entryTypes: ['longtask']});
  const transition = e => {
    if (start !== null) transitions.push({type: e.type, id: e.target.id,
      property: e.propertyName, at: performance.now() - start});
  };
  document.addEventListener('transitionrun', transition, true);
  document.addEventListener('transitionend', transition, true);
  const handlers = [];
  (window.SkillTree.canvases || []).forEach(canvas => {
    const cy = window.SkillTree.getCy(document.getElementById(canvas.cytoscapeId));
    if (!cy) return;
    const fn = e => {
      if (start !== null) layouts.push({type: e.type, key: canvas.key,
        at: performance.now() - start, count: cy.nodes().length});
    };
    cy.on('layoutstart layoutstop', fn);
    handlers.push([cy, fn]);
  });
  const resourcesStart = performance.getEntriesByType('resource').length;
  function tick(now) {
    if (stopped) return;
    if (previous !== null) intervals.push({at: now - start, gap: now - previous});
    previous = now;
    frame = requestAnimationFrame(tick);
  }
  function finish() {
    stopped = true;
    cancelAnimationFrame(frame);
    observer.takeRecords().forEach(e => tasks.push({start: e.startTime, duration: e.duration}));
    observer.disconnect();
    document.removeEventListener('transitionrun', transition, true);
    document.removeEventListener('transitionend', transition, true);
    handlers.forEach(([cy, fn]) => cy.off('layoutstart layoutstop', fn));
    const resources = performance.getEntriesByType('resource').slice(resourcesStart)
      .filter(e => e.name.includes('_dash-update-component'));
    audit.result = {elapsed: performance.now() - start, intervals, layouts, transitions,
      longTasks: tasks.filter(t => t.start >= start).map(t => ({at: t.start - start, duration: t.duration})),
      requests: resources.length, requestBytes: resources.reduce((s,e) => s + e.encodedBodySize, 0)};
  }
  function onClick(e) {
    if (!e.target.closest(selector)) return;
    document.removeEventListener('click', onClick, true);
    start = performance.now();
    previous = start;
    frame = requestAnimationFrame(tick);
    setTimeout(finish, duration);
  }
  document.addEventListener('click', onClick, true);
};
'''

def metrics(result):
    gaps = [x['gap'] for x in result['intervals']]
    slide_gaps = [x['gap'] for x in result['intervals'] if x['at'] <= 400]
    def percentile(values, p):
        values = sorted(values)
        return values[min(len(values) - 1, int((len(values) - 1) * p))] if values else 0
    return dict(p95=round(percentile(gaps, .95), 1), p99=round(percentile(gaps, .99), 1),
                worst=round(max(gaps, default=0), 1),
                frames_over_33=sum(gap > 33.4 for gap in gaps),
                frames_over_50=sum(gap > 50 for gap in gaps),
                first_400ms_worst=round(max(slide_gaps, default=0), 1),
                long_tasks=len(result['longTasks']),
                long_task_ms=round(sum(t['duration'] for t in result['longTasks']), 1),
                requests=result['requests'])

def measure(page, selector, duration, cdp):
    events, ended = [], []
    on_data = lambda data: events.extend(data['value'])
    on_end = lambda data: ended.append(True)
    cdp.on('Tracing.dataCollected', on_data)
    cdp.on('Tracing.tracingComplete', on_end)
    cdp.send('Tracing.start', {'categories': 'devtools.timeline,blink.user_timing',
                              'transferMode': 'ReportEvents'})
    page.evaluate(INSTRUMENT)
    page.evaluate('(args) => animationAudit.arm(args[0], args[1])', [selector, duration])
    page.click(selector)
    page.wait_for_function('animationAudit.result !== null', timeout=60000)
    result = page.evaluate('animationAudit.result')
    cdp.send('Tracing.end')
    for _ in range(200):
        if ended:
            break
        page.wait_for_timeout(20)
    grouped = defaultdict(lambda: {'count': 0, 'ms': 0})
    for event in events:
        if event.get('ph') == 'X' and event['name'] in ['Layout', 'UpdateLayoutTree', 'Paint', 'FunctionCall']:
            group = grouped[event['name']]
            group['count'] += 1
            group['ms'] += event.get('dur', 0) / 1000
    result['timeline'] = {key: {'count': value['count'], 'ms': round(value['ms'], 2)}
                          for key, value in grouped.items()}
    cdp.remove_listener('Tracing.dataCollected', on_data)
    cdp.remove_listener('Tracing.tracingComplete', on_end)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--nodes', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--rate', type=int, default=1)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--app-root')
    parser.add_argument('--details-only', action='store_true')
    args = parser.parse_args()
    if args.rate < 1 or args.repeats < 1:
        parser.error('--rate and --repeats must be positive')
    if args.nodes < 20:
        parser.error('--nodes must be at least 20')
    if args.app_root:
        sys.modules[Server.__module__].ROOT = Path(args.app_root).resolve()
    work = Path(tempfile.mkdtemp(prefix='skilltree-animation-'))
    os.environ['SKILLTREE_HOME'] = str(work)
    data = work / 'Data'
    data.mkdir(parents=True, exist_ok=True)
    import perf_graph
    counts = perf_graph.build(data / 'sandbox_skilltree.db', args.nodes, args.seed)
    server = Server(work).start()
    results = {'rate': args.rate, 'graph': counts, 'seed': args.seed,
               'source': str(sys.modules[Server.__module__].ROOT), 'samples': {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM') or None)
            results['browser'] = browser.version
            page = browser.new_page(viewport={'width': 1400, 'height': 900})
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.goto(server.link)
            page.wait_for_selector('#startup-cover.is-lifted', state='attached', timeout=120000)
            page.wait_for_timeout(800)
            cdp = page.context.new_cdp_session(page)
            cdp.send('Emulation.setCPUThrottlingRate', {'rate': args.rate})
            for label, selector in ([] if args.details_only else [('Home filters', '#btn-filters-toggle'),
                                    ('Goals sidebar', '#btn-goals-toggle'),
                                    ('Node editor', '#btn-add')]):
                samples = []
                for _ in range(args.repeats):
                    result = measure(page, selector, 1400, cdp)
                    samples.append(result)
                    print(label, metrics(result), result['timeline'], flush=True)
                    page.click(selector)
                    page.wait_for_timeout(600)
                results['samples'][label] = samples
            page.click('a.nav-link:has-text("Nodes")')
            page.wait_for_selector('#canvas-first-paint-cover.is-lifted', state='attached', timeout=120000)
            page.wait_for_timeout(1400)
            results['visible_nodes'] = page.evaluate("SkillTree.getCy(document.getElementById('cytoscape-graph')).nodes().length")
            samples = []
            for _ in range(0 if args.details_only else args.repeats):
                result = measure(page, '#btn-filters-toggle', 1400, cdp)
                samples.append(result)
                print('Nodes filters', metrics(result), result['timeline'], flush=True)
                page.click('#btn-filters-toggle')
                page.wait_for_timeout(600)
            results['samples']['Nodes filters'] = samples
            page.click('a.nav-link:has-text("Details")')
            page.wait_for_timeout(1000)
            selector = '.details-suggestion-row'
            cdp.send('Profiler.enable')
            cdp.send('Profiler.start')
            result = measure(page, selector, 6000, cdp)
            cpu = cdp.send('Profiler.stop')['profile']
            if args.output:
                args.output.with_suffix('.cpu.json').write_text(json.dumps(cpu), encoding='utf-8')
            results['samples']['Details suggestion'] = [result]
            print('Details suggestion', metrics(result), result['timeline'], result['layouts'], flush=True)
            page.wait_for_timeout(2000)
            page.evaluate('''() => {
                const button = document.createElement('button');
                button.id = 'bench-pan'; button.textContent = 'Pan';
                button.style.cssText = 'position:fixed;top:0;left:150px;z-index:20000';
                button.onclick = () => {
                  const cy = SkillTree.getCy(document.getElementById('details-mini-graph'));
                  const pan = cy.pan();
                  cy.animate({pan:{x:pan.x + 100,y:pan.y + 20}}, {duration:1000});
                };
                document.body.appendChild(button);
            }''')
            samples = []
            for _ in range(args.repeats):
                result = measure(page, '#bench-pan', 1400, cdp)
                samples.append(result)
                print('Details pan', metrics(result), result['timeline'], flush=True)
                page.wait_for_timeout(600)
            results['samples']['Details pan'] = samples
            results['errors'] = errors
            browser.close()
    finally:
        server.stop()
        # Only remove the exact temporary directory this invocation created.
        assert work.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert work.name.startswith('skilltree-animation-')
        shutil.rmtree(work)
    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
