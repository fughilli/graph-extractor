"""Top-level pipeline: point cloud -> reduction -> graph -> topology."""

from __future__ import annotations

from typing import Optional

import numpy as np

from .config import Config
from .neighbors import build_neighbor_graph, prune_shortcut_edges
from .reduce import reduce_points
from .cleanup import consolidate_branch_points, median_edge_length
from .topology import Topology, extract_topology, Segment


def _prune_stubs(topo: Topology, min_points: int) -> Topology:
    """Drop stub segments (one branch end, one free tip) shorter than min_points.

    Only removes leaf stubs so connectivity between real junctions is kept.
    """
    if min_points <= 0:
        return topo
    keep = []
    for s in topo.segments:
        is_stub = s.n_branch_ends == 1 and not s.closed and (None in s.ends)
        if is_stub and len(s.points) < min_points:
            continue
        keep.append(s)
    topo.segments = keep
    return topo


def extract(points: np.ndarray, config: Optional[Config] = None) -> Topology:
    """Extract branch points and segments from a 3-D point cloud.

    Parameters
    ----------
    points:
        ``(N, 3)`` array of coordinates sampled along a curve network.
    config:
        Pipeline configuration; defaults to :class:`Config` (reduce mode
        ``"none"``, radius neighbour graph).

    Returns
    -------
    Topology
        Branch points and segments; see :class:`~skelgraph.topology.Topology`.
    """
    points = np.asarray(points, dtype=float)
    cfg = config or Config()

    reduced, skel_graph, mode = reduce_points(points, cfg.reduce)
    # collapse mode returns a connectivity-preserving skeleton graph; other
    # modes build the neighbour graph from the (reduced) points here.
    if skel_graph is not None:
        graph = skel_graph
    else:
        graph = build_neighbor_graph(reduced, cfg.neighbors)

    # Shortcut edges -- a diagonal across a junction's fan of arms or the
    # hypotenuse across a corner -- inflate node degree, turning a junction into
    # a clique and a bend into a triangle.  They arise both in a proximity graph
    # of a 1-D skeleton and in the little blob the collapse reduction leaves at a
    # tube junction, so prune in every mode except ``surface`` (which wants its
    # 2-D mesh intact).
    if mode != "surface" and cfg.neighbors.prune_shortcuts:
        graph = prune_shortcut_edges(graph, reduced)

    # Cleanup (junction consolidation, stub pruning) assumes a 1-D skeleton.
    # In surface mode the graph is intentionally 2-D (every interior node has
    # degree >= 3), so skip it.
    if mode != "surface":
        if cfg.junction_merge_factor > 0:
            max_gap = cfg.junction_merge_factor * median_edge_length(graph, reduced)
            graph, reduced = consolidate_branch_points(graph, reduced, max_gap)
        topo = extract_topology(graph, reduced)
        topo = _prune_stubs(topo, cfg.min_stub_points)
    else:
        topo = extract_topology(graph, reduced)
    return topo
