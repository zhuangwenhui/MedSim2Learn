"""Sequence (clip) dataset for per-frame force regression.

Builds fixed-length temporal windows of CONSECUTIVE frames that never cross a
sequence boundary, using the authoritative ``sequence_index.json`` written by
the Deform_post ``assemble`` step (each sequence occupies a contiguous global
index range ``[start, end)`` and frame order equals global-index order). This
sidesteps sample-id parsing entirely -- which matters because the synthetic
twin frames all share one id prefix and do NOT encode the sequence number.

Because the dataset splits are authored BY SEQUENCE (a whole sequence is in
exactly one of train/val/test), restricting windows to a split's index set is
equivalent to windowing within that split's sequences -- there is no temporal
leakage across splits.

:class:`SequenceDataset` is generic over its frame source: any object that is
indexable by global frame index and returns ``{"image": tensor, "force":
(3,)}``. With a :class:`~dknet.data.dataset.ForceDataset` source each window is
``(T, 3, H, W)``; with a cached-feature source each window is ``(T, F)``. The
per-window dict uses the keys ``image``/``force`` so the default DataLoader
collate stacks them to ``(B, T, ...)`` with no custom collate function.
"""

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import torch
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)

SEQUENCE_INDEX_FILENAME = "sequence_index.json"


def load_sequence_ranges(data_dir: str) -> Dict[str, Tuple[int, int]]:
    """Load ``seq_id -> (start, end)`` ranges (end exclusive) for *data_dir*.

    Args:
        data_dir: Merged dataset directory containing ``sequence_index.json``.

    Returns:
        Ordered mapping of sequence id to its ``(start, end)`` global range,
        in the canonical ``seq_order``.

    Raises:
        FileNotFoundError: If ``sequence_index.json`` is absent (the dataset was
            not produced by the Deform_post assemble step).
    """
    path = os.path.join(data_dir, SEQUENCE_INDEX_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Required {SEQUENCE_INDEX_FILENAME} not found in {data_dir}. "
            "Sequence datasets need the by-sequence index authored by the "
            "Deform_post assemble step."
        )
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    sequences = payload["sequences"]
    order = payload.get("seq_order", list(sequences.keys()))
    return {sid: (sequences[sid]["start"], sequences[sid]["end"]) for sid in order}


def build_windows(
    seq_ranges: Dict[str, Tuple[int, int]],
    subset_indices: Sequence[int],
    window_length: int,
    stride: int,
    include_tail: bool = True,
) -> Tuple[List[Tuple[str, List[int]]], Dict[str, Any]]:
    """Build per-sequence sliding windows restricted to *subset_indices*.

    A sequence contributes windows only when its whole range is present in the
    subset (true for by-sequence splits). Sequences shorter than
    ``window_length`` are skipped and reported.

    Args:
        seq_ranges: ``seq_id -> (start, end)`` from :func:`load_sequence_ranges`.
        subset_indices: Global indices of this split partition.
        window_length: Frames per window ``T`` (>= 1).
        stride: Step between consecutive window starts (>= 1).
        include_tail: Append a final end-aligned window when the last stride does
            not reach the sequence end, so trailing frames are not dropped.

    Returns:
        Tuple ``(windows, stats)`` where each window is ``(seq_id, [global
        indices])`` of length ``window_length`` and ``stats`` records counts.
    """
    if window_length < 1:
        raise ValueError(f"window_length must be >= 1, got {window_length}")
    if stride < 1:
        raise ValueError(f"stride must be >= 1, got {stride}")

    subset_set = set(int(i) for i in subset_indices)
    windows: List[Tuple[str, List[int]]] = []
    used_seqs: List[str] = []
    skipped_short: List[Tuple[str, int]] = []

    for seq_id, (start, end) in seq_ranges.items():
        if start not in subset_set or (end - 1) not in subset_set:
            continue  # sequence not in this split partition
        length = end - start
        if length < window_length:
            skipped_short.append((seq_id, length))
            continue
        used_seqs.append(seq_id)
        starts = list(range(start, end - window_length + 1, stride))
        last_start = end - window_length
        if include_tail and (not starts or starts[-1] != last_start):
            starts.append(last_start)
        for st in starts:
            windows.append((seq_id, list(range(st, st + window_length))))

    stats = {
        "n_windows": len(windows),
        "n_sequences": len(used_seqs),
        "sequences": used_seqs,
        "n_skipped_short": len(skipped_short),
        "skipped_short": skipped_short,
        "window_length": window_length,
        "stride": stride,
    }
    if skipped_short:
        logger.warning(
            "build_windows: skipped %d sequence(s) shorter than window_length=%d: %s",
            len(skipped_short), window_length, skipped_short,
        )
    return windows, stats


