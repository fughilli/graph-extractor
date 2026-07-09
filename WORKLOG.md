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
- **Test coverage** (`tests/test_topology.py`, `tests/test_pipeline.py`): open
  chains, Y / H junctions, adjacent junctions, pure loops, lollipops, isolated
  points, edge-partition invariants, and end-to-end collapse of a cylinder to
  its axis and a branching tube to a single junction. All passing.
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
3. **Loop-through-collapse end-to-end test.** The topology core handles loops
   and cycles (unit-tested), but there is no end-to-end test of a *thick* looped
   tube (e.g. a torus) surviving reduction. Add one.
4. **Visualization + I/O.** Helpers for viewing skeletons and readers/writers
   for common point-cloud formats.

## Open questions / blockers
- None currently blocking.

## Don't retry (dead ends)
- (none recorded yet)
