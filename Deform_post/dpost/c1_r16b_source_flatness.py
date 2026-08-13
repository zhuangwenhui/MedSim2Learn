"""Rank accepted source patches by low-frequency luminance flatness."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Callable, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw

from dpost.c1_r13_source import AcceptedPatch, FOLDS
from dpost.c1_r13b_image_quilting import _srgb_to_linear, quilt_atlas
from dpost.c1_r16_uv_render import (
    FORMAL_CAMERA_NAMES,
    FORMAL_STATUS,
    RenderedView,
    read_formal_bundle,
    validate_render_set,
)


HELD_OUT_FOLD = "dev-fold-0"
ARM_PATCH_COUNTS = {
    "b0": 690,
    "f75": 518,
    "f50": 345,
    "f25": 173,
}
A1_SCHEMA = "c1-r16b-a1-source-flatness-v1"
A1_STATUS = "C1_R16B_A1_READY"
_A1_ARMS = tuple(ARM_PATCH_COUNTS)
_A1_MESHES = ("canonical", "deformed-s0521-v0000")
_A1_SEED = 4652038117840977932
_MIN_AVAILABLE_MEMORY_BYTES = 4_000_000_000
_MAX_PROCESS_TREE_RSS_BYTES = 500_000_000
_A1_INPUTS_SCHEMA = "c1-r16b-a1-inputs-v1"
_A1_VALIDATION_SCHEMA = "c1-r16b-a1-validation-v1"
_A1_TELEMETRY_SCHEMA = "c1-r16b-a1-telemetry-v2"

FilteredRenderer = Callable[
    [np.ndarray, Path],
    Mapping[str, Mapping[str, RenderedView]],
]


@dataclass(frozen=True)
class ScoredPatch:
    """Associate one accepted patch with its flatness span."""

    patch: AcceptedPatch
    flatness_span: float


def _validate_accepted_patch(patch: AcceptedPatch) -> None:
    """Validate a legal A1 source patch without mutating it."""
    if not isinstance(patch, AcceptedPatch):
        raise ValueError("A1 patch is not an accepted patch")
    if patch.rgb.shape != (64, 64, 3) or patch.rgb.dtype != np.uint8:
        raise ValueError("accepted patch must be uint8 64x64 RGB")
    if patch.identity.source_fold not in FOLDS:
        raise ValueError("accepted patch source fold is not frozen")
    if patch.identity.source_fold == HELD_OUT_FOLD:
        raise ValueError("accepted patch belongs to the held-out fold")
    digest = hashlib.sha256(patch.rgb.tobytes()).hexdigest()
    if digest != patch.identity.rgb_sha256:
        raise ValueError("accepted patch RGB SHA-256 does not match pixels")


def _linear_luminance(patch: AcceptedPatch) -> np.ndarray:
    """Return one patch's linear Rec. 709 luminance in float64 precision."""
    _validate_accepted_patch(patch)
    linear = _srgb_to_linear(patch.rgb[np.newaxis, ...])[0].astype(
        np.float64,
        copy=False,
    )
    return (
        0.2126 * linear[..., 0]
        + 0.7152 * linear[..., 1]
        + 0.0722 * linear[..., 2]
    )


def _lowpass_luminance(patch: AcceptedPatch) -> np.ndarray:
    """Return the fixed sigma-8 low-pass linear luminance image."""
    return cv2.GaussianBlur(
        _linear_luminance(patch),
        (0, 0),
        sigmaX=8.0,
        sigmaY=8.0,
        borderType=cv2.BORDER_REFLECT101,
    )


def score_patch_flatness(patch: AcceptedPatch) -> float:
    """Return the low-pass luminance 95th-minus-5th percentile span."""
    lowpass = _lowpass_luminance(patch)
    return float(np.percentile(lowpass, 95) - np.percentile(lowpass, 5))


def rank_patch_flatness(patches: Sequence[AcceptedPatch]) -> tuple[ScoredPatch, ...]:
    """Validate, score, and order legal patches by span then RGB SHA-256."""
    accepted = tuple(patches)
    seen_sha256: set[str] = set()
    for patch in accepted:
        _validate_accepted_patch(patch)
        digest = patch.identity.rgb_sha256
        if digest in seen_sha256:
            raise ValueError("legal A1 patch pool contains a duplicate SHA-256")
        seen_sha256.add(digest)
    scored = tuple(
        ScoredPatch(patch=patch, flatness_span=score_patch_flatness(patch))
        for patch in accepted
    )
    return tuple(
        sorted(
            scored,
            key=lambda entry: (entry.flatness_span, entry.patch.identity.rgb_sha256),
        )
    )


def select_arm_patches(
    ranked_patches: Sequence[ScoredPatch],
    arm: str,
) -> tuple[AcceptedPatch, ...]:
    """Return the fixed retained prefix for one A1 source-flatness arm."""
    if arm not in ARM_PATCH_COUNTS:
        raise ValueError("A1 arm is not one of b0, f75, f50, or f25")
    ranked = tuple(ranked_patches)
    if len(ranked) != ARM_PATCH_COUNTS["b0"]:
        raise ValueError("A1 arm selection requires exactly 690 ranked legal patches")
    previous_key: tuple[float, str] | None = None
    seen_sha256: set[str] = set()
    for entry in ranked:
        if not isinstance(entry, ScoredPatch):
            raise ValueError("A1 arm selection input is not a scored patch")
        _validate_accepted_patch(entry.patch)
        digest = entry.patch.identity.rgb_sha256
        if digest in seen_sha256:
            raise ValueError("legal A1 patch pool contains a duplicate SHA-256")
        seen_sha256.add(digest)
        key = (entry.flatness_span, digest)
        if not math.isfinite(entry.flatness_span):
            raise ValueError("A1 flatness span is not finite")
        if previous_key is not None and key < previous_key:
            raise ValueError("A1 arm selection input is not ranked")
        previous_key = key
    return tuple(entry.patch for entry in ranked[:ARM_PATCH_COUNTS[arm]])


