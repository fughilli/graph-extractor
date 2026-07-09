"""Smoke + correctness tests for the viz backend (generators + instrumented trace).

These guard the visualizer's data path: every dataset must generate a valid
cloud, and the instrumented pipeline must reproduce the same topology the
library produces (it calls the same primitives, so any drift is a bug).
"""

import numpy as np
import pytest

from viz import generators, trace


ALL_DATASETS = [s["key"] for s in generators.dataset_schema()]


@pytest.mark.parametrize("key", ALL_DATASETS)
def test_every_dataset_generates(key):
    points, meta = generators.generate(key, {})
    assert points.ndim == 2 and points.shape[1] == 3
    assert len(points) > 0
    assert meta["category"] in ("skeleton", "tubiform")
    assert len(meta["labels"]) == len(points)
    assert "polylines" in meta["truth"] and "branch_points" in meta["truth"]


def test_dataset_schema_is_json_safe():
    import json
    json.dumps(generators.dataset_schema())  # no numpy / function objects


def _run(key, flat, animate=False):
    points, _ = generators.generate(key, {})
    cfg = trace.build_config(flat)
    return trace.run(points, cfg, animate=animate)


def test_trace_stage_shape_and_serialisable():
    import json
    st = _run("y_junction", {"reduce.mode": "none"})
    for k in ("input", "reduce", "topology", "summary", "notes", "effective_mode"):
        assert k in st
    json.dumps(st)  # entire trace must be JSON-serialisable for the API


def test_y_junction_topology():
    st = _run("y_junction", {"reduce.mode": "none"})
    T = st["topology"]
    assert len(T["branch_points"]) == 1
    assert len(T["segments"]) == 3
    assert all(s["n_branch_ends"] == 1 for s in T["segments"])


def test_loop_is_one_cycle():
    st = _run("loop", {"reduce.mode": "none"})
    segs = st["topology"]["segments"]
    assert len(st["topology"]["branch_points"]) == 0
    assert len(segs) == 1 and segs[0]["closed"]


def test_h_network_has_two_junctions_and_a_bridge():
    st = _run("h_network", {"reduce.mode": "none"})
    T = st["topology"]
    assert len(T["branch_points"]) == 2
    assert sum(s["n_branch_ends"] == 2 for s in T["segments"]) == 1  # the bridge


def test_cylinder_collapses_to_single_centerline():
    st = _run("cylinder", {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8})
    assert st["effective_mode"] == "collapse"
    assert len(st["topology"]["branch_points"]) == 0
    assert len(st["topology"]["segments"]) == 1
    assert st["reduce"]["skeleton_points"]  # reduction produced a skeleton


def test_y_tube_collapses_to_one_junction():
    st = _run("y_tube", {"reduce.mode": "collapse"})
    assert len(st["topology"]["branch_points"]) == 1
    assert len(st["topology"]["segments"]) == 3


def test_torus_collapses_to_one_loop():
    st = _run("torus", {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8})
    segs = st["topology"]["segments"]
    assert len(st["topology"]["branch_points"]) == 0
    assert len(segs) == 1 and segs[0]["closed"]


def test_contraction_frames_present_when_animating():
    st = _run("cylinder", {"reduce.mode": "collapse", "reduce.contraction_iterations": 8},
              animate=True)
    frames = st["reduce"]["contraction_frames"]
    assert frames and len(frames) >= 2
    n = st["input"]["n"]
    assert all(len(f) == n for f in frames)  # every frame covers every point


@pytest.mark.parametrize("key,flat", [
    ("y_junction", {"reduce.mode": "none"}),
    ("grid", {"reduce.mode": "none"}),
    ("lollipop", {"reduce.mode": "none"}),
    ("cylinder", {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8}),
    ("y_tube", {"reduce.mode": "collapse"}),
    ("cross_tube", {"reduce.mode": "collapse"}),
    ("torus", {"reduce.mode": "collapse", "neighbors.radius_factor": 1.8}),
    ("cylinder", {"reduce.mode": "surface"}),
])
def test_trace_indices_in_bounds(key, flat):
    """Every index the viewer dereferences must be valid (guards rendering)."""
    st = _run(key, flat)

    def edges_ok(edges, n):
        return all(0 <= a < n and 0 <= b < n for a, b in edges)

    rd = st["reduce"]
    if rd["mode"] == "collapse":
        assert edges_ok(rd["contraction_graph_edges"], len(rd["contracted"]))
        assert edges_ok(rd["skeleton_edges"], len(rd["skeleton_points"]))
    else:
        assert edges_ok(rd["adjacency_edges"], len(rd["reduced_points"]))

    if "consolidate" in st:
        bp = st["consolidate"]["before_points"]
        assert edges_ok(st["consolidate"]["merged_edges"], len(bp))

    T = st["topology"]
    n = len(T["coords"])
    assert edges_ok(T["edges"], n)
    assert all(0 <= i < n for i in T["tips"])
    assert all(0 <= int(k) < n for k in T["degree"])
    assert len(T["kinds"]) == len(T["degree"])
    for s in T["segments"]:
        assert all(0 <= i < n for i in s["points"])
        for e in s["ends"]:
            assert e is None or 0 <= e < len(T["branch_points"])


def test_auto_mode_reports_decision():
    st = _run("cylinder", {"reduce.mode": "auto"})
    assert "auto" in st
    assert st["auto"]["chosen"] in ("collapse", "surface")
    assert st["effective_mode"] == st["auto"]["chosen"]
