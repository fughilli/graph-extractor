"""Stdlib HTTP server for the skelgraph visualizer.

No third-party web framework: it uses :mod:`http.server` so the only runtime
dependencies are the ones skelgraph already needs (numpy / scipy / networkx).

Endpoints
---------
``GET  /``                 -> the single-page viewer (viz/static/index.html)
``GET  /static/<file>``    -> static assets
``GET  /api/datasets``     -> dataset descriptors + parameter schema
``GET  /api/config-schema``-> pipeline-config parameter schema
``POST /api/pipeline``     -> generate a cloud and run the instrumented pipeline

Run
---
    PYTHONPATH=. python3 viz/server.py                 # then open the printed URL
    PYTHONPATH=. python3 viz/server.py --port 8000 --no-open
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

# Allow running both as ``python3 viz/server.py`` and ``python3 -m viz.server``.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viz import generators, trace  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# --------------------------------------------------------------------------
# Pipeline-config schema (drives the UI; grouped for readability)
# --------------------------------------------------------------------------
def config_schema():
    return [
        {"group": "Reduction", "params": [
            {"name": "reduce.mode", "type": "enum", "default": "none",
             "options": ["none", "surface", "collapse", "auto"], "label": "Mode"},
            {"name": "reduce.scale", "type": "float", "default": 0.0, "min": 0.0,
             "max": 5.0, "step": 0.05, "label": "Scale (0 = auto)"},
            {"name": "reduce.contraction_iterations", "type": "int", "default": 10,
             "min": 0, "max": 30, "step": 1, "label": "Contraction iters"},
            {"name": "reduce.contraction_neighbor_factor", "type": "float", "default": 2.5,
             "min": 1.0, "max": 5.0, "step": 0.1, "label": "Contraction radius ×"},
            {"name": "reduce.merge_factor", "type": "float", "default": 0.5,
             "min": 0.1, "max": 1.0, "step": 0.05, "label": "Edge-collapse ×"},
        ]},
        {"group": "Adjacency (none / surface / auto)", "params": [
            {"name": "neighbors.method", "type": "enum", "default": "radius",
             "options": ["radius", "mst", "knn"], "label": "Method"},
            {"name": "neighbors.radius_factor", "type": "float", "default": 1.6,
             "min": 1.0, "max": 3.0, "step": 0.05, "label": "Radius ×"},
            {"name": "neighbors.k", "type": "int", "default": 10, "min": 2, "max": 20,
             "step": 1, "label": "k (knn / mst)"},
            {"name": "neighbors.prune_shortcuts", "type": "bool", "default": True,
             "label": "Prune shortcut edges"},
        ]},
        {"group": "Topology cleanup", "params": [
            {"name": "junction_merge_factor", "type": "float", "default": 2.0,
             "min": 0.0, "max": 5.0, "step": 0.25, "label": "Junction merge × (0=off)"},
            {"name": "min_stub_points", "type": "int", "default": 0, "min": 0, "max": 20,
             "step": 1, "label": "Prune stubs < (0=off)"},
        ]},
    ]


def _clean_config(flat):
    """Drop 'auto' sentinels: a scale of 0 means 'estimate' (None)."""
    out = {}
    for k, v in (flat or {}).items():
        if k.endswith(".scale") and (v in (0, 0.0, "", None)):
            continue  # leave unset -> ReduceConfig/NeighborConfig default None
        out[k] = v
    return out


# --------------------------------------------------------------------------
# Request handler
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "skelgraph-viz/0.1"

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers --
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routes --
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        if path == "/api/datasets":
            return self._send_json({"datasets": generators.dataset_schema()})
        if path == "/api/config-schema":
            return self._send_json({"groups": config_schema()})
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            safe = os.path.normpath(rel).lstrip("/.")
            ct = "text/javascript" if safe.endswith(".js") else \
                 "text/css" if safe.endswith(".css") else "application/octet-stream"
            return self._send_file(os.path.join(STATIC_DIR, safe), ct)
        self.send_error(404, "Not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/pipeline":
            return self.send_error(404, "Not found")
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError) as exc:
            return self._send_json({"error": f"bad request: {exc}"}, status=400)

        try:
            dataset = req.get("dataset", "y_junction")
            gen_params = req.get("gen_params", {})
            flat_cfg = _clean_config(req.get("config", {}))
            animate = bool(req.get("animate", False))

            points, meta = generators.generate(dataset, gen_params)
            cfg = trace.build_config(flat_cfg)
            stages = trace.run(points, cfg, animate=animate)

            resp = {
                "dataset": dataset,
                "meta": {
                    "category": meta.get("category"),
                    "labels": np.asarray(meta.get("labels", []), int).tolist(),
                    "truth": meta.get("truth", {"polylines": [], "branch_points": []}),
                },
                "stages": stages,
            }
            return self._send_json(resp)
        except Exception as exc:  # surface errors to the UI rather than 500-ing silently
            import traceback
            return self._send_json(
                {"error": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc()},
                status=500,
            )


def main(argv=None):
    ap = argparse.ArgumentParser(description="skelgraph interactive visualizer")
    # Bind all interfaces by default so a container-published port (see
    # .claude-container-overlay/overlay.json) is reachable from the host; pass
    # --host 127.0.0.1 to restrict to loopback.
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args(argv)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    display_host = "localhost" if args.host in ("0.0.0.0", "") else args.host
    url = f"http://{display_host}:{args.port}/"
    print(f"skelgraph visualizer serving at {url}  (bound to {args.host}:{args.port})")
    print("  Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
