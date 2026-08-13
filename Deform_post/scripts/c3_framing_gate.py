#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C3 framing gate: deterministic organ-fraction check per candidate contact.

Owner ruling 2026-08-11: a candidate contact enters the full production batch
only if the organ-pixel fraction of a WHITE render of the canonical mesh from
that contact's auto camera clears the floor. The floor is anchored to the
production contact's own fraction (--relative, e.g. 0.9 x reference): the
originally proposed absolute 0.5 came from the textured-render measure and
would reject the production grammar itself under this clean measure
(reference 0.463) -- calibration correction recorded in the gate JSON. Measuring on
the undeformed canonical mesh with appearance OFF makes the gate a pure
function of geometry + camera: deformation is sub-millimetre and the
stochastic per-frame post-process chain never enters the measurement (the
pilot's per-frame fraction spread was post-process measurement noise, not
framing change).

Output: JSON with per-candidate fraction + verdict, plus the production
contact's fraction as the in-grammar reference.
"""
import argparse
import json
import os
import shutil
import tempfile

import numpy as np
import open3d as o3d
from PIL import Image

from dpost.camera import resolve_camera
from dpost.config import CameraConfig
from dpost.meshio import contact_normal, load_mesh
from dpost.render import render_fixed_camera_sequence

WHITE_CUTOFF = 245  # a pixel is background iff all three channels exceed this


def organ_fraction(png_path):
    arr = np.asarray(Image.open(png_path).convert("RGB"))
    return float((arr < WHITE_CUTOFF).any(axis=2).mean())


def render_candidate(mesh_path, mesh, seed, workdir):
    p_world, n_unit = contact_normal(mesh, seed)
    cam, _eye, _info = resolve_camera(p_world, n_unit, CameraConfig(), None)
    stage = os.path.join(workdir, f"s{seed:04d}")
    ply_dir = os.path.join(stage, "ply")
    png_dir = os.path.join(stage, "png")
    os.makedirs(ply_dir, exist_ok=True)
    shutil.copyfile(mesh_path, os.path.join(ply_dir, f"deformed_s{seed:04d}_v0000.ply"))
    cam_path = os.path.join(stage, "camera.json")
    o3d.io.write_pinhole_camera_parameters(cam_path, cam)
    render_fixed_camera_sequence(ply_dir, cam_path, png_dir)
    return organ_fraction(os.path.join(png_dir, f"deformed_s{seed:04d}_v0000.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", required=True, help="c3_candidates.json")
    ap.add_argument("--mesh", required=True, help="Canonical mesh PLY")
    ap.add_argument("--out", required=True, help="Gate-result JSON path")
    ap.add_argument("--threshold", type=float, default=None,
                    help="Absolute organ-fraction floor")
    ap.add_argument("--relative", type=float, default=None,
                    help="Floor = production reference fraction x this value "
                         "(calibration-correct anchoring: an absolute floor "
                         "above the reference would reject the production "
                         "grammar itself)")
    args = ap.parse_args()
    if (args.threshold is None) == (args.relative is None):
        ap.error("pass exactly one of --threshold / --relative")

    with open(args.candidates, "r") as fh:
        cand = json.load(fh)
    mesh = load_mesh(args.mesh)

    results = []
    with tempfile.TemporaryDirectory() as td:
        ref_seed = cand["production_seeds"][0]
        ref_frac = render_candidate(args.mesh, mesh, ref_seed, td)
        floor = (args.threshold if args.threshold is not None
                 else ref_frac * args.relative)
        print(f"reference (production s{ref_seed:04d}): fraction {ref_frac:.3f}"
              f" -> floor {floor:.4f}")
        for c in cand["candidates"]:
            seed = c["seed"]
            frac = render_candidate(args.mesh, mesh, seed, td)
            ok = frac >= floor
            results.append({"seed": seed, "fraction": round(frac, 4), "pass": ok,
                            "dist_from_production_mm": c["dist_from_production_mm"]})
            print(f"s{seed:04d}: fraction {frac:.3f} dist {c['dist_from_production_mm']:.1f}mm "
                  f"-> {'PASS' if ok else 'FAIL'}")

    n_pass = sum(1 for r in results if r["pass"])
    summary = {"floor": round(floor, 4), "threshold_abs": args.threshold,
               "threshold_relative": args.relative, "white_cutoff": WHITE_CUTOFF,
               "production_reference": {"seed": cand["production_seeds"][0],
                                        "fraction": round(ref_frac, 4)},
               "n_pass": n_pass, "n_total": len(results), "results": results}
    with open(args.out, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"gate: {n_pass}/{len(results)} candidates pass -> {args.out}")


if __name__ == "__main__":
    main()
