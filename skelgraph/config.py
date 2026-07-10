"""Configuration objects for the skeleton-graph extraction pipeline.

The pipeline has two configurable stages:

1. **Reduction / skeletonization** (:class:`ReduceConfig`) -- turn a possibly
   thick / surface-sampled cloud into a 1-D skeleton (or keep it as a surface
   graph).  See the README, section 6.
2. **Neighbour graph** (:class:`NeighborConfig`) -- how adjacency between
   (reduced) points is inferred before topology extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence
import math


@dataclass
class NeighborConfig:
    """How to connect points into an adjacency graph.

    Attributes
    ----------
    method:
        ``"radius"`` connects every pair closer than ``radius`` (preserves
        loops, keeps interior points at degree 2 when ``radius`` is just above
        the sampling pitch).  ``"mst"`` builds a minimum spanning tree over a
        k-NN graph (robust to non-uniform pitch, but **cannot represent
        loops** -- every component becomes a tree).
    scale:
        Characteristic sampling pitch.  If ``None`` it is estimated as the
        median nearest-neighbour distance.
    radius_factor:
        ``radius = radius_factor * scale``.  Values around ``1.5`` connect a
        point only to its immediate chain neighbours (recommended); larger
        values create shortcuts that inflate node degree.
    k:
        Neighbour count for the k-NN graph underlying ``"mst"``.
    """

    method: str = "radius"
    scale: Optional[float] = None
    radius_factor: float = 1.6
    k: int = 10

    # Remove junction/corner "shortcut" edges (a diagonal across a fan of arms,
    # or the hypotenuse across a right-angle bend) before topology extraction.
    # Keeps a junction as one central node -- returning the fan's outer points
    # to their arms rather than absorbing them -- and keeps a bent segment
    # degree-2 (no spurious branch point / stub).  Applied to radius/knn graphs
    # of 1-D skeletons only; never in ``surface`` mode.  See
    # :func:`skelgraph.neighbors.prune_shortcut_edges`.
    prune_shortcuts: bool = True


@dataclass
class ReduceConfig:
    """How to reduce the raw cloud before topology extraction.

    ``mode``:
        - ``"none"``     -- input is already a 1-D skeleton; skip reduction.
        - ``"surface"``  -- keep surface/manifold connectivity (2-D graph).
        - ``"collapse"`` -- contract tubular structure onto its medial axis
          (Laplacian / graph contraction), producing a 1-D centerline.
        - ``"auto"``     -- decide per point from local covariance shape and
          ``collapse_radius``.
    """

    mode: str = "none"
    scale: Optional[float] = None

    # -- collapse / auto parameters ---------------------------------------
    collapse_radius: float = math.inf
    contraction_iterations: int = 10
    contraction_neighbor_factor: float = 2.5
    wl_init: Optional[float] = None      # initial contraction weight (auto if None)
    sl: float = 1.6                      # per-iteration growth of WL
    wh: float = 1.0                      # attraction-to-original weight
    boundary_anchor: float = 8.0         # extra attraction weight for surface-
                                         # boundary points (tube ends / segment
                                         # tips), whose one-sided neighbourhoods
                                         # otherwise make contraction retract them
                                         # inward and shrink segments lengthwise.
                                         # 0 disables (uniform anchoring).
    merge_factor: float = 0.5            # collapse edge if len < merge_factor * longest
                                         # incident edge (adaptive, scale-free)
    axis_hint: Optional[Sequence[float]] = None


@dataclass
class Config:
    """Top-level configuration."""

    reduce: ReduceConfig = field(default_factory=ReduceConfig)
    neighbors: NeighborConfig = field(default_factory=NeighborConfig)

    # Prune stub segments (one branch end + one free tip) shorter, in point
    # count, than this.  0 disables pruning.
    min_stub_points: int = 0

    # Consolidate clustered branch points: merge directly-adjacent junctions
    # closer than ``junction_merge_factor * median_skeleton_edge_length`` into
    # one branch point (resolves thick-junction fragmentation).  0 disables.
    junction_merge_factor: float = 2.0
