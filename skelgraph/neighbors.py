"""Build adjacency graphs over a point cloud."""

from __future__ import annotations

from typing import Optional

import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

from .config import NeighborConfig


def estimate_pitch(points: np.ndarray) -> float:
    """Median nearest-neighbour distance -- the characteristic sampling pitch."""
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return 1.0
    tree = cKDTree(points)
    d, _ = tree.query(points, k=2)  # column 1 is the nearest distinct neighbour
    return float(np.median(d[:, 1]))


def radius_graph(points: np.ndarray, radius: float) -> nx.Graph:
    """Connect every pair of points within ``radius``. Preserves loops."""
    points = np.asarray(points, dtype=float)
    tree = cKDTree(points)
    G = nx.Graph()
    G.add_nodes_from(range(len(points)))
    pairs = tree.query_pairs(radius, output_type="ndarray")
    for i, j in pairs:
        d = float(np.linalg.norm(points[i] - points[j]))
        G.add_edge(int(i), int(j), weight=d)
    return G


def knn_graph(points: np.ndarray, k: int) -> nx.Graph:
    """Symmetric k-nearest-neighbour graph."""
    points = np.asarray(points, dtype=float)
    n = len(points)
    k = min(k, n - 1)
    tree = cKDTree(points)
    d, idx = tree.query(points, k=k + 1)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for i in range(n):
        for jj, dist in zip(idx[i, 1:], d[i, 1:]):
            G.add_edge(int(i), int(jj), weight=float(dist))
    return G


def mst_graph(points: np.ndarray, k: int) -> nx.Graph:
    """Minimum spanning tree over each connected component of a k-NN graph.

    Produces a tree per component (no loops), robust to non-uniform pitch.
    """
    G = knn_graph(points, k)
    forest = nx.Graph()
    forest.add_nodes_from(G.nodes())
    for comp in nx.connected_components(G):
        sub = G.subgraph(comp)
        forest.add_edges_from(nx.minimum_spanning_edges(sub, data=True))
    return forest


def prune_shortcut_edges(
    graph: nx.Graph, coords: np.ndarray, eps: float = 1e-9
) -> nx.Graph:
    """Drop "shortcut" edges with a relative-neighbourhood rule.

    A proximity graph over points sampled along a curve network picks up edges
    that are short in space but *not* adjacent along the curve: the diagonal
    across the fan of arms meeting at a junction, or the hypotenuse across a
    right-angle corner.  These inflate node degree -- turning the single centre
    of a junction into a clique of degree>=3 nodes, and turning a bent segment
    into a triangle -- which later fragments into spurious branch points and
    stubs.

    An edge ``(i, j)`` is a shortcut when some **common neighbour** ``k`` is
    strictly closer to *both* endpoints than they are to each other: the detour
    ``i - k - j`` is shorter on both legs than the direct hop, so ``i`` and
    ``j`` are not genuine chain neighbours (this is the Relative Neighbourhood
    Graph condition, restricted to edges already present).  Removing such an
    edge:

    * leaves the true junction centre as the only high-degree node (the fan's
      outer members fall back to degree 2, i.e. they are returned to their
      arms), and
    * turns a corner triangle back into a single degree-2 bend (no branch
      point, no stub).

    Because the witness ``k`` is a *common neighbour*, the path ``i - k - j``
    already exists, so removal never disconnects the graph.  Edges are examined
    longest-first against the live graph, so each removal always has a strictly
    shorter surviving detour -- connectivity is preserved even in dense
    clusters.
    """
    coords = np.asarray(coords, dtype=float)
    H = graph.copy()

    def elen(e):
        return float(np.linalg.norm(coords[e[0]] - coords[e[1]]))

    for i, j in sorted(graph.edges(), key=elen, reverse=True):
        if not H.has_edge(i, j):
            continue
        d_ij = float(np.linalg.norm(coords[i] - coords[j]))
        for k in set(H.neighbors(i)) & set(H.neighbors(j)):
            if (np.linalg.norm(coords[i] - coords[k]) < d_ij - eps
                    and np.linalg.norm(coords[j] - coords[k]) < d_ij - eps):
                H.remove_edge(i, j)
                break
    return H


def build_neighbor_graph(points: np.ndarray, cfg: NeighborConfig) -> nx.Graph:
    """Build an adjacency graph according to ``cfg``.

    This is the raw proximity graph only.  Shortcut-edge removal
    (:func:`prune_shortcut_edges`) is applied by the pipeline
    (:func:`skelgraph.extract.extract`) for 1-D skeletons but *not* for surface
    mode, so it is deliberately left out here.
    """
    scale = cfg.scale if cfg.scale is not None else estimate_pitch(points)
    if cfg.method == "radius":
        return radius_graph(points, cfg.radius_factor * scale)
    if cfg.method == "mst":
        return mst_graph(points, cfg.k)
    if cfg.method == "knn":
        return knn_graph(points, cfg.k)
    raise ValueError(f"unknown neighbor method: {cfg.method!r}")
