"""Deform_post pipeline package.

Turns DeformSim FEM output into vision-force training data that mirrors the
real recordings: per-sequence force preparation (real sensor CSV -> rotated
model forces), DeformSim replay invocation, fixed-camera rendering, .pt
serialization, dataset assembly, and QA artifacts.

`main.py` at the package's parent directory is the single CLI entry point;
every subcommand maps onto one module here. Submodules are imported lazily by
the CLI (and via `from dpost import <name>`), never eagerly at package import,
so the heavy optional dependencies (Open3D, torch, OpenCV) load only when the
subcommand that needs them runs. There is deliberately no `__all__`: the
package is not meant to be wildcard-imported.
"""
