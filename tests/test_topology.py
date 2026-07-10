"""Unit tests for the core topology extractor on hand-built graphs."""

import numpy as np
import networkx as nx
import pytest

from skelgraph.topology import extract_topology
from skelgraph.neighbors import prune_shortcut_edges


def _graph(edges, n):
    G = nx.Graph()
    G.add_nodes_from(range(n))
    G.add_edges_from(edges)
    return G


def test_prune_shortcut_removes_corner_hypotenuse():
    # Right triangle: the hypotenuse (1,2) is a shortcut across the corner at 0.
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    G = _graph([(0, 1), (0, 2), (1, 2)], 3)
    H = prune_shortcut_edges(G, coords)
    assert {frozenset(e) for e in H.edges()} == {frozenset((0, 1)), frozenset((0, 2))}
    assert nx.is_connected(H)          # never disconnects
    assert H.degree(0) == 2            # corner stays a degree-2 bend


def test_prune_shortcut_keeps_chordless_cycle():
    # A genuine loop sampled as a chordless ring: no point is closer to two ring
    # neighbours than they are to each other, so every edge must survive (loops
    # are preserved). (RNG is triangle-free, so real loops need >= 4 points --
    # true of any realistically sampled cycle.)
    th = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    coords = np.column_stack([np.cos(th), np.sin(th), np.zeros(6)])
    G = _graph([(i, (i + 1) % 6) for i in range(6)], 6)
    H = prune_shortcut_edges(G, coords)
    assert H.number_of_edges() == 6
    assert nx.is_connected(H)


def test_prune_shortcut_preserves_connectivity_dense_cluster():
    # A 5-clique (all pairs edged): pruning may thin it but must not split it.
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0.5, 0.5, 0]], float)
    G = nx.complete_graph(5)
    H = prune_shortcut_edges(G, coords)
    assert nx.is_connected(H)


def _coords(n):
    # Coordinates are irrelevant to topology; supply distinct points.
    return np.arange(3 * n, dtype=float).reshape(n, 3)


def _seg_end_counts(topo):
    return sorted(s.n_branch_ends for s in topo.segments)


def test_open_chain():
    G = _graph([(0, 1), (1, 2), (2, 3), (3, 4)], 5)
    t = extract_topology(G, _coords(5))
    assert len(t.branch_points) == 0
    assert len(t.segments) == 1
    s = t.segments[0]
    assert s.points == [0, 1, 2, 3, 4]
    assert s.n_branch_ends == 0
    assert not s.closed


def test_y_junction():
    edges = [(0, 1), (1, 2), (0, 3), (3, 4), (0, 5), (5, 6)]
    t = extract_topology(_graph(edges, 7), _coords(7))
    assert len(t.branch_points) == 1
    assert t.branch_nodes == [0]
    assert len(t.segments) == 3
    assert _seg_end_counts(t) == [1, 1, 1]
    for s in t.segments:
        assert 0 in s.end_nodes            # every arm touches the junction
        assert len(s.points) == 3


def test_h_two_junctions_and_bridge():
    edges = [(0, 1), (0, 2), (0, 6), (6, 7), (7, 3), (3, 4), (3, 5)]
    t = extract_topology(_graph(edges, 8), _coords(8))
    assert len(t.branch_points) == 2
    assert len(t.segments) == 5
    # 4 stubs (1 branch end) + 1 bridge (2 branch ends)
    assert _seg_end_counts(t) == [1, 1, 1, 1, 2]
    bridge = [s for s in t.segments if s.n_branch_ends == 2][0]
    assert bridge.points in ([0, 6, 7, 3], [3, 7, 6, 0])


def test_adjacent_junctions_no_interior():
    edges = [(0, 1), (0, 2), (0, 3), (3, 4), (3, 5)]
    t = extract_topology(_graph(edges, 6), _coords(6))
    assert len(t.branch_points) == 2
    bridge = [s for s in t.segments if s.n_branch_ends == 2][0]
    assert set(bridge.points) == {0, 3}
    assert len(bridge.points) == 2


def test_pure_loop():
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    t = extract_topology(_graph(edges, 4), _coords(4))
    assert len(t.branch_points) == 0
    assert len(t.segments) == 1
    s = t.segments[0]
    assert s.closed
    assert s.n_branch_ends == 0
    assert s.points[0] == s.points[-1]
    assert len(s.points) == 5  # 4 nodes + closing repeat


def test_lollipop():
    # stub 0-1, loop 0-2-3-4-0; node 0 has degree 3.
    edges = [(0, 1), (0, 2), (2, 3), (3, 4), (4, 0)]
    t = extract_topology(_graph(edges, 5), _coords(5))
    assert len(t.branch_points) == 1
    assert len(t.segments) == 2
    loop = [s for s in t.segments if s.closed][0]
    stub = [s for s in t.segments if not s.closed][0]
    assert loop.n_branch_ends == 1
    assert loop.end_nodes == (0, 0)
    assert stub.n_branch_ends == 1
    assert set(stub.points) == {0, 1}


def test_isolated_point_and_component():
    # isolated node 9 plus a separate chain 0-1-2
    G = _graph([(0, 1), (1, 2)], 10)
    for k in range(3, 9):
        G.remove_node(k)
    t = extract_topology(G, _coords(10))
    assert 9 in t.isolated
    # one real chain segment + one single-point segment for the isolate
    chains = [s for s in t.segments if len(s.points) > 1]
    assert len(chains) == 1


def test_every_edge_used_exactly_once():
    # A more complex graph; verify segments partition the edges.
    edges = [(0, 1), (1, 2), (2, 0),          # a triangle loop
             (2, 3), (3, 4),                   # tail off the loop
             (4, 5), (4, 6)]                    # fork at the end
    t = extract_topology(_graph(edges, 7), _coords(7))
    seen = []
    for s in t.segments:
        for a, b in zip(s.points, s.points[1:]):
            seen.append(tuple(sorted((a, b))))
    assert sorted(seen) == sorted(tuple(sorted(e)) for e in edges)
