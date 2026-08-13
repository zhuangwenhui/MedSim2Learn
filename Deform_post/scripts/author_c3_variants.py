#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Author C3 contact-diversity variant annotations from the production one.

Track C factor C3 (PLAN 2026-07-03 section 2-C3) varies the contact seed while
everything else -- the freeze set, k_ring, mesh, material, real force
waveform -- stays frozen at production values. The DeformSim exe simulates
every contact in its annotation, so a variant is simply a derived annotation
whose ONLY contact is the chosen candidate; the existing per-sequence
pipeline (prep -> sim -> render -> serialize) then does the rest, with the
sample ids (deformed_s%%04d_v%%04d) and the auto camera following the new
contact by construction.

Candidates come from dpost.annotate.select_contacts on the production freeze
set (Poisson-disk over the accessible zone, deterministic under --rng-seed).
The production freeze vertex list is copied VERBATIM into every variant so
the FEM boundary conditions are bit-identical across variants.

Outputs under --out-dir:
  c3_candidates.json            all accepted centers + distances + provenance
  c3_contact_s<seed>.json       one single-contact annotation per picked variant
"""
import argparse
import hashlib
import json
import os

import numpy as np

from dpost.annotate import select_contacts
from dpost.meshio import load_mesh


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--annotation", required=True,
                    help="Production annotation JSON (freeze + contacts)")
    ap.add_argument("--mesh", required=True, help="Canonical mesh PLY")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--num-centers", type=int, default=30)
    ap.add_argument("--rng-seed", type=int, default=42)
    ap.add_argument("--pick", type=int, default=2,
                    help="How many variant annotations to write (acceptance "
                         "order, production seeds excluded)")
    args = ap.parse_args()

    with open(args.annotation, "r") as fh:
        prod = json.load(fh)
    with open(args.annotation, "rb") as fh:
        prod_sha = hashlib.sha256(fh.read()).hexdigest()
    freeze = prod["freeze"]["vertices"]
    prod_seeds = [int(c["seed"]) for c in prod["contacts"]]
    k_ring = int(prod["contacts"][0]["k_ring"])

    mesh = load_mesh(args.mesh)
    verts = np.asarray(mesh.vertices)
    zone, centers = select_contacts(
        mesh, set(int(v) for v in freeze), args.num_centers,
        k_ring=k_ring, rng_seed=args.rng_seed)

    ref = verts[prod_seeds[0]]
    cand = [{"seed": int(c),
             "dist_from_production_mm": float(np.linalg.norm(verts[c] - ref))}
            for c in centers]

    os.makedirs(args.out_dir, exist_ok=True)
    picked = [c for c in cand if c["seed"] not in prod_seeds][:args.pick]
    for c in picked:
        variant = {"freeze": {"vertices": freeze},
                   "contacts": [{"seed": c["seed"], "k_ring": k_ring}]}
        path = os.path.join(args.out_dir, f"c3_contact_s{c['seed']:04d}.json")
        with open(path, "w") as fh:
            json.dump(variant, fh, indent=2)
        print(f"variant: seed={c['seed']} k_ring={k_ring} "
              f"dist={c['dist_from_production_mm']:.2f}mm -> {path}")

    summary = {
        "production_annotation": os.path.abspath(args.annotation),
        "production_annotation_sha256": prod_sha,
        "production_seeds": prod_seeds,
        "k_ring": k_ring,
        "freeze_count": len(freeze),
        "num_centers_requested": args.num_centers,
        "rng_seed": args.rng_seed,
        "zone_size": len(zone),
        "candidates": cand,
        "picked": [c["seed"] for c in picked],
    }
    with open(os.path.join(args.out_dir, "c3_candidates.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"candidates: {len(cand)} accepted (zone {len(zone)} vertices), "
          f"picked {len(picked)} -> {args.out_dir}")


if __name__ == "__main__":
    main()
