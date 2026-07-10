"""End-to-end tests on synthetic point clouds."""

import numpy as np
import pytest

from skelgraph import extract, Config, ReduceConfig, NeighborConfig


def _chain(start, direction, n, pitch):
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    return np.asarray(start, float) + np.outer(np.arange(1, n + 1) * pitch, d)


def test_y_junction_from_points():
    pitch = 1.0
    origin = np.zeros((1, 3))
    dirs = [(np.cos(a), np.sin(a), 0.0)
            for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]  # 120 deg apart
    arms = [_chain((0, 0, 0), d, 6, pitch) for d in dirs]
    pts = np.vstack([origin] + arms)

    topo = extract(pts, Config(reduce=ReduceConfig(mode="none")))
    assert len(topo.branch_points) == 1
    assert len(topo.segments) == 3
    assert np.allclose(topo.branch_points[0], [0, 0, 0], atol=1e-9)
    for s in topo.segments:
        assert s.n_branch_ends == 1


def test_x_junction_returns_extrema_to_arms():
    # Four arms meeting at the origin. A radius graph links each arm's first
    # point to the neighbouring arms' first points (diagonals across the fan),
    # which without pruning would inflate them to degree>=3 and let
    # consolidation absorb them into the junction. Shortcut pruning must leave
    # one degree-4 centre and return every arm point to its arm.
    pitch = 1.0
    dirs = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
    arms = [_chain((0, 0, 0), d, 6, pitch) for d in dirs]
    pts = np.vstack([np.zeros((1, 3))] + arms)      # 1 + 4*6 = 25 points

    topo = extract(pts, Config(reduce=ReduceConfig(mode="none")))
    assert len(topo.branch_points) == 1
    assert np.allclose(topo.branch_points[0], [0, 0, 0], atol=1e-9)
    arm_segs = [s for s in topo.segments if s.n_branch_ends == 1]
    assert len(arm_segs) == 4
    assert len(topo.segments) == 4
    # No point absorbed into the junction: all 25 survive as graph nodes...
    assert len(topo.coords) == len(pts)
    # ...and each arm keeps the junction + all six of its points.
    for s in arm_segs:
        assert len(s.points) == 7


def test_x_junction_without_pruning_absorbs_extrema():
    # The same cloud with pruning off: the fan collapses and arm points are
    # absorbed, so fewer nodes survive. Locks in what the flag controls.
    pitch = 1.0
    dirs = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
    pts = np.vstack([np.zeros((1, 3))] + [_chain((0, 0, 0), d, 6, pitch) for d in dirs])
    cfg = Config(reduce=ReduceConfig(mode="none"),
                 neighbors=NeighborConfig(prune_shortcuts=False))
    topo = extract(pts, cfg)
    assert len(topo.coords) < len(pts)              # extrema were absorbed


def _grid_points(nx_, ny_, spacing, pitch):
    xs = np.arange(nx_) * spacing
    ys = np.arange(ny_) * spacing
    per = max(1, round(spacing / pitch))
    parts = []
    for y in ys:
        parts.append(np.linspace([xs[0], y, 0], [xs[-1], y, 0], per * (nx_ - 1) + 1))
    for x in xs:
        parts.append(np.linspace([x, ys[0], 0], [x, ys[-1], 0], per * (ny_ - 1) + 1))
    return np.unique(np.round(np.vstack(parts), 6), axis=0)


def test_grid_corners_stay_degree_two():
    # In a 3x2 lattice, only the two edge-midpoint crossings are real (T)
    # junctions; the four outer corners are 90-degree bends. The corner diagonal
    # shortcut must be pruned so each corner stays a single degree-2 bend --
    # no branch point, no stub segment.
    pts = _grid_points(3, 2, 4.0, 0.5)
    topo = extract(pts, Config(reduce=ReduceConfig(mode="none")))
    assert len(topo.branch_points) == 2
    stubs = [s for s in topo.segments if s.n_branch_ends == 1 and not s.closed]
    assert stubs == []                              # no spurious corner stubs
    # Each corner survives as exactly one degree-2 node.
    for cx, cy in [(0, 0), (8, 0), (0, 4), (8, 4)]:
        idx = np.where((np.abs(topo.coords[:, 0] - cx) < 1e-6)
                       & (np.abs(topo.coords[:, 1] - cy) < 1e-6))[0]
        assert len(idx) == 1
        assert topo.graph.degree(int(idx[0])) == 2


def test_open_line_from_points():
    pts = _chain((0, 0, 0), (1, 0, 0), 20, 0.5)
    topo = extract(pts, Config(reduce=ReduceConfig(mode="none")))
    assert len(topo.branch_points) == 0
    assert len(topo.segments) == 1
    assert topo.segments[0].n_branch_ends == 0


def _cylinder_grid(radius, length, n_axial, n_circ):
    z = np.linspace(0, length, n_axial)
    theta = np.linspace(0, 2 * np.pi, n_circ, endpoint=False)
    pts = []
    for zz in z:
        for th in theta:
            pts.append((radius * np.cos(th), radius * np.sin(th), zz))
    return np.asarray(pts)


