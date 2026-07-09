"""Demo: extract topology from a few synthetic point clouds.

Run:  PYTHONPATH=. python3 examples/demo.py
"""

import numpy as np

from skelgraph import extract, Config, ReduceConfig, NeighborConfig


def chain(start, direction, n, pitch):
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    return np.asarray(start, float) + np.outer(np.arange(1, n + 1) * pitch, d)


def y_junction():
    dirs = [(np.cos(a), np.sin(a), 0.0)
            for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    arms = [chain((0, 0, 0), d, 6, 1.0) for d in dirs]
    return np.vstack([np.zeros((1, 3))] + arms)


def cylinder_grid(radius, length, n_axial, n_circ):
    z = np.linspace(0, length, n_axial)
    th = np.linspace(0, 2 * np.pi, n_circ, endpoint=False)
    return np.array([(radius * np.cos(t), radius * np.sin(t), zz)
                     for zz in z for t in th])


def show(title, topo):
    print(f"\n=== {title} ===")
    print(" ", topo.summary())
    for i, s in enumerate(topo.segments):
        kind = "loop" if s.closed else "chain"
        print(f"  segment {i}: {kind}, {len(s.points)} pts, "
              f"{s.n_branch_ends} branch end(s), ends={s.ends}")


if __name__ == "__main__":
    show("Y junction (reduce=none)",
         extract(y_junction(), Config(reduce=ReduceConfig(mode="none"))))

    pts = cylinder_grid(1.0, 10.0, 20, 16)
    show("Cylinder -> centerline (reduce=collapse)",
         extract(pts, Config(
             reduce=ReduceConfig(mode="collapse"),
             neighbors=NeighborConfig(method="radius", radius_factor=1.8))))

    # A 3-D "Y" made of three tubes meeting at the origin.
    def tube(axis, length, rad, n_ax, n_circ, start):
        d = np.asarray(axis, float); d /= np.linalg.norm(d)
        a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(d, a); u /= np.linalg.norm(u); v = np.cross(d, u)
        return np.array([t * d + rad * (np.cos(th) * u + np.sin(th) * v)
                         for t in np.linspace(start, length, n_ax)
                         for th in np.linspace(0, 2 * np.pi, n_circ, endpoint=False)])

    dirs = [(np.cos(a), np.sin(a), 0.0) for a in (0, 2 * np.pi / 3, 4 * np.pi / 3)]
    ytube = np.vstack([tube(d, 6.0, 0.6, 14, 12, 0.3) for d in dirs])
    show("Branching tube -> junction (reduce=collapse)",
         extract(ytube, Config(reduce=ReduceConfig(mode="collapse"))))
