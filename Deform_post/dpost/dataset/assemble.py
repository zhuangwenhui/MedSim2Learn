#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Assemble per-sequence digital-twin datasets into a single KiDKNet data_dir.

This is the bridge between the kidney digital-twin DATA production
(``twin_full/seqNN/dataset/`` folders, each holding a
``preprocessed_batch_0000.pt`` plus ``metadata.yaml``) and KiDKNet
TRAINING (a single ``data_dir`` whose ``.pt`` files are sorted and concatenated
by ``dknet.data.dataset.ForceDataset``).

It performs four jobs:

1. Discover READY sequence directories (those that contain both
   ``dataset/preprocessed_batch_0000.pt`` and ``dataset/metadata.yaml``),
   sorted by sequence id; not-ready sequences are skipped and logged.
2. Materialise each sequence's batch into the output directory as
   ``preprocessed_batch_{i:04d}.pt`` in sequence order. By default this is a
   hard link (``os.link``) with a copy fallback; with ``--limit-per-seq N`` a
   truncated ``.pt`` holding the first ``N`` samples is written instead.
3. Write ``sequence_index.json`` (global index ranges per sequence) and a
   KiDKNet-compatible ``metadata.yaml``.
4. Author ``dataset_split.json`` BY SEQUENCE -- whole sequences are assigned to
   train/val/test (explicit ``--val-seqs``/``--test-seqs`` or random-by-ratio
   over sequences with ``--seed``), never splitting individual frames across
   splits. This avoids temporal leakage that the built-in random holdout would
   introduce.

Identifiers and comments are English; user-facing output is plain ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict

import torch
import yaml


# =========================================================================
# Sequence discovery
# =========================================================================
BATCH_FILENAME = "preprocessed_batch_0000.pt"
METADATA_FILENAME = "metadata.yaml"


class SeqEntry(TypedDict):
    """Per-sequence entry in the assembled dataset index (``end`` exclusive)."""

    batch_file: str
    start: int
    end: int
    n: int


def _parse_seq_id(name: str) -> Tuple[int, str]:
    """Return a sort key for a sequence directory name.

    Names look like ``seq02`` / ``seq32``. The numeric suffix drives ordering
    so ``seq02`` precedes ``seq10``. Falls back to the raw name for
    non-conforming directories so discovery never crashes.

    Args:
        name: Directory base name.

    Returns:
        Tuple ``(numeric_key, name)`` usable as a stable sort key.
    """
    digits = "".join(ch for ch in name if ch.isdigit())
    numeric = int(digits) if digits else 1_000_000
    return numeric, name


class ReadySequence:
    """A discovered, ready sequence and its sample count."""

    def __init__(self, seq_id: str, root: Path, batch_path: Path,
                 metadata_path: Path, n_samples: int) -> None:
        self.seq_id = seq_id
        self.root = root
        self.batch_path = batch_path
        self.metadata_path = metadata_path
        self.n_samples = n_samples