def reuse_statistics(used_patch_sha256: Sequence[str]) -> dict[str, float | int]:
    """Return literal reuse counts, entropy in nats, and effective count."""
    counts = Counter(used_patch_sha256)
    used_patch_count = sum(counts.values())
    if not used_patch_count:
        return {
            "used_patch_count": 0,
            "unique_patch_count": 0,
            "maximum_reuse": 0,
            "reuse_entropy_nats": 0.0,
            "effective_patch_count": 0.0,
        }
    probabilities = tuple(count / used_patch_count for count in counts.values())
    entropy = -sum(probability * math.log(probability) for probability in probabilities)
    return {
        "used_patch_count": used_patch_count,
        "unique_patch_count": len(counts),
        "maximum_reuse": max(counts.values()),
        "reuse_entropy_nats": entropy,
        "effective_patch_count": math.exp(entropy),
    }


def lowpass_gradient_statistics(
    patch: AcceptedPatch,
    mask: np.ndarray,
) -> dict[str, float | int]:
    """Return masked finite-difference statistics of fixed low-pass luminance."""
    mask_array = np.asarray(mask)
    if mask_array.shape != (64, 64) or mask_array.dtype != np.bool_:
        raise ValueError("A1 gradient mask must be boolean 64x64")
    lowpass = _lowpass_luminance(patch)
    horizontal_valid = mask_array[:, :-1] & mask_array[:, 1:]
    vertical_valid = mask_array[:-1, :] & mask_array[1:, :]
    horizontal = np.abs(lowpass[:, 1:] - lowpass[:, :-1])
    vertical = np.abs(lowpass[1:, :] - lowpass[:-1, :])
    horizontal_count = int(np.count_nonzero(horizontal_valid))
    vertical_count = int(np.count_nonzero(vertical_valid))
    horizontal_mean = (
        float(np.mean(horizontal[horizontal_valid])) if horizontal_count else 0.0
    )
    vertical_mean = float(np.mean(vertical[vertical_valid])) if vertical_count else 0.0
    return {
        "horizontal_valid_count": horizontal_count,
        "vertical_valid_count": vertical_count,
        "mean_absolute_horizontal_gradient": horizontal_mean,
        "mean_absolute_vertical_gradient": vertical_mean,
    }


