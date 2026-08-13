"""Extract and publish the frozen R13 p64 source contact sheet."""

from __future__ import annotations

import os

_THREAD_ENVIRONMENT_KEYS = (
    "PYTHONDONTWRITEBYTECODE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
for _key in _THREAD_ENVIRONMENT_KEYS:
    os.environ[_key] = "1"

import argparse
import hashlib
import json
import sys
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from dpost import c1_r12_source as source_v1
from dpost import c1_r12_source_feasibility as source_v2


FOLDS = tuple(f"dev-fold-{index}" for index in range(4))
EXPECTED_SOURCE_COUNTS = {
    "dev-fold-0": 186,
    "dev-fold-1": 271,
    "dev-fold-2": 209,
    "dev-fold-3": 210,
}
EXPECTED_CROSSFIT_COUNTS = {
    "dev-fold-0": 690,
    "dev-fold-1": 605,
    "dev-fold-2": 667,
    "dev-fold-3": 666,
}
DEFAULT_FORMAL_ROOT = source_v2.DEFAULT_OUTPUT_ROOT
DEFAULT_OUTPUT_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r13-texture-atlas-stage0"
    r"\source-common-v1"
)
DEFAULT_STAGING_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r13-texture-atlas-stage0"
    r"\source-common-attempt-v1"
)
_CONTACT_COLUMNS = 6
_CONTACT_LABEL_HEIGHT = 40
_CONTACT_TILE_SIZE = 64
_CONTACT_ROWS = len(FOLDS)
_CONTACT_CELL_HEIGHT = _CONTACT_TILE_SIZE + _CONTACT_LABEL_HEIGHT
CONTACT_SHEET_SHAPE = (
    _CONTACT_ROWS * _CONTACT_CELL_HEIGHT,
    _CONTACT_COLUMNS * _CONTACT_TILE_SIZE,
    3,
)
_RELOCATABLE_PROVENANCE_FILES = (
    ("cli_script_path", "cli_script_sha256"),
    ("source_v1_module_path", "source_v1_module_sha256"),
    ("source_v2_module_path", "source_v2_module_sha256"),
    ("spec_path", "spec_sha256"),
    ("split_manifest_path", "split_manifest_sha256"),
)


@dataclass(frozen=True)
class PatchIdentity:
    """Identify one accepted R12 p64 source patch."""

    source_fold: str
    sequence_id: str
    frame_index: int
    frame_id: str
    y: int
    x: int
    rgb_sha256: str


@dataclass(frozen=True)
class AcceptedPatch:
    """Pair one source identity with its in-memory RGB pixels."""

    identity: PatchIdentity
    rgb: np.ndarray


@dataclass(frozen=True)
class SourceCorpus:
    """Hold accepted source patches and their frozen provenance."""

    patches: Sequence[AcceptedPatch]
    provenance: Mapping[str, object]


