# skelgraph interactive visualizer

An in-browser viewer that runs the **real** skelgraph pipeline and draws every
intermediate stage in 3-D, plus generators for synthetic **skeleton** (thin,
1-D) and **tubiform** (thick, surface-sampled) point clouds.

Nothing here re-implements the algorithm: the backend calls the same
`skelgraph` functions the library and tests use (`reduce`, `neighbors`,
`cleanup`, `topology`) and records what each produces.

## Run it

```bash
# with Bazel:
bazel run //viz:server              # opens the printed URL automatically

# or plain Python (needs numpy/scipy/networkx importable):
PYTHONPATH=. python3 viz/server.py
PYTHONPATH=. python3 viz/server.py --port 8000 --no-open
```

The server binds `0.0.0.0:8765` by default. Container port **8765** is
published to the host via `.claude-container-overlay/overlay.json`, so from the
host browser just open <http://localhost:8765>. (Port changes there take effect
on the next `claude-container` launch and never trigger an image rebuild.) Pass
`--host 127.0.0.1` to restrict the server to loopback.

Then use the sidebar: pick a dataset, tweak generation and pipeline
parameters, and the view updates live (auto-run, debounced). Three.js loads
from a CDN, so the browser needs network access; the server itself is
stdlib-only.

## What you see

The **stage stepper** across the top walks the pipeline; the **Layers** panel
lets you toggle anything freely.

| Stage | Shown |
|-------|-------|
| Input | raw cloud (curve-grey vs surface-tan) + dashed ground-truth centerlines |
| Contraction *(collapse)* | Laplacian contraction pulling the cloud to its medial axis — scrub/▶ the **Contraction** frames |
| Adjacency *(none/surface)* | the radius / kNN / MST neighbour graph |
| Skeleton *(collapse)* | centerline nodes + edges after connectivity-preserving edge collapse |
| Consolidate | branch-to-branch edges fused into single junctions (highlighted red) |
| Degrees | every node coloured tip (green) / interior (blue) / branch (red) |
| Segments | each traced un-branching chain in its own colour; branch points as red spheres |

`auto` mode additionally reports the local-covariance sheet-vs-curve vote that
picks collapse vs surface.

## Datasets

**Skeleton** (`reduce=none`): open chain, closed loop, Y junction, H network
(bridge), lollipop (stub + loop), grid lattice.

**Tubiform** (`reduce=collapse`/`surface`/`auto`): cylinder, Y tube, X tube
(4-way), torus (looped tube). Selecting a dataset pre-loads a sensible
pipeline config; every generator supports noise and a reseed button.

## Files

| File | Role |
|------|------|
| `generators.py` | synthetic clouds + parameter schema + ground truth |
| `trace.py` | the instrumented pipeline (mirrors `skelgraph.extract`, captures stages) |
| `server.py` | stdlib HTTP server: `/api/datasets`, `/api/config-schema`, `/api/pipeline` |
| `static/index.html` | the Three.js single-page viewer |
