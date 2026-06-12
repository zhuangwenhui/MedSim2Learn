"""Deform_post pipeline package.

Turns DeformSim FEM output into vision-force training data that mirrors the
real recordings: per-sequence force preparation (real sensor CSV -> rotated
model forces), DeformSim replay invocation, fixed-camera rendering, .pt
serialization, dataset assembly, and QA artifacts.

`main.py` at the package's parent directory is the single CLI entry point;
every subcommand maps onto one module here.
"""

__all__ = [
    "annotate",
    "artifacts",
    "camera",
    "config",
    "dataset",
    "forces",
    "meshio",
    "paths",
    "render",
    "replay",
    "runtime",
    "simrun",
]
