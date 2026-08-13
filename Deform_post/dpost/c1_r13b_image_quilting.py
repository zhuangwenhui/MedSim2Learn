"""Synthesize deterministic cross-fit atlases with image quilting."""

from __future__ import annotations

import os

for _key in (
    "PYTHONDONTWRITEBYTECODE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_key] = "1"

import hashlib
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dpost.c1_r13_artifacts import (
    EXPECTED_CROSSFIT_COUNTS,
    AtlasCandidate,
    MethodBundle,
    read_method_bundle,
)
from dpost.c1_r13_source import (
    AcceptedPatch,
    FOLDS,
    SourceCorpus,
    patches_for_held_out_fold,
)


_CANDIDATE_TOLERANCE = 1.10
_BLOCK_SIZE = 64
_OVERLAP = 16
_METHOD_ID = "quilting-v1"
_POSITIONS = tuple(range(0, 481, _BLOCK_SIZE - _OVERLAP))
_PLACEMENT_COUNT = len(_POSITIONS) ** 2
_EXPECTED_SEEDS = tuple(
    int.from_bytes(
        hashlib.sha256(f"{_METHOD_ID}:{fold}".encode("utf-8")).digest()[:8],
        "big",
    )
    for fold in FOLDS
)
_EXPECTED_BUNDLE_FILES = {
    "artifact-hashes.json",
    *(f"atlas-{fold}.png" for fold in FOLDS),
    "candidate-metadata.json",
    "method-sheet.png",
    "provenance.json",
    "receipt.json",
    "source-contact-sheet.png",
    "source-selection.json",
}


def minimum_error_boundary(cost: np.ndarray) -> np.ndarray:
    """Return the deterministic boolean keep-new side of one minimum cut."""
    values = np.asarray(cost, dtype=np.float64)
    if (
        values.ndim != 2
        or 0 in values.shape
        or not np.all(np.isfinite(values))
        or np.any(values < 0.0)
    ):
        raise ValueError("boundary cost must be finite nonnegative 2D data")

    # Each row stores the cheapest cumulative path ending at that column.
    cumulative = values.copy()
    predecessor = np.zeros(values.shape, dtype=np.intp)
    column_count = values.shape[1]
    for row in range(1, values.shape[0]):
        for column in range(column_count):
            first = max(0, column - 1)
            stop = min(column_count, column + 2)
            previous = cumulative[row - 1, first:stop]
            # np.argmin supplies a stable lowest-column tie break.
            parent = first + int(np.argmin(previous))
            predecessor[row, column] = parent
            cumulative[row, column] += cumulative[row - 1, parent]

    seam = np.empty(values.shape[0], dtype=np.intp)
    seam[-1] = int(np.argmin(cumulative[-1]))
    for row in range(values.shape[0] - 1, 0, -1):
        seam[row - 1] = predecessor[row, seam[row]]
    columns = np.arange(column_count, dtype=np.intp)
    return columns[np.newaxis, :] >= seam[:, np.newaxis]


def _eligible_candidate_indices(errors: np.ndarray) -> np.ndarray:
    """Return the exact tolerance-set indices for one placement."""
    values = np.asarray(errors, dtype=np.float64)
    if (
        values.ndim != 1
        or values.size == 0
        or not np.all(np.isfinite(values))
        or np.any(values < 0.0)
    ):
        raise ValueError("candidate errors must be finite and nonnegative")
    minimum = float(np.min(values))
    if minimum == 0.0:
        return np.flatnonzero(values == 0.0)
    return np.flatnonzero(values <= _CANDIDATE_TOLERANCE * minimum)


def _placement_positions(
    size: int,
    block_size: int,
    overlap: int,
) -> tuple[int, ...]:
    """Return stride-spaced origins, cropping only the final edge block."""
    if (
        not isinstance(size, int)
        or not isinstance(block_size, int)
        or not isinstance(overlap, int)
        or size < block_size
        or not 0 < overlap < block_size
    ):
        raise ValueError("quilting geometry is invalid")
    stride = block_size - overlap
    positions = [0]
    while positions[-1] + block_size < size:
        positions.append(positions[-1] + stride)
    return tuple(positions)


def _combined_boundary_mask(
    left_cost: np.ndarray | None,
    top_cost: np.ndarray | None,
    block_shape: tuple[int, int],
) -> np.ndarray:
    """Combine left and top cuts by intersecting keep-new corner sides."""
    height, width = block_shape
    if height <= 0 or width <= 0:
        raise ValueError("block shape must be positive")
    keep_new = np.ones((height, width), dtype=bool)
    if left_cost is not None:
        left_values = np.asarray(left_cost)
        if left_values.shape[0] != height or left_values.shape[1] > width:
            raise ValueError("left boundary cost shape differs")
        left_keep = minimum_error_boundary(left_values)
        keep_new[:, :left_values.shape[1]] &= left_keep
    if top_cost is not None:
        top_values = np.asarray(top_cost)
        if top_values.shape[1] != width or top_values.shape[0] > height:
            raise ValueError("top boundary cost shape differs")
        top_keep = minimum_error_boundary(top_values.T).T
        keep_new[:top_values.shape[0], :] &= top_keep
    return keep_new


def _validate_patches(
    patches: Sequence[AcceptedPatch],
) -> tuple[AcceptedPatch, ...]:
    """Validate exact accepted-patch pixels and their SHA identities."""
    accepted = tuple(patches)
    if not accepted:
        raise ValueError("quilting requires at least one accepted patch")
    for patch in accepted:
        if not isinstance(patch, AcceptedPatch):
            raise ValueError("quilting input is not an accepted patch")
        if patch.rgb.shape != (64, 64, 3) or patch.rgb.dtype != np.uint8:
            raise ValueError("accepted patch must be uint8 64x64 RGB")
        if patch.identity.source_fold not in FOLDS:
            raise ValueError("accepted patch source fold is not frozen")
        digest = hashlib.sha256(patch.rgb.tobytes()).hexdigest()
        if digest != patch.identity.rgb_sha256:
            raise ValueError(
                "accepted patch RGB SHA-256 does not match pixels"
            )
    return accepted


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 sRGB values to float32 linear RGB."""
    normalized = rgb.astype(np.float32) / np.float32(255.0)
    return np.where(
        normalized <= np.float32(0.04045),
        normalized / np.float32(12.92),
        ((normalized + np.float32(0.055)) / np.float32(1.055))
        ** np.float32(2.4),
    ).astype(np.float32, copy=False)


def _boundary_energy(cost: np.ndarray, keep_new: np.ndarray) -> float:
    """Return the literal energy along a computed vertical boundary."""
    seam_columns = np.argmax(keep_new, axis=1)
    rows = np.arange(cost.shape[0], dtype=np.intp)
    return float(np.sum(cost[rows, seam_columns], dtype=np.float64))


def _candidate_overlap_errors(
    reference: np.ndarray,
    candidates: np.ndarray,
    *,
    left_width: int,
    top_height: int,
) -> np.ndarray:
    """Return weighted overlap errors with the corner counted in the top."""
    left_difference = (
        candidates[:, top_height:, :left_width]
        - reference[top_height:, :left_width]
    )
    top_difference = candidates[:, :top_height] - reference[:top_height]
    left_error = np.sum(
        left_difference * left_difference,
        axis=(1, 2, 3),
        dtype=np.float64,
    )
    top_error = np.sum(
        top_difference * top_difference,
        axis=(1, 2, 3),
        dtype=np.float64,
    )
    return left_error + np.float64(4.0) * top_error


def _validate_used_patch_isolation(
    patches: Sequence[AcceptedPatch],
    used_patch_sha256: Sequence[str],
    held_out_fold: str,
) -> None:
    """Reject unknown used hashes and any held-out source membership."""
    if held_out_fold not in FOLDS:
        raise ValueError("held-out fold is not frozen")
    by_hash: dict[str, set[str]] = {}
    for patch in patches:
        by_hash.setdefault(patch.identity.rgb_sha256, set()).add(
            patch.identity.source_fold
        )
    for digest in used_patch_sha256:
        if digest not in by_hash:
            raise ValueError("used patch SHA-256 is outside source custody")
        if held_out_fold in by_hash[digest]:
            raise ValueError("used patch belongs to the held-out fold")


def quilt_atlas(
    patches: Sequence[AcceptedPatch],
    *,
    seed: int,
    size: int = 512,
    block_size: int = 64,
    overlap: int = 16,
) -> tuple[np.ndarray, Sequence[str], Mapping[str, object]]:
    """Return sRGB atlas, used patch hashes and descriptive diagnostics."""
    return _quilt_atlas(
        patches,
        seed=seed,
        size=size,
        block_size=block_size,
        overlap=overlap,
        placement_patch_sha256=None,
    )


def quilt_atlas_from_schedule(
    patches: Sequence[AcceptedPatch],
    *,
    seed: int,
    placement_patch_sha256: Sequence[str],
) -> tuple[np.ndarray, Sequence[str], Mapping[str, object]]:
    """Replay the hard-cut compositor with one frozen S1 patch schedule."""
    schedule = tuple(placement_patch_sha256)
    if len(schedule) != _PLACEMENT_COUNT or any(
        not isinstance(digest, str) for digest in schedule
    ):
        raise ValueError("frozen placement schedule is malformed")
    return _quilt_atlas(
        patches,
        seed=seed,
        size=512,
        block_size=_BLOCK_SIZE,
        overlap=_OVERLAP,
        placement_patch_sha256=schedule,
    )


def _quilt_atlas(
    patches: Sequence[AcceptedPatch],
    *,
    seed: int,
    size: int,
    block_size: int,
    overlap: int,
    placement_patch_sha256: tuple[str, ...] | None,
) -> tuple[np.ndarray, Sequence[str], Mapping[str, object]]:
    """Compose one atlas through the shared random or frozen placement loop."""
    if not isinstance(seed, int):
        raise ValueError("quilting seed must be an integer")
    if block_size != _BLOCK_SIZE or overlap != _OVERLAP:
        raise ValueError(
            "quilting requires exact 64-block/16-overlap geometry"
        )
    accepted = _validate_patches(patches)
    positions = _placement_positions(size, block_size, overlap)
    patch_pixels = np.stack([patch.rgb for patch in accepted])
    linear_patches = _srgb_to_linear(patch_pixels)
    patch_hashes = tuple(patch.identity.rgb_sha256 for patch in accepted)
    patch_index_by_sha256 = {
        digest: index for index, digest in enumerate(patch_hashes)
    }
    random = np.random.default_rng(seed)

    atlas = np.zeros((size, size, 3), dtype=np.uint8)
    selected_hashes: list[str] = []
    candidate_counts: list[int] = []
    minimum_errors: list[float] = []
    selected_errors: list[float] = []
    seam_energies: list[dict[str, float | None]] = []
    for row, top in enumerate(positions):
        for column, left in enumerate(positions):
            placement_index = row * len(positions) + column
            height = min(block_size, size - top)
            width = min(block_size, size - left)
            region = atlas[top:top + height, left:left + width]
            left_width = min(overlap, width) if left > 0 else 0
            top_height = min(overlap, height) if top > 0 else 0
            if left_width or top_height:
                reference = _srgb_to_linear(region)
                candidates = linear_patches[:, :height, :width]
                errors = _candidate_overlap_errors(
                    reference,
                    candidates,
                    left_width=left_width,
                    top_height=top_height,
                )
            else:
                errors = np.zeros(len(accepted), dtype=np.float64)
            eligible = _eligible_candidate_indices(errors)
            if placement_patch_sha256 is None:
                selected = int(eligible[random.integers(len(eligible))])
            else:
                selected_hash = placement_patch_sha256[placement_index]
                try:
                    selected = patch_index_by_sha256[selected_hash]
                except KeyError as error:
                    raise ValueError(
                        "frozen placement hash is outside source custody"
                    ) from error
            selected_hashes.append(patch_hashes[selected])
            candidate_counts.append(int(eligible.size))
            minimum_errors.append(float(np.min(errors)))
            selected_errors.append(float(errors[selected]))

            block = patch_pixels[selected, :height, :width]
            block_linear = linear_patches[selected, :height, :width]
            reference_linear = _srgb_to_linear(region)
            left_cost = None
            top_cost = None
            if left > 0:
                left_difference = (
                    reference_linear[:, :left_width]
                    - block_linear[:, :left_width]
                )
                left_cost = np.sum(
                    left_difference * left_difference,
                    axis=2,
                    dtype=np.float64,
                )
            if top > 0:
                top_difference = (
                    reference_linear[:top_height]
                    - block_linear[:top_height]
                )
                top_cost = np.sum(
                    top_difference * top_difference,
                    axis=2,
                    dtype=np.float64,
                )
            keep_new = _combined_boundary_mask(
                left_cost,
                top_cost,
                (height, width),
            )
            region[keep_new] = block[keep_new]
            left_energy = None
            top_energy = None
            if left_cost is not None:
                left_keep = minimum_error_boundary(left_cost)
                left_energy = _boundary_energy(left_cost, left_keep)
            if top_cost is not None:
                top_keep = minimum_error_boundary(top_cost.T)
                top_energy = _boundary_energy(top_cost.T, top_keep)
            seam_energies.append({"left": left_energy, "top": top_energy})

    reuse_counts = Counter(selected_hashes)
    diagnostics: dict[str, object] = {
        "candidate_counts": candidate_counts,
        "candidate_tolerance": _CANDIDATE_TOLERANCE,
        "candidate_error_top_weight": 4.0,
        "color_space": "linear-rgb",
        "corner_rule": "keep-new intersection",
        "geometry": {
            "block_size": block_size,
            "edge_block_shape": [
                min(block_size, size - positions[-1]),
                min(block_size, size - positions[-1]),
            ],
            "overlap": overlap,
            "placement_count": len(positions) ** 2,
            "positions_x": list(positions),
            "positions_y": list(positions),
            "size": size,
            "stride": block_size - overlap,
        },
        "minimum_errors": minimum_errors,
        "placement_patch_sha256": selected_hashes,
        "selected_errors": selected_errors,
        "seam_energies": seam_energies,
        "source_patch_count": len(accepted),
        "source_reuse_counts": dict(sorted(reuse_counts.items())),
        "used_patch_count": len(reuse_counts),
        "zero_minimum_rule": "eligible errors equal zero",
    }
    if placement_patch_sha256 is not None:
        if (
            tuple(selected_hashes) != placement_patch_sha256
            or Counter(selected_hashes) != Counter(placement_patch_sha256)
        ):
            raise ValueError("frozen placement schedule does not close")
        diagnostics["placement_schedule_mode"] = "frozen-s1"
        diagnostics["placement_schedule_sha256"] = hashlib.sha256(
            "\n".join(placement_patch_sha256).encode("utf-8")
        ).hexdigest()
    if atlas.dtype != np.uint8 or not np.all(np.isfinite(atlas)):
        raise RuntimeError("quilting produced invalid sRGB pixels")
    return atlas, tuple(sorted(reuse_counts)), diagnostics


def _is_nonnegative_number(value: object) -> bool:
    """Return whether one JSON value is a finite nonnegative number."""
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and np.isfinite(value)
        and value >= 0.0
    )


def _validate_quilting_candidate(
    candidate: AtlasCandidate,
    index: int,
) -> None:
    """Validate one loaded candidate against the frozen quilting contract."""
    expected_fold = FOLDS[index]
    expected_count = EXPECTED_CROSSFIT_COUNTS[index]
    if (
        candidate.method_id != _METHOD_ID
        or candidate.held_out_fold != expected_fold
        or candidate.seed != _EXPECTED_SEEDS[index]
        or candidate.source_patch_count != expected_count
    ):
        raise ValueError("quilting candidate identity differs")

    diagnostics = candidate.diagnostics
    required_keys = {
        "candidate_counts",
        "candidate_error_top_weight",
        "candidate_tolerance",
        "color_space",
        "corner_rule",
        "geometry",
        "minimum_errors",
        "placement_patch_sha256",
        "seam_energies",
        "selected_errors",
        "source_patch_count",
        "source_reuse_counts",
        "used_patch_count",
        "zero_minimum_rule",
    }
    if (
        not isinstance(diagnostics, Mapping)
        or set(diagnostics) != required_keys
    ):
        raise ValueError("quilting diagnostics keys differ")
    expected_geometry = {
        "block_size": _BLOCK_SIZE,
        "edge_block_shape": [32, 32],
        "overlap": _OVERLAP,
        "placement_count": _PLACEMENT_COUNT,
        "positions_x": list(_POSITIONS),
        "positions_y": list(_POSITIONS),
        "size": 512,
        "stride": _BLOCK_SIZE - _OVERLAP,
    }
    if (
        diagnostics["candidate_tolerance"] != _CANDIDATE_TOLERANCE
        or diagnostics["candidate_error_top_weight"] != 4.0
        or diagnostics["color_space"] != "linear-rgb"
        or diagnostics["corner_rule"] != "keep-new intersection"
        or diagnostics["geometry"] != expected_geometry
        or diagnostics["source_patch_count"] != expected_count
        or diagnostics["zero_minimum_rule"] != "eligible errors equal zero"
    ):
        raise ValueError("quilting diagnostics semantics differ")

    candidate_counts = diagnostics["candidate_counts"]
    minimum_errors = diagnostics["minimum_errors"]
    selected_errors = diagnostics["selected_errors"]
    placement_hashes = diagnostics["placement_patch_sha256"]
    seam_energies = diagnostics["seam_energies"]
    sequences = (
        candidate_counts,
        minimum_errors,
        selected_errors,
        placement_hashes,
        seam_energies,
    )
    if any(not isinstance(values, list) for values in sequences) or any(
        len(values) != _PLACEMENT_COUNT for values in sequences
    ):
        raise ValueError("quilting diagnostics lengths differ")
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= expected_count
        for value in candidate_counts
    ):
        raise ValueError("quilting candidate counts are malformed")
    if any(
        not _is_nonnegative_number(value) for value in minimum_errors
    ) or any(
        not _is_nonnegative_number(value) for value in selected_errors
    ):
        raise ValueError("quilting selection errors are malformed")
    for minimum, selected in zip(minimum_errors, selected_errors):
        if minimum == 0.0:
            valid = selected == 0.0
        else:
            valid = minimum <= selected <= _CANDIDATE_TOLERANCE * minimum
        if not valid:
            raise ValueError("quilting selected error exceeds tolerance")

    def valid_digest(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    if any(not valid_digest(value) for value in placement_hashes):
        raise ValueError("quilting placement hashes are malformed")
    used_hashes = tuple(candidate.used_patch_sha256)
    if tuple(sorted(set(placement_hashes))) != used_hashes:
        raise ValueError("quilting used patch hashes differ from placements")
    reuse_counts = diagnostics["source_reuse_counts"]
    if not isinstance(reuse_counts, Mapping) or any(
        not valid_digest(digest)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        for digest, count in reuse_counts.items()
    ):
        raise ValueError("quilting reuse counts are malformed")
    if (
        dict(Counter(placement_hashes)) != dict(reuse_counts)
        or sum(reuse_counts.values()) != _PLACEMENT_COUNT
        or diagnostics["used_patch_count"] != len(reuse_counts)
    ):
        raise ValueError("quilting reuse diagnostics do not close")

    for placement_index, energies in enumerate(seam_energies):
        if (
            not isinstance(energies, Mapping)
            or set(energies) != {"left", "top"}
        ):
            raise ValueError("quilting seam diagnostics are malformed")
        row, column = divmod(placement_index, len(_POSITIONS))
        for key, absent in (("left", column == 0), ("top", row == 0)):
            value = energies[key]
            if (absent and value is not None) or (
                not absent and not _is_nonnegative_number(value)
            ):
                raise ValueError("quilting seam diagnostics differ")


def _validate_quilting_replay(
    candidate: AtlasCandidate,
    patches: Sequence[AcceptedPatch],
) -> None:
    """Bind a candidate to a deterministic replay of all quilting outputs."""
    atlas, used_hashes, diagnostics = quilt_atlas(
        patches,
        seed=candidate.seed,
    )
    if (
        not np.array_equal(atlas, candidate.atlas_srgb)
        or tuple(used_hashes) != tuple(candidate.used_patch_sha256)
        or dict(diagnostics) != dict(candidate.diagnostics)
    ):
        raise ValueError("quilting deterministic replay differs")


def read_quilting_bundle(
    root: Path,
    corpus: SourceCorpus | None = None,
) -> MethodBundle:
    """Read a hash-closed bundle and enforce Arm B quilting semantics."""
    resolved = Path(root).resolve()
    files = {
        path.relative_to(resolved).as_posix()
        for path in resolved.rglob("*")
        if path.is_file()
    }
    directories = tuple(path for path in resolved.rglob("*") if path.is_dir())
    if files != _EXPECTED_BUNDLE_FILES or directories:
        raise ValueError("quilting bundle must contain the exact 11-file set")
    bundle = read_method_bundle(resolved, _METHOD_ID)
    for index, candidate in enumerate(bundle.candidates):
        _validate_quilting_candidate(candidate, index)
        if corpus is not None:
            allowed = tuple(
                patches_for_held_out_fold(corpus, candidate.held_out_fold)
            )
            allowed_hashes = {patch.identity.rgb_sha256 for patch in allowed}
            if (
                len(allowed) != candidate.source_patch_count
                or not set(candidate.used_patch_sha256) <= allowed_hashes
            ):
                raise ValueError(
                    "quilting used patches are outside candidates"
                )
            _validate_used_patch_isolation(
                corpus.patches,
                candidate.used_patch_sha256,
                candidate.held_out_fold,
            )
            _validate_quilting_replay(candidate, allowed)
    return bundle
