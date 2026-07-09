"""skelgraph -- extract graph connectivity (branch points & segments) from a
3-D point cloud sampled along the edges of a curve network.

Quick start
-----------
>>> import numpy as np
>>> from skelgraph import extract, Config, ReduceConfig
>>> topo = extract(points)                     # points: (N, 3)
>>> print(topo.summary())
>>> topo.branch_points                          # (M, 3) junction coordinates
>>> topo.segments                               # list of Segment
"""

from .config import Config, ReduceConfig, NeighborConfig
from .topology import Topology, Segment, extract_topology
from .extract import extract

__all__ = [
    "extract",
    "extract_topology",
    "Config",
    "ReduceConfig",
    "NeighborConfig",
    "Topology",
    "Segment",
]

__version__ = "0.1.0"