def test_cylinder_collapse_to_axis():
    radius = 1.0
    pts = _cylinder_grid(radius=radius, length=10.0, n_axial=20, n_circ=16)
    cfg = Config(
        reduce=ReduceConfig(mode="collapse", contraction_iterations=12),
        neighbors=NeighborConfig(method="radius", radius_factor=1.8),
    )
    topo = extract(pts, cfg)

    # Reduced nodes should sit near the z-axis (contracted inward).
    radial = np.linalg.norm(topo.coords[:, :2], axis=1)
    assert radial.mean() < 0.25 * radius

    # A tube collapses to a single un-branching centerline: no junctions.
    assert len(topo.branch_points) == 0
    assert len(topo.segments) == 1

    seg = topo.segments[0]
    assert seg.n_branch_ends == 0        # open chain, terminated by two tips
    assert not seg.closed
    # The centerline must span the axis, not collapse to a blob: keep a node
    # per cross-section (20 rings) and cover most of the original z-extent.
    assert len(seg.points) >= 15
    zspan = np.ptp(topo.coords[:, 2])
    assert zspan > 0.6 * 10.0


def _tube(axis_dir, length, rad, n_ax, n_circ, start):
    d = np.asarray(axis_dir, float)
    d /= np.linalg.norm(d)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a); u /= np.linalg.norm(u)
    v = np.cross(d, u)
    pts = []
    for t in np.linspace(start, length, n_ax):
        c = t * d
        for th in np.linspace(0, 2 * np.pi, n_circ, endpoint=False):
            pts.append(c + rad * (np.cos(th) * u + np.sin(th) * v))
    return np.asarray(pts)


def test_branching_tube_collapses_to_one_junction():
    # Three cylindrical arms meeting at the origin (a 3-D "Y" made of tubes).
    dirs = [(np.cos(a), np.sin(a), 0.0)
            for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    pts = np.vstack([_tube(d, 6.0, 0.6, 14, 12, start=0.3) for d in dirs])

    topo = extract(pts, Config(reduce=ReduceConfig(mode="collapse")))
    # Junction consolidation should yield exactly one branch point of degree 3
    # feeding three arm segments (each a stub terminated by the junction).
    assert len(topo.branch_points) == 1
    assert np.allclose(topo.branch_points[0], [0, 0, 0], atol=0.4)
    arms = [s for s in topo.segments if s.n_branch_ends == 1]
    assert len(arms) == 3
    assert len(topo.segments) == 3


def test_branching_tube_junction_collapses_to_single_node():
    # The collapse reduction leaves a little blob of degree>=3 nodes at a tube
    # junction (overlapping cross-sections). Shortcut pruning must elect a single
    # central junction node -- the same "connected neighbourhood -> one centre"
    # cleanup the skeleton cases get -- without disconnecting the skeleton.
    import networkx as nx
    from skelgraph.reduce import collapse_to_skeleton
    from skelgraph.neighbors import prune_shortcut_edges

    dirs = [(np.cos(a), np.sin(a), 0.0)
            for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    pts = np.vstack([_tube(d, 6.0, 0.6, 14, 12, start=0.3) for d in dirs])
    sk_pts, sk_g = collapse_to_skeleton(pts, ReduceConfig(mode="collapse"))

    before = sum(1 for n in sk_g if sk_g.degree(n) >= 3)
    pruned = prune_shortcut_edges(sk_g, sk_pts)
    after = sum(1 for n in pruned if pruned.degree(n) >= 3)

    assert before > 1          # collapse leaves a multi-node junction blob
    assert after == 1          # pruning elects one central junction
    assert nx.is_connected(pruned)


def test_cylinder_surface_mode_keeps_points():
    pts = _cylinder_grid(radius=1.0, length=5.0, n_axial=8, n_circ=12)
    cfg = Config(reduce=ReduceConfig(mode="surface"))
    topo = extract(pts, cfg)
    # Surface mode does not move or merge points.
    assert len(topo.coords) == len(pts)


def _torus_grid(major_radius, minor_radius, n_major, n_minor):
    """Surface samples on a torus whose centerline is a circle of radius R."""
    u = np.linspace(0.0, 2 * np.pi, n_major, endpoint=False)
    v = np.linspace(0.0, 2 * np.pi, n_minor, endpoint=False)
    pts = []
    for uu in u:
        cu, su = np.cos(uu), np.sin(uu)
        for vv in v:
            rr = major_radius + minor_radius * np.cos(vv)
            pts.append((rr * cu, rr * su, minor_radius * np.sin(vv)))
    return np.asarray(pts)


def test_torus_collapses_to_one_loop():
    # A *thick* looped tube: the collapse reduction must recover the underlying
    # cycle (a segment closing on itself, no junctions and no tips).
    R, r = 5.0, 1.0
    pts = _torus_grid(major_radius=R, minor_radius=r, n_major=32, n_minor=12)

    topo = extract(pts, Config(reduce=ReduceConfig(mode="collapse")))

    assert len(topo.branch_points) == 0
    assert len(topo.segments) == 1
    seg = topo.segments[0]
    assert seg.closed                    # a cycle, not an open chain
    assert seg.n_branch_ends == 0

    # The recovered centerline is the tube axis: a ring of radius ~R in z~0,
    # not the r-thick surface it was collapsed from.
    radial = np.linalg.norm(topo.coords[:, :2], axis=1)
    assert abs(radial.mean() - R) < 0.25 * R
    assert np.abs(topo.coords[:, 2]).mean() < 0.25 * r
    # Keep a node per cross-section rather than collapsing the loop to a blob.
    assert len(seg.points) >= 24
