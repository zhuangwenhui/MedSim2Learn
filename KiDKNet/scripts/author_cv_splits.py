#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Author K-fold leakage-free CV splits shared across all 8 conditions.

Builds ONE id-level GroupKFold partition over the (seq04-excluded) sequence ids
and, for each fold, authors the three leakage-free splits that all reuse the
SAME fold's (train, val, test) id partition, so every cross-condition comparison
stays on identical id folds:

- fold{f}/real_split.json          (cond1/cond5): real frames only, over
  real_merged. Full coverage of real_merged each fold.
- fold{f}/c2_synt2real_split.json  (cond2/cond6): synt(train/val) -> real(test),
  over mixed_merged_256. The synt twins of the real test ids never train -> no
  force-trajectory leakage (asserted per fold).
- fold{f}/c3_mixed_split.json      (cond3/cond7): both domains per id, exactly
  50:50, over mixed_merged_256. Full coverage of the mixed dataset each fold.

Properties guaranteed (and asserted) by construction:
- Every id is a TEST id in exactly one fold; train/val/test id-disjoint per fold.
- seq04 is absent from the merged dirs, so it never enters any fold.
- Folds are deterministic from --seed (one shuffle, round-robin test groups).
- The transfer conditions (cond4/cond8) reuse the cond2/cond6 fold splits and
  init from the matching fold's cond2/cond6 checkpoint (pinned downstream).

This reuses author_paired_splits._ranges/_idx/_payload verbatim; it only adds the
K-fold id partitioning and the per-fold driver.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from author_paired_splits import _idx, _payload, _ranges  # noqa: E402  (sibling reuse)


def _kfold_id_partition(ids: List[str], k: int, seed: int
                        ) -> Tuple[List[List[str]], List[str]]:
    """Deterministic round-robin GroupKFold test groups over bare sequence ids.

    Returns the K test groups and the shuffled id order (reused for nested val).
    """
    shuffled = sorted(ids)
    random.Random(seed).shuffle(shuffled)
    groups = [sorted(shuffled[f::k]) for f in range(k)]
    # coverage + disjointness of the test groups
    flat = [i for g in groups for i in g]
    assert sorted(flat) == sorted(ids), "kfold test groups do not partition the ids"
    assert len(flat) == len(set(flat)), "an id appears in two test groups"
    return groups, shuffled


def _fold_ids(shuffled: List[str], test_ids: List[str], val_count: int, fold: int
              ) -> Tuple[List[str], List[str], List[str]]:
    """Split the non-test ids into nested val + train.

    The val window rotates with ``fold`` (offset ``fold * val_count``) so each
    fold validates on a different id subset instead of always reusing the first
    few shuffled ids; this keeps the per-fold model-selection signal varied.
    """
    test_set = set(test_ids)
    pool = [i for i in shuffled if i not in test_set]
    if val_count >= len(pool):
        raise ValueError(f"val_count {val_count} leaves no train ids (pool={len(pool)})")
    start = (fold * val_count) % len(pool)
    window = (pool + pool)[start:start + val_count]
    val_set = set(window)
    val_ids = sorted(val_set)
    train_ids = sorted(i for i in pool if i not in val_set)
    return train_ids, val_ids, sorted(test_ids)


def _real(ids: List[str]) -> List[str]:
    return [f"real_{i}" for i in ids]


def _synt(ids: List[str]) -> List[str]:
    return [f"synt_{i}" for i in ids]


def _frames(ranges: Dict[str, Tuple[int, int]], seqs: List[str]) -> int:
    return sum(ranges[s][1] - ranges[s][0] for s in seqs)


