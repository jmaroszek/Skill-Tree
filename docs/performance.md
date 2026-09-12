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