def discover_ready_sequences(
    twin_roots: Sequence[Path],
    only_seqs: Optional[Sequence[str]] = None,
) -> Tuple[List[ReadySequence], List[str]]:
    """Find READY sequence directories under the supplied twin roots.

    A sequence is READY when ``dataset/preprocessed_batch_0000.pt`` and
    ``dataset/metadata.yaml`` both exist. The metadata's ``total_samples`` is
    used as the authoritative sample count.

    Args:
        twin_roots: One or more roots holding per-sequence dirs, e.g. ``twin_full``.
        only_seqs: Optional allow-list of sequence ids; when given, sequences
            outside the list are skipped even if ready (used to build small
            subsets such as the smoke dataset).

    Returns:
        Tuple ``(ready, skipped)`` where ``ready`` is the list of
        :class:`ReadySequence` sorted by sequence id and ``skipped`` lists the
        directories that were not ready (with a reason).
    """
    ready: List[ReadySequence] = []
    skipped: List[str] = []
    seen_ids: Dict[str, Path] = {}
    allow = set(only_seqs) if only_seqs else None

    for root in twin_roots:
        if not root.exists():
            skipped.append(f"{root} (root does not exist)")
            continue
        for entry in sorted(root.iterdir(), key=lambda p: _parse_seq_id(p.name)):
            if not entry.is_dir():
                continue
            if not entry.name.lower().startswith("seq"):
                continue
            if allow is not None and entry.name not in allow:
                skipped.append(f"{entry} (excluded by --only-seqs)")
                continue
            batch_path = entry / "dataset" / BATCH_FILENAME
            metadata_path = entry / "dataset" / METADATA_FILENAME
            if not batch_path.exists() or not metadata_path.exists():
                skipped.append(f"{entry} (not ready: missing batch/metadata)")
                continue

            with open(metadata_path, "r", encoding="utf-8") as handle:
                meta = yaml.safe_load(handle)
            n_samples = meta.get("total_samples")
            if not isinstance(n_samples, int) or n_samples <= 0:
                skipped.append(
                    f"{entry} (invalid total_samples={n_samples!r})"
                )
                continue

            if entry.name in seen_ids:
                # Sequence ids must be unique across roots so global indexing
                # and split assignment stay unambiguous.
                raise ValueError(
                    f"Duplicate sequence id '{entry.name}' found in both "
                    f"{seen_ids[entry.name]} and {root}. Sequence ids must be "
                    "unique across twin roots."
                )
            seen_ids[entry.name] = root

            ready.append(
                ReadySequence(
                    seq_id=entry.name,
                    root=root,
                    batch_path=batch_path,
                    metadata_path=metadata_path,
                    n_samples=n_samples,
                )
            )

    ready.sort(key=lambda s: _parse_seq_id(s.seq_id))

    if allow is not None:
        found = {s.seq_id for s in ready}
        missing = sorted(allow - found)
        if missing:
            raise ValueError(
                f"--only-seqs references sequences that are not present/ready: "
                f"{missing}. Ready+allowed: {sorted(found)}"
            )

    return ready, skipped


# =========================================================================
# Batch materialisation
# =========================================================================
def _materialise_batch(
    src: Path, dst: Path, limit: Optional[int]
) -> int:
    """Place one sequence batch at *dst*, optionally truncated.

    When *limit* is ``None`` the file is hard-linked (copy fallback). When
    *limit* is set, the first *limit* samples are loaded and re-serialised so
    the output is a fast subset.

    Args:
        src: Source ``.pt`` file.
        dst: Destination ``.pt`` file (overwritten if present).
        limit: Optional cap on the number of samples to keep.

    Returns:
        Number of samples written to *dst*.
    """
    if dst.exists():
        dst.unlink()

    if limit is None:
        try:
            os.link(src, dst)
        except OSError:
            # Hard link can fail across volumes or on filesystems without
            # link support; fall back to a plain copy.
            shutil.copy2(src, dst)
        data = torch.load(dst, map_location="cpu", weights_only=False)
        return len(data)

    data = torch.load(src, map_location="cpu", weights_only=False)
    truncated = data[:limit]
    torch.save(truncated, dst)
    return len(truncated)


# =========================================================================
# Split authoring (by sequence)
# =========================================================================
def _normalise_seq_token(token: str) -> str:
    """Normalise a user-supplied sequence token to a ``seqNN`` id.

    Accepts ``seq02``, ``2``, ``02`` and returns the matching ``seqNN`` form
    using zero-padded width 2 (the convention used on disk).
    """
    token = token.strip()
    if not token:
        return token
    if token.lower().startswith("seq"):
        return token
    if token.isdigit():
        return f"seq{int(token):02d}"
    return token


def _parse_seq_list(raw: Optional[str]) -> List[str]:
    """Parse a comma-separated sequence list into normalised ids."""
    if not raw:
        return []
    return [
        _normalise_seq_token(tok)
        for tok in raw.split(",")
        if tok.strip()
    ]