def _sha256(path: Path) -> str:
    """Return the SHA-256 of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lf_normalized_sha256(path: Path) -> str:
    """Return a text-file SHA-256 after normalizing CRLF to LF."""
    content = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _repo_text_suffix(value: object) -> str | None:
    """Return the Deform_post-relative suffix of one provenance path."""
    if not isinstance(value, str):
        return None
    parts = value.replace("\\", "/").split("/")
    try:
        start = len(parts) - 1 - parts[::-1].index("Deform_post")
    except ValueError:
        return None
    return "/".join(parts[start:])


def _provenance_differences(
    observed: Mapping[str, object],
    expected: Mapping[str, object],
) -> list[str]:
    """Return strict differences with five relocatable text-file pairs."""
    differing = {
        key
        for key in set(observed) | set(expected)
        if observed.get(key) != expected.get(key)
        or (key in observed) != (key in expected)
    }
    for path_key, sha_key in _RELOCATABLE_PROVENANCE_FILES:
        required = (path_key, sha_key)
        if not all(
            key in observed and key in expected for key in required
        ):
            continue
        observed_suffix = _repo_text_suffix(observed[path_key])
        current_suffix = _repo_text_suffix(expected[path_key])
        if (
            observed_suffix is not None
            and observed_suffix == current_suffix
        ):
            differing.discard(path_key)
        else:
            differing.add(path_key)
        current_path = expected[path_key]
        if not isinstance(current_path, str):
            differing.add(sha_key)
            continue
        if observed[sha_key] == _lf_normalized_sha256(Path(current_path)):
            differing.discard(sha_key)
        else:
            differing.add(sha_key)
    return sorted(differing)


def _load_json(path: Path) -> object:
    """Load one UTF-8 JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    """Write deterministic UTF-8 JSON."""
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_rgb_png(path: Path, rgb: np.ndarray) -> None:
    """Write one RGB uint8 array as a PNG."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise OSError(f"could not write PNG: {path}")


def _read_rgb_png(path: Path) -> np.ndarray:
    """Read one PNG as RGB uint8 pixels."""
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"could not read PNG: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _validate_publish_roots(
    output_root: Path,
    staging_root: Path,
) -> None:
    """Reject cross-drive, non-sibling, or existing publication roots."""
    if output_root.drive != staging_root.drive:
        raise ValueError("publish roots must use the same drive")
    if output_root.parent != staging_root.parent:
        raise ValueError("publish roots must be siblings")
    if output_root.exists() or staging_root.exists():
        raise FileExistsError("publish root already exists")


def _patch_key(patch: AcceptedPatch) -> tuple[int, int, int, str]:
    """Return the canonical within-sequence patch order."""
    identity = patch.identity
    return identity.frame_index, identity.y, identity.x, identity.frame_id


def _validate_patch(patch: AcceptedPatch, *, verify_hash: bool) -> None:
    """Validate one in-memory p64 RGB patch."""
    rgb = patch.rgb
    if rgb.shape != (64, 64, 3) or rgb.dtype != np.uint8:
        raise ValueError("accepted patch must be uint8 64x64 RGB")
    if patch.identity.source_fold not in FOLDS:
        raise ValueError("accepted patch source fold is not frozen")
    if verify_hash and hashlib.sha256(rgb.tobytes()).hexdigest() != (
        patch.identity.rgb_sha256
    ):
        raise ValueError("accepted patch RGB SHA-256 does not match pixels")


def _validate_corpus(corpus: SourceCorpus, *, verify_hash: bool) -> None:
    """Validate patch structure and optional provenance fold counts."""
    for patch in corpus.patches:
        _validate_patch(patch, verify_hash=verify_hash)
    expected = corpus.provenance.get("source_fold_counts")
    if expected is None:
        return
    observed = Counter(patch.identity.source_fold for patch in corpus.patches)
    if dict(observed) != dict(expected):
        raise ValueError("source corpus fold counts differ from provenance")


def _extract_p64_patches(
    frames: np.ndarray,
    positions: Sequence[tuple[str, str]],
    fold_map: Mapping[str, str],
    geometry: source_v2.PatchGeometry,
) -> tuple[AcceptedPatch, ...]:
    """Extract accepted p64 patches while building one mask per frame."""
    if geometry != source_v2.PatchGeometry("p64-s32", 64, 32):
        raise ValueError("source geometry is not the frozen p64-s32 arm")
    if frames.shape != (len(positions), 256, 256, 3):
        raise ValueError("source frame array shape does not match positions")
    if frames.dtype != np.uint8:
        raise ValueError("source frame array must be uint8")
    patches: list[AcceptedPatch] = []
    for frame_index, (sequence_id, frame_id) in enumerate(positions):
        frame = frames[frame_index]
        exclusion_mask, _ = source_v1._build_exclusion_mask(frame)
        for y, x in source_v2.candidate_positions(geometry):
            if source_v2._position_state(
                exclusion_mask,
                y,
                x,
                geometry,
            ) != "accepted":
                continue
            rgb = frame[y:y + geometry.size, x:x + geometry.size].copy()
            rgb.setflags(write=False)
            patches.append(
                AcceptedPatch(
                    PatchIdentity(
                        source_fold=fold_map[sequence_id],
                        sequence_id=sequence_id,
                        frame_index=frame_index,
                        frame_id=frame_id,
                        y=y,
                        x=x,
                        rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                    ),
                    rgb,
                )
            )
    return tuple(patches)


def _validate_r12_formal_root(
    formal_root: Path,
    expected_provenance: Mapping[str, object],
) -> dict[str, int]:
    """Verify the complete formal R12 bundle before source pixel access."""
    root = Path(formal_root)
    decision = _load_json(root / "decision.json")
    summary = _load_json(root / "p64-s32" / "summary.json")
    manifest_path = root / "artifact-hashes.json"
    manifest = _load_json(manifest_path)
    receipt = _load_json(root / "receipt.json")
    if not all(
        isinstance(value, dict)
        for value in (decision, summary, manifest, receipt)
    ):
        raise ValueError("R12 formal bundle JSON is malformed")
    expected_content = {
        "decision.json",
        "p64-s32/coverage-montage.png",
        "p64-s32/summary.json",
        "p96-s32/coverage-montage.png",
        "p96-s32/summary.json",
    }
    if set(manifest) != expected_content:
        raise ValueError("R12 formal content manifest is incomplete")
    for relative_path, digest in manifest.items():
        if _sha256(root / relative_path) != digest:
            raise ValueError("R12 formal content hash differs")
    if receipt.get("artifact_hashes_sha256") != _sha256(manifest_path):
        raise ValueError("R12 formal manifest hash differs")
    for value in (decision, receipt):
        if value.get("status") != "PASS_SOURCE_FEASIBILITY_EXPLORATORY":
            raise ValueError("R12 formal source status is not accepted")
        if value.get("winner") != "p64-s32":
            raise ValueError("R12 formal source winner is not p64-s32")
    observed_provenance = receipt.get("provenance")
    if not isinstance(observed_provenance, dict):
        raise ValueError("R12 formal provenance is malformed")
    expected_json = json.loads(json.dumps(dict(expected_provenance)))
    differing = _provenance_differences(
        observed_provenance,
        expected_json,
    )
    if differing:
        raise ValueError(
            f"R12 formal provenance {', '.join(differing)} differs"
        )
    if (
        summary.get("arm_id") != "p64-s32"
        or summary.get("size") != 64
        or summary.get("stride") != 32
    ):
        raise ValueError("R12 formal p64 geometry differs")
    source_counts = summary.get("available_patch_count")
    crossfit_counts = summary.get("crossfit_available_patch_count")
    if source_counts != EXPECTED_SOURCE_COUNTS:
        raise ValueError("R12 formal p64 source counts differ")
    if crossfit_counts != EXPECTED_CROSSFIT_COUNTS:
        raise ValueError("R12 formal p64 cross-fit counts differ")
    return dict(source_counts)


def load_p64_source(
    anchor_path: Path,
    receipt_path: Path,
    source_v1_root: Path,
    diagnostic_root: Path,
    formal_root: Path,
) -> SourceCorpus:
    """Revalidate R12 and extract the accepted p64 patches in memory."""
    anchor_path = Path(anchor_path)
    receipt_path = Path(receipt_path)
    source_v1_root = Path(source_v1_root)
    diagnostic_root = Path(diagnostic_root)
    formal_root = Path(formal_root)
    source_v2._configure_cpu_only()
    thread_environment = source_v2._validated_thread_environment()
    positions, provenance = source_v2._validate_inputs_before_pixels(
        anchor_path,
        receipt_path,
        source_v1_root,
        diagnostic_root,
        thread_environment,
    )
    fold_map = source_v1._load_fold_map()
    geometry = source_v2.PATCH_GEOMETRIES[0]
    assert geometry == source_v2.PatchGeometry("p64-s32", 64, 32)
    provenance_value = asdict(provenance)
    expected_counts = _validate_r12_formal_root(
        formal_root,
        provenance_value,
    )
    with np.load(anchor_path, allow_pickle=False) as anchor:
        if set(anchor.files) != {"real_frames"}:
            raise ValueError("anchor has unexpected arrays")
        frames = anchor["real_frames"]
        if frames.shape != (288, 256, 256, 3) or frames.dtype != np.uint8:
            raise ValueError("anchor frame array does not match frozen shape")
        patches = _extract_p64_patches(
            frames,
            positions,
            fold_map,
            geometry,
        )
    observed_counts = Counter(
        patch.identity.source_fold for patch in patches
    )
    if dict(observed_counts) != expected_counts:
        raise ValueError(
            "extracted p64 counts differ from the R12 formal summary"
        )
    provenance_value.update(
        {
            "r12_formal_root": str(formal_root.resolve()),
            "r12_artifact_hashes_sha256": _sha256(
                formal_root / "artifact-hashes.json"
            ),
            "source_fold_counts": expected_counts,
            "geometry": {"arm_id": "p64-s32", "size": 64, "stride": 32},
        }
    )
    return SourceCorpus(patches, provenance_value)


def patches_for_held_out_fold(
    corpus: SourceCorpus,
    held_out_fold: str,
) -> Sequence[AcceptedPatch]:
    """Return only patches outside one frozen held-out fold."""
    if held_out_fold not in FOLDS:
        raise ValueError("held-out fold is not in the frozen four-fold map")
    _validate_corpus(corpus, verify_hash=False)
    return tuple(
        patch
        for patch in corpus.patches
        if patch.identity.source_fold != held_out_fold
    )


def _frozen_sequences_by_fold() -> dict[str, tuple[str, ...]]:
    """Return frozen sequence IDs in canonical order for every fold."""
    fold_map = source_v1._load_fold_map()
    return {
        fold: tuple(
            sequence_id
            for sequence_id in source_v1.FROZEN_SEQUENCE_IDS
            if fold_map[sequence_id] == fold
        )
        for fold in FOLDS
    }


def _zero_accepted_sequence_audit(
    corpus: SourceCorpus,
) -> dict[str, list[str]]:
    """List frozen sequences with zero accepted patches in fold order."""
    observed = {
        (patch.identity.source_fold, patch.identity.sequence_id)
        for patch in corpus.patches
    }
    return {
        fold: [
            sequence_id
            for sequence_id in sequence_ids
            if (fold, sequence_id) not in observed
        ]
        for fold, sequence_ids in _frozen_sequences_by_fold().items()
    }


def bind_source_common_provenance(
    corpus: SourceCorpus,
    source_root: Path,
) -> SourceCorpus:
    """Validate source-common and bind its exact frozen provenance."""
    root = Path(source_root).resolve()
    expected_paths = {
        "artifact-hashes.json",
        "receipt.json",
        "source-contact-sheet.png",
        "source-provenance.json",
        "source-selection.json",
    }
    observed_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if observed_paths != expected_paths:
        raise ValueError("source-common file set differs")

    manifest_path = root / "artifact-hashes.json"
    manifest = _load_json(manifest_path)
    receipt = _load_json(root / "receipt.json")
    selection_payload = _load_json(root / "source-selection.json")
    frozen_provenance = _load_json(root / "source-provenance.json")
    expected_content = expected_paths - {"artifact-hashes.json", "receipt.json"}
    if not isinstance(manifest, dict) or set(manifest) != expected_content:
        raise ValueError("source-common content manifest differs")
    if any(
        not isinstance(digest, str)
        or _sha256(root / relative_path) != digest
        for relative_path, digest in manifest.items()
    ):
        raise ValueError("source-common content hash differs")

    expected_receipt_keys = {
        "artifact_hashes_sha256",
        "source_contact_sheet_sha256",
        "source_fold_counts",
        "source_patch_count",
        "source_provenance_sha256",
        "source_selection_sha256",
        "status",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_receipt_keys:
        raise ValueError("source-common receipt schema differs")
    expected_receipt = {
        "artifact_hashes_sha256": _sha256(manifest_path),
        "source_contact_sheet_sha256": manifest["source-contact-sheet.png"],
        "source_fold_counts": dict(
            Counter(patch.identity.source_fold for patch in corpus.patches)
        ),
        "source_patch_count": len(corpus.patches),
        "source_provenance_sha256": manifest["source-provenance.json"],
        "source_selection_sha256": manifest["source-selection.json"],
        "status": "PASS_SOURCE_CONTACT_SHEET",
    }
    if receipt != expected_receipt:
        raise ValueError("source-common receipt differs")

    _validate_corpus(corpus, verify_hash=True)
    selection = tuple(select_contact_sheet_patches(corpus))
    zero_audit = _zero_accepted_sequence_audit(corpus)
    expected_selection = {
        "selection": [asdict(patch.identity) for patch in selection],
        "zero_accepted_sequences": zero_audit,
    }
    if selection_payload != expected_selection:
        raise ValueError("source-common selection differs")
    expected_sheet = render_contact_sheet(selection)
    observed_sheet = _read_rgb_png(root / "source-contact-sheet.png")
    if not np.array_equal(observed_sheet, expected_sheet):
        raise ValueError("source-common contact sheet differs")

    if not isinstance(frozen_provenance, dict):
        raise ValueError("source-common provenance is malformed")
    current_provenance = json.loads(json.dumps(dict(corpus.provenance)))
    comparable_provenance = dict(frozen_provenance)
    if comparable_provenance.pop("zero_accepted_sequences", None) != zero_audit:
        raise ValueError("source-common zero-accepted audit differs")
    differing = _provenance_differences(
        comparable_provenance,
        current_provenance,
    )
    if differing:
        raise ValueError(
            f"source-common provenance {', '.join(differing)} differs"
        )
    return SourceCorpus(tuple(corpus.patches), frozen_provenance)


def select_contact_sheet_patches(
    corpus: SourceCorpus,
    per_fold: int = 6,
) -> Sequence[AcceptedPatch]:
    """Select patches by frozen-sequence round robin within each fold."""
    if per_fold < 1:
        raise ValueError("contact-sheet count must be positive")
    _validate_corpus(corpus, verify_hash=False)
    sequences_by_fold = _frozen_sequences_by_fold()
    selected: list[AcceptedPatch] = []
    for fold in FOLDS:
        sequence_ids = sequences_by_fold[fold]
        grouped: dict[str, list[AcceptedPatch]] = {
            sequence_id: [] for sequence_id in sequence_ids
        }
        for patch in corpus.patches:
            if patch.identity.source_fold == fold:
                if patch.identity.sequence_id not in grouped:
                    raise ValueError(
                        "source patch sequence differs from frozen fold map"
                    )
                grouped[patch.identity.sequence_id].append(patch)
        queues = {
            sequence_id: deque(sorted(grouped[sequence_id], key=_patch_key))
            for sequence_id in sequence_ids
        }
        fold_selection: list[AcceptedPatch] = []
        while len(fold_selection) < per_fold:
            made_progress = False
            for sequence_id in sequence_ids:
                if not queues[sequence_id]:
                    continue
                fold_selection.append(queues[sequence_id].popleft())
                made_progress = True
                if len(fold_selection) == per_fold:
                    break
            if not made_progress:
                break
        if len(fold_selection) != per_fold:
            raise ValueError(f"fold {fold} has too few accepted patches")
        selected.extend(fold_selection)
    return tuple(selected)


def contact_sheet_tile_slice(index: int) -> tuple[slice, slice]:
    """Return the native-pixel slice for one fold-major contact tile."""
    if not 0 <= index < _CONTACT_ROWS * _CONTACT_COLUMNS:
        raise ValueError("source contact sheet tile index is out of range")
    row, column = divmod(index, _CONTACT_COLUMNS)
    top = row * _CONTACT_CELL_HEIGHT
    left = column * _CONTACT_TILE_SIZE
    return (
        slice(top, top + _CONTACT_TILE_SIZE),
        slice(left, left + _CONTACT_TILE_SIZE),
    )


def contact_sheet_native_tiles(sheet: np.ndarray) -> tuple[np.ndarray, ...]:
    """Return the 24 native RGB tiles, excluding every label band."""
    if sheet.shape != CONTACT_SHEET_SHAPE or sheet.dtype != np.uint8:
        raise ValueError("source contact sheet shape or dtype differs")
    return tuple(
        sheet[contact_sheet_tile_slice(index)]
        for index in range(_CONTACT_ROWS * _CONTACT_COLUMNS)
    )


def render_contact_sheet(selection: Sequence[AcceptedPatch]) -> np.ndarray:
    """Render 24 native RGB tiles with labels below their pixels."""
    patches = tuple(selection)
    if len(patches) != 24:
        raise ValueError("source contact sheet requires exactly 24 patches")
    expected_folds = tuple(
        fold for fold in FOLDS for _ in range(_CONTACT_COLUMNS)
    )
    if tuple(patch.identity.source_fold for patch in patches) != expected_folds:
        raise ValueError("source contact sheet fold order differs")
    canvas = np.zeros(CONTACT_SHEET_SHAPE, dtype=np.uint8)
    for index, patch in enumerate(patches):
        _validate_patch(patch, verify_hash=True)
        row, column = divmod(index, _CONTACT_COLUMNS)
        top = row * _CONTACT_CELL_HEIGHT
        left = column * _CONTACT_TILE_SIZE
        canvas[contact_sheet_tile_slice(index)] = patch.rgb
        identity = patch.identity
        lines = (
            f"f{row} {identity.sequence_id}",
            f"i{identity.frame_index}",
            f"y{identity.y} x{identity.x}",
        )
        for line_index, line in enumerate(lines):
            cv2.putText(
                canvas,
                line,
                (left + 1, top + 73 + line_index * 11),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.25,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
    return canvas


def write_source_bundle(
    corpus: SourceCorpus,
    selection: Sequence[AcceptedPatch],
    *,
    output_root: Path,
    staging_root: Path,
) -> str:
    """Publish a no-clobber hash-closed source contact-sheet bundle."""
    output = Path(output_root).resolve()
    staging = Path(staging_root).resolve()
    _validate_publish_roots(output, staging)
    _validate_corpus(corpus, verify_hash=True)
    selected = tuple(selection)
    expected = tuple(select_contact_sheet_patches(corpus))
    if tuple(patch.identity for patch in selected) != tuple(
        patch.identity for patch in expected
    ):
        raise ValueError(
            "source selection differs from deterministic selection"
        )
    for patch in selected:
        _validate_patch(patch, verify_hash=True)
    sheet = render_contact_sheet(selected)
    zero_accepted_sequences = _zero_accepted_sequence_audit(corpus)
    provenance = dict(corpus.provenance)
    provenance["zero_accepted_sequences"] = zero_accepted_sequences
    staging.mkdir()
    content_paths = {
        "source-contact-sheet.png": staging / "source-contact-sheet.png",
        "source-selection.json": staging / "source-selection.json",
        "source-provenance.json": staging / "source-provenance.json",
    }
    _write_rgb_png(content_paths["source-contact-sheet.png"], sheet)
    _write_json(
        content_paths["source-selection.json"],
        {
            "selection": [asdict(patch.identity) for patch in selected],
            "zero_accepted_sequences": zero_accepted_sequences,
        },
    )
    _write_json(
        content_paths["source-provenance.json"],
        provenance,
    )
    hashes = {
        relative_path: _sha256(path)
        for relative_path, path in sorted(content_paths.items())
    }
    manifest_path = staging / "artifact-hashes.json"
    _write_json(manifest_path, hashes)
    receipt_path = staging / "receipt.json"
    _write_json(
        receipt_path,
        {
            "status": "PASS_SOURCE_CONTACT_SHEET",
            "source_patch_count": len(corpus.patches),
            "source_fold_counts": dict(
                Counter(
                    patch.identity.source_fold for patch in corpus.patches
                )
            ),
            "source_contact_sheet_sha256": hashes[
                "source-contact-sheet.png"
            ],
            "source_selection_sha256": hashes["source-selection.json"],
            "source_provenance_sha256": hashes["source-provenance.json"],
            "artifact_hashes_sha256": _sha256(manifest_path),
        },
    )
    if any(
        _sha256(staging / name) != digest
        for name, digest in hashes.items()
    ):
        raise OSError("source content hash self-check failed")
    receipt = _load_json(receipt_path)
    if not isinstance(receipt, dict) or receipt.get(
        "artifact_hashes_sha256"
    ) != _sha256(manifest_path):
        raise OSError("source manifest hash self-check failed")
    staging.rename(output)
    return "PASS_SOURCE_CONTACT_SHEET"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the sole source-contact-sheet action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", nargs="?")
    arguments = parser.parse_args(tuple(sys.argv[1:] if argv is None else argv))
    if arguments.action != "source-contact-sheet":
        return 2
    if DEFAULT_OUTPUT_ROOT.exists() or DEFAULT_STAGING_ROOT.exists():
        return 3
    try:
        corpus = load_p64_source(
            source_v2.DEFAULT_ANCHOR_PATH,
            source_v2.DEFAULT_RECEIPT_PATH,
            source_v2.DEFAULT_SOURCE_V1_ROOT,
            source_v2.DEFAULT_DIAGNOSTIC_ROOT,
            DEFAULT_FORMAL_ROOT,
        )
        selection = select_contact_sheet_patches(corpus)
        write_source_bundle(
            corpus,
            selection,
            output_root=DEFAULT_OUTPUT_ROOT,
            staging_root=DEFAULT_STAGING_ROOT,
        )
    except ValueError:
        return 2
    except (OSError, FileExistsError):
        return 3
    return 0
