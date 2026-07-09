# Graph Skeleton Extraction from Point Clouds

Extract the **topology** of a 3D graph (a network of curves) from a set of
points that were sampled along its edges.

The input is a "dumb" bag of 3D coordinates. The output is a structured
description of the network: *where the junctions are* and *which chains of
points connect them*.

---

## 1. Problem statement

We are given a **point cloud**

```
P = { p_1, p_2, ..., p_N },   p_i ∈ ℝ³
```

The points are *not* random. They were sampled from (they "lie along") the
edges of some underlying **1D graph embedded in 3D space** — think of the
centerlines of blood vessels, plant roots, neuron arbors, wires, or road
networks. Each point sits on a thin curve; the curves meet at junctions.

We want to recover the graph's **connectivity / topology**, expressed as two
kinds of object:

| Object | Definition |
|--------|-----------|
| **Branch point** | A point where **2 or more segments meet** — a junction of the network. |
| **Segment** | An ordered list of **simply-connected** points forming a single un-branching chain, **terminated by 0, 1, or 2 branch points**. |

Informally:

- A **segment** is a piece of the network you can walk along without ever
  having to choose which way to go — a "corridor" with no doors branching off.
- A **branch point** is where corridors meet — a "junction" / "intersection".

The result is effectively a **graph** whose *nodes* are branch points and
whose *edges* are segments (each edge carrying the full polyline of points
between its endpoints).

---

## 2. Vocabulary and precise definitions

### Simply-connected points
A point `a` is *adjacent* to point `b` if they are neighbours along the same
underlying curve (in practice: close together and locally collinear). A
**simply-connected** run of points is a maximal chain

```
q_1 — q_2 — q_3 — ... — q_k
```

where every interior point `q_j` (`1 < j < k`) has exactly **two** neighbours
in the chain — i.e. the chain never branches internally.

### Degree of a point
The **degree** of a point is the number of distinct segments/curve-directions
incident to it:

```
degree 0  →  isolated point (noise, or a lone sample)
degree 1  →  endpoint / tip   (a free end of a curve)
degree 2  →  interior point   (ordinary point in the middle of a segment)
degree ≥ 3 →  branch point     (a junction — the interesting topology)
```

> A **branch point** is a point of degree ≥ 3 (three or more segments meet).
> The definition "2 or more segments meet" also admits degree-2 *loops* — see
> §4 — but a plain degree-2 point in the middle of a chain is **not** a branch
> point; it is just an interior point of a segment.

### Segment termination
Every segment is bounded ("terminated") at each of its two ends by one of:

- a **branch point** (junction), or
- a **tip / endpoint** (a free degree-1 end), or
- nothing — it closes on itself (a loop) or the whole component is a single
  open chain.

This yields the "0, 1, or 2 branch points" in the definition:

| Terminating branch points | Shape of the segment |
|:-:|:--|
| **0** | An isolated component with no junctions: a lone open chain (tip—tip) or a closed loop. |
| **1** | A **stub**: one end at a junction, the other a free tip; *or* a loop attached to a single junction. |
| **2** | A **bridge**: a chain running from one junction to another. |

---

## 3. Diagrams

Diagrams below are 2D sketches of what are really 3D structures.
Legend:

```
  o   ordinary (interior, degree-2) point of a segment
  ●   branch point (junction, degree ≥ 3)
  ×   tip / endpoint (degree 1)
```

### 3.1 A simple "Y" junction — one branch point, three segments

```
        ×  tip
         \
          o
           \
            o
             \
   ×--o--o----●----o--o--×
                     (branch point ●, degree 3)
```

Extracted topology:

```
Branch points:  B0 = ●
Segments:
  S0:  × — o — o — ●        (terminated by 1 branch point:  tip … B0)
  S1:  ● — o — o — ×        (terminated by 1 branch point:  B0 … tip)
  S2:  × — o — o — ●        (the diagonal arm; tip … B0)
```

### 3.2 An "H" / two-junction network — a bridge between branch points

```
   ×        ×
    \      /
     ●----●          the middle bar is a bridge segment
    /      \
   ×        ×
```

```
Branch points:  B0 (left ●),  B1 (right ●)
Segments:
  S0:  × — ● (B0)               1 branch point
  S1:  × — ● (B0)               1 branch point
  S2:  B0 — o — o — B1          2 branch points   (the bridge)
  S3:  ● (B1) — ×               1 branch point
  S4:  ● (B1) — ×               1 branch point
```

### 3.3 Special cases (0 branch points)

**A lone open chain** — no junctions anywhere:

```
   ×--o--o--o--o--o--×
```
```
Branch points:  (none)
Segments:  S0:  × — o — o — o — o — o — ×     (0 branch points)
```

**A closed loop** — no junctions, no tips:

```
        o--o--o
       /       \
      o         o
       \       /
        o--o--o
```
```
Branch points:  (none)
Segments:  S0:  o — o — … — o — (back to start)   (0 branch points, cyclic)
```

**A lollipop** — a loop meeting a stub at a single junction (1 branch point):

