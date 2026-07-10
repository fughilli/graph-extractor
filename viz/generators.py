"""Synthetic point-cloud generators for the skelgraph visualizer.

Two families, matching the README's distinction:

* **skeleton** clouds -- points sampled *along the curves themselves* (thin,
  already ~1-D).  These exercise the topology core directly (reduce mode
  ``none``): open chains, loops, Y/H junctions, lollipops, grids.
* **tubiform** clouds -- points sampled on the *surface of thick tubes*
  (non-skeleton, 2-D manifolds).  These exercise the reduction stage
  (``collapse`` / ``surface`` / ``auto``): single cylinders, branching Y
  tubes, tori (looped tubes), and X crossings.

Every generator returns ``(points, meta)`` where ``points`` is an ``(N, 3)``
float array and ``meta`` carries:

* ``category``  -- ``"skeleton"`` or ``"tubiform"``.
* ``labels``    -- per-point int, ``0`` curve-like / ``1`` surface-like
                   (used only to colour the input cloud).
* ``truth``     -- ground-truth topology for overlay/comparison:
                   ``{"polylines": [[[x,y,z], ...], ...],
                      "branch_points": [[x,y,z], ...]}``.

Each entry in :data:`DATASETS` also declares a parameter *schema* so the web
UI can build its controls automatically, plus a ``recommended_config`` used to
pre-set sensible pipeline options when the dataset is selected.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np


# --------------------------------------------------------------------------
# Small geometry helpers
# --------------------------------------------------------------------------
def _rng(seed) -> np.random.Generator:
    return np.random.default_rng(int(seed))


def _jitter(points: np.ndarray, noise: float, rng: np.random.Generator) -> np.ndarray:
    """Add isotropic Gaussian noise of standard deviation ``noise``."""
    if noise <= 0:
        return points
    return points + rng.normal(0.0, noise, size=points.shape)


def _densify(polyline: np.ndarray, per_unit: float = 6.0) -> np.ndarray:
    """Resample a coarse polyline to a smooth dense one (for truth overlays)."""
    polyline = np.asarray(polyline, float)
    if len(polyline) < 2:
        return polyline
    seg = np.diff(polyline, axis=0)
    seglen = np.linalg.norm(seg, axis=1)
    out = [polyline[0]]
    for i, L in enumerate(seglen):
        k = max(1, int(L * per_unit))
        for j in range(1, k + 1):
            out.append(polyline[i] + seg[i] * (j / k))
    return np.asarray(out)


def _basis(direction: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """An orthonormal frame ``(d, u, v)`` with ``d`` along ``direction``."""
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    a = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    return d, u, v


def _straight_tube(
    axis_dir, length, radius, n_axial, n_circ, start=0.0, origin=(0, 0, 0)
) -> np.ndarray:
    """Surface samples on a straight cylinder from ``start`` to ``length``."""
    d, u, v = _basis(axis_dir)
    origin = np.asarray(origin, float)
    th = np.linspace(0.0, 2 * np.pi, n_circ, endpoint=False)
    ring = np.outer(np.cos(th), u) + np.outer(np.sin(th), v)  # (n_circ, 3)
    pts = []
    for t in np.linspace(start, length, n_axial):
        pts.append(origin + t * d + radius * ring)
    return np.vstack(pts)


# --------------------------------------------------------------------------
# Skeleton (thin, ~1-D) generators
# --------------------------------------------------------------------------
def gen_open_chain(**p) -> Tuple[np.ndarray, Dict]:
    n = int(p["n"])
    length = float(p["length"])
    curl = float(p["curl"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    t = np.linspace(0.0, length, n)
    pts = np.column_stack([t, curl * np.sin(t / length * np.pi), np.zeros_like(t)])
    truth = _densify(pts, per_unit=4.0)
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {"polylines": [truth.tolist()], "branch_points": []},
    }


def gen_loop(**p) -> Tuple[np.ndarray, Dict]:
    n = int(p["n"])
    radius = float(p["radius"])
    tilt = float(p["tilt"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    th = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    pts = np.column_stack(
        [radius * np.cos(th), radius * np.sin(th), tilt * radius * np.sin(th)]
    )
    truth = np.vstack([pts, pts[:1]])
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {"polylines": [truth.tolist()], "branch_points": []},
    }


def gen_y_junction(**p) -> Tuple[np.ndarray, Dict]:
    n_arm = int(p["n_per_arm"])
    length = float(p["arm_length"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    pitch = length / n_arm
    dirs = [(np.cos(a), np.sin(a), 0.0) for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    arms, polylines = [], []
    for d in dirs:
        d = np.asarray(d, float)
        arm = np.outer(np.arange(1, n_arm + 1) * pitch, d)
        arms.append(arm)
        polylines.append(np.vstack([[0, 0, 0], arm[-1]]).tolist())
    pts = np.vstack([np.zeros((1, 3))] + arms)
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": [[0.0, 0.0, 0.0]]},
    }


def gen_h_network(**p) -> Tuple[np.ndarray, Dict]:
    """Two junctions joined by a bridge, each with two free tips (an 'H')."""
    bridge = float(p["bridge"])
    arm = float(p["arm_length"])
    pitch = float(p["pitch"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    left = np.array([-bridge / 2, 0.0, 0.0])
    right = np.array([bridge / 2, 0.0, 0.0])

    def chain(a, b):
        L = np.linalg.norm(b - a)
        k = max(2, int(round(L / pitch)) + 1)
        return np.linspace(a, b, k)

    diag = np.array([0.6, 0.8, 0.0])
    parts, polylines = [], []
    # four tip directions (two per junction), plus the central bridge
    tips = [
        (left, left + arm * np.array([-diag[0], diag[1], 0])),
        (left, left + arm * np.array([-diag[0], -diag[1], 0])),
        (right, right + arm * np.array([diag[0], diag[1], 0])),
        (right, right + arm * np.array([diag[0], -diag[1], 0])),
    ]
    for a, b in tips:
        parts.append(chain(a, b))
        polylines.append(np.vstack([a, b]).tolist())
    parts.append(chain(left, right))
    polylines.append(np.vstack([left, right]).tolist())
    pts = np.vstack(parts)
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": [left.tolist(), right.tolist()]},
    }


def gen_lollipop(**p) -> Tuple[np.ndarray, Dict]:
    """A stub meeting a closed loop at one junction (degree-3 branch point)."""
    stub = float(p["stub_length"])
    radius = float(p["radius"])
    pitch = float(p["pitch"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    junc = np.array([0.0, 0.0, 0.0])
    # stub along -x, ending at the junction
    k = max(2, int(round(stub / pitch)) + 1)
    stub_pts = np.linspace(np.array([-stub, 0, 0]), junc, k)
    # loop centred at (radius, 0, 0) so its leftmost point sits on the junction
    centre = np.array([radius, 0.0, 0.0])
    m = max(8, int(round(2 * np.pi * radius / pitch)))
    th = np.linspace(0.0, 2 * np.pi, m, endpoint=False)
    loop_pts = centre + radius * np.column_stack([-np.cos(th), np.sin(th), np.zeros(m)])
    pts = np.vstack([stub_pts, loop_pts])
    truth_loop = np.vstack([loop_pts, loop_pts[:1]])
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {
            "polylines": [np.vstack([[-stub, 0, 0], junc]).tolist(), truth_loop.tolist()],
            "branch_points": [junc.tolist()],
        },
    }


def gen_grid(**p) -> Tuple[np.ndarray, Dict]:
    """A rectangular lattice of curves -> a mesh of degree-4 junctions."""
    nx = int(p["nx"])
    ny = int(p["ny"])
    spacing = float(p["spacing"])
    pitch = float(p["pitch"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    xs = np.arange(nx) * spacing
    ys = np.arange(ny) * spacing
    per = max(1, int(round(spacing / pitch)))
    parts, polylines = [], []
    # horizontal lines
    for y in ys:
        a = np.array([xs[0], y, 0.0])
        b = np.array([xs[-1], y, 0.0])
        parts.append(np.linspace(a, b, per * (nx - 1) + 1))
        polylines.append(np.vstack([a, b]).tolist())
    # vertical lines
    for x in xs:
        a = np.array([x, ys[0], 0.0])
        b = np.array([x, ys[-1], 0.0])
        parts.append(np.linspace(a, b, per * (ny - 1) + 1))
        polylines.append(np.vstack([a, b]).tolist())
    pts = np.vstack(parts)
    # dedupe near-coincident lattice crossings so degrees are clean
    pts = np.unique(np.round(pts, 6), axis=0)
    bps = [[x, y, 0.0] for x in xs for y in ys]
    return _jitter(pts, noise, rng), {
        "category": "skeleton",
        "labels": np.zeros(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": bps},
    }


# --------------------------------------------------------------------------
# Tubiform (thick, surface-sampled) generators
# --------------------------------------------------------------------------
def gen_cylinder(**p) -> Tuple[np.ndarray, Dict]:
    radius = float(p["radius"])
    length = float(p["length"])
    n_axial = int(p["n_axial"])
    n_circ = int(p["n_circ"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    pts = _straight_tube((0, 0, 1), length, radius, n_axial, n_circ)
    truth = [[[0, 0, 0], [0, 0, length]]]
    return _jitter(pts, noise, rng), {
        "category": "tubiform",
        "labels": np.ones(len(pts), int),
        "truth": {"polylines": truth, "branch_points": []},
    }


def gen_y_tube(**p) -> Tuple[np.ndarray, Dict]:
    radius = float(p["radius"])
    length = float(p["arm_length"])
    n_axial = int(p["n_axial"])
    n_circ = int(p["n_circ"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    start = radius * 0.5
    dirs = [(np.cos(a), np.sin(a), 0.0) for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    arms, polylines = [], []
    for d in dirs:
        arms.append(_straight_tube(d, length, radius, n_axial, n_circ, start=start))
        end = (np.asarray(d, float) / np.linalg.norm(d)) * length
        polylines.append([[0.0, 0.0, 0.0], end.tolist()])
    pts = np.vstack(arms)
    return _jitter(pts, noise, rng), {
        "category": "tubiform",
        "labels": np.ones(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": [[0.0, 0.0, 0.0]]},
    }


def gen_cross_tube(**p) -> Tuple[np.ndarray, Dict]:
    """Four tubes meeting at the origin (an 'X'/'+' crossing, degree 4)."""
    radius = float(p["radius"])
    length = float(p["arm_length"])
    n_axial = int(p["n_axial"])
    n_circ = int(p["n_circ"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    start = radius * 0.5
    dirs = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
    arms, polylines = [], []
    for d in dirs:
        arms.append(_straight_tube(d, length, radius, n_axial, n_circ, start=start))
        end = (np.asarray(d, float)) * length
        polylines.append([[0.0, 0.0, 0.0], end.tolist()])
    pts = np.vstack(arms)
    return _jitter(pts, noise, rng), {
        "category": "tubiform",
        "labels": np.ones(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": [[0.0, 0.0, 0.0]]},
    }


def gen_torus(**p) -> Tuple[np.ndarray, Dict]:
    """A looped tube: a torus whose centerline is a circle (0 branch points)."""
    R = float(p["major_radius"])
    r = float(p["minor_radius"])
    n_major = int(p["n_major"])
    n_minor = int(p["n_minor"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])
    u = np.linspace(0.0, 2 * np.pi, n_major, endpoint=False)
    v = np.linspace(0.0, 2 * np.pi, n_minor, endpoint=False)
    pts = []
    for uu in u:
        cu, su = np.cos(uu), np.sin(uu)
        for vv in v:
            rr = R + r * np.cos(vv)
            pts.append((rr * cu, rr * su, r * np.sin(vv)))
    pts = np.asarray(pts, float)
    truth = np.column_stack([R * np.cos(u), R * np.sin(u), np.zeros_like(u)])
    truth = np.vstack([truth, truth[:1]])
    return _jitter(pts, noise, rng), {
        "category": "tubiform",
        "labels": np.ones(len(pts), int),
        "truth": {"polylines": [truth.tolist()], "branch_points": []},
    }


def gen_tree(**p) -> Tuple[np.ndarray, Dict]:
    """An organic, recursively-branching tube tree (many junctions).

    A trunk grows along +z and repeatedly forks into ``branch`` children, each
    spread off the parent axis by ``spread`` degrees (with per-child jitter so
    the tree is not perfectly symmetric).  Each generation shrinks in length and
    radius, so deep twigs are short and thin.  Surface-sampled like the other
    tubiform inputs: exercises collapse reduction + junction resolution on a
    structure with **many** degree-3 branch points, not just one.
    """
    depth = int(p["depth"])
    branch = int(p["branch"])
    trunk_length = float(p["trunk_length"])
    radius = float(p["radius"])
    length_decay = float(p["length_decay"])
    radius_decay = float(p["radius_decay"])
    spread = np.radians(float(p["spread"]))
    pitch = float(p["pitch"])
    noise = float(p["noise"])
    rng = _rng(p["seed"])

    parts: List[np.ndarray] = []
    polylines: List = []
    branch_points: List = []

    def grow(origin, direction, length, rad, level):
        d = np.asarray(direction, float)
        d = d / np.linalg.norm(d)
        # Uniform surface density: axial spacing and ring spacing both ~= pitch,
        # regardless of tube radius, so a single global radius graph connects the
        # whole (multi-scale) tree and the collapse reduction stays well-posed.
        n_axial = max(2, int(round(length / pitch))) + 1
        n_circ = max(6, int(round(2 * np.pi * rad / pitch)))
        parts.append(_straight_tube(d, length, rad, n_axial, n_circ, origin=origin))
        end = np.asarray(origin, float) + d * length
        polylines.append([list(map(float, origin)), end.tolist()])
        if level >= depth:
            return
        branch_points.append(end.tolist())
        _, u, v = _basis(d)
        for k in range(branch):
            azimuth = 2 * np.pi * k / branch + rng.uniform(-0.4, 0.4)
            tilt = spread * (0.7 + 0.6 * rng.random())
            child = (np.cos(tilt) * d
                     + np.sin(tilt) * (np.cos(azimuth) * u + np.sin(azimuth) * v))
            child_len = length * length_decay * (0.85 + 0.3 * rng.random())
            grow(end, child, child_len, rad * radius_decay, level + 1)

    grow(origin=np.zeros(3), direction=np.array([0.0, 0.0, 1.0]),
         length=trunk_length, rad=radius, level=1)
    pts = np.vstack(parts)
    return _jitter(pts, noise, rng), {
        "category": "tubiform",
        "labels": np.ones(len(pts), int),
        "truth": {"polylines": polylines, "branch_points": branch_points},
    }


# --------------------------------------------------------------------------
# Registry + schema (drives the UI controls)
# --------------------------------------------------------------------------
def _pn(name, default, lo, hi, step, label):
    return {"name": name, "type": "float", "default": default,
            "min": lo, "max": hi, "step": step, "label": label}


def _pi(name, default, lo, hi, label):
    return {"name": name, "type": "int", "default": default,
            "min": lo, "max": hi, "step": 1, "label": label}


_NOISE = _pn("noise", 0.0, 0.0, 0.5, 0.01, "Noise σ")
_SEED = _pi("seed", 0, 0, 999, "Seed")

DATASETS: Dict[str, Dict] = {
    # ---- skeleton ----
    "open_chain": {
        "label": "Open chain (tip — tip)", "category": "skeleton",
        "fn": gen_open_chain,
        "params": [_pi("n", 25, 4, 200, "Points"), _pn("length", 12.0, 2.0, 30.0, 0.5, "Length"),
                   _pn("curl", 2.0, 0.0, 6.0, 0.1, "Curl"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none"},
    },
    "loop": {
        "label": "Closed loop (cycle)", "category": "skeleton", "fn": gen_loop,
        "params": [_pi("n", 40, 8, 300, "Points"), _pn("radius", 4.0, 1.0, 10.0, 0.5, "Radius"),
                   _pn("tilt", 0.3, 0.0, 1.0, 0.05, "Tilt"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none", "neighbors.method": "radius"},
    },
    "y_junction": {
        "label": "Y junction (1 branch pt)", "category": "skeleton", "fn": gen_y_junction,
        "params": [_pi("n_per_arm", 6, 2, 40, "Points / arm"),
                   _pn("arm_length", 6.0, 2.0, 20.0, 0.5, "Arm length"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none"},
    },
    "h_network": {
        "label": "H network (bridge, 2 branch pts)", "category": "skeleton", "fn": gen_h_network,
        "params": [_pn("bridge", 4.0, 1.0, 12.0, 0.5, "Bridge length"),
                   _pn("arm_length", 3.0, 1.0, 10.0, 0.5, "Arm length"),
                   _pn("pitch", 0.5, 0.2, 1.5, 0.05, "Pitch"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none"},
    },
    "lollipop": {
        "label": "Lollipop (stub + loop)", "category": "skeleton", "fn": gen_lollipop,
        "params": [_pn("stub_length", 4.0, 1.0, 10.0, 0.5, "Stub length"),
                   _pn("radius", 2.0, 0.5, 6.0, 0.25, "Loop radius"),
                   _pn("pitch", 0.5, 0.2, 1.5, 0.05, "Pitch"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none"},
    },
    "grid": {
        "label": "Grid lattice (mesh of junctions)", "category": "skeleton", "fn": gen_grid,
        "params": [_pi("nx", 4, 2, 8, "Columns"), _pi("ny", 3, 2, 8, "Rows"),
                   _pn("spacing", 4.0, 1.0, 8.0, 0.5, "Spacing"),
                   _pn("pitch", 0.5, 0.2, 1.5, 0.05, "Pitch"), _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "none", "junction_merge_factor": 2.0},
    },
    # ---- tubiform ----
    "cylinder": {
        "label": "Cylinder (single tube)", "category": "tubiform", "fn": gen_cylinder,
        "params": [_pn("radius", 1.0, 0.3, 3.0, 0.1, "Radius"),
                   _pn("length", 10.0, 3.0, 25.0, 0.5, "Length"),
                   _pi("n_axial", 20, 5, 40, "Axial rings"), _pi("n_circ", 16, 6, 40, "Circumf. samples"),
                   _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8},
    },
    "y_tube": {
        "label": "Y tube (branching tubes)", "category": "tubiform", "fn": gen_y_tube,
        "params": [_pn("radius", 0.6, 0.2, 2.0, 0.1, "Radius"),
                   _pn("arm_length", 6.0, 3.0, 15.0, 0.5, "Arm length"),
                   _pi("n_axial", 14, 5, 30, "Axial rings"), _pi("n_circ", 12, 6, 30, "Circumf. samples"),
                   _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "collapse"},
    },
    "cross_tube": {
        "label": "X tube (4-way crossing)", "category": "tubiform", "fn": gen_cross_tube,
        "params": [_pn("radius", 0.6, 0.2, 2.0, 0.1, "Radius"),
                   _pn("arm_length", 6.0, 3.0, 15.0, 0.5, "Arm length"),
                   _pi("n_axial", 14, 5, 30, "Axial rings"), _pi("n_circ", 12, 6, 30, "Circumf. samples"),
                   _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "collapse"},
    },
    "torus": {
        "label": "Torus (looped tube)", "category": "tubiform", "fn": gen_torus,
        "params": [_pn("major_radius", 5.0, 2.0, 10.0, 0.5, "Major radius R"),
                   _pn("minor_radius", 1.0, 0.3, 3.0, 0.1, "Minor radius r"),
                   _pi("n_major", 32, 8, 60, "Around loop"), _pi("n_minor", 12, 6, 30, "Around tube"),
                   _NOISE, _SEED],
        "recommended_config": {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8},
    },
    "tree": {
        "label": "Tree (branching tubes)", "category": "tubiform", "fn": gen_tree,
        "params": [_pi("depth", 4, 3, 5, "Depth (generations)"),
                   _pi("branch", 2, 2, 3, "Children / split"),
                   _pn("trunk_length", 5.0, 2.0, 10.0, 0.5, "Trunk length"),
                   _pn("radius", 0.5, 0.2, 1.5, 0.05, "Trunk radius"),
                   _pn("length_decay", 0.72, 0.4, 0.95, 0.02, "Length decay"),
                   _pn("radius_decay", 0.72, 0.4, 0.95, 0.02, "Radius decay"),
                   _pn("spread", 35.0, 10.0, 70.0, 2.5, "Branch spread (deg)"),
                   _pn("pitch", 0.3, 0.15, 0.6, 0.05, "Sample pitch"), _NOISE, _SEED],
        # The compact, multi-scale tree over-contracts at the default 10
        # iterations; 6 keeps the junctions distinct across the usable depth
        # range (see WORKLOG -- collapse contraction strength is global).
        "recommended_config": {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8,
                               "reduce.contraction_iterations": 6},
    },
}


def dataset_schema() -> List[Dict]:
    """JSON-serialisable dataset descriptors (no function objects)."""
    return [
        {
            "key": key,
            "label": d["label"],
            "category": d["category"],
            "params": d["params"],
            "recommended_config": d.get("recommended_config", {}),
        }
        for key, d in DATASETS.items()
    ]


def generate(key: str, params: Dict) -> Tuple[np.ndarray, Dict]:
    """Generate a named dataset, filling any missing params from the schema."""
    if key not in DATASETS:
        raise KeyError(f"unknown dataset {key!r}")
    spec = DATASETS[key]
    merged = {p["name"]: p["default"] for p in spec["params"]}
    merged.update({k: v for k, v in (params or {}).items() if k in merged})
    points, meta = spec["fn"](**merged)
    meta["dataset"] = key
    return np.asarray(points, float), meta
