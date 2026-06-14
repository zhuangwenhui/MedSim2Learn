#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for evaluate._resolve_test_domains (decision #4 domain slicing).

Synthetic, data-independent: builds a tiny paired sequence_index.json + split
JSON in a tempdir and checks the per-test-sample domain labels for the
single-image and sequence (windowed) paths, plus the single-domain and
count-mismatch fallbacks. Skips cleanly if scripts.evaluate cannot be imported
(its heavy torch/grad-cam deps are absent).
"""
import json
import logging
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from scripts.evaluate import _resolve_test_domains
except Exception as exc:  # noqa: BLE001 - torch / grad-cam deps may be absent
    _resolve_test_domains = None
    _IMPORT_ERROR = exc

LOG = logging.getLogger("test_cv_domain_slicing")


def _require():
    if _resolve_test_domains is None:
        raise unittest.SkipTest(f"scripts.evaluate not importable: {_IMPORT_ERROR}")


def _write_fixture(tmp: str) -> None:
    """4 paired sequences (real/synt seqA,seqB), 4 frames each, 16 total."""
    seq = {
        "seq_order": ["real_seqA", "synt_seqA", "real_seqB", "synt_seqB"],
        "sequences": {
            "real_seqA": {"start": 0, "end": 4, "n": 4, "batch_file": "b.pt"},
            "synt_seqA": {"start": 4, "end": 8, "n": 4, "batch_file": "b.pt"},
            "real_seqB": {"start": 8, "end": 12, "n": 4, "batch_file": "b.pt"},
            "synt_seqB": {"start": 12, "end": 16, "n": 4, "batch_file": "b.pt"},
        },
        "total_samples": 16,
    }
    with open(os.path.join(tmp, "sequence_index.json"), "w", encoding="utf-8") as fh:
        json.dump(seq, fh)


def _split(tmp: str, name: str, test_sequences, test_indices) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"test_sequences": test_sequences, "test_indices": test_indices}, fh)
    return path


def _cfg(data_dir: str, window_length: int = 2, stride: int = 2) -> dict:
    return {
        "data": {
            "data_dir": data_dir,
            "sequence": {
                "window_length": window_length,
                "stride": stride,
                "include_tail": True,
            },
        }
    }


def test_single_image_mixed_slices():
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        _write_fixture(tmp)
        split = _split(tmp, "c3.json", ["real_seqA", "synt_seqA"], list(range(8)))
        labels = _resolve_test_domains(_cfg(tmp), split, False, 8, LOG)
        assert labels == ["real"] * 4 + ["synt"] * 4, labels


def test_single_image_single_domain_returns_none():
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        _write_fixture(tmp)
        split = _split(
            tmp, "real.json", ["real_seqA", "real_seqB"],
            list(range(0, 4)) + list(range(8, 12)),
        )
        labels = _resolve_test_domains(_cfg(tmp), split, False, 8, LOG)
        assert labels is None, labels


def test_sequence_mixed_window_domains():
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        _write_fixture(tmp)
        split = _split(tmp, "c3seq.json", ["real_seqA", "synt_seqA"], list(range(8)))
        # window_length=2 stride=2 -> real_seqA windows [0,1],[2,3];
        # synt_seqA windows [4,5],[6,7] -> 4 windows.
        labels = _resolve_test_domains(_cfg(tmp), split, True, 4, LOG)
        assert labels == ["real", "real", "synt", "synt"], labels


def test_count_mismatch_returns_none():
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        _write_fixture(tmp)
        split = _split(tmp, "c3.json", ["real_seqA", "synt_seqA"], list(range(8)))
        labels = _resolve_test_domains(_cfg(tmp), split, False, 999, LOG)
        assert labels is None, labels


def _main() -> int:
    tests = [
        test_single_image_mixed_slices,
        test_single_image_single_domain_returns_none,
        test_sequence_mixed_window_domains,
        test_count_mismatch_returns_none,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except unittest.SkipTest as skip:
            print(f"SKIP {fn.__name__}: {skip}")
        except AssertionError as err:
            failed += 1
            print(f"FAIL {fn.__name__}: {err}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
