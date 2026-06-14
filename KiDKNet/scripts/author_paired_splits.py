#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Author leakage-free real/synt splits for the mixed dataset (paired by id).

Real and synthetic share the SAME per-sequence force trajectory (the twin
replays the real forces), so ``real_seqNN`` and ``synt_seqNN`` are the same
clip's force under different appearance. Splitting them independently leaks the
test force trajectory into training. This script re-authors the two mixed-domain
splits using ONE canonical sequence-id partition (taken from the real split), so
that for every id both domains land in the SAME partition:

- ``c2_synt2real_split.json`` (cond2 / cond6): train+val = SYNT of the train/val
  ids, test = REAL of the test ids. The synt twins of the real test ids never
  appear in training -> no force-trajectory leakage; same test ids as cond1, so
  cond1 vs cond2 is comparable. (Partial coverage: real of train/val ids and
  synt of test ids are intentionally unused.)
- ``c3_mixed_split.json`` (cond3 / cond7): each id contributes BOTH domains to
  the same partition -> exactly 50:50 real:synt in every split, no cross-id
  leakage, test = mixed. (Full coverage of the mixed dataset.)

The canonical id partition is read from the real split's ``*_sequences`` lists so
all conditions share one partition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple


def _load_id_partition(real_split_path: str) -> Tuple[List[str], List[str], List[str]]:
    """Read the canonical (train, val, test) sequence-id lists from the real split."""
    with open(real_split_path, "r", encoding="utf-8") as fh:
        s = json.load(fh)
    train = list(s["train_sequences"])
    val = list(s["val_sequences"])
    test = list(s["test_sequences"])
    if not (train and val and test):
        raise ValueError(f"real split missing *_sequences lists: {real_split_path}")
    overlap = (set(train) & set(val)) | (set(train) & set(test)) | (set(val) & set(test))
    if overlap:
        raise ValueError(f"real split id partition overlaps on: {sorted(overlap)}")
    return train, val, test


def _ranges(mixed_dir: str) -> Tuple[Dict[str, Tuple[int, int]], int]:
    """Return (seq_id -> (start, end), total_samples) from sequence_index.json."""
    with open(os.path.join(mixed_dir, "sequence_index.json"), "r", encoding="utf-8") as fh:
        d = json.load(fh)
    seqs = d["sequences"]
    return {k: (v["start"], v["end"]) for k, v in seqs.items()}, d["total_samples"]


def _idx(ranges: Dict[str, Tuple[int, int]], seq_ids: List[str]) -> List[int]:
    out: List[int] = []
    for sid in seq_ids:
        if sid not in ranges:
            raise KeyError(f"sequence '{sid}' not found in mixed sequence_index")
        s, e = ranges[sid]
        out.extend(range(s, e))
    return out


def _payload(train_idx, val_idx, test_idx, train_seqs, val_seqs, test_seqs,
             dataset_size, data_dir, tag, require_full_coverage):
    tr, va, te = set(train_idx), set(val_idx), set(test_idx)
    assert len(tr) == len(train_idx) and len(va) == len(val_idx) and len(te) == len(test_idx), "dup indices"
    assert tr.isdisjoint(va) and tr.isdisjoint(te) and va.isdisjoint(te), "splits overlap"
    if require_full_coverage:
        assert (tr | va | te) == set(range(dataset_size)), "c3 must fully cover the mixed dataset"
    n = len(train_idx) + len(val_idx) + len(test_idx)
    return {
        "train_indices": train_idx,
        "val_indices": val_idx,
        "test_indices": test_idx,
        "train_ratio": len(train_idx) / n,
        "val_ratio": len(val_idx) / n,
        "test_ratio": len(test_idx) / n,
        "dataset_size": dataset_size,
        "data_dir": data_dir,
        "creation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config_hash": hashlib.md5(f"{tag}|{data_dir}".encode()).hexdigest(),
        "dataset_stats": {
            "train_samples": len(train_idx),
            "val_samples": len(val_idx),
            "test_samples": len(test_idx),
        },
        "split_by": "sequence_id_paired",
        "scheme": tag,
        "train_sequences": train_seqs,
        "val_sequences": val_seqs,
        "test_sequences": test_seqs,
    }


def author(mixed_dir: str, real_split_path: str, out_dir: str) -> None:
    train_ids, val_ids, test_ids = _load_id_partition(real_split_path)
    ranges, total = _ranges(mixed_dir)
    data_dir = str(Path(mixed_dir).resolve())
    os.makedirs(out_dir, exist_ok=True)

    def real(ids): return [f"real_{i}" for i in ids]
    def synt(ids): return [f"synt_{i}" for i in ids]

    # --- c2/c6: synt(train/val) -> real(test), no shared id, partial coverage ---
    c2_train_seqs = synt(train_ids)
    c2_val_seqs = synt(val_ids)
    c2_test_seqs = real(test_ids)
    # leakage guard: no id appears in both a synt-train/val seq and a real-test seq
    train_val_ids = set(train_ids) | set(val_ids)
    assert not (train_val_ids & set(test_ids)), "id partition overlap (synt train/val vs real test)"
    c2 = _payload(
        _idx(ranges, c2_train_seqs), _idx(ranges, c2_val_seqs), _idx(ranges, c2_test_seqs),
        c2_train_seqs, c2_val_seqs, c2_test_seqs, total, data_dir,
        "c2_synt2real_paired", require_full_coverage=False,
    )

    # --- c3/c7: both domains per id in the same split, balanced, full coverage ---
    c3_train_seqs = real(train_ids) + synt(train_ids)
    c3_val_seqs = real(val_ids) + synt(val_ids)
    c3_test_seqs = real(test_ids) + synt(test_ids)
    c3 = _payload(
        _idx(ranges, c3_train_seqs), _idx(ranges, c3_val_seqs), _idx(ranges, c3_test_seqs),
        c3_train_seqs, c3_val_seqs, c3_test_seqs, total, data_dir,
        "c3_mixed_paired", require_full_coverage=True,
    )

    for name, payload in [("c2_synt2real_split.json", c2), ("c3_mixed_split.json", c3)]:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        st = payload["dataset_stats"]
        print(f"[ok] {name}: train={st['train_samples']} val={st['val_samples']} "
              f"test={st['test_samples']} ({payload['scheme']})")
        print(f"     train_seqs={payload['train_sequences']}")
        print(f"     test_seqs ={payload['test_sequences']}")
    print(f"[id partition] train={train_ids}\n               val={val_ids}\n               test={test_ids}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Author leakage-free paired real/synt splits.")
    p.add_argument("--mixed-dir", required=True, help="mixed_merged_256 dir (has sequence_index.json).")
    p.add_argument("--real-split", required=True, help="real_dataset_split.json (canonical id partition).")
    p.add_argument("--out-dir", required=True, help="splits output dir.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    author(a.mixed_dir, a.real_split, a.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
