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


def build_neighbor_graph(points: np.ndarray, cfg: NeighborConfig) -> nx.Graph:
    """Build an adjacency graph according to ``cfg``."""
    scale = cfg.scale if cfg.scale is not None else estimate_pitch(points)
    if cfg.method == "radius":
        return radius_graph(points, cfg.radius_factor * scale)
    if cfg.method == "mst":
        return mst_graph(points, cfg.k)
    if cfg.method == "knn":
        return knn_graph(points, cfg.k)
    raise ValueError(f"unknown neighbor method: {cfg.method!r}")
