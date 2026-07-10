# WORKLOG

_Last updated: 2026-07-09 by an agent session. Read together with `git log`._

## Goal
Extract graph **topology** (branch points + segments) from 3-D point clouds
sampled along the edges of a 1-D network. See `README.md` for the durable spec.

## State of play
- Core pipeline is implemented and green: reduce → adjacency → junction
  consolidation → degree classification → segment tracing → prune → emit
  (`see e15cc3e`, `914f9c8`).
- README was last synced to the implemented config API in `e15cc3e`; it is the
  authoritative spec and is currently accurate.
- **Hermetic Bazel (bzlmod) build** is in place (`fdb15d2`): `bazel test //...`
  and `bazel run //examples:demo` / `//viz:server`. The pip lockfile
  (`requirements.lock`) is generated via `bazel run
  //:generate_requirements_lock` — regenerate it after editing
  `requirements.in`, never hand-edit.
- **Interactive visualizer** (`viz/`): a browser viewer that runs the *real*
  pipeline and draws every stage in 3-D, plus synthetic-cloud generators for
  skeleton (thin 1-D) and tubiform (thick surface) inputs. `viz/trace.py`
  mirrors `extract()` but calls the same primitives while capturing
  intermediates (contraction frames, adjacency/skeleton graph, consolidation,
  degrees, segments); `viz/server.py` is a stdlib HTTP server (no new deps);
  `viz/static/index.html` is the Three.js UI. Run: `bazel run
  //viz:server`. **Three.js is vendored locally** under `viz/static/vendor/`
  (`three.module.js` + `OrbitControls.js`) and referenced via an import map —
  there is **no runtime CDN dependency**, so the viewer works offline / on
  locked-down networks. (A CDN import previously killed the whole ES module at
  load time on any browser that couldn't reach unpkg — empty dropdown, dead
  buttons, stuck "loading…". Symptom to watch for: the browser only ever GETs
  `/`, never `/api/datasets`.) `viz:server`'s Bazel `data` is `glob(["static/**"])`
  so vendored assets ship in the runfiles. A second, latent bug surfaced once
  the CDN import was fixed: the render loop read `let playing` before its
  declaration (temporal dead zone), throwing on the first frame and aborting
  the module before `boot()` — same dead-app symptom, masked earlier because
  the module died at the CDN import first. Fixed by hoisting the
  `playing`/`playT` declaration above the loop.
- **Live WebGL rendering is now VERIFIED end-to-end in-container.** The overlay
  installs Playwright + headless Chromium (`/opt/ms-playwright`); drive it with
  `NODE_PATH=$(npm root -g) node /workspace/.pw-smoke.cjs` (server must be up).
  Confirmed: dropdown fills (10 datasets), status leaves "loading…" for
  `N pts • <mode>`, canvas initialises, geometry draws, zero page errors.
- Container **port 8765 is published** to the host
  (`.claude-container-overlay/overlay.json`); the server binds `0.0.0.0` by
  default so the mapping works. Takes effect on the next `claude-container`
  launch.
- **Test coverage** (`tests/test_topology.py`, `tests/test_pipeline.py`,
  `tests/test_viz.py`): open chains, Y / H junctions, adjacent junctions, pure
  loops, lollipops, isolated points, edge-partition invariants, and end-to-end
  collapse of a cylinder to its axis and a branching tube to a single junction.
  `test_viz.py` adds every generator, trace-vs-library topology agreement,
  index-in-bounds guards (proxy for render safety), and a **thick torus
  collapsing to one closed loop**. All passing.
- **Reserved-but-unused config fields:** `ReduceConfig.collapse_radius` (the τ
  threshold) and `ReduceConfig.axis_hint` are declared in `skelgraph/config.py`
  but not referenced anywhere else in `skelgraph/` (verified by grep). They are
  placeholders for the refinements listed under "Next up".
- **`auto` mode** makes a single *global* collapse-vs-surface decision from
  neighbourhood-covariance eigenvalues; it is not yet per-region.
- **Shortcut-edge pruning** (`neighbors.prune_shortcut_edges`, on by default via
  `NeighborConfig.prune_shortcuts`). A radius/knn graph over a 1-D skeleton picks
  up "shortcut" edges that are short in space but not adjacent along the curve:
  the diagonal across a junction's fan of arms, and the hypotenuse across a
  right-angle corner. These inflated node degree, so a junction became a clique
  of degree>=3 nodes that consolidation then centroid-collapsed (absorbing the
  arm extrema), and a corner became a triangle that fragmented into a spurious
  branch point + stub. The fix is a Relative-Neighbourhood-Graph rule: drop edge
  (i,j) when a **common** neighbour k is strictly closer to both endpoints (the
  i-k-j detour proves i-j is a shortcut). Because k is a common neighbour the
  i-k-j path already exists, and edges are pruned longest-first against the live
  graph, so it **never disconnects**. Result: junctions stay one central node
  with extrema returned to their arms (0 points absorbed on Y/X/grid), and bent
  corners stay degree-2 (no branch point, no stub). Applied in `extract.py` and
  `viz/trace.py` for **every mode except surface** (which keeps its 2-D mesh) --
  including the **collapse** skeleton, whose overlapping cross-sections leave a
  little multi-node blob at a tube junction; pruning elects one central node
  there too (e.g. the Y-tube junction blob `{3:1,4:3}` -> a single degree-3
  centre). The viz shows pruned edges as an orange "Pruned shortcuts" layer (on
  the Adjacency step for `none`, the Skeleton step for `collapse`) + a sidebar
  toggle. Note: this makes grid corners degree-2 bends, so a 3x2 grid yields
  **2** branch points (the two real T-junctions), not the 6 the generator's
  ground-truth over-counts.

## Next up
1. **Wire in `collapse_radius` (τ) and `axis_hint`.** τ should gate
   collapse-vs-surface by local minor extent; `axis_hint` should seed ring
   detection when collapsing. Both are currently dead fields.
2. **Per-region `auto`.** Replace the single global collapse/surface choice
   with a per-point (mixed) reduction decision.
3. ~~**Loop-through-collapse end-to-end test.**~~ *Done* —
   `tests/test_pipeline.py::test_torus_collapses_to_one_loop` collapses a thick
   torus to a single closed loop (0 branch points, centerline ring of radius R);
   `tests/test_viz.py` covers the same via the viz backend.
4. **I/O.** Readers/writers for common point-cloud formats (`.ply`/`.xyz`/`.npy`);
   the *visualization* half of the original item is now covered by `viz/`.

## Open questions / blockers
- None currently blocking.

## Don't retry (dead ends)
- (none recorded yet)
