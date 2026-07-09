"""Graph cleanup: consolidate clustered branch points into single junctions.

Skeletonization of a *thick* junction (e.g. where several tubes meet) often
yields a little cluster of degree>=3 nodes joined by very short edges rather
than one clean branch point.  :func:`consolidate_branch_points` merges such
clusters, resolving the "near-junction ambiguity" noted in the README.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import networkx as nx


def median_edge_length(graph: nx.Graph, coords: np.ndarray) -> float:
    lengths = [np.linalg.norm(coords[a] - coords[b]) for a, b in graph.edges()]
    return float(np.median(lengths)) if lengths else 0.0


def consolidate_branch_points(
    graph: nx.Graph, coords: np.ndarray, max_gap: float
) -> Tuple[nx.Graph, np.ndarray]:
    """Merge directly-adjacent branch points closer than ``max_gap``.

    Two branch points (degree >= 3) joined by a single graph edge shorter than
    ``max_gap`` are fused into one node placed at their centroid.  Only
    *direct* branch-to-branch edges are merged, so genuine junctions separated
    by a real segment (with interior points) are never combined.  ``max_gap <=
    0`` disables consolidation.
    """
    if max_gap <= 0:
        return graph, coords

    coords = np.asarray(coords, dtype=float)
    deg = dict(graph.degree())
    branch = {n for n in graph.nodes() if deg[n] >= 3}

    parent = {n: n for n in graph.nodes()}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in graph.edges():
        if a in branch and b in branch:
            if np.linalg.norm(coords[a] - coords[b]) < max_gap:
                union(a, b)

    # Build merged node set and coordinates (centroid of each cluster).
    clusters: dict = {}
    for n in graph.nodes():
        clusters.setdefault(find(n), []).append(n)
    roots = list(clusters.keys())
    rep = {root: k for k, root in enumerate(roots)}
    new_coords = np.array([coords[clusters[r]].mean(axis=0) for r in roots])

    new_graph = nx.Graph()
    new_graph.add_nodes_from(range(len(roots)))
    for a, b in graph.edges():
        ra, rb = rep[find(a)], rep[find(b)]
        if ra != rb:
            new_graph.add_edge(ra, rb)
    return new_graph, new_coords