def _a1_content_paths() -> set[str]:
    """Return the exact pre-closure content paths for one A1 bundle."""
    paths = {
        "inputs.json",
        "ranking/all-legal-patches.json",
        "contact-sheets/flatness-ranked.png",
        "comparison/blind-labeled.png",
        "comparison/blind-map.json",
        "metrics.json",
        "validation.json",
        "telemetry.json",
    }
    for arm in _A1_ARMS:
        paths.update(
            {
                f"ranking/{arm}-retained.json",
                f"ranking/{arm}-rejected.json",
                f"arms/{arm}/atlas-dev-fold-0.png",
            }
        )
    for arm in ("f75", "f50", "f25"):
        paths.update(
            {
                f"contact-sheets/{arm}-retained.png",
                f"contact-sheets/{arm}-rejected.png",
            }
        )
    for arm in _A1_ARMS:
        for mesh_name in _A1_MESHES:
            for view_name in FORMAL_CAMERA_NAMES:
                paths.add(f"renders/{arm}/{mesh_name}/{view_name}.png")
    for mesh_name in _A1_MESHES:
        for view_name in FORMAL_CAMERA_NAMES:
            paths.add(f"masks/{mesh_name}/{view_name}.png")
    return paths


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of one exact file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, value: object) -> None:
    """Write one UTF-8 JSON object without overwriting an existing artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")


def _write_rgb_exclusive(path: Path, rgb: np.ndarray) -> None:
    """Write one exact RGB PNG without resizing or replacing existing bytes."""
    if rgb.shape[:2] == (0, 0) or rgb.dtype != np.uint8 or rgb.shape[-1:] != (3,):
        raise ValueError("A1 RGB artifact is not a nonempty uint8 RGB array")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("A1 output PNG already exists")
    Image.fromarray(rgb, mode="RGB").save(path)


def _load_png(path: Path, mode: str, size: tuple[int, int]) -> np.ndarray:
    """Load one exact PNG and enforce its native mode and dimensions."""
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.mode != mode or image.size != size:
            raise ValueError("A1 bundle PNG contract differs")
        return np.array(image, copy=True)


def _recursive_file_paths(root: Path) -> set[str]:
    """Collect normalized recursive file paths without following link semantics."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _expected_directory_paths(content_paths: set[str]) -> set[str]:
    """Return every required non-root directory for an exact closed file tree."""
    directories: set[str] = set()
    for relative_path in content_paths | {"artifact-hashes.json", "receipt.json"}:
        parent = Path(relative_path).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _recursive_directory_paths(root: Path) -> set[str]:
    """Collect all non-root directories so empty extras cannot evade validation."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }


def _ranking_payload(entries: Sequence[ScoredPatch]) -> list[dict[str, object]]:
    """Serialize ordered score and custody data without changing source pixels."""
    return [
        {
            "identity": asdict(entry.patch.identity),
            "flatness_span": entry.flatness_span,
        }
        for entry in entries
    ]


def _contact_sheet(
    entries: Sequence[ScoredPatch],
    title: str,
    cutoff_indices: Sequence[int] = (),
) -> np.ndarray:
    """Compose native 64-pixel patch tiles with a separate text band per tile."""
    columns = 15
    tile_size = 64
    label_height = 32
    rows = max(1, math.ceil(len(entries) / columns))
    canvas = np.zeros(
        (rows * (tile_size + label_height), columns * tile_size, 3),
        dtype=np.uint8,
    )
    for index, entry in enumerate(entries):
        row, column = divmod(index, columns)
        top = row * (tile_size + label_height)
        left = column * tile_size
        canvas[top : top + tile_size, left : left + tile_size] = entry.patch.rgb
    image = Image.fromarray(canvas, mode="RGB")
    draw = ImageDraw.Draw(image)
    for index, entry in enumerate(entries):
        row, column = divmod(index, columns)
        top = row * (tile_size + label_height)
        left = column * tile_size
        digest = entry.patch.identity.rgb_sha256[:8]
        draw.text(
            (left + 1, top + tile_size),
            f"{digest} {entry.flatness_span:.5f}",
            fill="white",
        )
        draw.text(
            (left + 1, top + tile_size + 14),
            f"{entry.patch.identity.source_fold} {title}",
            fill="white",
        )
    for cutoff_index in cutoff_indices:
        cutoff_row = cutoff_index // columns
        top = cutoff_row * (tile_size + label_height) + tile_size
        if 0 <= top < canvas.shape[0]:
            draw.rectangle(
                (0, top, canvas.shape[1] - 1, top + 1),
                fill=(255, 0, 255),
            )
    return np.array(image, dtype=np.uint8, copy=True)


def _blind_map() -> dict[str, str]:
    """Return the preregistered blind label mapping from lexical arm digests."""
    ordered = sorted(
        _A1_ARMS,
        key=lambda arm: hashlib.sha256(
            f"c1-r16b-a1-blind-v1:{arm}".encode("utf-8")
        ).hexdigest(),
    )
    mapping = dict(zip(("A", "B", "C", "D"), ordered, strict=True))
    expected = {"A": "f75", "B": "b0", "C": "f25", "D": "f50"}
    if mapping != expected:
        raise ValueError("A1 blind mapping differs from the preregistered order")
    return mapping


def _blind_comparison(root: Path, blind_map: Mapping[str, str]) -> np.ndarray:
    """Rebuild the fixed blinded comparison image from saved arm renders."""
    rows = []
    for label, arm in blind_map.items():
        row = []
        for mesh_name in _A1_MESHES:
            for view_name in FORMAL_CAMERA_NAMES:
                row.append(
                    _load_png(
                        root / f"renders/{arm}/{mesh_name}/{view_name}.png",
                        "RGB",
                        (512, 512),
                    )
                )
        image = Image.fromarray(np.concatenate(row, axis=1), mode="RGB")
        ImageDraw.Draw(image).text((4, 4), label, fill="white")
        rows.append(np.array(image, dtype=np.uint8, copy=True))
    return np.concatenate(rows, axis=0)


def _inputs_payload(
    formal_root: Path,
    frozen_s1_path: Path,
    source_common_receipt: Path,
    formal_status: str,
) -> dict[str, object]:
    """Return the exact frozen-input binding payload for one A1 bundle."""
    formal_receipt = formal_root / "receipt.json"
    return {
        "schema": _A1_INPUTS_SCHEMA,
        "formal_root": str(formal_root.resolve()),
        "formal_receipt_path": str(formal_receipt.resolve()),
        "formal_receipt_sha256": _file_sha256(formal_receipt),
        "source_common_receipt_path": str(source_common_receipt.resolve()),
        "source_common_receipt_sha256": _file_sha256(source_common_receipt),
        "frozen_s1_path": str(frozen_s1_path.resolve()),
        "frozen_s1_sha256": _file_sha256(frozen_s1_path),
        "formal_status": formal_status,
        "seed": _A1_SEED,
        "arm_patch_counts": ARM_PATCH_COUNTS,
    }


def _validation_payload(blind_map: Mapping[str, str]) -> dict[str, object]:
    """Return the exact passed A1 validation-gate payload."""
    return {
        "schema": _A1_VALIDATION_SCHEMA,
        "all_gates_passed": True,
        "gates": {
            "inputs_bound": True,
            "rankings_replayed": True,
            "b0_bytes_matched": True,
            "filtered_outputs_replayed": True,
            "comparison_rebuilt": True,
            "metrics_recomputed": True,
            "telemetry_within_limit": True,
        },
        "retained_counts": ARM_PATCH_COUNTS,
        "blind_map": dict(blind_map),
    }


def _resolve_peak_rss(value: int | Callable[[], int]) -> int:
    """Resolve and validate one current process-tree RSS peak value."""
    peak = value() if callable(value) else value
    if (
        not isinstance(peak, int)
        or isinstance(peak, bool)
        or not 0 <= peak < _MAX_PROCESS_TREE_RSS_BYTES
    ):
        raise MemoryError("A1 RSS peak is outside the required ceiling")
    return peak


def _telemetry_payload(
    available_memory_bytes: int,
    peak_process_tree_rss_bytes: int,
) -> dict[str, object]:
    """Return the exact serial resource-policy telemetry payload."""
    return {
        "schema": _A1_TELEMETRY_SCHEMA,
        "available_memory_bytes_before": available_memory_bytes,
        "measurement_scope": "through_bundle_generation_before_readback",
        "peak_process_tree_rss_bytes": peak_process_tree_rss_bytes,
        "rss_limit_bytes": _MAX_PROCESS_TREE_RSS_BYTES,
        "sample_interval_seconds": 0.05,
        "within_limit": peak_process_tree_rss_bytes < _MAX_PROCESS_TREE_RSS_BYTES,
        "worker_count": 1,
    }


def _gradient_summary(rgb: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    """Return descriptive low-pass gradient summaries for one masked RGB image."""
    normalized = rgb.astype(np.float64) / 255.0
    linear = np.where(
        normalized <= 0.04045,
        normalized / 12.92,
        ((normalized + 0.055) / 1.055) ** 2.4,
    )
    luminance = (
        0.2126 * linear[..., 0]
        + 0.7152 * linear[..., 1]
        + 0.0722 * linear[..., 2]
    )
    lowpass = cv2.GaussianBlur(
        luminance,
        (0, 0),
        8.0,
        borderType=cv2.BORDER_REFLECT101,
    )
    horizontal = np.abs(lowpass[:, 1:] - lowpass[:, :-1])
    vertical = np.abs(lowpass[1:, :] - lowpass[:-1, :])
    valid = np.concatenate(
        (
            horizontal[mask[:, :-1] & mask[:, 1:]],
            vertical[mask[:-1, :] & mask[1:, :]],
        )
    )
    if not len(valid):
        raise ValueError("A1 image has no valid masked gradient samples")
    return {
        "mean": float(np.mean(valid)),
        "p95": float(np.percentile(valid, 95)),
        "max": float(np.max(valid)),
    }


def _score_summary(entries: Sequence[ScoredPatch]) -> dict[str, float | int]:
    """Return descriptive source-score distribution values for one patch set."""
    scores = np.asarray([entry.flatness_span for entry in entries], dtype=np.float64)
    if not len(scores):
        return {"count": 0, "mean": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "count": int(len(scores)),
        "mean": float(np.mean(scores)),
        "p95": float(np.percentile(scores, 95)),
        "max": float(np.max(scores)),
    }


def _atlas_gradient_metrics(atlas: np.ndarray) -> dict[str, dict[str, float]]:
    """Measure low-pass gradients in fixed quilting overlap and interior masks."""
    rows, columns = np.indices(atlas.shape[:2])
    overlap = ((rows % 48) < 16) | ((columns % 48) < 16)
    interior = ~overlap
    return {
        "overlap": _gradient_summary(atlas, overlap),
        "interior": _gradient_summary(atlas, interior),
    }


def _descriptive_metrics(
    root: Path,
    formal_root: Path,
    ranked: Sequence[ScoredPatch],
    used_by_arm: Mapping[str, Sequence[str]],
    diagnostics_by_arm: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Recompute descriptive A1 metrics from closed images and ranked source data."""
    metrics: dict[str, object] = {}
    score_by_hash = {
        entry.patch.identity.rgb_sha256: entry.flatness_span for entry in ranked
    }
    for arm in _A1_ARMS:
        retained = select_arm_patches(ranked, arm)
        retained_hashes = {patch.identity.rgb_sha256 for patch in retained}
        retained_entries = tuple(
            entry
            for entry in ranked
            if entry.patch.identity.rgb_sha256 in retained_hashes
        )
        rejected_entries = tuple(
            entry
            for entry in ranked
            if entry.patch.identity.rgb_sha256 not in retained_hashes
        )
        compositor_hashes = tuple(used_by_arm[arm])
        if not set(compositor_hashes).issubset(retained_hashes):
            raise ValueError("A1 metrics used patch hash differs from retained set")
        diagnostics = dict(diagnostics_by_arm[arm])
        placement_value = diagnostics.get("placement_patch_sha256", ())
        if not isinstance(placement_value, (list, tuple)) or not all(
            isinstance(digest, str) for digest in placement_value
        ):
            raise ValueError("A1 placement patch hashes are invalid")
        placement_hashes = tuple(placement_value)
        if arm != "b0" and not placement_hashes:
            raise ValueError("A1 filtered arm has no placement patch hashes")
        if not set(placement_hashes).issubset(retained_hashes):
            raise ValueError("A1 placement patch hash differs from retained set")
        used_entries = tuple(
            ScoredPatch(
                next(
                    entry.patch
                    for entry in ranked
                    if entry.patch.identity.rgb_sha256 == digest
                ),
                score_by_hash[digest],
            )
            for digest in placement_hashes
        )
        atlas = _load_png(
            root / f"arms/{arm}/atlas-dev-fold-0.png",
            "RGB",
            (512, 512),
        )
        render_gradients = []
        occupancy = []
        variation = []
        checker_difference = []
        for mesh_name in _A1_MESHES:
            for view_name in FORMAL_CAMERA_NAMES:
                mask = _load_png(
                    root / f"masks/{mesh_name}/{view_name}.png",
                    "L",
                    (512, 512),
                ) == 255
                rgb = _load_png(
                    root / f"renders/{arm}/{mesh_name}/{view_name}.png",
                    "RGB",
                    (512, 512),
                )
                checker = _load_png(
                    formal_root
                    / "renders"
                    / mesh_name
                    / "checker"
                    / f"{view_name}.png",
                    "RGB",
                    (512, 512),
                )
                render_gradients.append(_gradient_summary(rgb, mask))
                occupancy.append(float(mask.mean()))
                variation.append(float(np.std(rgb[mask])))
                checker_difference.append(
                    float(np.mean(np.any(rgb != checker, axis=2)[mask]))
                )
        metrics[arm] = {
            "retained_count": len(retained_entries),
            "rejected_count": len(rejected_entries),
            "cutoff_flatness_span": retained_entries[-1].flatness_span,
            "score_summary": {
                "retained": _score_summary(retained_entries),
                "rejected": _score_summary(rejected_entries),
                "used": _score_summary(used_entries),
            },
            "reuse_measurement_status": (
                "unmeasured" if arm == "b0" else "measured"
            ),
            "used_patch_statistics": reuse_statistics(placement_hashes),
            "quilting_diagnostics": diagnostics,
            "atlas_gradient": _atlas_gradient_metrics(atlas),
            "masked_render_gradient": {
                key: float(np.mean([item[key] for item in render_gradients]))
                for key in ("mean", "p95", "max")
            },
            "occupancy_mean": float(np.mean(occupancy)),
            "variation_mean": float(np.mean(variation)),
            "checker_difference_mean": float(np.mean(checker_difference)),
        }
    return metrics


