# Performance checks

Source benchmarks on 2026-09-07 used temporary synthetic SQLite databases and
the local `skill-tree` Python environment. No production data was used. These are
function timings, not end-to-end browser latency or a promise for other graphs.

## Read/render work

Dataset: 100 or 500 Learn nodes, a ternary tree of Soft edges directed toward
the root, ratings 5 (value varies from 5 to 9), and time estimates 1/2/4 hours.
Warm/render timings are medians of three calls. Each Next table has 25 rows.

| Operation, 500 nodes | Before | After task 3 | Connections before → after |
|---|---:|---:|---:|
| Warm Next ranking | 26.04 ms | 19.39 ms | 9 → 1 |
| Render 25 Next rows | 26.48 ms | 11.00 ms | 50 → 1 |
| Generate canvas elements | 15.01 ms | 12.81 ms | 7 → 1 |
| Build page layout | 19.88 ms | 16.62 ms | 21 → 1 |

At 100 nodes, rendering 25 Next rows changed from 27.96 ms to 6.56 ms.
The snapshot does four bulk SELECTs, including one Settings read. Previously
that table render queried the same settings once per row. Nested subtree/time
helpers now reuse the detached graph rows rather than issuing per-node queries.

`tests/test_read_snapshots.py` checks query counts, connection closure, fresh
reads after writes, detached node objects, and bounded cache sizes. Timing
thresholds are deliberately not asserted in ordinary unit tests.

## Simulation

A Goal with 100/500 independent hard prerequisites, each estimated at 1/2/4
hours, took approximately 1.75/8.61 seconds at 10,000 trials, with `tracemalloc`
enabled. Traced peak allocations were 8.14/38.81 MiB. This includes simulation
and summary statistics, but excludes database reads and Plotly rendering.

After task 4, the same fixed 10,000-trial engine benchmark took 1.86/9.59
seconds, with peak traced allocations of 0.20/0.32 MiB. Streaming removes the
per-node sample arrays; it does not make the per-task duration sampling faster.

The interactive service caps work at 100,000 trials and two million node-trial
samples. On these graphs it used 10,000/4,000 trials, taking 1.86/3.78 seconds
without tracing. Reusing the cached summaries took 0.12/0.47 ms (excluding
database reads, Plotly construction and browser rendering). Fewer trials trade
some Monte Carlo precision for responsiveness; the panel reports the actual
count whenever it limits the requested count.

Regression tests cover streamed summation, cancellation during sampling,
deterministic local random generators, bounded caches, and out-of-order browser
responses. Full suite after tasks 1–4: 1,189 passing tests.
Sandbox browser smoke check: Details rendered a selected goal's histogram and
5,000-trial caption; dependency toggles and tab navigation worked with no captured
browser errors. This was a functional check, not an end-to-end latency benchmark.

## Next interaction follow-up

Next rows and Now cards now carry their descriptions in the initial layout.
Selecting either updates the highlight and description in a clientside callback;
no server callback subscribes to selection. Previously a click required a server
selection request followed by description, Now-card and core graph/table work.
Recommendation refreshes are now separate from the core graph callback, and
layout generation no longer builds the hidden canvas before Next can render.

Sandbox checks covered rapid row changes, Now selection and navigation to the
populated Nodes canvas. Regression tests cover initial saved filters, selection
refresh/removal, and the absence of server selection subscribers. These are
functional and callback-dependency checks; no end-to-end latency number is claimed.

## Startup

Measured on 2026-09-23 in headless Chrome over the Chrome DevTools Protocol,
with a warm cache. The server ran the way the desktop window runs it: no
debug mode, no dev bundles. Each figure is the median of five or six loads of
a copy of the 774-node sandbox. "Ready" is when the startup cover lifted, the
`skill-tree-ready` performance mark.

| | Before | After |
|---|---:|---:|
| Cover lifts | 4.7 s | 1.4 s |
| Startup callback requests | 82 | 13 |
| Home row selection right after the lift | 35–40 ms | 35–40 ms |
| First Nodes visit, click to graph | ready at startup | 1.4 s |
| Later Nodes visits | ~0.3 s re-send and diff | nothing sent |
| Core engine render, server | ~350 ms | ~60 ms |
| Server boot, warm (`create_app`) | 0.85 s | 0.71 s |

