#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Author the C3 full-batch per-sequence contact assignments.

Owner ruling 2026-08-11: each sequence independently draws K contacts from
the framing-gated candidate pool, seeded by default_rng([base_seed,
sequence_ordinal]) so the assignment is deterministic and auditable.
Sequence 04 is permanently excluded (repository owner ruling). One
single-contact annotation file is written per UNIQUE assigned contact (the
production freeze set verbatim); sequences sharing a contact share the file.
"""
import argparse
import json
import os

import numpy as np

STANDARD_SEQS = [f"{i:02d}" for i in range(1, 33) if i != 4]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--annotation", required=True,
                    help="Production annotation JSON (freeze + k_ring source)")
    ap.add_argument("--gate", required=True, help="c3_framing_gate.json")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    with open(args.annotation, "r") as fh:
        prod = json.load(fh)
    freeze = prod["freeze"]["vertices"]
    prod_seeds = {int(c["seed"]) for c in prod["contacts"]}
    k_ring = int(prod["contacts"][0]["k_ring"])

    with open(args.gate, "r") as fh:
        gate = json.load(fh)
    pool = sorted(r["seed"] for r in gate["results"]
                  if r["pass"] and r["seed"] not in prod_seeds)
    if len(pool) < args.k:
        raise SystemExit(f"gated pool too small: {len(pool)} < k={args.k}")

    os.makedirs(args.out_dir, exist_ok=True)
    assignments = {}
    for seq in STANDARD_SEQS:
        rng = np.random.default_rng([args.seed, int(seq)])
        picks = sorted(int(s) for s in rng.choice(pool, size=args.k, replace=False))
        assignments[seq] = picks
        print(f"seq{seq}: contacts {picks}")

    for seed in sorted({s for picks in assignments.values() for s in picks}):
        path = os.path.join(args.out_dir, f"c3_contact_s{seed:04d}.json")
        if not os.path.exists(path):
            with open(path, "w") as fh:
                json.dump({"freeze": {"vertices": freeze},
                           "contacts": [{"seed": seed, "k_ring": k_ring}]}, fh,
                          indent=2)

    used = sorted({s for p in assignments.values() for s in p})
    manifest = {"base_seed": args.seed, "k": args.k, "pool": pool,
                "pool_size": len(pool), "unique_contacts_used": used,
                "gate_floor": gate["floor"], "assignments": assignments}
    with open(os.path.join(args.out_dir, "c3_fleet_assignments.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"assignments: {len(assignments)} seqs x k={args.k}, "
          f"{len(used)}/{len(pool)} pool contacts used")


if __name__ == "__main__":
    main()
