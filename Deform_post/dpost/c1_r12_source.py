"""Build the frozen R12 source-patch registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np


ANCHOR_SHA256 = (
    "100a577f9e27f0cd719fc3713db4a5538d4dbecea9132efaf3b33bd8ee2cfcb5"
)
RECEIPT_SHA256 = (
    "f3e9fc5a9e62396f0e29f67b6ebc074ff6c5176249de6b21618c880498d2ae9e"
)
FROZEN_SEQUENCE_IDS = (
    "seq01", "seq02", "seq03", "seq05", "seq06", "seq07",
    "seq10", "seq12", "seq13", "seq14", "seq15", "seq16",
    "seq17", "seq18", "seq20", "seq23", "seq24", "seq25",
    "seq26", "seq27", "seq28", "seq29", "seq31", "seq32",
)
PATCH_SIZE = 128
PATCH_STRIDE = 64
_CIRCLE_CENTER = 127.5
_CIRCLE_RADIUS = 112.0
_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/data_improve/c1/r1/split_manifest.json"
)
_DEFAULT_ANCHOR_PATH = Path(
    r"D:\MedSim2Learn-C1-verification\r2-pbr\g1-rerun3\preflight-v1"
    r"\real-frames.npz"
)
_DEFAULT_OUTPUT_PATH = Path(
    r"D:\MedSim2Learn-C1-verification\r12-texture-pbr\source-registry-v1"
)


@dataclass(frozen=True)
class SourcePatchRecord:
    """Identify one accepted real-image source patch."""

    fold: str
    sequence_id: str
    frame_id: str
    frame_index: int
    y: int
    x: int
    rgb_sha256: str
    mean_v: float


@dataclass(frozen=True)
class SourceRegistry:
    """Hold the anchor identity and canonical source-patch records."""

    anchor_path: Path
    anchor_sha256: str
    records: tuple[SourcePatchRecord, ...]
    rejection_counts: Mapping[str, int]


def _sha256(path: Path) -> str:
    """Return the SHA-256 of a file without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_key(record: SourcePatchRecord) -> tuple[str, str, str, int, int]:
    """Return the frozen canonical source-registry sort key."""
    return (
        record.fold,
        record.sequence_id,
        record.frame_id,
        record.y,
        record.x,
    )


def _validate_sequence_ids(sequence_ids: Sequence[str]) -> None:
    """Reject any sequence collection other than the frozen development set."""
    observed = tuple(sequence_ids)
    if observed == FROZEN_SEQUENCE_IDS:
        return
    unexpected = sorted(set(observed) - set(FROZEN_SEQUENCE_IDS))
    if unexpected:
        raise ValueError(f"forbidden sequence ID: {unexpected[0]}")
    raise ValueError("development sequence IDs do not match the frozen 24 IDs")


