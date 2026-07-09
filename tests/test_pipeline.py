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


def test_cylinder_surface_mode_keeps_points():
    pts = _cylinder_grid(radius=1.0, length=5.0, n_axial=8, n_circ=12)
    cfg = Config(reduce=ReduceConfig(mode="surface"))
    topo = extract(pts, cfg)
    # Surface mode does not move or merge points.
    assert len(topo.coords) == len(pts)