```
        o--o
       /    \
   ×--●      o     ← the loop touches the junction ● once but re-enters it,
       \    /         so ● has degree 3 (one stub + two loop ends)
        o--o
```

---

## 4. Edge cases the algorithm must handle

- **Loops / cycles.** A segment may start and end at the *same* branch point,
  or form a closed component with no branch point at all. Ordering of points
  is cyclic, not linear.
- **Isolated components.** The point cloud may contain several disconnected
  networks; each is processed independently.
- **Tips vs. junctions.** Free ends (degree 1) terminate a segment but are
  **not** branch points.
- **Short / degenerate segments.** Two junctions directly adjacent produce a
  segment with no interior points (`B0 — B1`).
- **Noise & non-uniform sampling.** Real point clouds have gaps, density
  variation, and outliers; adjacency must be inferred robustly, not assumed.
- **Near-junction ambiguity.** Points clustered around a junction may need to
  be collapsed so a single branch point is reported rather than several.

---

## 5. Input / output specification

### Input
```
points : array of shape (N, 3)      # xyz coordinates
config : options controlling reduction/skeletonization and adjacency (see §6)
```
The raw cloud is **not assumed to be a clean 1-point-wide skeleton**. It may be
thick, surface-sampled, or noisy, and a configurable **reduction** stage (§6)
turns it into the 1-D graph the topology extractor operates on.

### Output
```
branch_points : array of shape (M, 3)          # coordinates of the M junctions
segments      : list of segments, where each segment is
                {
                  points   : ordered list of point indices (the polyline),
                  ends     : (end_a, end_b),   # each is a branch-point id or
                                               # None (a free tip / loop)
                }
```

Equivalently the output is a graph `G = (V, E)`:
- `V` = branch points (junctions),
- `E` = segments, each edge annotated with the ordered list of point indices
  it passes through and whether each of its ends is a junction or a tip.

---

## 6. Reduction / skeletonization (configurable)

Because the input may be **thick or surface-sampled**, the hardest choice is
*what dimensionality the skeleton should be*. The same points can legitimately
be interpreted at different scales, and the right interpretation depends on the
data and the user's intent — so this stage is **configurable**.

### 6.1 The cylinder example

Take points arranged as a **grid on the surface of a cylinder** — rings spaced
by an *axial pitch* `a`, samples around each ring spaced by a *circumferential
pitch* `c`. Unrolled, the samples look like:

```
   circumferential  (wraps around, period = 2πR) →
 a │ o   o   o   o   o   o   o        each column is one ring;
 x │ o   o   o   o   o   o   o        the left/right edges are glued
 i │ o   o   o   o   o   o   o        (the surface is a tube)
 a │ o   o   o   o   o   o   o
 l ↓
```

There are (at least) two valid reductions, selected by configuration:

**(A) Collapse to the major axis → a 1-D centerline.**
Each ring collapses to its centroid; the tube becomes a single chain of points
along its axis. This is what you want when the cylinder is really *a tube in a
network* and you care about network topology, not surface detail.

```
   o───o───o───o───o───o───o        (ring centroids → centerline)
```

**(B) Keep connectivity on the surface → a 2-D surface graph.**
Neighbours are joined circumferentially *and* axially; the result is the grid
graph living on the cylinder surface. This is what you want when the surface
itself carries the structure of interest.

```
   o─o─o─o─o        (a 4-neighbour surface grid; edges also wrap
   │ │ │ │ │         around the seam, so interior points have degree 4)
   o─o─o─o─o
   │ │ │ │ │
   o─o─o─o─o
```

> **Why the pitch matters.** The ratio of circumferential to axial pitch (and
> both relative to the tube radius `R`) governs which reduction is sensible:
> - If `c ≪ a` (rings densely sampled, sparsely stacked), a naive neighbour
>   graph wires up each ring but may miss ring-to-ring links — collapsing to
>   the centerline is robust and natural.
> - If `c ≈ a` and both are small vs. `R` (a well-sampled surface), surface
>   connectivity is well-defined and can be preserved.
> - If the tube radius `R` is small vs. the overall structure, the tube is
>   "thin" and is almost always best treated as a 1-D curve (collapse).
>
> Note the abstraction of §1–2 (branch points + segments) describes a **1-D
> graph**. A full surface grid has interior points of degree 4 and is *not*
> curve-like, so branch-point/segment output is only meaningful in **surface**
> mode when the surface is itself ribbon/curve-like. In **collapse** mode the
> output is always a clean 1-D graph.

### 6.2 Configuration (as implemented)

Configuration is a `Config` with two nested groups plus two cleanup knobs
(`skelgraph/config.py`):

