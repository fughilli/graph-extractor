"""Extract branch points and segments from a 1-D adjacency graph.

Given an undirected graph whose nodes are points on a curve network (each
interior point at degree 2), this module classifies nodes by degree and traces
the maximal un-branching chains ("segments") between junctions/tips.

Definitions (see README):
  * degree 1        -> tip / free endpoint
  * degree 2        -> interior point of a segment
  * degree >= 3     -> **branch point** (junction)

A **segment** is an ordered list of points forming one un-branching chain,
terminated at each end by a branch point, a tip, or nothing (a closed loop).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import networkx as nx


def _ekey(a: int, b: int) -> Tuple[int, int]:
    """Canonical undirected edge key."""
    return (a, b) if a <= b else (b, a)


@dataclass
class Segment:
    """One un-branching chain of points.

    Attributes
    ----------
    points:
        Ordered list of node indices along the chain, including both ends.
        For a closed loop the first and last index are equal.
    end_nodes:
        The two terminating node indices, or ``None`` for a free/open end.
        For a closed loop with no junction both are ``None``.
    ends:
        The two terminators expressed as branch-point ids (index into
        :attr:`Topology.branch_points`) or ``None`` if that end is a tip or
        open loop.
    closed:
        ``True`` if the chain returns to its starting node (a loop).
    """

    points: List[int]
    end_nodes: Tuple[Optional[int], Optional[int]]
    ends: Tuple[Optional[int], Optional[int]]
    closed: bool

    @property
    def n_branch_ends(self) -> int:
        """Number of *distinct* branch points terminating this segment (0/1/2)."""
        return len({e for e in self.ends if e is not None})

    @property
    def is_loop(self) -> bool:
        return self.closed


@dataclass
class Topology:
    """Result of :func:`extract_topology`."""

    coords: np.ndarray             # (n, 3) coordinates of all skeleton nodes
    branch_nodes: List[int]        # node index of each branch point
    branch_points: np.ndarray      # (m, 3) coordinates of branch points
    segments: List[Segment]
    isolated: List[int]            # degree-0 node indices
    graph: nx.Graph

    def summary(self) -> str:
        by_ends = {0: 0, 1: 0, 2: 0}
        loops = 0
        for s in self.segments:
            if s.closed and s.n_branch_ends == 0:
                loops += 1
            by_ends[s.n_branch_ends] = by_ends.get(s.n_branch_ends, 0) + 1
        return (
            f"{len(self.branch_points)} branch points, "
            f"{len(self.segments)} segments "
            f"(0-branch: {by_ends[0]}, 1-branch: {by_ends[1]}, "
            f"2-branch: {by_ends[2]}), "
            f"{loops} closed loop(s), {len(self.isolated)} isolated point(s)"
        )


def extract_topology(graph: nx.Graph, coords: np.ndarray) -> Topology:
    """Extract branch points and segments from a 1-D adjacency ``graph``.

    Parameters
    ----------
    graph:
        Undirected graph. Node ids must index into ``coords``. Interior points
        are expected at degree 2; degree >= 3 nodes become branch points.
    coords:
        ``(n, 3)`` array of coordinates.
    """
    coords = np.asarray(coords, dtype=float)
    G = graph

    degree = dict(G.degree())
    branch_nodes = sorted(n for n in G.nodes() if degree[n] >= 3)
    tips = {n for n in G.nodes() if degree[n] == 1}
    isolated = sorted(n for n in G.nodes() if degree[n] == 0)
    specials = set(branch_nodes) | tips
    branch_id = {n: i for i, n in enumerate(branch_nodes)}

    def to_end(node: Optional[int]) -> Optional[int]:
        return branch_id.get(node) if node is not None else None

    used_edges = set()
    segments: List[Segment] = []

    # --- 1. Chains anchored at a special node (branch point or tip) ---------
    for u in sorted(specials):
        for v in sorted(G.neighbors(u)):
            ek = _ekey(u, v)
            if ek in used_edges:
                continue
            used_edges.add(ek)
            path = [u, v]
            prev, cur = u, v
            # Walk along degree-2 interior nodes until the next special node.
            while cur not in specials:
                nxt = None
                for w in G.neighbors(cur):
                    if w != prev and _ekey(cur, w) not in used_edges:
                        nxt = w
                        break
                if nxt is None:
                    # Fall back: the only other neighbour (handles the final
                    # step of a loop back onto the start node).
                    others = [w for w in G.neighbors(cur) if w != prev]
                    if not others:
                        break
                    nxt = others[0]
                used_edges.add(_ekey(cur, nxt))
                path.append(nxt)
                prev, cur = cur, nxt
                if cur == u:  # closed back onto the anchor (loop on a junction)
                    break
            end_a, end_b = path[0], path[-1]
            segments.append(
                Segment(
                    points=path,
                    end_nodes=(end_a, end_b),
                    ends=(to_end(end_a), to_end(end_b)),
                    closed=(end_a == end_b),
                )
            )

    # --- 2. Pure loops: components of all-degree-2 nodes, no special anchor --
    all_edges = {_ekey(a, b) for a, b in G.edges()}
    leftover = all_edges - used_edges
    while leftover:
        a, b = next(iter(leftover))
        used_edges.add(_ekey(a, b))
        leftover.discard(_ekey(a, b))
        path = [a, b]
        prev, cur = a, b
        while cur != a:
            nxt = None
            for w in G.neighbors(cur):
                if w != prev and _ekey(cur, w) in leftover:
                    nxt = w
                    break
            if nxt is None:
                break
            used_edges.add(_ekey(cur, nxt))
            leftover.discard(_ekey(cur, nxt))
            path.append(nxt)
            prev, cur = cur, nxt
        segments.append(
            Segment(points=path, end_nodes=(None, None), ends=(None, None),
                    closed=True)
        )

    # --- 3. Isolated points -------------------------------------------------
    for n in isolated:
        segments.append(
            Segment(points=[n], end_nodes=(None, None), ends=(None, None),
                    closed=False)
        )

    branch_points = (
        coords[branch_nodes] if branch_nodes else np.empty((0, coords.shape[1]))
    )
    return Topology(
        coords=coords,
        branch_nodes=branch_nodes,
        branch_points=branch_points,
        segments=segments,
        isolated=isolated,
        graph=G,
    )
