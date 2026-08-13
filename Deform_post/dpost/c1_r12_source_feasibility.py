"""Geometry primitives for the R12 source-v2 feasibility check."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from dpost import c1_r12_source as source


@dataclass(frozen=True)
class PatchGeometry:
    """A source-v2 candidate patch grid definition."""

    arm_id: str
    size: int
    stride: int


@dataclass(frozen=True)
class CoveragePosition:
    """Coverage counts for one candidate patch position."""

    y: int
    x: int
    accepted_frame_count: int
    candidate_frame_count: int
    outside_circle_count: int
    masked_count: int


PATCH_GEOMETRIES = (
    PatchGeometry("p64-s32", 64, 32),
    PatchGeometry("p96-s32", 96, 32),
)
_FOLDS = tuple(f"dev-fold-{index}" for index in range(4))
MONTAGE_ROWS = (
    ("dev-fold-0", 96, "seq13", "deformed_s0521_v0000"),
    ("dev-fold-0", 180, "seq23", "deformed_s0521_v0000"),
    ("dev-fold-0", 275, "seq31", "deformed_s0521_v0011"),
    ("dev-fold-1", 0, "seq01", "deformed_s0521_v0000"),
    ("dev-fold-1", 72, "seq10", "deformed_s0521_v0000"),
    ("dev-fold-1", 203, "seq24", "deformed_s0521_v0011"),
    ("dev-fold-2", 12, "seq02", "deformed_s0521_v0000"),
    ("dev-fold-2", 204, "seq25", "deformed_s0521_v0000"),
    ("dev-fold-2", 239, "seq27", "deformed_s0521_v0011"),
    ("dev-fold-3", 24, "seq03", "deformed_s0521_v0000"),
    ("dev-fold-3", 144, "seq17", "deformed_s0521_v0000"),
    ("dev-fold-3", 287, "seq32", "deformed_s0521_v0011"),
)
SPLIT_MANIFEST_SHA256 = (
    "5ad2ac3e015c29595f697589a61e196435315dc9be75fb0a6a6aa0762fe65bb7"
)
SOURCE_V1_REGISTRY_SHA256 = (
    "a85ce998505dc2d51fe145eaa36e79f997cca24cde29b01b5ed7ebd8a0965a6d"
)
DIAGNOSTIC_RECEIPT_SHA256 = (
    "813ca25136c475fa17e29d7143a2c6d35073cf0e5b76d0c7be2f3314057260e9"
)
DEFAULT_ANCHOR_PATH = Path(
    r"D:\MedSim2Learn-C1-verification\r2-pbr\g1-rerun3\preflight-v1"
    r"\real-frames.npz"
)
DEFAULT_RECEIPT_PATH = DEFAULT_ANCHOR_PATH.with_name("g1-preflight-v1.json")
DEFAULT_SOURCE_V1_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r12-texture-pbr\source-registry-v1"
)
DEFAULT_DIAGNOSTIC_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r12-texture-pbr"
    r"\source-registry-v1-diagnostic"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r12-texture-pbr\source-feasibility-v2"
)
DEFAULT_STAGING_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r12-texture-pbr"
    r"\source-feasibility-v2-attempt-v1"
)
_SPEC_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/data_improve/2026-08-03-c1-r12-source-v2-feasibility-spec.md"
)
_CLI_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts/run_c1_r12_source_feasibility.py"
)
_CONTROLLED_ENVIRONMENT_KEYS = (
    "PYTHONDONTWRITEBYTECODE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


@dataclass(frozen=True)
class ArmSummary:
    """Aggregate coverage and fold availability for one geometry arm."""

    geometry: PatchGeometry
    available_patch_count: Mapping[str, int]
    crossfit_available_patch_count: Mapping[str, int]
    rejection_totals: Mapping[str, int]
    coverage_positions: Mapping[str, tuple[CoveragePosition, ...]]


@dataclass(frozen=True)
class MontageArmOverlay:
    """The row-major state overlay for one montage arm."""

    arm_id: str
    position_states: tuple[tuple[int, int, str], ...]


@dataclass(frozen=True)
class MontagePanel:
    """One retained RGB frame and its two feasibility overlays."""

    fold: str
    frame_index: int
    sequence_id: str
    frame_id: str
    rgb: np.ndarray
    arm_overlays: tuple[MontageArmOverlay, MontageArmOverlay]


@dataclass(frozen=True)
class FeasibilityResult:
    """Hold the preregistered source-feasibility decision."""

    arms: tuple[ArmSummary, ArmSummary]
    status: str
    winner: str | None
    comparison_keys: Mapping[str, tuple[int, int, int]]
    montage_panels: tuple[MontagePanel, ...] = ()


@dataclass(frozen=True)
class SourceFeasibilityProvenance:
    """Bind the source-v2 aggregation to its immutable source inputs."""

    spec_path: str
    spec_sha256: str
    source_v2_module_path: str
    source_v2_module_sha256: str
    cli_script_path: str
    cli_script_sha256: str
    source_v1_module_path: str
    source_v1_module_sha256: str
    anchor_path: str
    anchor_sha256: str
    receipt_path: str
    receipt_sha256: str
    split_manifest_path: str
    split_manifest_sha256: str
    source_v1_registry_path: str
    source_v1_registry_sha256: str
    diagnostic_receipt_path: str
    diagnostic_receipt_sha256: str
    python_version: str
    opencv_version: str
    thread_environment: Mapping[str, str]
    action: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class SourceFeasibilityBundle:
    """Pair a feasibility result with its validated input provenance."""

    result: FeasibilityResult
    provenance: SourceFeasibilityProvenance


def _configure_cpu_only() -> None:
    """Disable OpenCV parallel and OpenCL execution for a build process."""
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)


def _validated_thread_environment() -> dict[str, str]:
    """Return the five required CPU-only environment values."""
    environment = {
        key: os.environ.get(key, "")
        for key in _CONTROLLED_ENVIRONMENT_KEYS
    }
    for key, value in environment.items():
        if value != "1":
            raise ValueError(f"controlled environment {key} must equal '1'")
    return environment


def candidate_positions(geometry: PatchGeometry) -> tuple[tuple[int, int], ...]:
    """Return row-major candidate top-left positions for one patch geometry."""
    return tuple(
        (y, x)
        for y in range(0, 256 - geometry.size + 1, geometry.stride)
        for x in range(0, 256 - geometry.size + 1, geometry.stride)
    )


def patch_is_inside_circle(y: int, x: int, size: int) -> bool:
    """Return whether every inclusive patch corner lies in the source circle."""
    return all(
        source._point_is_inside_circle(corner_y, corner_x)
        for corner_y, corner_x in (
            (y, x),
            (y, x + size - 1),
            (y + size - 1, x),
            (y + size - 1, x + size - 1),
        )
    )


def _held_out_crossfit_counts(
    available_patch_count: Mapping[str, int],
) -> dict[str, int]:
    """Return each held-out fold's availability from the other folds."""
    total = sum(available_patch_count[fold] for fold in _FOLDS)
    return {
        fold: total - available_patch_count[fold]
        for fold in _FOLDS
    }