```python
Config(
    reduce = ReduceConfig(
        mode = "none",                    # none | surface | collapse | auto
        scale = None,                     # sampling pitch (None → estimated as
                                          #   median nearest-neighbour distance)
        contraction_iterations = 10,      # collapse: Laplacian contraction steps
        contraction_neighbor_factor = 2.5,# collapse: neighbour radius = factor·scale
        wl_init = None, sl = 1.6, wh = 1.0,# collapse: contraction weight schedule
        merge_factor = 0.5,               # collapse: fuse edge if len < factor ·
                                          #   longest incident edge (adaptive)
        # collapse_radius, axis_hint      # RESERVED — declared but not yet used
    ),
    neighbors = NeighborConfig(           # used by none / surface / auto modes
        method = "radius",                # radius | mst | knn
        scale = None,                     # None → estimated pitch
        radius_factor = 1.6,              # radius = radius_factor · scale
        k = 10,                           # neighbours for knn / mst
    ),
    min_stub_points = 0,                  # prune leaf stubs shorter than this (0=off)
    junction_merge_factor = 2.0,          # consolidate junctions closer than
                                          #   factor · median-edge-length (0=off)
)
```

> **Note.** `collapse_radius` (the τ threshold) and `axis_hint` are declared as
> placeholders for the intended `auto`/collapse refinements but are **not yet
> wired in** — see the roadmap in `WORKLOG.md`.

**`auto` mode (current heuristic).** `auto` makes a *single global* choice, not
a per-region one. It estimates local shape from neighbourhood covariance
eigenvalues `λ1 ≥ λ2 ≥ λ3` at each point and flags a point as sheet/tube-like
when `λ2/λ1 > 0.35` and `λ3/λ1 < 0.2`. If more than half the points are
sheet-like it runs `collapse`, otherwise `surface`. (The τ / `collapse_radius`
per-region gating in the original sketch is future work.)

## 7. Pipeline (as implemented)

1. **Reduce / skeletonize** the raw cloud per §6 configuration.
   - `collapse` runs **Laplacian graph contraction** (pulls the cloud toward
     its medial axis) followed by a **connectivity-preserving edge collapse**:
     each tube cross-section fuses to one centerline node while along-axis
     links survive. Contraction decides *connectivity*; nodes are placed at the
     centroid of their cluster's **original** points, so the centerline stays
     geometrically faithful regardless of how far contraction shrank the cloud.
   - `surface` / `none` skip contraction.
2. **Build the adjacency graph** — for `collapse` the skeleton graph from step 1
   is used directly; otherwise a radius graph (loops preserved) or MST (tree)
   is built over the reduced points.
3. **Consolidate junctions** (1-D skeletons only): merge directly-adjacent
   branch points closer than `junction_merge_factor × median-edge-length` so a
   thick junction becomes one branch point instead of a small cluster. Skipped
   in `surface` mode (where every node is degree ≥ 3 by design).
4. **Classify points by degree**:
   degree 1 → tip, degree 2 → interior, degree ≥ 3 → **branch point**.
5. **Trace segments**: from every branch point and every tip, walk along
   degree-2 chains until the next branch point or tip; record the ordered
   points. Pure cycles and isolated points are handled separately.
6. **(Optional) prune** leaf stubs shorter than `min_stub_points`.
7. **Emit** branch points and segments in the format of §5.

---

## 8. Usage

```python
import numpy as np
from skelgraph import extract, Config, ReduceConfig, NeighborConfig

points = np.load("cloud.npy")            # (N, 3)

# Already a clean 1-D skeleton:
topo = extract(points)                    # reduce mode defaults to "none"

# Thick / surface-sampled tubes -> centerlines:
topo = extract(points, Config(reduce=ReduceConfig(mode="collapse")))

print(topo.summary())
for seg in topo.segments:
    print(seg.n_branch_ends, "branch end(s),", len(seg.points), "points",
          "loop" if seg.closed else "")
topo.branch_points        # (M, 3) junction coordinates
```

Run the demos and tests:

```bash
PYTHONPATH=. python3 examples/demo.py
PYTHONPATH=. python3 -m pytest
```

### Module map
| Module | Responsibility |
|--------|----------------|
| `skelgraph/topology.py` | degree classification + segment tracing (the core) |
| `skelgraph/reduce.py`   | reduction: Laplacian contraction, edge collapse, `auto` |
| `skelgraph/neighbors.py`| radius / kNN / MST adjacency graphs, pitch estimation |
| `skelgraph/cleanup.py`  | junction consolidation |
| `skelgraph/extract.py`  | top-level `extract()` orchestration |
| `skelgraph/config.py`   | configuration dataclasses |

Built with **Python + NumPy/SciPy** (SciPy KD-trees, NetworkX graphs).

---

## 9. Success criteria

A correct extraction reproduces the underlying network's topology:

- the number and location of junctions (branch points) match,
- every un-branching chain is captured as exactly one segment,
- each segment correctly records its two terminators (branch point vs. tip),
- loops and disconnected components are preserved.

The test suite (`tests/`) exercises the topology core and the end-to-end
pipeline. See **`WORKLOG.md`** for the current coverage inventory.

---

## 10. Project status & roadmap

Current implementation status, the test-coverage inventory, the
reserved-but-unused config fields, and the roadmap of not-yet-implemented work
are tracked in **`WORKLOG.md`** at the repo root (read alongside `git log`)
rather than duplicated here. That split keeps this README a durable
specification and the WORKLOG the forward-looking status board.