def assign_sequences_to_splits(
    seq_ids: List[str],
    val_seqs: List[str],
    test_seqs: List[str],
    ratios: Tuple[float, float, float],
    seed: int,
) -> Tuple[List[str], List[str], List[str]]:
    """Assign whole sequences to train/val/test.

    Explicit ``val_seqs``/``test_seqs`` take precedence; remaining sequences go
    to train. If neither is supplied, sequences are shuffled with *seed* and
    partitioned by *ratios* (computed over the number of sequences, NOT frames).

    Args:
        seq_ids: All ready sequence ids, in canonical order.
        val_seqs: Explicit validation sequence ids (may be empty).
        test_seqs: Explicit test sequence ids (may be empty).
        ratios: ``(train, val, test)`` fractions over sequences.
        seed: RNG seed for the ratio-based assignment.

    Returns:
        Tuple ``(train_ids, val_ids, test_ids)``.
    """
    known = set(seq_ids)
    for label, requested in (("--val-seqs", val_seqs),
                             ("--test-seqs", test_seqs)):
        unknown = [s for s in requested if s not in known]
        if unknown:
            raise ValueError(
                f"{label} references sequences not present/ready: {unknown}. "
                f"Available: {sorted(known)}"
            )
    overlap = set(val_seqs) & set(test_seqs)
    if overlap:
        raise ValueError(
            f"--val-seqs and --test-seqs overlap on: {sorted(overlap)}"
        )

    if val_seqs or test_seqs:
        val_ids = [s for s in seq_ids if s in set(val_seqs)]
        test_ids = [s for s in seq_ids if s in set(test_seqs)]
        assigned = set(val_ids) | set(test_ids)
        train_ids = [s for s in seq_ids if s not in assigned]
        return train_ids, val_ids, test_ids

    # Ratio-based assignment over sequences.
    train_ratio, val_ratio, _test_ratio = ratios
    rng = random.Random(seed)
    shuffled = list(seq_ids)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = round(n * train_ratio)
    n_val = round(n * val_ratio)
    # Guarantee val/test each receive at least one sequence when feasible so
    # downstream loaders (which need >= 2 full batches) are not starved.
    if n >= 3:
        n_train = min(n_train, n - 2)
        if n_val < 1:
            n_val = 1
        if n_train < 1:
            n_train = 1
        if n_train + n_val > n - 1:
            n_val = n - 1 - n_train
    train_ids = sorted(shuffled[:n_train], key=lambda s: _parse_seq_id(s))
    val_ids = sorted(shuffled[n_train:n_train + n_val],
                     key=lambda s: _parse_seq_id(s))
    test_ids = sorted(shuffled[n_train + n_val:], key=lambda s: _parse_seq_id(s))
    return train_ids, val_ids, test_ids


def build_split_payload(
    seq_index: Dict[str, SeqEntry],
    train_ids: List[str],
    val_ids: List[str],
    test_ids: List[str],
    dataset_size: int,
    data_dir_resolved: str,
    config_hash_source: str,
) -> Dict:
    """Construct and VALIDATE the ``dataset_split.json`` payload.

    The three index lists are filled with the global integer sample indices of
    each assigned sequence's frames. The function asserts the lists are
    pairwise disjoint and that their union equals ``range(dataset_size)``.

    Args:
        seq_index: Map ``seq_id -> {start, end, n, batch_file}`` (end exclusive).
        train_ids: Sequences assigned to train.
        val_ids: Sequences assigned to validation.
        test_ids: Sequences assigned to test.
        dataset_size: Total sample count (must equal metadata total_samples).
        data_dir_resolved: ``str(Path(out_dir).resolve())``.
        config_hash_source: String hashed into ``config_hash``.

    Returns:
        The validated split dictionary ready to dump as JSON.
    """
    def indices_for(ids: List[str]) -> List[int]:
        out: List[int] = []
        for sid in ids:
            rng = seq_index[sid]
            out.extend(range(rng["start"], rng["end"]))
        return out

    train_indices = indices_for(train_ids)
    val_indices = indices_for(val_ids)
    test_indices = indices_for(test_ids)

    # --- Validation: disjoint + full coverage + size match -------------------
    train_set = set(train_indices)
    val_set = set(val_indices)
    test_set = set(test_indices)
    assert len(train_set) == len(train_indices), "duplicate train indices"
    assert len(val_set) == len(val_indices), "duplicate val indices"
    assert len(test_set) == len(test_indices), "duplicate test indices"
    assert train_set.isdisjoint(val_set), "train/val indices overlap"
    assert train_set.isdisjoint(test_set), "train/test indices overlap"
    assert val_set.isdisjoint(test_set), "val/test indices overlap"
    union = train_set | val_set | test_set
    assert union == set(range(dataset_size)), (
        "split index union does not cover range(dataset_size); "
        f"|union|={len(union)} dataset_size={dataset_size}"
    )
    total = len(train_indices) + len(val_indices) + len(test_indices)
    assert total == dataset_size, (
        f"index total {total} != dataset_size {dataset_size}"
    )

    # Effective ratios reflect the actual frame counts per split.
    train_ratio = len(train_indices) / dataset_size
    val_ratio = len(val_indices) / dataset_size
    test_ratio = len(test_indices) / dataset_size

    return {
        "train_indices": train_indices,
        "val_indices": val_indices,
        "test_indices": test_indices,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
        "dataset_size": dataset_size,
        "data_dir": data_dir_resolved,
        "creation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config_hash": hashlib.md5(config_hash_source.encode()).hexdigest(),
        "dataset_stats": {
            "train_samples": len(train_indices),
            "val_samples": len(val_indices),
            "test_samples": len(test_indices),
        },
        # Extra provenance (ignored by load_split, useful for humans).
        "split_by": "sequence",
        "train_sequences": train_ids,
        "val_sequences": val_ids,
        "test_sequences": test_ids,
    }