A devtools trace showed the main thread busy without a break from 0.5 s until
the lift, so the server's timing hardly mattered. The before profile split
roughly as: dash-renderer's store updates 2.1 s, Cytoscape ingest and fCoSE
1.0 s, Analyze's Plotly charts 0.6 s. The store updates scale with mounted
components times updates, which is why removing startup callbacks paid off
more than their server time suggests. [app_architecture.md](app_architecture.md)
lists the changes under Startup readiness.

Analyze and the Nodes canvas now load on their first visit. With the hover
head start, Analyze's charts appeared about 0.8 s after the click. The Nodes
canvas answer came back in about 30 ms; the rest of its 1.4 s is Cytoscape
ingesting 567 nodes and running fCoSE. Its payload is 374 KB, down from
747 KB, since elements carry only the fields something reads.

## 1,000 nodes (P6.6)

Measured on 2026-09-27 with `tools/perf_bench.py --browser`. It builds a
graph with `tools/perf_graph.py`, using the app's own code: 1,000 nodes and
about 1,770 edges, mostly within each node's context, with 25 goals, 10
milestones, finished work, Now nodes, events and aliases. Done nodes are
hidden by default, which leaves 831 on the Nodes canvas. The machine was a
4-core Linux container, roughly 2.5 times slower here than the machine behind
the startup figures above. CI's `perf` job runs the same check on each
platform and prints its table in the job summary; the budgets there fail a
run that is several times slower, not one that is noisy.

The server's share of each interaction, median of five:

| Operation | Seconds |
|---|---:|
| Home ranking after an edit | 0.46 |
| Nodes canvas payload | 0.03 |
| Editor save | 0.005 |
| Done and back, cascading to 91 nodes | 0.008 |
| Launch repair | 0.03 |
| Export (JSON) | 0.02 |
| Backup | 0.005 |
| Time simulation, goal with 86 prerequisites | 0.02 |

What a person sees, in Chromium:

| | Before | After |
|---|---:|---:|
| Server boot to ready | 0.8 s | 0.8 s |
| First load, until the cover lifts | about 5 s | about 5 s |
| First Nodes visit, until the canvas is drawn | 10.6 s | 4.1 s |
| A node added: its layout blocks the page for | 6.1 s | 1.6 s |
| Editor save, click to message | 1.3 s | 1.3 s |

The canvas was the problem. A CPU profile of the first visit put 8.2 s of its
10.6 s in fCoSE's spring embedder. The payload had arrived in 0.3 s. At
`proof` quality the embedder cools slowly, and its cost grows with about the
square of the node count: 0.5 s at 226 nodes, 1.7 s at 403, 3.7 s at 637 and
7.4 s at 831. Nodes re-runs the layout on every node added or removed, so
every edit that changed the graph froze the page that long. Capping the
iteration count did nothing, since fCoSE treats it as a suggestion; `default`
quality cut the cost to a third. Past 600 nodes every canvas now lays out at
`default` ([app_architecture.md](app_architecture.md), Layout requests).
Smaller graphs keep `proof`, which is how the author's 567-node graph still
lays out.

CI's first `perf` run (run 36286069199, after the change), in seconds:

| | Linux | Windows | macOS arm64 | macOS Intel |
|---|---:|---:|---:|---:|
| Server boot to ready | 0.9 | 1.4 | 1.1 | 2.3 |
| First load, until the cover lifts | 5.1 | 5.5 | 5.7 | 7.2 |
| First Nodes visit, until the canvas is drawn | 3.5 | 4.1 | 4.2 | 5.8 |
| Editor save, click to message | 1.2 | 1.3 | 1.3 | 2.0 |
| Home ranking after an edit (server) | 0.48 | 0.58 | 0.54 | 0.89 |

The Intel Mac runner is the slowest machine CI has, and a fair stand-in for an
older laptop. Windows pays for SQLite's commits on NTFS (an editor save is 41 ms
of server time there, against 4–8 ms elsewhere), which is still small.

The first load is dash-renderer and React mounting the page. The server had
answered every startup callback by 0.5 s. That matches the startup section
above, scaled for this machine, so 1,000 nodes add no new cost there.

The time simulation now runs 10,000 trials over 97 open tasks in 27 ms,
against about 1.9 s for 100 tasks in the September 7 measurement above.

