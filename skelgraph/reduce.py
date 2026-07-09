"""Reduction / skeletonization: turn a raw cloud into a 1-D skeleton.

Modes (see :class:`~skelgraph.config.ReduceConfig`):

* ``none``     -- pass the cloud through unchanged.
* ``surface``  -- pass through unchanged; a surface graph is built downstream.
* ``collapse`` -- Laplacian / graph contraction pulls tubular structure onto
  its medial axis, then a **connectivity-preserving edge collapse** merges each
  cross-section into one centerline node while keeping along-axis links.
* ``auto``     -- inspect local covariance shape and pick collapse vs surface.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import networkx as nx
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from .config import ReduceConfig
from .neighbors import estimate_pitch, radius_graph


def _graph_laplacian(n: int, edges) -> sp.csr_matrix:
    """Combinatorial (uniform-weight) graph Laplacian L = D - A."""
    if len(edges) == 0:
        return sp.csr_matrix((n, n))
    e = np.asarray(edges, dtype=np.int64)
    i = np.concatenate([e[:, 0], e[:, 1]])
    j = np.concatenate([e[:, 1], e[:, 0]])
    data = np.ones(len(i))
    A = sp.coo_matrix((data, (i, j)), shape=(n, n)).tocsr()
    deg = np.asarray(A.sum(axis=1)).ravel()
    D = sp.diags(deg)
    return (D - A).tocsr()


def laplacian_contraction(
    points: np.ndarray, cfg: ReduceConfig, graph: Optional[nx.Graph] = None
) -> np.ndarray:
    """Contract ``points`` toward their local medial axis.

    Solves, each iteration, the least-squares system

        [ WL * L ] P' = [ 0      ]
        [ WH     ]      [ WH * P ]

    increasing the contraction weight ``WL`` geometrically.  Uniform-weight
    Laplacian ``L`` moves each point toward the centroid of its neighbours;
    ``WH`` anchors it toward its current position.  A closed cross-section
    (a ring) has high graph curvature and collapses quickly; the long, low
    curvature axial direction barely moves -- which is what lets the following
    edge-collapse tell cross-section edges from axial edges.

    ``graph`` may be supplied to reuse a prebuilt neighbour graph (and to keep
    contraction and collapse consistent); otherwise a radius graph is built.
    """
    points = np.asarray(points, dtype=float)
    n = len(points)
    if n < 3:
        return points.copy()

    scale = cfg.scale if cfg.scale is not None else estimate_pitch(points)
    radius = cfg.contraction_neighbor_factor * scale

    P = points.copy()
    G = graph if graph is not None else radius_graph(P, radius)
    edges = list(G.edges())
    L = _graph_laplacian(n, edges)

    avg_deg = max(1.0, 2 * len(edges) / n)
    wl = cfg.wl_init if cfg.wl_init is not None else cfg.wh / avg_deg
    wh = np.full(n, cfg.wh)
    WH2 = sp.diags(wh ** 2)

    for _ in range(cfg.contraction_iterations):
        # Normal equations: (WL^2 L^T L + WH^2) P' = WH^2 P
        LtL = (L.T @ L).tocsc()
        Asys = (wl ** 2) * LtL + WH2
        rhs = WH2 @ P
        P = np.column_stack([spsolve(Asys.tocsc(), rhs[:, d]) for d in range(P.shape[1])])
        wl *= cfg.sl

    return P


def edge_collapse(
    contracted: np.ndarray,
    graph: nx.Graph,
    merge_factor: float,
    positions: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, nx.Graph]:
    """Collapse cross-section edges via an adaptive, scale-free threshold.

    An edge ``(a, b)`` is contracted (union-find) when its contracted length is
    small *relative to the longest edge incident to either endpoint*::

        len(a, b) < merge_factor * min(maxlen[a], maxlen[b])

    where ``maxlen[x]`` is the longest contracted edge at node ``x``.  A tube
    cross-section (ring) has edges that collapse toward zero while its along-axis
    edges keep a finite length, so ring edges satisfy the test and axial edges do
    not -- independent of *how far* contraction has progressed (which a fixed
    absolute threshold is sensitive to).

    ``positions`` gives the coordinates used to *place* each skeleton node (the
    centroid of its cluster).  Pass the **original** point positions so the
    centerline stays geometrically faithful even though contraction shrinks the
    cloud; if ``None``, the contracted positions are used.

    Returns the skeleton node coordinates and the induced skeleton graph.
    Because it uses the original connectivity, it never merges two distinct
    cross-sections that merely lie close along the axis after contraction.
    """
    contracted = np.asarray(contracted, dtype=float)
    positions = contracted if positions is None else np.asarray(positions, dtype=float)
    n = len(contracted)

    length = {}
    maxlen = np.zeros(n)
    for a, b in graph.edges():
        d = float(np.linalg.norm(contracted[a] - contracted[b]))
        length[(a, b)] = d
        maxlen[a] = max(maxlen[a], d)
        maxlen[b] = max(maxlen[b], d)

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for (a, b), d in length.items():
        if d < merge_factor * min(maxlen[a], maxlen[b]):
            union(a, b)

    clusters: dict = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    roots = list(clusters.keys())
    rep = {root: k for k, root in enumerate(roots)}

    coords = np.array([positions[clusters[r]].mean(axis=0) for r in roots])
    skel = nx.Graph()
    skel.add_nodes_from(range(len(roots)))
    for a, b in graph.edges():
        ra, rb = rep[find(a)], rep[find(b)]
        if ra != rb:
            skel.add_edge(ra, rb)
    return coords, skel


def collapse_to_skeleton(
    points: np.ndarray, cfg: ReduceConfig
) -> Tuple[np.ndarray, nx.Graph]:
    """Full collapse: contract, then edge-collapse cross-sections to a centerline.

    Returns ``(skeleton_points, skeleton_graph)``.
    """
    points = np.asarray(points, dtype=float)
    scale = cfg.scale if cfg.scale is not None else estimate_pitch(points)
    G0 = radius_graph(points, cfg.contraction_neighbor_factor * scale)
    contracted = laplacian_contraction(points, cfg, graph=G0)
    return edge_collapse(contracted, G0, cfg.merge_factor, positions=points)


def local_dimensionality(points: np.ndarray, radius: float) -> np.ndarray:
    """Per-point covariance eigenvalue ratios ``(lambda2/lambda1, lambda3/lambda1)``.

    ``lambda2/lambda1`` near 0 -> curve-like (1-D); near 1 with small
    ``lambda3/lambda1`` -> sheet/tube-like (2-D).
    """
    from scipy.spatial import cKDTree

    points = np.asarray(points, dtype=float)
    tree = cKDTree(points)
    ratios = np.zeros((len(points), 2))
    for i, p in enumerate(points):
        nb = tree.query_ball_point(p, radius)
        if len(nb) < 3:
            continue
        c = points[nb] - points[nb].mean(axis=0)
        vals = np.linalg.eigvalsh(c.T @ c)[::-1]  # descending
        l1 = vals[0] if vals[0] > 0 else 1.0
        ratios[i] = (vals[1] / l1, vals[2] / l1)
    return ratios


def reduce_points(
    points: np.ndarray, cfg: ReduceConfig
) -> Tuple[np.ndarray, Optional[nx.Graph], str]:
    """Apply the configured reduction.

    Returns ``(reduced_points, skeleton_graph_or_None, effective_mode)``. For
    ``collapse`` the skeleton graph carries the preserved connectivity and
    should be used directly; for other modes the graph is ``None`` and the
    neighbour graph is built downstream.
    """
    points = np.asarray(points, dtype=float)
    scale = cfg.scale if cfg.scale is not None else estimate_pitch(points)

    mode = cfg.mode
    if mode == "auto":
        ratios = local_dimensionality(points, cfg.contraction_neighbor_factor * scale)
        # Sheet/tube-like: lambda2/lambda1 large while lambda3/lambda1 small.
        sheet = (ratios[:, 0] > 0.35) & (ratios[:, 1] < 0.2)
        mode = "collapse" if sheet.mean() > 0.5 else "surface"

    if mode in ("none", "surface"):
        return points.copy(), None, mode

    if mode == "collapse":
        skel_pts, skel_graph = collapse_to_skeleton(points, cfg)
        return skel_pts, skel_graph, "collapse"

    raise ValueError(f"unknown reduce mode: {cfg.mode!r}")
