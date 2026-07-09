"""Instrumented pipeline: run skelgraph's real primitives while capturing every
intermediate stage for visualization.

This mirrors :func:`skelgraph.extract.extract` step for step but, instead of
returning only the final :class:`~skelgraph.topology.Topology`, records the
artifacts produced along the way:

* the raw input,
* (collapse) the Laplacian-contracted cloud, optionally frame-by-frame,
* the adjacency / skeleton graph edges,
* junction consolidation (which branch-to-branch edges were fused),
* per-node degree classification (tip / interior / branch),
* the traced segments.

It calls the *same* functions the library uses (``reduce``, ``neighbors``,
``cleanup``, ``topology``) so what you see is the real algorithm, not a
re-implementation.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

import numpy as np
import networkx as nx

from skelgraph.config import Config, ReduceConfig, NeighborConfig
from skelgraph.neighbors import estimate_pitch, radius_graph, build_neighbor_graph
from skelgraph.reduce import laplacian_contraction, edge_collapse, local_dimensionality
from skelgraph.cleanup import consolidate_branch_points, median_edge_length
from skelgraph.topology import extract_topology
from skelgraph.extract import _prune_stubs


# --------------------------------------------------------------------------
# Config assembly from a flat dict of dotted keys (mirrors the UI controls)
# --------------------------------------------------------------------------
_REDUCE_FIELDS = {f.name for f in dataclasses.fields(ReduceConfig)}
_NEIGHBOR_FIELDS = {f.name for f in dataclasses.fields(NeighborConfig)}
_TOP_FIELDS = {"min_stub_points", "junction_merge_factor"}


def build_config(flat: Optional[Dict]) -> Config:
    """Build a :class:`Config` from ``{"reduce.mode": ..., "neighbors.k": ...}``."""
    flat = flat or {}
    reduce_kw, neigh_kw, top_kw = {}, {}, {}
    for key, val in flat.items():
        if key.startswith("reduce."):
            name = key.split(".", 1)[1]
            if name in _REDUCE_FIELDS:
                reduce_kw[name] = val
        elif key.startswith("neighbors."):
            name = key.split(".", 1)[1]
            if name in _NEIGHBOR_FIELDS:
                neigh_kw[name] = val
        elif key in _TOP_FIELDS:
            top_kw[key] = val
    return Config(
        reduce=ReduceConfig(**reduce_kw),
        neighbors=NeighborConfig(**neigh_kw),
        **top_kw,
    )


# --------------------------------------------------------------------------
# Serialization helpers
# --------------------------------------------------------------------------
def _pts(a: np.ndarray) -> List:
    return np.round(np.asarray(a, float), 4).tolist()


def _edges(g: nx.Graph) -> List:
    return [[int(a), int(b)] for a, b in g.edges()]


# --------------------------------------------------------------------------
# The instrumented pipeline
# --------------------------------------------------------------------------
def run(points: np.ndarray, config: Config, animate: bool = False,
        max_frames: int = 12) -> Dict:
    """Run the pipeline, returning a dict of JSON-serialisable stages."""
    points = np.asarray(points, float)
    cfg = config
    stages: Dict = {}
    notes: List[str] = []

    mode = cfg.reduce.mode
    scale = cfg.reduce.scale if cfg.reduce.scale is not None else estimate_pitch(points)

    # ---- Stage 0: input --------------------------------------------------
    stages["input"] = {"points": _pts(points), "n": len(points), "scale": round(float(scale), 4)}

    # ---- auto: report the local-shape decision --------------------------
    if mode == "auto":
        ratios = local_dimensionality(points, cfg.reduce.contraction_neighbor_factor * scale)
        sheet = (ratios[:, 0] > 0.35) & (ratios[:, 1] < 0.2)
        chosen = "collapse" if sheet.mean() > 0.5 else "surface"
        stages["auto"] = {
            "sheet_mask": sheet.astype(int).tolist(),
            "sheet_fraction": round(float(sheet.mean()), 3),
            "chosen": chosen,
        }
        notes.append(f"auto: {sheet.mean():.0%} sheet-like → {chosen}")
        mode = chosen

    # ---- Stage 1: reduce -------------------------------------------------
    if mode == "collapse":
        G0 = radius_graph(points, cfg.reduce.contraction_neighbor_factor * scale)
        contracted = laplacian_contraction(points, cfg.reduce, graph=G0)

        frames = None
        if animate:
            # Reproduce the intermediate states by re-running with fewer
            # iterations (deterministic: same start, same WL schedule).
            total = cfg.reduce.contraction_iterations
            steps = sorted(set(np.linspace(0, total, min(max_frames, total + 1)).astype(int)))
            frames = []
            for k in steps:
                c = dataclasses.replace(cfg.reduce, contraction_iterations=int(k))
                frames.append(_pts(laplacian_contraction(points, c, graph=G0)))

        skel_pts, skel_graph = edge_collapse(
            contracted, G0, cfg.reduce.merge_factor, positions=points
        )
        stages["reduce"] = {
            "mode": "collapse",
            "contraction_graph_edges": _edges(G0),
            "contracted": _pts(contracted),
            "contraction_frames": frames,
            "skeleton_points": _pts(skel_pts),
            "skeleton_edges": _edges(skel_graph),
        }
        reduced, graph = skel_pts, skel_graph
        notes.append(
            f"collapse: {len(points)} pts → {len(skel_pts)} skeleton nodes "
            f"({G0.number_of_edges()} contraction edges)"
        )
    else:  # none / surface
        reduced = points.copy()
        graph = build_neighbor_graph(reduced, cfg.neighbors)
        stages["reduce"] = {
            "mode": mode,
            "reduced_points": _pts(reduced),
            "adjacency_edges": _edges(graph),
            "method": cfg.neighbors.method,
        }
        notes.append(
            f"{mode}: {cfg.neighbors.method} graph, "
            f"{graph.number_of_edges()} edges over {len(reduced)} points"
        )

    # ---- Stage 2: junction consolidation (1-D skeletons only) -----------
    if mode != "surface" and cfg.junction_merge_factor > 0:
        max_gap = cfg.junction_merge_factor * median_edge_length(graph, reduced)
        deg = dict(graph.degree())
        branch = {n for n in graph.nodes() if deg[n] >= 3}
        # Same rule as consolidate_branch_points, captured for display.
        merged_edges = [
            [int(a), int(b)]
            for a, b in graph.edges()
            if a in branch and b in branch
            and float(np.linalg.norm(reduced[a] - reduced[b])) < max_gap
        ]
        new_graph, new_reduced = consolidate_branch_points(graph, reduced, max_gap)
        stages["consolidate"] = {
            "max_gap": round(float(max_gap), 4),
            "merged_edges": merged_edges,
            "before_points": _pts(reduced),
            "n_before": graph.number_of_nodes(),
            "n_after": new_graph.number_of_nodes(),
        }
        graph, reduced = new_graph, new_reduced
        if merged_edges:
            notes.append(
                f"consolidate: fused {len(merged_edges)} branch-branch edge(s) "
                f"(gap < {max_gap:.3g})"
            )

    # ---- Stage 3-5: classify degrees + trace segments -------------------
    topo = extract_topology(graph, reduced)
    if mode != "surface":
        topo = _prune_stubs(topo, cfg.min_stub_points)

    deg = dict(graph.degree())
    branch_set = set(topo.branch_nodes)
    tips = [int(n) for n in graph.nodes() if deg[n] == 1]
    kinds = []
    for n in graph.nodes():
        d = deg[n]
        kinds.append("branch" if d >= 3 else "tip" if d == 1 else "interior" if d == 2 else "isolated")
    node_degree = {int(n): int(deg[n]) for n in graph.nodes()}

    segments = []
    for s in topo.segments:
        segments.append({
            "points": [int(i) for i in s.points],
            "ends": [None if e is None else int(e) for e in s.ends],
            "closed": bool(s.closed),
            "n_branch_ends": int(s.n_branch_ends),
        })

    stages["topology"] = {
        "coords": _pts(topo.coords),
        "edges": _edges(graph),
        "degree": node_degree,
        "kinds": kinds,
        "branch_nodes": [int(n) for n in topo.branch_nodes],
        "branch_points": _pts(topo.branch_points),
        "tips": tips,
        "isolated": [int(n) for n in topo.isolated],
        "segments": segments,
    }
    stages["summary"] = topo.summary()
    stages["notes"] = notes
    stages["effective_mode"] = mode
    return stages