# =========================================================================
# Orchestration
# =========================================================================
def assemble(
    twin_roots: List[Path],
    out_dir: Path,
    split_out: Path,
    val_seqs: List[str],
    test_seqs: List[str],
    ratios: Tuple[float, float, float],
    seed: int,
    limit_per_seq: Optional[int],
    only_seqs: Optional[List[str]] = None,
) -> Dict:
    """Run the full assembly + split authoring pipeline.

    Returns:
        A summary dict describing the merged dataset and split assignment.
    """
    ready, skipped = discover_ready_sequences(twin_roots, only_seqs=only_seqs)
    if not ready:
        raise RuntimeError("No READY sequences discovered; nothing to assemble.")

    print(f"[discover] READY sequences ({len(ready)}):")
    for seq in ready:
        print(f"    {seq.seq_id:<8} n={seq.n_samples:<6} <- {seq.batch_path}")
    if skipped:
        print(f"[discover] skipped ({len(skipped)}):")
        for item in skipped:
            print(f"    {item}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Materialise batches in sequence order and compute global index ranges.
    seq_index: Dict[str, SeqEntry] = {}
    seq_order: List[str] = []
    cursor = 0
    representative_batch_size = ready[0].n_samples
    for i, seq in enumerate(ready):
        dst_name = f"preprocessed_batch_{i:04d}.pt"
        dst = out_dir / dst_name
        written = _materialise_batch(seq.batch_path, dst, limit_per_seq)
        start = cursor
        end = cursor + written
        seq_index[seq.seq_id] = {
            "batch_file": dst_name,
            "start": start,
            "end": end,
            "n": written,
        }
        seq_order.append(seq.seq_id)
        cursor = end
        mode = "link" if limit_per_seq is None else f"trunc<= {limit_per_seq}"
        print(f"[merge] {seq.seq_id} -> {dst_name} "
              f"[{start}:{end}) n={written} ({mode})")

    dataset_size = cursor

    # Write sequence_index.json.
    sequence_index_payload = {
        "seq_order": seq_order,
        "sequences": seq_index,
        "total_samples": dataset_size,
    }
    with open(out_dir / "sequence_index.json", "w", encoding="utf-8") as handle:
        json.dump(sequence_index_payload, handle, indent=2)

    # Write metadata.yaml (KiDKNet-compatible; loose batch_size).
    metadata = {
        "total_samples": dataset_size,
        "batch_size": representative_batch_size,
        "normalize_images": False,
        "normalize_forces": False,
        "force_normalization": None,
        "image_size": [224, 224],
        "original_image_size": [800, 800],
        "n_sequences": len(seq_order),
        "sequences": seq_order,
        "dataset_name": "twin_merged",
        "creation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(out_dir / "metadata.yaml", "w", encoding="utf-8") as handle:
        yaml.safe_dump(metadata, handle, sort_keys=True)

    # Assign sequences to splits and author dataset_split.json.
    train_ids, val_ids, test_ids = assign_sequences_to_splits(
        seq_order, val_seqs, test_seqs, ratios, seed
    )
    data_dir_resolved = str(out_dir.resolve())
    split_payload = build_split_payload(
        seq_index=seq_index,
        train_ids=train_ids,
        val_ids=val_ids,
        test_ids=test_ids,
        dataset_size=dataset_size,
        data_dir_resolved=data_dir_resolved,
        config_hash_source=f"twin_merged|{data_dir_resolved}|{seed}",
    )

    # The contract requires dataset_size == metadata total_samples.
    assert split_payload["dataset_size"] == metadata["total_samples"], (
        "split dataset_size != metadata total_samples"
    )

    split_out.parent.mkdir(parents=True, exist_ok=True)
    with open(split_out, "w", encoding="utf-8") as handle:
        json.dump(split_payload, handle, indent=2)

    print()
    print("[split] by-sequence assignment:")
    print(f"    train: {train_ids} "
          f"({split_payload['dataset_stats']['train_samples']} frames, "
          f"{split_payload['train_ratio']:.3f})")
    print(f"    val:   {val_ids} "
          f"({split_payload['dataset_stats']['val_samples']} frames, "
          f"{split_payload['val_ratio']:.3f})")
    print(f"    test:  {test_ids} "
          f"({split_payload['dataset_stats']['test_samples']} frames, "
          f"{split_payload['test_ratio']:.3f})")
    print(f"[split] dataset_size={dataset_size} "
          f"== metadata total_samples={metadata['total_samples']}  OK")
    print(f"[split] disjoint + full coverage of range({dataset_size})  OK")
    print()
    print(f"[out] merged data_dir : {data_dir_resolved}")
    print(f"[out] metadata.yaml   : {out_dir / 'metadata.yaml'}")
    print(f"[out] sequence_index  : {out_dir / 'sequence_index.json'}")
    print(f"[out] split file      : {split_out.resolve()}")

    return {
        "n_ready": len(ready),
        "n_skipped": len(skipped),
        "dataset_size": dataset_size,
        "seq_order": seq_order,
        "train_sequences": train_ids,
        "val_sequences": val_ids,
        "test_sequences": test_ids,
        "dataset_stats": split_payload["dataset_stats"],
        "data_dir": data_dir_resolved,
        "split_file": str(split_out.resolve()),
    }


# =========================================================================
# Self-test
# =========================================================================
def run_self_test() -> bool:
    """Verify merge indexing + split disjointness/coverage on synthetic data.

    Creates two tiny synthetic sequences, assembles them with truncation, and
    asserts the merged index ranges, metadata size, and by-sequence split are
    correct. Prints PASS/FAIL and returns the boolean.
    """
    import tempfile

    ok = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            roots = [tmp_path / "twin_a", tmp_path / "twin_b"]

            def make_seq(root: Path, seq_id: str, n: int) -> None:
                ds = root / seq_id / "dataset"
                ds.mkdir(parents=True, exist_ok=True)
                samples = [
                    {
                        "id": f"{seq_id}_s{j:04d}",
                        "image": torch.zeros(3, 224, 224, dtype=torch.float32),
                        "force": torch.tensor(
                            [float(j), 0.0, 0.0], dtype=torch.float32
                        ),
                    }
                    for j in range(n)
                ]
                torch.save(samples, ds / BATCH_FILENAME)
                with open(ds / METADATA_FILENAME, "w", encoding="utf-8") as fh:
                    yaml.safe_dump({"total_samples": n, "batch_size": 2000,
                                    "normalize_images": False}, fh)

            # seq01 -> 10 samples in twin_a; seq02 -> 7 in twin_a; seq03 -> 5 in
            # twin_b. Truncate to 4 per sequence -> sizes 4/4/4 = 12 total.
            make_seq(roots[0], "seq01", 10)
            make_seq(roots[0], "seq02", 7)
            make_seq(roots[1], "seq03", 5)

            out_dir = tmp_path / "merged"
            split_out = tmp_path / "split.json"
            summary = assemble(
                twin_roots=roots,
                out_dir=out_dir,
                split_out=split_out,
                val_seqs=["seq02"],
                test_seqs=["seq03"],
                ratios=(0.6, 0.2, 0.2),
                seed=0,
                limit_per_seq=4,
            )

            # Expected: order seq01, seq02, seq03; each truncated to 4.
            assert summary["seq_order"] == ["seq01", "seq02", "seq03"], \
                summary["seq_order"]
            assert summary["dataset_size"] == 12, summary["dataset_size"]

            seq_index = json.loads(
                (out_dir / "sequence_index.json").read_text()
            )["sequences"]
            assert seq_index["seq01"]["start"] == 0
            assert seq_index["seq01"]["end"] == 4
            assert seq_index["seq02"]["start"] == 4
            assert seq_index["seq02"]["end"] == 8
            assert seq_index["seq03"]["start"] == 8
            assert seq_index["seq03"]["end"] == 12

            split = json.loads(split_out.read_text())
            assert split["dataset_size"] == 12
            assert split["train_indices"] == [0, 1, 2, 3]
            assert split["val_indices"] == [4, 5, 6, 7]
            assert split["test_indices"] == [8, 9, 10, 11]
            tr, va, te = (set(split["train_indices"]),
                          set(split["val_indices"]),
                          set(split["test_indices"]))
            assert tr.isdisjoint(va) and tr.isdisjoint(te) and va.isdisjoint(te)
            assert (tr | va | te) == set(range(12))

            # data_dir must resolve char-for-char to the merged dir.
            assert split["data_dir"] == str(out_dir.resolve())

            # Verify the truncated batch really holds 4 samples and is loadable.
            b0 = torch.load(out_dir / "preprocessed_batch_0000.pt",
                            map_location="cpu", weights_only=False)
            assert len(b0) == 4 and b0[0]["image"].shape == (3, 224, 224)
    except Exception as exc:  # noqa: BLE001 - self-test must report any failure
        ok = False
        print(f"[self-test] exception: {exc}")
        import traceback
        traceback.print_exc()

    print(f"[self-test] {'PASS' if ok else 'FAIL'}")
    return ok


# =========================================================================
# CLI
# =========================================================================
def _parse_ratios(raw: str) -> Tuple[float, float, float]:
    parts = [float(x) for x in raw.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "--ratios needs exactly three comma-separated values"
        )
    if abs(sum(parts) - 1.0) > 1e-6:
        raise argparse.ArgumentTypeError(
            f"--ratios must sum to 1.0, got {sum(parts)}"
        )
    return parts[0], parts[1], parts[2]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble per-sequence twin datasets into one KiDKNet "
                    "data_dir and author a by-sequence split."
    )
    parser.add_argument(
        "--twin-roots",
        type=str,
        help="Comma-separated twin root dir(s), e.g. "
             "'D:\\...\\DataFlow\\Deform_post\\twin_full'.",
    )
    parser.add_argument("--out-dir", type=str,
                        help="Output merged data_dir.")
    parser.add_argument("--split-out", type=str,
                        help="Path to write dataset_split.json.")
    parser.add_argument("--val-seqs", type=str, default=None,
                        help="Comma-separated validation sequence ids "
                             "(e.g. 'seq05,seq11').")
    parser.add_argument("--test-seqs", type=str, default=None,
                        help="Comma-separated test sequence ids.")
    parser.add_argument("--ratios", type=_parse_ratios, default=(0.6, 0.2, 0.2),
                        help="train,val,test fractions over SEQUENCES "
                             "(used only when val/test seqs not given).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed for ratio-based sequence assignment.")
    parser.add_argument("--limit-per-seq", type=int, default=None,
                        help="If set, write truncated .pt with first N samples "
                             "per sequence (fast subset).")
    parser.add_argument("--only-seqs", type=str, default=None,
                        help="Comma-separated allow-list of sequence ids to "
                             "include (e.g. 'seq02,seq05,seq32'); others are "
                             "skipped. Used to build small subsets.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run synthetic self-test and exit.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.self_test:
        return 0 if run_self_test() else 1

    missing = [name for name in ("twin_roots", "out_dir", "split_out")
               if getattr(args, name) is None]
    if missing:
        print(f"[error] missing required arguments: {missing}", file=sys.stderr)
        return 2

    twin_roots = [Path(p.strip()) for p in args.twin_roots.split(",") if p.strip()]
    summary = assemble(
        twin_roots=twin_roots,
        out_dir=Path(args.out_dir),
        split_out=Path(args.split_out),
        val_seqs=_parse_seq_list(args.val_seqs),
        test_seqs=_parse_seq_list(args.test_seqs),
        ratios=args.ratios,
        seed=args.seed,
        limit_per_seq=args.limit_per_seq,
        only_seqs=_parse_seq_list(args.only_seqs) or None,
    )
    print()
    print(f"[done] assembled {summary['n_ready']} sequences, "
          f"{summary['dataset_size']} frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