def author(real_merged: str, mixed_dir: str, out_dir: str,
           folds: int, seed: int, val_count: int) -> None:
    real_ranges, real_total = _ranges(real_merged)
    mixed_ranges, mixed_total = _ranges(mixed_dir)
    ids = sorted(real_ranges.keys())
    real_dir = str(Path(real_merged).resolve())
    mixed_dd = str(Path(mixed_dir).resolve())

    groups, shuffled = _kfold_id_partition(ids, folds, seed)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        "scheme": "grouped_kfold_paired",
        "folds": folds,
        "seed": seed,
        "val_count": val_count,
        "num_ids": len(ids),
        "ids": ids,
        "real_merged": real_dir,
        "mixed_merged": mixed_dd,
        "per_fold": [],
    }
    tested_once: Dict[str, int] = {i: 0 for i in ids}

    for f in range(folds):
        test_ids = groups[f]
        train_ids, val_ids, test_ids = _fold_ids(shuffled, test_ids, val_count, f)

        # per-fold id-disjointness
        s_tr, s_va, s_te = set(train_ids), set(val_ids), set(test_ids)
        assert s_tr.isdisjoint(s_va) and s_tr.isdisjoint(s_te) and s_va.isdisjoint(s_te), \
            f"fold {f}: id partition overlaps"
        assert s_tr | s_va | s_te == set(ids), f"fold {f}: ids not fully partitioned"
        for i in test_ids:
            tested_once[i] += 1

        # --- cond1/cond5 real: bare ids over real_merged, full coverage ---
        real_payload = _payload(
            _idx(real_ranges, train_ids), _idx(real_ranges, val_ids), _idx(real_ranges, test_ids),
            train_ids, val_ids, test_ids, real_total, real_dir,
            "cv_real", require_full_coverage=True,
        )
        real_payload["split_by"] = "sequence"  # real split is not domain-paired

        # --- cond2/cond6 synt->real over mixed, partial coverage, leakage-guarded ---
        assert not ((s_tr | s_va) & s_te), f"fold {f}: synt train/val vs real test id overlap"
        c2_train, c2_val, c2_test = _synt(train_ids), _synt(val_ids), _real(test_ids)
        c2_payload = _payload(
            _idx(mixed_ranges, c2_train), _idx(mixed_ranges, c2_val), _idx(mixed_ranges, c2_test),
            c2_train, c2_val, c2_test, mixed_total, mixed_dd,
            "cv_c2_synt2real_paired", require_full_coverage=False,
        )

        # --- cond3/cond7 mixed: both domains per id, 50:50, full coverage ---
        c3_train = _real(train_ids) + _synt(train_ids)
        c3_val = _real(val_ids) + _synt(val_ids)
        c3_test = _real(test_ids) + _synt(test_ids)
        c3_payload = _payload(
            _idx(mixed_ranges, c3_train), _idx(mixed_ranges, c3_val), _idx(mixed_ranges, c3_test),
            c3_train, c3_val, c3_test, mixed_total, mixed_dd,
            "cv_c3_mixed_paired", require_full_coverage=True,
        )

        # c3 frame-level 50:50 balance per partition (real_n == synt_n per id => exact)
        c3_balance = {}
        for part, t_ids in (("train", train_ids), ("val", val_ids), ("test", test_ids)):
            rf = _frames(mixed_ranges, _real(t_ids))
            sf = _frames(mixed_ranges, _synt(t_ids))
            assert rf == sf, f"fold {f} c3 {part}: real {rf} != synt {sf} frames"
            c3_balance[part] = {"real": rf, "synt": sf, "ratio": rf / (rf + sf)}

        fold_dir = os.path.join(out_dir, f"fold{f}")
        os.makedirs(fold_dir, exist_ok=True)
        for name, payload in (
            ("real_split.json", real_payload),
            ("c2_synt2real_split.json", c2_payload),
            ("c3_mixed_split.json", c3_payload),
        ):
            with open(os.path.join(fold_dir, name), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)

        manifest["per_fold"].append({
            "fold": f,
            "train_ids": train_ids,
            "val_ids": val_ids,
            "test_ids": test_ids,
            "frames": {
                "real": {
                    "train": _frames(real_ranges, train_ids),
                    "val": _frames(real_ranges, val_ids),
                    "test": _frames(real_ranges, test_ids),
                },
                "c2": {
                    "train": _frames(mixed_ranges, c2_train),
                    "val": _frames(mixed_ranges, c2_val),
                    "test": _frames(mixed_ranges, c2_test),
                },
                "c3": {
                    "train": _frames(mixed_ranges, c3_train),
                    "val": _frames(mixed_ranges, c3_val),
                    "test": _frames(mixed_ranges, c3_test),
                },
            },
            "c3_balance": c3_balance,
        })
        print(f"[fold{f}] test_ids={test_ids}")
        print(f"         val_ids={val_ids}  (train={len(train_ids)} ids)")
        print(f"         real frames tr/va/te = "
              f"{manifest['per_fold'][-1]['frames']['real']['train']}/"
              f"{manifest['per_fold'][-1]['frames']['real']['val']}/"
              f"{manifest['per_fold'][-1]['frames']['real']['test']}")

    # global: every id tested exactly once across folds
    bad = {i: c for i, c in tested_once.items() if c != 1}
    assert not bad, f"ids not tested exactly once: {bad}"

    with open(os.path.join(out_dir, "cv_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[ok] {folds}-fold CV authored under {out_dir}")
    print(f"[ok] every one of {len(ids)} ids is a test id in exactly one fold")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Author K-fold leakage-free paired CV splits.")
    p.add_argument("--real-merged", required=True, help="real_merged dir (has sequence_index.json).")
    p.add_argument("--mixed-dir", required=True, help="mixed_merged_256 dir (has sequence_index.json).")
    p.add_argument("--out-dir", required=True, help="CV splits output dir (e.g. splits/cv5).")
    p.add_argument("--folds", type=int, default=5, help="number of folds K (default 5).")
    p.add_argument("--seed", type=int, default=42, help="shuffle seed (default 42).")
    p.add_argument("--val-count", type=int, default=3, help="nested val ids per fold (default 3).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    author(a.real_merged, a.mixed_dir, a.out_dir, a.folds, a.seed, a.val_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