def _validate_formal_input(formal_root: Path) -> dict[str, object]:
    """Require a passed R16A-v2 formal bundle before creating any A1 content."""
    formal = read_formal_bundle(formal_root)
    receipt = formal.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != FORMAL_STATUS:
        raise ValueError("A1 requires a passed R16A-v2 formal bundle")
    return formal


def _copy_b0_inputs(root: Path, formal_root: Path, frozen_s1_path: Path) -> None:
    """Copy frozen B0 atlas and native S1 renders byte-for-byte."""
    destination = root / "arms/b0/atlas-dev-fold-0.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(frozen_s1_path, destination)
    if _file_sha256(destination) != _file_sha256(frozen_s1_path):
        raise ValueError("A1 B0 atlas copy hash differs")
    for mesh_name in _A1_MESHES:
        for view_name in FORMAL_CAMERA_NAMES:
            source = formal_root / "renders" / mesh_name / "s1" / f"{view_name}.png"
            copied = root / "renders/b0" / mesh_name / f"{view_name}.png"
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copied)
            if copied.read_bytes() != source.read_bytes():
                raise ValueError("A1 B0 render copy bytes differ")
            mask_source = formal_root / "masks" / mesh_name / f"{view_name}.png"
            mask_destination = root / "masks" / mesh_name / f"{view_name}.png"
            mask_destination.parent.mkdir(parents=True, exist_ok=True)
            if not mask_destination.exists():
                shutil.copyfile(mask_source, mask_destination)


