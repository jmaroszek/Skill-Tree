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

## Simulation baseline

A Goal with 100/500 independent hard prerequisites, each estimated at 1/2/4
hours, took approximately 1.75/8.61 seconds at 10,000 trials, with `tracemalloc`
enabled. Traced peak allocations were 8.14/38.81 MiB. This includes simulation
and summary statistics, but excludes database reads and Plotly rendering.