def _build_exclusion_mask(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build the specified black, highlight, and instrument exclusion mask."""
    rgb = np.asarray(frame, dtype=np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    saturation = hsv[..., 1]
    value = hsv[..., 2]

    # Black is retained at its exact extent; only the other exclusions dilate.
    black = value <= 8
    highlight = (value >= 230) & (saturation <= 32)
    instrument_candidate = (value >= 160) & (saturation <= 24)

    label_count, labels, statistics, _ = cv2.connectedComponentsWithStats(
        instrument_candidate.astype(np.uint8),
        connectivity=8,
    )
    kept_instrument = np.zeros_like(instrument_candidate, dtype=np.uint8)
    for label in range(1, label_count):
        if statistics[label, cv2.CC_STAT_AREA] >= 64:
            kept_instrument[labels == label] = 1

    kernel = np.ones((5, 5), dtype=np.uint8)
    dilated_highlight = cv2.dilate(
        highlight.astype(np.uint8),
        kernel,
        iterations=1,
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    dilated_instrument = cv2.dilate(
        kept_instrument,
        kernel,
        iterations=1,
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return black | (dilated_highlight != 0) | (dilated_instrument != 0), hsv


def _point_is_inside_circle(y: float, x: float) -> bool:
    """Return whether a point is within the registered center and radius."""
    return (
        (y - _CIRCLE_CENTER) ** 2
        + (x - _CIRCLE_CENTER) ** 2
        <= _CIRCLE_RADIUS ** 2
    )


def _patch_is_inside_circle(y: int, x: int) -> bool:
    """Return whether all four patch corners fit the registered image circle."""
    return all(
        _point_is_inside_circle(corner_y, corner_x)
        for corner_y, corner_x in (
            (y, x),
            (y, x + PATCH_SIZE - 1),
            (y + PATCH_SIZE - 1, x),
            (y + PATCH_SIZE - 1, x + PATCH_SIZE - 1),
        )
    )


def _mean_patch_v(hsv: np.ndarray, y: int, x: int) -> float:
    """Return the arithmetic mean V of one accepted source-patch location."""
    return float(
        np.mean(
            hsv[y:y + PATCH_SIZE, x:x + PATCH_SIZE, 2],
            dtype=np.float64,
        )
    )


def _load_fold_map() -> dict[str, str]:
    """Load and validate the fixed four-fold development partition."""
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    _validate_sequence_ids(manifest.get("development_ids", ()))
    fold_map: dict[str, str] = {}
    folds = manifest.get("folds", ())
    if len(folds) != 4:
        raise ValueError("split manifest must provide four development folds")
    for index, fold in enumerate(folds):
        fold_name = f"dev-fold-{index}"
        if fold.get("name") != fold_name:
            raise ValueError(
                "split manifest fold names do not match the frozen map"
            )
        sequence_ids = tuple(fold.get("real_test_ids", ()))
        if len(sequence_ids) != 6:
            raise ValueError(
                "each development fold must contain six real test IDs"
            )
        for sequence_id in sequence_ids:
            if sequence_id in fold_map:
                raise ValueError(
                    "split manifest repeats a development sequence ID"
                )
            fold_map[sequence_id] = fold_name
    if tuple(sorted(fold_map)) != FROZEN_SEQUENCE_IDS:
        raise ValueError(
            "split manifest does not cover exactly the frozen 24 IDs"
        )
    return fold_map


def _load_receipt(receipt_path: Path) -> dict[str, object]:
    """Validate and load the frozen preflight receipt."""
    if _sha256(receipt_path) != RECEIPT_SHA256:
        raise ValueError("receipt SHA-256 differs from the frozen receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("kind") != "g1-preflight-v1"
        or receipt.get("decision") != "pass"
    ):
        raise ValueError("receipt is not the accepted frozen preflight")
    if receipt.get("real_frames_cache_sha256") != ANCHOR_SHA256:
        raise ValueError("receipt does not bind the frozen frame anchor")
    identities = receipt.get("input_identities")
    if not isinstance(identities, dict):
        raise ValueError("receipt has no input identities")
    _validate_sequence_ids(identities.get("development_ids", ()))
    return receipt


def _validate_positions(
    position_records: object,
    fold_map: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    """Reject malformed or forbidden receipt positions before opening pixels."""
    if not isinstance(position_records, list) or len(position_records) != 288:
        raise ValueError(
            "receipt position records do not match the frozen anchor"
        )
    parsed: list[tuple[str, str]] = []
    for position in position_records:
        if not isinstance(position, dict):
            raise ValueError("receipt position record is malformed")
        sequence_id = position.get("seq_id")
        frame_id = position.get("sample_id")
        if not isinstance(sequence_id, str):
            raise ValueError("receipt position record has no sequence ID")
        if sequence_id not in fold_map:
            raise ValueError(f"forbidden sequence ID: {sequence_id}")
        if not isinstance(frame_id, str):
            raise ValueError("receipt position record has no frame ID")
        parsed.append((sequence_id, frame_id))
    counts = Counter(sequence_id for sequence_id, _ in parsed)
    if set(counts) != set(FROZEN_SEQUENCE_IDS):
        raise ValueError(
            "position records do not cover exactly the frozen 24 IDs"
        )
    if any(counts[sequence_id] != 12 for sequence_id in FROZEN_SEQUENCE_IDS):
        raise ValueError(
            "each frozen sequence must provide exactly twelve positions"
        )
    return tuple(parsed)


def _candidate_positions() -> tuple[tuple[int, int], ...]:
    """Return the fixed 128-pixel patches on the registered 64-pixel grid."""
    return tuple(
        (y, x)
        for y in range(0, 256 - PATCH_SIZE + 1, PATCH_STRIDE)
        for x in range(0, 256 - PATCH_SIZE + 1, PATCH_STRIDE)
    )


def build_source_registry(
    anchor_path: Path,
    receipt_path: Path,
) -> SourceRegistry:
    """Build canonical source records from the frozen real-frame anchor."""
    anchor_path = Path(anchor_path)
    receipt_path = Path(receipt_path)
    if _sha256(anchor_path) != ANCHOR_SHA256:
        raise ValueError("anchor SHA-256 differs from the frozen anchor")
    receipt = _load_receipt(receipt_path)
    fold_map = _load_fold_map()
    positions = _validate_positions(receipt.get("position_records"), fold_map)

    records: list[SourcePatchRecord] = []
    rejection_counts = {"outside_circle": 0, "masked": 0}
    with np.load(anchor_path, allow_pickle=False) as anchor:
        if set(anchor.files) != {"real_frames"}:
            raise ValueError("anchor has unexpected arrays")
        frames = anchor["real_frames"]
        if frames.shape != (288, 256, 256, 3) or frames.dtype != np.uint8:
            raise ValueError(
                "anchor frame array does not match the frozen shape"
            )
        for frame_index, (sequence_id, frame_id) in enumerate(positions):
            frame = frames[frame_index]
            exclusion_mask, hsv = _build_exclusion_mask(frame)
            for y, x in _candidate_positions():
                if not _patch_is_inside_circle(y, x):
                    rejection_counts["outside_circle"] += 1
                    continue
                if exclusion_mask[y:y + PATCH_SIZE, x:x + PATCH_SIZE].any():
                    rejection_counts["masked"] += 1
                    continue
                patch = frame[y:y + PATCH_SIZE, x:x + PATCH_SIZE]
                mean_v = _mean_patch_v(hsv, y, x)
                records.append(
                    SourcePatchRecord(
                        fold=fold_map[sequence_id],
                        sequence_id=sequence_id,
                        frame_id=frame_id,
                        frame_index=frame_index,
                        y=y,
                        x=x,
                        rgb_sha256=hashlib.sha256(patch.tobytes()).hexdigest(),
                        mean_v=mean_v,
                    )
                )
    return SourceRegistry(
        anchor_path=anchor_path,
        anchor_sha256=ANCHOR_SHA256,
        records=tuple(sorted(records, key=_canonical_key)),
        rejection_counts=rejection_counts,
    )


def _srgb_uint8_to_linear(patches: np.ndarray) -> np.ndarray:
    """Convert sRGB uint8 patches to float32 linear RGB for atlas builders."""
    encoded = np.asarray(patches, dtype=np.float32) / 255.0
    return np.where(
        encoded <= 0.04045,
        encoded / 12.92,
        ((encoded + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def patches_for_fold(
    registry: SourceRegistry,
    held_out_fold: str,
) -> np.ndarray:
    """Return linear RGB patches excluding the specified held-out fold."""
    if held_out_fold not in {f"dev-fold-{index}" for index in range(4)}:
        raise ValueError("held-out fold is not in the frozen four-fold map")
    if registry.anchor_sha256 != ANCHOR_SHA256:
        raise ValueError(
            "registry anchor SHA-256 differs from the frozen anchor"
        )
    allowed_records = tuple(
        record for record in registry.records if record.fold != held_out_fold
    )
    patches: list[np.ndarray] = []
    with np.load(registry.anchor_path, allow_pickle=False) as anchor:
        frames = anchor["real_frames"]
        for record in allowed_records:
            patch = frames[
                record.frame_index,
                record.y:record.y + PATCH_SIZE,
                record.x:record.x + PATCH_SIZE,
            ]
            if hashlib.sha256(patch.tobytes()).hexdigest() != record.rgb_sha256:
                raise ValueError(
                    "registry source RGB SHA-256 differs from the anchor"
                )
            patches.append(patch.copy())
    if not patches:
        return np.empty((0, PATCH_SIZE, PATCH_SIZE, 3), dtype=np.float32)
    return _srgb_uint8_to_linear(np.stack(patches))


def select_source_sheet_records(
    records: Sequence[SourcePatchRecord],
) -> tuple[SourcePatchRecord, ...]:
    """Select canonical, high-V, and low-V records without reopening anchor."""
    canonical = tuple(sorted(records, key=_canonical_key))
    if len(canonical) < 16:
        return canonical
    equispaced = tuple(
        canonical[round(index * (len(canonical) - 1) / 15)]
        for index in range(16)
    )
    high_v = tuple(
        sorted(
            canonical,
            key=lambda item: (-item.mean_v, _canonical_key(item)),
        )[:8]
    )
    low_v = tuple(
        sorted(
            canonical,
            key=lambda item: (item.mean_v, _canonical_key(item)),
        )[:8]
    )
    selected: list[SourcePatchRecord] = []
    seen: set[SourcePatchRecord] = set()
    for record in equispaced + high_v + low_v:
        if record not in seen:
            selected.append(record)
            seen.add(record)
    return tuple(selected)


def _write_json(path: Path, value: object) -> None:
    """Write deterministic UTF-8 JSON inside an exclusive output root."""
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_source_registry(
    anchor_path: Path = _DEFAULT_ANCHOR_PATH,
    receipt_path: Path | None = None,
    output_path: Path = _DEFAULT_OUTPUT_PATH,
) -> str:
    """Write no-clobber source-registry receipts and source-sheet selections."""
    anchor_path = Path(anchor_path)
    receipt_path = (
        anchor_path.with_name("g1-preflight-v1.json")
        if receipt_path is None
        else Path(receipt_path)
    )
    output_path = Path(output_path)
    output_path.mkdir()
    registry = build_source_registry(anchor_path, receipt_path)
    registry_value = {
        "anchor_path": str(registry.anchor_path),
        "anchor_sha256": registry.anchor_sha256,
        "records": [asdict(record) for record in registry.records],
        "rejection_counts": dict(registry.rejection_counts),
    }
    registry_path = output_path / "registry.json"
    _write_json(registry_path, registry_value)
    registry_sha256 = _sha256(registry_path)
    _write_json(
        output_path / "input-hashes.json",
        {
            "anchor_sha256": _sha256(anchor_path),
            "receipt_sha256": _sha256(receipt_path),
            "split_manifest_sha256": _sha256(_MANIFEST_PATH),
        },
    )
    _write_json(
        output_path / "rejection-counts.json",
        registry.rejection_counts,
    )
    _write_json(
        output_path / "registry-sha256.json",
        {"sha256": registry_sha256},
    )
    selected_by_fold: dict[str, list[dict[str, object]]] = {}
    for fold in (f"dev-fold-{index}" for index in range(4)):
        fold_records = tuple(
            record for record in registry.records if record.fold == fold
        )
        selected = select_source_sheet_records(fold_records)
        selected_value = [asdict(record) for record in selected]
        selected_by_fold[fold] = selected_value
        _write_json(
            output_path / f"{fold}-source-sheet.json",
            {"fold": fold, "records": selected_value},
        )
    _write_json(output_path / "selected-records.json", selected_by_fold)
    status = (
        "PASS_SOURCE_REGISTRY" if registry.records else "INVALID_SOURCE_INPUT"
    )
    _write_json(output_path / "decision.json", {"status": status})
    return status


def main() -> int:
    """Run the one supported source-registry action."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("source-registry",))
    arguments = parser.parse_args()
    if arguments.action == "source-registry":
        return 0 if write_source_registry() == "PASS_SOURCE_REGISTRY" else 2
    raise AssertionError("argparse accepted an unsupported action")


if __name__ == "__main__":
    raise SystemExit(main())
