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
  `viz/static/index.html` is the Three.js UI (CDN). Run: `bazel run
  //viz:server`. **Live WebGL rendering is unverified** (no browser in CI/the
  container); the data path is covered by tests instead.
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