class SequenceDataset(Dataset):
    """Windowed view over a per-frame source for sequence force regression."""

    def __init__(
        self,
        frame_source: Any,
        subset_indices: Sequence[int],
        seq_ranges: Dict[str, Tuple[int, int]],
        window_length: int,
        stride: int,
        transform: Optional[Callable] = None,
        include_tail: bool = True,
    ) -> None:
        """Create the windowed dataset.

        Args:
            frame_source: Object indexable by global frame index returning
                ``{"image": tensor, "force": (3,) tensor}`` (e.g. a
                :class:`ForceDataset` or a cached-feature source).
            subset_indices: Global indices of this split partition.
            seq_ranges: ``seq_id -> (start, end)`` ranges.
            window_length: Frames per window ``T``.
            stride: Step between window starts.
            transform: Optional transform applied to the stacked window tensor
                (e.g. image Normalize, which broadcasts over the leading time
                dim). Pass ``None`` for feature sources.
            include_tail: Append an end-aligned tail window (see
                :func:`build_windows`).
        """
        self.frame_source = frame_source
        self.transform = transform
        self.window_length = window_length
        self.windows, self.stats = build_windows(
            seq_ranges, subset_indices, window_length, stride, include_tail
        )
        if not self.windows:
            raise RuntimeError(
                "SequenceDataset built 0 windows. Check window_length/stride "
                f"against sequence sizes (stats={self.stats})."
            )

    def __len__(self) -> int:
        """Number of windows."""
        return len(self.windows)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """Return one window: stacked frames and per-frame forces."""
        if idx < 0 or idx >= len(self.windows):
            raise IndexError(
                f"Index {idx} out of range for {len(self.windows)} windows"
            )
        seq_id, frame_indices = self.windows[idx]
        images = []
        forces = []
        for global_idx in frame_indices:
            sample = self.frame_source[global_idx]
            images.append(sample["image"])
            forces.append(sample["force"])
        image = torch.stack(images, dim=0)  # (T, ...) e.g. (T, 3, H, W) or (T, F)
        force = torch.stack(forces, dim=0)  # (T, 3)
        if self.transform is not None:
            image = self.transform(image)
        return {
            "id": seq_id,
            "image": image,
            "force": force,
            "frame_indices": frame_indices,
        }


def _self_test() -> bool:
    """Window-builder coverage + SequenceDataset shapes on a fake source."""
    ok = True
    try:
        # Two sequences: seq01 [0,10), seq02 [10,17); seq02 in val only.
        seq_ranges = {"seq01": (0, 10), "seq02": (10, 17)}

        # Train subset = seq01 frames; T=4 stride=3 -> starts 0,3,6 + tail 6 (=6,
        # dup avoided) -> {0,3,6}; window 6 covers [6,10). include_tail keeps 6.
        train_idx = list(range(0, 10))
        wins, stats = build_windows(seq_ranges, train_idx, 4, 3, include_tail=True)
        starts = [w[1][0] for w in wins]
        assert starts == [0, 3, 6], starts
        assert all(len(w[1]) == 4 for w in wins)
        assert stats["n_sequences"] == 1 and stats["n_skipped_short"] == 0

        # Tail handling when last stride misses the end: T=4 stride=4 on [0,10)
        # -> starts 0,4 then tail 6.
        wins2, _ = build_windows(seq_ranges, train_idx, 4, 4, include_tail=True)
        assert [w[1][0] for w in wins2] == [0, 4, 6], [w[1][0] for w in wins2]

        # Sequence shorter than window is skipped.
        val_idx = list(range(10, 17))  # length 7
        _, stats_short = build_windows(seq_ranges, val_idx, 8, 1)
        assert stats_short["n_windows"] == 0
        assert stats_short["n_skipped_short"] == 1

        # SequenceDataset stacks frames from a fake source.
        class _FakeSource:
            def __getitem__(self, i):
                return {
                    "image": torch.full((3, 8, 8), float(i)),
                    "force": torch.tensor([float(i), 0.0, 0.0]),
                }

        ds = SequenceDataset(_FakeSource(), train_idx, seq_ranges,
                             window_length=4, stride=3)
        item = ds[0]
        assert item["image"].shape == (4, 3, 8, 8), item["image"].shape
        assert item["force"].shape == (4, 3), item["force"].shape
        assert item["frame_indices"] == [0, 1, 2, 3]
        assert item["id"] == "seq01"
        # Default collate stacks to (B, T, ...).
        from torch.utils.data._utils.collate import default_collate
        batch = default_collate([ds[0], ds[1]])
        assert batch["image"].shape == (2, 4, 3, 8, 8), batch["image"].shape
        assert batch["force"].shape == (2, 4, 3)
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[sequence_dataset self-test] FAILED: {exc}")
        import traceback
        traceback.print_exc()
    print(f"sequence_dataset self-test {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _self_test() else 1)