def _render_filtered_arm(
    root: Path,
    arm: str,
    atlas: np.ndarray,
    formal_root: Path,
    renderer: FilteredRenderer,
) -> None:
    """Render one filtered arm and require the saved R16A masks unchanged."""
    views = renderer(atlas, formal_root)
    if set(views) != set(_A1_MESHES):
        raise ValueError("A1 filtered renderer mesh set differs")
    for mesh_name in _A1_MESHES:
        mesh_views = views[mesh_name]
        if set(mesh_views) != set(FORMAL_CAMERA_NAMES):
            raise ValueError("A1 filtered renderer camera set differs")
        checker_views = {}
        for view_name in FORMAL_CAMERA_NAMES:
            mask = _load_png(
                root / "masks" / mesh_name / f"{view_name}.png",
                "L",
                (512, 512),
            )
            if not set(np.unique(mask)).issubset({0, 255}):
                raise ValueError("A1 saved mask is not binary")
            view = mesh_views[view_name]
            if not isinstance(view, RenderedView) or not np.array_equal(
                view.object_mask,
                mask == 255,
            ):
                raise ValueError("A1 filtered render mask differs from R16A-v2")
            _write_rgb_exclusive(
                root / "renders" / arm / mesh_name / f"{view_name}.png",
                view.rgb,
            )
            checker_views[view_name] = RenderedView(
                _load_png(
                    formal_root
                    / "renders"
                    / mesh_name
                    / "checker"
                    / f"{view_name}.png",
                    "RGB",
                    (512, 512),
                ),
                mask == 255,
            )
        validate_render_set(checker_views, dict(mesh_views))


def _write_closure(root: Path, receipt_fields: Mapping[str, object]) -> None:
    """Hash every A1 content file then write the exact manifest and receipt."""
    expected = _a1_content_paths()
    if _recursive_file_paths(root) != expected:
        raise ValueError("A1 bundle content tree differs before closure")
    manifest = {path: _file_sha256(root / path) for path in sorted(expected)}
    _write_json_exclusive(root / "artifact-hashes.json", manifest)
    receipt = dict(receipt_fields)
    receipt["artifact_hashes_sha256"] = _file_sha256(root / "artifact-hashes.json")
    _write_json_exclusive(root / "receipt.json", receipt)