def _load_json(path: Path) -> object:
    """Read one UTF-8 JSON identity artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_inputs_before_pixels(
    anchor_path: Path,
    receipt_path: Path,
    source_v1_root: Path,
    diagnostic_root: Path,
    thread_environment: Mapping[str, str],
) -> tuple[tuple[tuple[str, str], ...], SourceFeasibilityProvenance]:
    """Validate frozen identity artifacts before opening the anchor pixels."""
    if source._sha256(anchor_path) != source.ANCHOR_SHA256:
        raise ValueError("anchor SHA-256 differs from the frozen anchor")
    receipt = source._load_receipt(receipt_path)
    split_manifest_path = source._MANIFEST_PATH
    split_manifest_sha256 = source._sha256(split_manifest_path)
    if split_manifest_sha256 != SPLIT_MANIFEST_SHA256:
        raise ValueError("split manifest SHA-256 does not match")
    fold_map = source._load_fold_map()
    positions = source._validate_positions(
        receipt.get("position_records"),
        fold_map,
    )
    decision = _load_json(source_v1_root / "decision.json")
    registry_path = source_v1_root / "registry.json"
    registry = _load_json(registry_path)
    registry_sha256 = _load_json(source_v1_root / "registry-sha256.json")
    input_hashes = _load_json(source_v1_root / "input-hashes.json")
    diagnostic_path = diagnostic_root / "receipt.json"
    diagnostic = _load_json(diagnostic_path)
    if not isinstance(decision, dict) or decision.get("status") != (
        "INVALID_SOURCE_INPUT"
    ):
        raise ValueError("source-v1 decision is not the frozen invalid result")
    if not isinstance(registry, dict) or registry.get("anchor_sha256") != (
        source.ANCHOR_SHA256
    ):
        raise ValueError("source-v1 registry anchor does not match")
    if registry.get("records") != [] or registry.get("rejection_counts") != {
        "masked": 288,
        "outside_circle": 2304,
    }:
        raise ValueError(
            "source-v1 registry does not match frozen rejection counts"
        )
    if source._sha256(registry_path) != SOURCE_V1_REGISTRY_SHA256:
        raise ValueError("source-v1 registry SHA-256 does not match")
    if (
        not isinstance(registry_sha256, dict)
        or registry_sha256.get("sha256") != SOURCE_V1_REGISTRY_SHA256
    ):
        raise ValueError("source-v1 registry receipt does not match")
    expected_input_hashes = {
        "anchor_sha256": source.ANCHOR_SHA256,
        "receipt_sha256": source.RECEIPT_SHA256,
        "split_manifest_sha256": SPLIT_MANIFEST_SHA256,
    }
    if input_hashes != expected_input_hashes:
        raise ValueError("source-v1 input hashes do not match")
    if source._sha256(diagnostic_path) != DIAGNOSTIC_RECEIPT_SHA256:
        raise ValueError("source-v1 diagnostic receipt SHA-256 does not match")
    if not isinstance(diagnostic, dict):
        raise ValueError("source-v1 diagnostic receipt is malformed")
    comparison = diagnostic.get("comparison")
    if diagnostic.get("status") != "DONE_WITH_CONCERNS" or not isinstance(
        comparison,
        dict,
    ):
        raise ValueError("source-v1 diagnostic receipt does not match")
    if comparison.get("accepted_record_match") is not True:
        raise ValueError(
            "source-v1 diagnostic accepted-record comparison failed"
        )
    if comparison.get("aggregate_match") is not True:
        raise ValueError("source-v1 diagnostic aggregate comparison failed")
    if comparison.get("production_record_count") != 0:
        raise ValueError("source-v1 diagnostic production record count changed")
    if comparison.get("production_registry_sha256") != (
        SOURCE_V1_REGISTRY_SHA256
    ):
        raise ValueError("source-v1 diagnostic registry SHA-256 changed")
    return positions, SourceFeasibilityProvenance(
        spec_path=str(_SPEC_PATH),
        spec_sha256=_sha256(_SPEC_PATH),
        source_v2_module_path=str(Path(__file__).resolve()),
        source_v2_module_sha256=_sha256(Path(__file__).resolve()),
        cli_script_path=str(_CLI_SCRIPT_PATH),
        cli_script_sha256=_sha256(_CLI_SCRIPT_PATH),
        source_v1_module_path=str(Path(source.__file__).resolve()),
        source_v1_module_sha256=_sha256(Path(source.__file__).resolve()),
        anchor_path=str(anchor_path),
        anchor_sha256=source.ANCHOR_SHA256,
        receipt_path=str(receipt_path),
        receipt_sha256=source.RECEIPT_SHA256,
        split_manifest_path=str(split_manifest_path),
        split_manifest_sha256=split_manifest_sha256,
        source_v1_registry_path=str(registry_path),
        source_v1_registry_sha256=SOURCE_V1_REGISTRY_SHA256,
        diagnostic_receipt_path=str(diagnostic_path),
        diagnostic_receipt_sha256=DIAGNOSTIC_RECEIPT_SHA256,
        python_version=platform.python_version(),
        opencv_version=cv2.__version__,
        thread_environment=dict(thread_environment),
        action="source-feasibility",
        argv=("source-feasibility",),
    )


def _new_counters() -> dict[str, dict[str, dict[tuple[int, int], list[int]]]]:
    """Allocate integer counters for every geometry, fold, and position."""
    return {
        geometry.arm_id: {
            fold: {
                position: [0, 0, 0, 0]
                for position in candidate_positions(geometry)
            }
            for fold in _FOLDS
        }
        for geometry in PATCH_GEOMETRIES
    }


def _update_counters_for_frame(
    mask: np.ndarray,
    fold: str,
    counters: dict[str, dict[str, dict[tuple[int, int], list[int]]]],
) -> None:
    """Classify every candidate position for one frame using one mask."""
    for geometry in PATCH_GEOMETRIES:
        positions = counters[geometry.arm_id][fold]
        for (y, x), counts in positions.items():
            state = _position_state(mask, y, x, geometry)
            if state == "outside_circle":
                counts[2] += 1
            elif state == "masked":
                counts[1] += 1
                counts[3] += 1
            else:
                counts[1] += 1
                counts[0] += 1


def _position_state(
    mask: np.ndarray,
    y: int,
    x: int,
    geometry: PatchGeometry,
) -> str:
    """Return one circle-first position classification."""
    if not patch_is_inside_circle(y, x, geometry.size):
        return "outside_circle"
    if mask[y:y + geometry.size, x:x + geometry.size].any():
        return "masked"
    return "accepted"


def _montage_overlays(
    mask: np.ndarray,
) -> tuple[MontageArmOverlay, MontageArmOverlay]:
    """Capture both row-major overlay states from one frame mask."""
    overlays = tuple(
        MontageArmOverlay(
            geometry.arm_id,
            tuple(
                (y, x, _position_state(mask, y, x, geometry))
                for y, x in candidate_positions(geometry)
            ),
        )
        for geometry in PATCH_GEOMETRIES
    )
    return overlays[0], overlays[1]


def _arm_summary_from_counters(
    geometry: PatchGeometry,
    counters: Mapping[str, Mapping[tuple[int, int], list[int]]],
) -> ArmSummary:
    """Convert mutable per-frame counters to immutable row-major coverage."""
    coverage_positions = {
        fold: tuple(
            CoveragePosition(y, x, *counters[fold][(y, x)])
            for y, x in candidate_positions(geometry)
        )
        for fold in _FOLDS
    }
    available = {
        fold: sum(
            position.accepted_frame_count
            for position in coverage_positions[fold]
        )
        for fold in _FOLDS
    }
    return ArmSummary(
        geometry=geometry,
        available_patch_count=available,
        crossfit_available_patch_count=_held_out_crossfit_counts(available),
        rejection_totals={
            "outside_circle": sum(
                position.outside_circle_count
                for positions in coverage_positions.values()
                for position in positions
            ),
            "masked": sum(
                position.masked_count
                for positions in coverage_positions.values()
                for position in positions
            ),
        },
        coverage_positions=coverage_positions,
    )


def decide_feasibility(arms: Sequence[ArmSummary]) -> FeasibilityResult:
    """Apply the preregistered eligibility and lexicographic winner rule."""
    arm_pair = tuple(arms)
    if len(arm_pair) != 2:
        raise ValueError(
            "source feasibility requires exactly two geometry arms"
        )
    comparison_keys = {
        arm.geometry.arm_id: (
            min(arm.available_patch_count[fold] for fold in _FOLDS),
            sum(arm.available_patch_count[fold] for fold in _FOLDS),
            -arm.geometry.size,
        )
        for arm in arm_pair
    }
    eligible = tuple(
        arm
        for arm in arm_pair
        if all(arm.available_patch_count[fold] >= 1 for fold in _FOLDS)
    )
    if not eligible:
        return FeasibilityResult(
            arms=(arm_pair[0], arm_pair[1]),
            status="BLOCKED_SOURCE_FEASIBILITY",
            winner=None,
            comparison_keys=comparison_keys,
        )
    winner = max(eligible, key=lambda arm: comparison_keys[arm.geometry.arm_id])
    return FeasibilityResult(
        arms=(arm_pair[0], arm_pair[1]),
        status="PASS_SOURCE_FEASIBILITY_EXPLORATORY",
        winner=winner.geometry.arm_id,
        comparison_keys=comparison_keys,
    )


def build_source_feasibility(
    anchor_path: Path = DEFAULT_ANCHOR_PATH,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    *,
    source_v1_root: Path = DEFAULT_SOURCE_V1_ROOT,
    diagnostic_root: Path = DEFAULT_DIAGNOSTIC_ROOT,
) -> SourceFeasibilityBundle:
    """Validate inputs and aggregate both geometry arms in one frame pass."""
    anchor_path = Path(anchor_path)
    receipt_path = Path(receipt_path)
    source_v1_root = Path(source_v1_root)
    diagnostic_root = Path(diagnostic_root)
    _configure_cpu_only()
    thread_environment = _validated_thread_environment()
    positions, provenance = _validate_inputs_before_pixels(
        anchor_path,
        receipt_path,
        source_v1_root,
        diagnostic_root,
        thread_environment,
    )
    fold_map = source._load_fold_map()
    counters = _new_counters()
    expected_panels = {
        frame_index: (fold, sequence_id, frame_id)
        for fold, frame_index, sequence_id, frame_id in MONTAGE_ROWS
    }
    panels_by_index: dict[int, MontagePanel] = {}
    with np.load(anchor_path, allow_pickle=False) as anchor:
        if set(anchor.files) != {"real_frames"}:
            raise ValueError("anchor has unexpected arrays")
        frames = anchor["real_frames"]
        if frames.shape != (288, 256, 256, 3) or frames.dtype != np.uint8:
            raise ValueError(
                "anchor frame array does not match the frozen shape"
            )
        for frame_index, (sequence_id, frame_id) in enumerate(positions):
            mask, _ = source._build_exclusion_mask(frames[frame_index])
            fold = fold_map[sequence_id]
            _update_counters_for_frame(mask, fold, counters)
            expected = expected_panels.get(frame_index)
            if expected is not None:
                if expected != (fold, sequence_id, frame_id):
                    raise ValueError(
                        "montage row does not match frozen identity"
                    )
                panels_by_index[frame_index] = MontagePanel(
                    fold=fold,
                    frame_index=frame_index,
                    sequence_id=sequence_id,
                    frame_id=frame_id,
                    rgb=frames[frame_index].copy(),
                    arm_overlays=_montage_overlays(mask),
                )
    arms = tuple(
        _arm_summary_from_counters(geometry, counters[geometry.arm_id])
        for geometry in PATCH_GEOMETRIES
    )
    decision = decide_feasibility(arms)
    panels = tuple(
        panels_by_index[frame_index]
        for _, frame_index, _, _ in MONTAGE_ROWS
    )
    if tuple(
        (panel.fold, panel.frame_index, panel.sequence_id, panel.frame_id)
        for panel in panels
    ) != MONTAGE_ROWS:
        raise ValueError("retained montage panels do not match frozen rows")
    result = FeasibilityResult(
        arms=decision.arms,
        status=decision.status,
        winner=decision.winner,
        comparison_keys=decision.comparison_keys,
        montage_panels=panels,
    )
    return SourceFeasibilityBundle(result=result, provenance=provenance)


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one written artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    """Write stable UTF-8 JSON inside a staging root."""
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_publish_roots(output_root: Path, staging_root: Path) -> None:
    """Reject non-sibling, cross-drive, or pre-existing publish roots."""
    if output_root.drive != staging_root.drive:
        raise ValueError("publish roots must use the same drive")
    if output_root.parent != staging_root.parent:
        raise ValueError("publish roots must be siblings")
    if output_root.exists() or staging_root.exists():
        raise FileExistsError("publish root already exists")


def _arm_summary_value(arm: ArmSummary) -> dict[str, object]:
    """Serialize one arm without retaining source pixels or masks."""
    return {
        "arm_id": arm.geometry.arm_id,
        "size": arm.geometry.size,
        "stride": arm.geometry.stride,
        "available_patch_count": dict(arm.available_patch_count),
        "crossfit_available_patch_count": dict(
            arm.crossfit_available_patch_count
        ),
        "rejection_totals": dict(arm.rejection_totals),
        "coverage_positions": {
            fold: [asdict(position) for position in positions]
            for fold, positions in arm.coverage_positions.items()
        },
    }


def _write_montage(
    path: Path,
    panels: Sequence[MontagePanel],
    arm_index: int,
) -> None:
    """Render deterministic panel order from retained frames and overlays."""
    panel_size = 128
    canvas = np.zeros((panel_size * 3, panel_size * 4, 3), dtype=np.uint8)
    colors = {
        "outside_circle": (255, 0, 0),
        "masked": (0, 0, 255),
        "accepted": (0, 255, 0),
    }
    geometry = PATCH_GEOMETRIES[arm_index]
    for index, panel in enumerate(panels):
        row, column = divmod(index, 4)
        image = cv2.resize(panel.rgb, (panel_size, panel_size))
        overlay = panel.arm_overlays[arm_index]
        scale = panel_size / 256
        for y, x, state in overlay.position_states:
            color = colors[state]
            top_left = (round(x * scale), round(y * scale))
            bottom_right = (
                round((x + geometry.size) * scale),
                round((y + geometry.size) * scale),
            )
            cv2.rectangle(image, top_left, bottom_right, color, 1)
        cv2.putText(
            image,
            str(panel.frame_index),
            (3, 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        canvas[
            row * panel_size:(row + 1) * panel_size,
            column * panel_size:(column + 1) * panel_size,
        ] = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), canvas):
        raise OSError(f"could not write montage: {path}")


def write_source_feasibility(
    bundle: SourceFeasibilityBundle,
    *,
    output_root: Path,
    staging_root: Path,
) -> str:
    """Publish verified feasibility content from a complete in-memory bundle."""
    resolved_output = Path(output_root).resolve()
    resolved_staging = Path(staging_root).resolve()
    _validate_publish_roots(resolved_output, resolved_staging)
    panel_rows = tuple(
        (panel.fold, panel.frame_index, panel.sequence_id, panel.frame_id)
        for panel in bundle.result.montage_panels
    )
    if panel_rows != MONTAGE_ROWS:
        raise ValueError(
            "bundle montage panels do not match frozen montage rows"
        )
    resolved_staging.mkdir()
    content_paths: dict[str, Path] = {}
    try:
        result = bundle.result
        _write_json(
            resolved_staging / "decision.json",
            {
                "status": result.status,
                "winner": result.winner,
                "comparison_keys": dict(result.comparison_keys),
            },
        )
        content_paths["decision.json"] = resolved_staging / "decision.json"
        for arm_index, arm in enumerate(result.arms):
            arm_root = resolved_staging / arm.geometry.arm_id
            arm_root.mkdir()
            summary_path = arm_root / "summary.json"
            montage_path = arm_root / "coverage-montage.png"
            _write_json(summary_path, _arm_summary_value(arm))
            _write_montage(montage_path, result.montage_panels, arm_index)
            content_paths[f"{arm.geometry.arm_id}/summary.json"] = summary_path
            content_paths[
                f"{arm.geometry.arm_id}/coverage-montage.png"
            ] = montage_path
        hashes = {
            relative_path: _sha256(path)
            for relative_path, path in sorted(content_paths.items())
        }
        manifest_path = resolved_staging / "artifact-hashes.json"
        _write_json(manifest_path, hashes)
        receipt_path = resolved_staging / "receipt.json"
        _write_json(
            receipt_path,
            {
                "status": result.status,
                "winner": result.winner,
                "provenance": asdict(bundle.provenance),
                "artifact_hashes_sha256": _sha256(manifest_path),
            },
        )
        if any(
            _sha256(resolved_staging / key) != value
            for key, value in hashes.items()
        ):
            raise OSError("content artifact hash self-check failed")
        if _sha256(manifest_path) != json.loads(
            receipt_path.read_text(encoding="utf-8")
        )["artifact_hashes_sha256"]:
            raise OSError("manifest hash self-check failed")
        resolved_staging.rename(resolved_output)
    except Exception:
        raise
    return bundle.result.status


def main(argv: Sequence[str] | None = None) -> int:
    """Run the only source-feasibility publish action."""
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments != ("source-feasibility",):
        return 2
    if DEFAULT_OUTPUT_ROOT.exists() or DEFAULT_STAGING_ROOT.exists():
        return 3
    try:
        bundle = build_source_feasibility()
    except ValueError:
        return 2
    except OSError:
        return 3
    try:
        write_source_feasibility(
            bundle,
            output_root=DEFAULT_OUTPUT_ROOT,
            staging_root=DEFAULT_STAGING_ROOT,
        )
    except Exception:
        return 3
    return 0
