"""Interactive browser visualizer for the skelgraph pipeline.

Modules
-------
* :mod:`viz.generators` -- synthetic skeleton / tubiform point-cloud generators.
* :mod:`viz.trace`      -- the real skelgraph pipeline, instrumented to capture
  every intermediate stage.
* :mod:`viz.server`     -- a stdlib HTTP server exposing the generators and the
  instrumented pipeline as JSON, plus the single-page Three.js viewer.

Run ``PYTHONPATH=. python3 viz/server.py`` and open the printed URL.
"""