def write_a1_bundle(
    output_root: Path,
    *,
    formal_root: Path,
    source_patches: Sequence[AcceptedPatch],
    frozen_s1_path: Path,
    source_common_receipt: Path,
    render_filtered: FilteredRenderer | None = None,
    available_memory_bytes: int = _MIN_AVAILABLE_MEMORY_BYTES,
    peak_process_tree_rss_bytes: int | Callable[[], int] = 0,
) -> dict[str, object]:
    """Write one no-clobber A1 bundle using only ranked source eligibility."""
    root = Path(output_root)
    if root.exists():
        raise FileExistsError("A1 output root already exists")
    if available_memory_bytes < _MIN_AVAILABLE_MEMORY_BYTES:
        raise MemoryError("A1 available memory is below the required ceiling")
    if not callable(peak_process_tree_rss_bytes):
        _resolve_peak_rss(peak_process_tree_rss_bytes)
    formal = _validate_formal_input(Path(formal_root))
    ranked = rank_patch_flatness(source_patches)
    if len(ranked) != ARM_PATCH_COUNTS["b0"]:
        raise ValueError("A1 source ranking must contain exactly 690 legal patches")
    frozen_s1 = Path(frozen_s1_path)
    if _load_png(frozen_s1, "RGB", (512, 512)).shape != (512, 512, 3):
        raise ValueError("A1 frozen S1 atlas differs")
    source_receipt = Path(source_common_receipt)
    if not source_receipt.is_file():
        raise ValueError("A1 source-common receipt is missing")

    root.mkdir(parents=True)
    _write_json_exclusive(
        root / "ranking/all-legal-patches.json",
        _ranking_payload(ranked),
    )
    _write_rgb_exclusive(
        root / "contact-sheets/flatness-ranked.png",
        _contact_sheet(ranked, "all", (518, 345, 173)),
    )
    selected: dict[str, tuple[AcceptedPatch, ...]] = {}
    arm_atlas_hashes: dict[str, str] = {}
    _copy_b0_inputs(root, Path(formal_root), frozen_s1)
    selected["b0"] = select_arm_patches(ranked, "b0")
    arm_atlas_hashes["b0"] = _file_sha256(root / "arms/b0/atlas-dev-fold-0.png")
    all_hashes = {entry.patch.identity.rgb_sha256 for entry in ranked}
    used_by_arm: dict[str, Sequence[str]] = {"b0": ()}
    diagnostics_by_arm: dict[str, Mapping[str, object]] = {"b0": {}}
    for arm in _A1_ARMS:
        retained = select_arm_patches(ranked, arm)
        selected[arm] = retained
        retained_hashes = {patch.identity.rgb_sha256 for patch in retained}
        retained_entries = tuple(
            entry
            for entry in ranked
            if entry.patch.identity.rgb_sha256 in retained_hashes
        )
        rejected_entries = tuple(
            entry
            for entry in ranked
            if entry.patch.identity.rgb_sha256 not in retained_hashes
        )
        _write_json_exclusive(
            root / f"ranking/{arm}-retained.json",
            _ranking_payload(retained_entries),
        )
        _write_json_exclusive(
            root / f"ranking/{arm}-rejected.json",
            _ranking_payload(rejected_entries),
        )
        if (
            {entry.patch.identity.rgb_sha256 for entry in retained_entries}
            != retained_hashes
        ):
            raise ValueError("A1 retained ranking identity differs")
        if arm != "b0":
            _write_rgb_exclusive(
                root / f"contact-sheets/{arm}-retained.png",
                _contact_sheet(retained_entries, f"{arm} retained"),
            )
            _write_rgb_exclusive(
                root / f"contact-sheets/{arm}-rejected.png",
                _contact_sheet(rejected_entries, f"{arm} rejected"),
            )
            atlas, used_hashes, diagnostics = quilt_atlas(retained, seed=_A1_SEED)
            if not set(used_hashes).issubset(retained_hashes):
                raise ValueError("A1 filtered quilt used an unretained patch")
            _write_rgb_exclusive(root / f"arms/{arm}/atlas-dev-fold-0.png", atlas)
            arm_atlas_hashes[arm] = _file_sha256(
                root / f"arms/{arm}/atlas-dev-fold-0.png"
            )
            if render_filtered is None:
                raise ValueError("A1 filtered renderer is required")
            _render_filtered_arm(root, arm, atlas, Path(formal_root), render_filtered)
            used_by_arm[arm] = tuple(used_hashes)
            diagnostics_by_arm[arm] = diagnostics
    if all_hashes != {entry.patch.identity.rgb_sha256 for entry in ranked}:
        raise ValueError("A1 source ranking hashes changed")
    blind_map = _blind_map()
    _write_rgb_exclusive(
        root / "comparison/blind-labeled.png",
        _blind_comparison(root, blind_map),
    )
    _write_json_exclusive(root / "comparison/blind-map.json", blind_map)
    _write_json_exclusive(
        root / "inputs.json",
        _inputs_payload(
            Path(formal_root),
            frozen_s1,
            source_receipt,
            formal["receipt"]["status"],
        ),
    )
    metrics = _descriptive_metrics(
        root,
        Path(formal_root),
        ranked,
        used_by_arm,
        diagnostics_by_arm,
    )
    _write_json_exclusive(root / "metrics.json", metrics)
    _write_json_exclusive(
        root / "validation.json",
        _validation_payload(blind_map),
    )
    _write_json_exclusive(
        root / "telemetry.json",
        _telemetry_payload(
            available_memory_bytes,
            _resolve_peak_rss(peak_process_tree_rss_bytes),
        ),
    )
    _write_closure(
        root,
        {
            "schema": A1_SCHEMA,
            "status": A1_STATUS,
            "formal_receipt_sha256": _file_sha256(Path(formal_root) / "receipt.json"),
            "source_common_receipt_sha256": _file_sha256(source_receipt),
            "frozen_s1_sha256": _file_sha256(frozen_s1),
            "inputs_sha256": _file_sha256(root / "inputs.json"),
            "arm_atlas_sha256": arm_atlas_hashes,
            "blind_map_sha256": _file_sha256(root / "comparison/blind-map.json"),
            "comparison_png_sha256": _file_sha256(
                root / "comparison/blind-labeled.png"
            ),
            "metrics_sha256": _file_sha256(root / "metrics.json"),
            "validation_sha256": _file_sha256(root / "validation.json"),
            "telemetry_sha256": _file_sha256(root / "telemetry.json"),
        },
    )
    return read_a1_bundle(
        root,
        formal_root=formal_root,
        source_patches=source_patches,
        frozen_s1_path=frozen_s1,
        source_common_receipt=source_receipt,
        render_filtered=render_filtered,
    )


def read_a1_bundle(
    root: Path,
    *,
    formal_root: Path,
    source_patches: Sequence[AcceptedPatch],
    frozen_s1_path: Path,
    source_common_receipt: Path,
    render_filtered: FilteredRenderer | None = None,
) -> dict[str, object]:
    """Read and strictly revalidate one closed A1 visual bundle."""
    bundle_root = Path(root)
    try:
        if not bundle_root.is_dir() or any(
            path.is_symlink() for path in bundle_root.rglob("*")
        ):
            raise ValueError("A1 bundle root or link contract differs")
        expected = _a1_content_paths() | {"artifact-hashes.json", "receipt.json"}
        if _recursive_file_paths(bundle_root) != expected:
            raise ValueError("A1 bundle recursive file tree differs")
        if _recursive_directory_paths(bundle_root) != _expected_directory_paths(
            _a1_content_paths()
        ):
            raise ValueError("A1 bundle recursive directory tree differs")
        manifest = json.loads(
            (bundle_root / "artifact-hashes.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (bundle_root / "receipt.json").read_text(encoding="utf-8")
        )
        if (
            set(manifest) != _a1_content_paths()
            or receipt.get("artifact_hashes_sha256")
            != _file_sha256(bundle_root / "artifact-hashes.json")
        ):
            raise ValueError("A1 bundle closure differs")
        if any(
            _file_sha256(bundle_root / path) != digest
            for path, digest in manifest.items()
        ):
            raise ValueError("A1 bundle content hash differs")
        if receipt.get("schema") != A1_SCHEMA or receipt.get("status") != A1_STATUS:
            raise ValueError("A1 bundle receipt differs")
        formal = _validate_formal_input(Path(formal_root))
        if receipt.get("formal_receipt_sha256") != _file_sha256(
            Path(formal_root) / "receipt.json"
        ):
            raise ValueError("A1 bundle formal receipt differs")
        if receipt.get("source_common_receipt_sha256") != _file_sha256(
            Path(source_common_receipt)
        ):
            raise ValueError("A1 bundle source receipt differs")
        if receipt.get("frozen_s1_sha256") != _file_sha256(Path(frozen_s1_path)):
            raise ValueError("A1 bundle frozen S1 differs")
        expected_receipt_fields = {
            "schema",
            "status",
            "formal_receipt_sha256",
            "source_common_receipt_sha256",
            "frozen_s1_sha256",
            "inputs_sha256",
            "arm_atlas_sha256",
            "blind_map_sha256",
            "comparison_png_sha256",
            "metrics_sha256",
            "validation_sha256",
            "telemetry_sha256",
            "artifact_hashes_sha256",
        }
        if set(receipt) != expected_receipt_fields:
            raise ValueError("A1 bundle receipt schema differs")
        bound_paths = {
            "inputs_sha256": "inputs.json",
            "blind_map_sha256": "comparison/blind-map.json",
            "comparison_png_sha256": "comparison/blind-labeled.png",
            "metrics_sha256": "metrics.json",
            "validation_sha256": "validation.json",
            "telemetry_sha256": "telemetry.json",
        }
        for field, relative_path in bound_paths.items():
            if receipt[field] != _file_sha256(bundle_root / relative_path):
                raise ValueError("A1 bundle receipt binding differs")
        expected_inputs = _inputs_payload(
            Path(formal_root),
            Path(frozen_s1_path),
            Path(source_common_receipt),
            formal["receipt"]["status"],
        )
        saved_inputs = json.loads(
            (bundle_root / "inputs.json").read_text(encoding="utf-8")
        )
        if saved_inputs != expected_inputs:
            raise ValueError("A1 bundle frozen input binding differs")
        blind_map = _blind_map()
        saved_blind_map = json.loads(
            (bundle_root / "comparison/blind-map.json").read_text(
                encoding="utf-8"
            )
        )
        if saved_blind_map != blind_map:
            raise ValueError("A1 bundle blind mapping differs")
        arm_hashes = receipt["arm_atlas_sha256"]
        if not isinstance(arm_hashes, dict) or set(arm_hashes) != set(_A1_ARMS):
            raise ValueError("A1 bundle arm-atlas receipt differs")
        for arm, digest in arm_hashes.items():
            if digest != _file_sha256(
                bundle_root / f"arms/{arm}/atlas-dev-fold-0.png"
            ):
                raise ValueError("A1 bundle arm-atlas receipt differs")
        ranked = rank_patch_flatness(source_patches)
        saved_ranking = json.loads(
            (bundle_root / "ranking/all-legal-patches.json").read_text(
                encoding="utf-8"
            )
        )
        if _ranking_payload(ranked) != saved_ranking:
            raise ValueError("A1 bundle saved ranking differs")
        ranked_sheet = _load_png(
            bundle_root / "contact-sheets/flatness-ranked.png",
            "RGB",
            (15 * 64, math.ceil(len(ranked) / 15) * 96),
        )
        if not np.array_equal(
            ranked_sheet,
            _contact_sheet(ranked, "all", (518, 345, 173)),
        ):
            raise ValueError("A1 bundle ranked contact sheet differs")
        used_by_arm: dict[str, Sequence[str]] = {"b0": ()}
        diagnostics_by_arm: dict[str, Mapping[str, object]] = {"b0": {}}
        for arm in _A1_ARMS:
            retained = select_arm_patches(ranked, arm)
            retained_hashes = {patch.identity.rgb_sha256 for patch in retained}
            retained_entries = tuple(
                entry
                for entry in ranked
                if entry.patch.identity.rgb_sha256 in retained_hashes
            )
            rejected_entries = tuple(
                entry
                for entry in ranked
                if entry.patch.identity.rgb_sha256 not in retained_hashes
            )
            for state, entries in (
                ("retained", retained_entries),
                ("rejected", rejected_entries),
            ):
                saved = json.loads(
                    (bundle_root / f"ranking/{arm}-{state}.json").read_text(
                        encoding="utf-8"
                    )
                )
                if saved != _ranking_payload(entries):
                    raise ValueError("A1 bundle saved arm ranking differs")
                if arm != "b0":
                    sheet = _load_png(
                        bundle_root / f"contact-sheets/{arm}-{state}.png",
                        "RGB",
                        (15 * 64, math.ceil(len(entries) / 15) * 96),
                    )
                    expected_sheet = _contact_sheet(entries, f"{arm} {state}")
                    if not np.array_equal(sheet, expected_sheet):
                        raise ValueError("A1 bundle filtered contact sheet differs")
            atlas_path = bundle_root / f"arms/{arm}/atlas-dev-fold-0.png"
            atlas = _load_png(atlas_path, "RGB", (512, 512))
            if float(np.std(atlas)) <= 0.0:
                raise ValueError("A1 bundle atlas is uniform")
            if arm == "b0":
                if atlas_path.read_bytes() != Path(frozen_s1_path).read_bytes():
                    raise ValueError("A1 bundle B0 atlas differs")
                for mesh_name in _A1_MESHES:
                    for view_name in FORMAL_CAMERA_NAMES:
                        saved_path = (
                            bundle_root
                            / f"renders/b0/{mesh_name}/{view_name}.png"
                        )
                        formal_path = (
                            Path(formal_root)
                            / "renders"
                            / mesh_name
                            / "s1"
                            / f"{view_name}.png"
                        )
                        if saved_path.read_bytes() != formal_path.read_bytes():
                            raise ValueError("A1 bundle B0 render differs")
            else:
                replay, used_hashes, diagnostics = quilt_atlas(
                    retained,
                    seed=_A1_SEED,
                )
                if not np.array_equal(atlas, replay):
                    raise ValueError("A1 bundle filtered atlas replay differs")
                used_by_arm[arm] = tuple(used_hashes)
                diagnostics_by_arm[arm] = diagnostics
                if render_filtered is not None:
                    expected_views = render_filtered(replay, Path(formal_root))
                    for mesh_name, views in expected_views.items():
                        for view_name, view in views.items():
                            saved_mask = _load_png(
                                bundle_root / f"masks/{mesh_name}/{view_name}.png",
                                "L",
                                (512, 512),
                            ) == 255
                            if not np.array_equal(view.object_mask, saved_mask):
                                raise ValueError(
                                    "A1 bundle filtered render mask differs"
                                )
                            saved_rgb = _load_png(
                                bundle_root
                                / f"renders/{arm}/{mesh_name}/{view_name}.png",
                                "RGB",
                                (512, 512),
                            )
                            if not np.array_equal(saved_rgb, view.rgb):
                                raise ValueError("A1 bundle filtered render differs")
        for mesh_name in _A1_MESHES:
            for view_name in FORMAL_CAMERA_NAMES:
                mask = _load_png(
                    bundle_root / f"masks/{mesh_name}/{view_name}.png",
                    "L",
                    (512, 512),
                )
                if not set(np.unique(mask)).issubset({0, 255}):
                    raise ValueError("A1 bundle mask is not binary")
                for arm in _A1_ARMS:
                    rgb = _load_png(
                        bundle_root / f"renders/{arm}/{mesh_name}/{view_name}.png",
                        "RGB",
                        (512, 512),
                    )
                    if float(np.std(rgb[mask == 255])) <= 0.0:
                        raise ValueError("A1 bundle render is blank")
        saved_metrics = json.loads(
            (bundle_root / "metrics.json").read_text(encoding="utf-8")
        )
        expected_metrics = _descriptive_metrics(
            bundle_root,
            Path(formal_root),
            ranked,
            used_by_arm,
            diagnostics_by_arm,
        )
        if saved_metrics != expected_metrics:
            raise ValueError("A1 bundle descriptive metrics differ")
        saved_comparison = _load_png(
            bundle_root / "comparison/blind-labeled.png",
            "RGB",
            (len(_A1_MESHES) * len(FORMAL_CAMERA_NAMES) * 512, 4 * 512),
        )
        if not np.array_equal(
            saved_comparison,
            _blind_comparison(bundle_root, blind_map),
        ):
            raise ValueError("A1 bundle blinded comparison differs")
        saved_validation = json.loads(
            (bundle_root / "validation.json").read_text(encoding="utf-8")
        )
        if saved_validation != _validation_payload(blind_map):
            raise ValueError("A1 bundle validation gates differ")
        telemetry = json.loads(
            (bundle_root / "telemetry.json").read_text(encoding="utf-8")
        )
        telemetry_keys = {
            "schema",
            "available_memory_bytes_before",
            "measurement_scope",
            "peak_process_tree_rss_bytes",
            "rss_limit_bytes",
            "sample_interval_seconds",
            "within_limit",
            "worker_count",
        }
        peak_rss = telemetry.get("peak_process_tree_rss_bytes")
        available_memory = telemetry.get("available_memory_bytes_before")
        if (
            set(telemetry) != telemetry_keys
            or telemetry.get("schema") != _A1_TELEMETRY_SCHEMA
            or telemetry.get("measurement_scope")
            != "through_bundle_generation_before_readback"
            or not isinstance(available_memory, int)
            or isinstance(available_memory, bool)
            or available_memory < _MIN_AVAILABLE_MEMORY_BYTES
            or not isinstance(peak_rss, int)
            or isinstance(peak_rss, bool)
            or not 0 <= peak_rss < _MAX_PROCESS_TREE_RSS_BYTES
            or telemetry.get("rss_limit_bytes") != _MAX_PROCESS_TREE_RSS_BYTES
            or telemetry.get("sample_interval_seconds") != 0.05
            or telemetry.get("within_limit") is not True
            or telemetry.get("worker_count") != 1
        ):
            raise ValueError("A1 bundle telemetry resource policy differs")
        return {"receipt": receipt, "artifact_hashes": manifest}
    except (KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("A1 bundle"):
            raise
        raise ValueError("A1 bundle validation failed") from error
