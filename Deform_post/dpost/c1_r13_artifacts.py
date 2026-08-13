"""Publish and verify common C1-R13 texture-atlas artifacts."""

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

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from dpost.c1_r13_source import (
    FOLDS,
    PatchIdentity,
    contact_sheet_native_tiles,
)


EXPECTED_CROSSFIT_COUNTS = (690, 605, 667, 666)
_METHOD_LABEL_HEIGHT = 40
_METHOD_PANEL_SIZE = 512
_METHOD_COLUMNS = 4
_METHOD_SHEET_SHAPE = (
    _METHOD_LABEL_HEIGHT + _METHOD_PANEL_SIZE,
    _METHOD_COLUMNS * _METHOD_PANEL_SIZE,
    3,
)


@dataclass(frozen=True)
class AtlasCandidate:
    """Hold one fold-isolated texture-atlas candidate."""

    method_id: str
    held_out_fold: str
    seed: int
    source_patch_count: int
    atlas_srgb: np.ndarray
    diagnostics: Mapping[str, object]
    used_patch_sha256: Sequence[str]


@dataclass(frozen=True)
class MethodBundle:
    """Hold one method's four candidates and shared source identity."""

    method_id: str
    candidates: Sequence[AtlasCandidate]
    source_contact_sheet: np.ndarray
    source_selection: Sequence[PatchIdentity]
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        """Reject bundle contract drift at construction time."""
        _validate_method_bundle(self)


def _sha256(path: Path) -> str:
    """Return the SHA-256 of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> object:
    """Load one UTF-8 JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    """Write deterministic UTF-8 JSON."""
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _configure_cpu_only() -> None:
    """Force verifiable single-threaded CPU-only OpenCV execution."""
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)


def _write_rgb_png(path: Path, rgb: np.ndarray) -> None:
    """Write one RGB uint8 array as a PNG."""
    _configure_cpu_only()
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise OSError(f"could not write PNG: {path}")


def _read_rgb_png(path: Path) -> np.ndarray:
    """Read one PNG as RGB uint8 pixels."""
    _configure_cpu_only()
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


def _validate_source_selection(
    selection: Sequence[PatchIdentity],
) -> None:
    """Require the shared 24-patch fold-major selection contract."""
    identities = tuple(selection)
    if len(identities) != 24:
        raise ValueError("source selection must contain 24 identities")
    expected_folds = tuple(fold for fold in FOLDS for _ in range(6))
    if tuple(identity.source_fold for identity in identities) != expected_folds:
        raise ValueError("source selection fold order differs")
    if len(set(identities)) != 24:
        raise ValueError("source selection repeats a patch identity")


def _validate_source_contact_sheet(
    sheet: np.ndarray,
    selection: Sequence[PatchIdentity],
) -> None:
    """Bind each native source tile to its fold-major patch identity."""
    tiles = contact_sheet_native_tiles(sheet)
    identities = tuple(selection)
    if any(
        hashlib.sha256(tile.tobytes()).hexdigest()
        != identity.rgb_sha256
        for tile, identity in zip(tiles, identities)
    ):
        raise ValueError("source contact sheet tile hash differs")


def _method_panel_slice(index: int) -> tuple[slice, slice]:
    """Return the native-pixel slice for one fold-major method panel."""
    if not 0 <= index < _METHOD_COLUMNS:
        raise ValueError("method sheet panel index is out of range")
    left = index * _METHOD_PANEL_SIZE
    return (
        slice(_METHOD_LABEL_HEIGHT, _METHOD_SHEET_SHAPE[0]),
        slice(left, left + _METHOD_PANEL_SIZE),
    )


def _method_sheet_native_panels(
    sheet: np.ndarray,
) -> tuple[np.ndarray, ...]:
    """Return four native atlas panels, excluding the label band."""
    if sheet.shape != _METHOD_SHEET_SHAPE or sheet.dtype != np.uint8:
        raise ValueError("method sheet shape or dtype differs")
    return tuple(
        sheet[_method_panel_slice(index)] for index in range(_METHOD_COLUMNS)
    )


def _validate_method_sheet(
    sheet: np.ndarray,
    candidates: Sequence[AtlasCandidate],
) -> None:
    """Bind each native method panel to its fold-major atlas candidate."""
    panels = _method_sheet_native_panels(sheet)
    if any(
        not np.array_equal(panel, candidate.atlas_srgb)
        for panel, candidate in zip(panels, candidates)
    ):
        raise ValueError("method sheet panel pixels differ")


def _validate_method_bundle(bundle: MethodBundle) -> None:
    """Validate the frozen common method-bundle contract."""
    candidates = tuple(bundle.candidates)
    expected_folds = tuple(f"dev-fold-{index}" for index in range(4))
    if len(candidates) != 4 or tuple(
        candidate.held_out_fold for candidate in candidates
    ) != expected_folds:
        raise ValueError("method candidate fold order differs")
    if any(candidate.method_id != bundle.method_id for candidate in candidates):
        raise ValueError("candidate method ID differs from bundle method ID")
    if tuple(
        candidate.source_patch_count for candidate in candidates
    ) != EXPECTED_CROSSFIT_COUNTS:
        raise ValueError("candidate source patch counts differ")
    for candidate in candidates:
        atlas = candidate.atlas_srgb
        if atlas.shape != (512, 512, 3) or atlas.dtype != np.uint8:
            raise ValueError("atlas candidate must be uint8 512x512 RGB")
        if not isinstance(candidate.seed, int):
            raise ValueError("atlas candidate seed must be an integer")
        if not isinstance(candidate.diagnostics, Mapping):
            raise ValueError("atlas candidate diagnostics are malformed")
        if not all(
            isinstance(value, str) for value in candidate.used_patch_sha256
        ):
            raise ValueError("used patch SHA-256 values are malformed")
    _validate_source_selection(bundle.source_selection)
    _validate_source_contact_sheet(
        bundle.source_contact_sheet,
        bundle.source_selection,
    )
    required_provenance = {
        "anchor_sha256",
        "source_v1_module_sha256",
        "source_v2_module_sha256",
    }
    if (
        not isinstance(bundle.provenance, Mapping)
        or not required_provenance <= set(bundle.provenance)
    ):
        raise ValueError("source provenance is incomplete")


def _render_method_sheet(bundle: MethodBundle) -> np.ndarray:
    """Render four unchanged atlases below an external label band."""
    _configure_cpu_only()
    canvas = np.zeros(_METHOD_SHEET_SHAPE, dtype=np.uint8)
    for index, candidate in enumerate(bundle.candidates):
        left = index * _METHOD_PANEL_SIZE
        canvas[_method_panel_slice(index)] = candidate.atlas_srgb
        labels = (
            f"{bundle.method_id} {candidate.held_out_fold}",
            f"seed={candidate.seed} n={candidate.source_patch_count}",
        )
        for line_index, label in enumerate(labels):
            cv2.putText(
                canvas,
                label,
                (left + 6, 15 + line_index * 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
    return canvas


def _candidate_metadata(bundle: MethodBundle) -> list[dict[str, object]]:
    """Serialize candidate custody without duplicating atlas pixels."""
    return [
        {
            "method_id": candidate.method_id,
            "held_out_fold": candidate.held_out_fold,
            "seed": candidate.seed,
            "source_patch_count": candidate.source_patch_count,
            "diagnostics": dict(candidate.diagnostics),
            "used_patch_sha256": list(candidate.used_patch_sha256),
        }
        for candidate in bundle.candidates
    ]


def _write_hash_closure(
    staging: Path,
    content_paths: Mapping[str, Path],
    receipt_value: Mapping[str, object],
) -> None:
    """Write a manifest, bind it in a receipt, and self-verify."""
    hashes = {
        relative_path: _sha256(path)
        for relative_path, path in sorted(content_paths.items())
    }
    manifest_path = staging / "artifact-hashes.json"
    _write_json(manifest_path, hashes)
    receipt = dict(receipt_value)
    receipt["artifact_hashes_sha256"] = _sha256(manifest_path)
    _write_json(staging / "receipt.json", receipt)
    if any(
        _sha256(staging / name) != digest
        for name, digest in hashes.items()
    ):
        raise OSError("content artifact hash self-check failed")
    written_receipt = _load_json(staging / "receipt.json")
    if not isinstance(written_receipt, dict) or written_receipt.get(
        "artifact_hashes_sha256"
    ) != _sha256(manifest_path):
        raise OSError("manifest hash self-check failed")


def write_method_bundle(
    bundle: MethodBundle,
    *,
    output_root: Path,
    staging_root: Path,
) -> str:
    """Publish one no-clobber, hash-closed four-fold method bundle."""
    _validate_method_bundle(bundle)
    output = Path(output_root).resolve()
    staging = Path(staging_root).resolve()
    _validate_publish_roots(output, staging)
    staging.mkdir()
    content_paths: dict[str, Path] = {}
    for candidate in bundle.candidates:
        relative_path = f"atlas-{candidate.held_out_fold}.png"
        path = staging / relative_path
        _write_rgb_png(path, candidate.atlas_srgb)
        content_paths[relative_path] = path
    method_sheet_path = staging / "method-sheet.png"
    method_sheet = _render_method_sheet(bundle)
    _validate_method_sheet(method_sheet, bundle.candidates)
    _write_rgb_png(method_sheet_path, method_sheet)
    content_paths["method-sheet.png"] = method_sheet_path
    contact_path = staging / "source-contact-sheet.png"
    _write_rgb_png(contact_path, bundle.source_contact_sheet)
    content_paths["source-contact-sheet.png"] = contact_path
    selection_path = staging / "source-selection.json"
    _write_json(
        selection_path,
        [asdict(identity) for identity in bundle.source_selection],
    )
    content_paths["source-selection.json"] = selection_path
    provenance_path = staging / "provenance.json"
    _write_json(provenance_path, dict(bundle.provenance))
    content_paths["provenance.json"] = provenance_path
    metadata_path = staging / "candidate-metadata.json"
    _write_json(metadata_path, _candidate_metadata(bundle))
    content_paths["candidate-metadata.json"] = metadata_path
    content_hashes = {
        name: _sha256(path) for name, path in content_paths.items()
    }
    _write_hash_closure(
        staging,
        content_paths,
        {
            "status": "METHOD_BUNDLE_READY",
            "method_id": bundle.method_id,
            "held_out_fold_order": list(FOLDS),
            "source_contact_sheet_sha256": content_hashes[
                "source-contact-sheet.png"
            ],
            "source_selection_sha256": content_hashes[
                "source-selection.json"
            ],
            "source_provenance_sha256": content_hashes["provenance.json"],
            "method_sheet_sha256": content_hashes["method-sheet.png"],
        },
    )
    staging.rename(output)
    return bundle.method_id


def _read_verified_content(
    root: Path,
) -> tuple[dict[str, object], dict[str, str]]:
    """Verify manifest closure and return the receipt and content hashes."""
    manifest_path = root / "artifact-hashes.json"
    manifest = _load_json(manifest_path)
    receipt = _load_json(root / "receipt.json")
    if not isinstance(manifest, dict) or not isinstance(receipt, dict):
        raise ValueError("method receipt or manifest is malformed")
    if receipt.get("artifact_hashes_sha256") != _sha256(manifest_path):
        raise ValueError("method manifest hash differs from receipt")
    expected_paths = {
        *(f"atlas-{fold}.png" for fold in FOLDS),
        "candidate-metadata.json",
        "method-sheet.png",
        "provenance.json",
        "source-contact-sheet.png",
        "source-selection.json",
    }
    if set(manifest) != expected_paths:
        raise ValueError("method content manifest path set differs")
    for relative_path, digest in manifest.items():
        if (
            not isinstance(digest, str)
            or _sha256(root / relative_path) != digest
        ):
            raise ValueError("method content hash differs from manifest")
    identity_keys = {
        "source_contact_sheet_sha256": "source-contact-sheet.png",
        "source_selection_sha256": "source-selection.json",
        "source_provenance_sha256": "provenance.json",
        "method_sheet_sha256": "method-sheet.png",
    }
    for receipt_key, relative_path in identity_keys.items():
        if receipt.get(receipt_key) != manifest[relative_path]:
            raise ValueError(f"method receipt {receipt_key} differs")
    return receipt, {key: str(value) for key, value in manifest.items()}


def _parse_patch_identity(value: object) -> PatchIdentity:
    """Parse one complete source-patch identity mapping."""
    if not isinstance(value, dict):
        raise ValueError("source selection identity is malformed")
    try:
        return PatchIdentity(**value)
    except TypeError as error:
        raise ValueError("source selection identity is malformed") from error


def _read_method_bundle_with_receipt(
    root: Path,
    expected_method_id: str,
) -> tuple[MethodBundle, dict[str, object]]:
    """Read one verified method bundle and its receipt."""
    resolved = Path(root).resolve()
    receipt, _ = _read_verified_content(resolved)
    if receipt.get("status") != "METHOD_BUNDLE_READY":
        raise ValueError("method bundle status is not ready")
    if receipt.get("method_id") != expected_method_id:
        raise ValueError("method ID differs from expected method")
    if receipt.get("held_out_fold_order") != list(FOLDS):
        raise ValueError("method receipt fold order differs")
    metadata = _load_json(resolved / "candidate-metadata.json")
    selection_value = _load_json(resolved / "source-selection.json")
    provenance = _load_json(resolved / "provenance.json")
    if not isinstance(metadata, list) or len(metadata) != 4:
        raise ValueError("candidate metadata is malformed")
    if (
        not isinstance(selection_value, list)
        or not isinstance(provenance, dict)
    ):
        raise ValueError("method source identity is malformed")
    candidates: list[AtlasCandidate] = []
    for value in metadata:
        if not isinstance(value, dict):
            raise ValueError("candidate metadata is malformed")
        try:
            candidates.append(
                AtlasCandidate(
                    method_id=value["method_id"],
                    held_out_fold=value["held_out_fold"],
                    seed=value["seed"],
                    source_patch_count=value["source_patch_count"],
                    atlas_srgb=_read_rgb_png(
                        resolved / f"atlas-{value['held_out_fold']}.png"
                    ),
                    diagnostics=value["diagnostics"],
                    used_patch_sha256=tuple(value["used_patch_sha256"]),
                )
            )
        except (KeyError, TypeError) as error:
            raise ValueError("candidate metadata is malformed") from error
    bundle = MethodBundle(
        method_id=expected_method_id,
        candidates=tuple(candidates),
        source_contact_sheet=_read_rgb_png(
            resolved / "source-contact-sheet.png"
        ),
        source_selection=tuple(
            _parse_patch_identity(value) for value in selection_value
        ),
        provenance=provenance,
    )
    _validate_method_sheet(
        _read_rgb_png(resolved / "method-sheet.png"),
        bundle.candidates,
    )
    return bundle, receipt


def read_method_bundle(root: Path, expected_method_id: str) -> MethodBundle:
    """Read and fully verify one formal method bundle."""
    bundle, _ = _read_method_bundle_with_receipt(root, expected_method_id)
    return bundle


def _method_id_from_root(root: Path) -> str:
    """Read the claimed method ID before full receipt verification."""
    receipt = _load_json(Path(root).resolve() / "receipt.json")
    if not isinstance(receipt, dict) or not isinstance(
        receipt.get("method_id"),
        str,
    ):
        raise ValueError("method receipt has no method ID")
    return str(receipt["method_id"])


def _render_cross_method_overview(
    bundles: Sequence[MethodBundle],
) -> np.ndarray:
    """Render eight unchanged atlas panels with external labels."""
    _configure_cpu_only()
    cell_height = _METHOD_LABEL_HEIGHT + 512
    canvas = np.zeros((2 * cell_height, 4 * 512, 3), dtype=np.uint8)
    for row, bundle in enumerate(bundles):
        for column, candidate in enumerate(bundle.candidates):
            top = row * cell_height
            left = column * 512
            canvas[
                top + _METHOD_LABEL_HEIGHT:(row + 1) * cell_height,
                left:left + 512,
            ] = candidate.atlas_srgb
            label = (
                f"{bundle.method_id} {candidate.held_out_fold} "
                f"seed={candidate.seed} n={candidate.source_patch_count}"
            )
            cv2.putText(
                canvas,
                label,
                (left + 6, top + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
    return canvas


def write_cross_method_overview(
    first_root: Path,
    second_root: Path,
    *,
    output_root: Path,
    staging_root: Path,
) -> str:
    """Verify two method bundles and publish a neutral visual overview."""
    output = Path(output_root).resolve()
    staging = Path(staging_root).resolve()
    _validate_publish_roots(output, staging)
    roots = (Path(first_root).resolve(), Path(second_root).resolve())
    method_ids = tuple(_method_id_from_root(root) for root in roots)
    if set(method_ids) != {"multiscale-v1", "quilting-v1"}:
        raise ValueError("overview requires one bundle from each race method")
    loaded = tuple(
        _read_method_bundle_with_receipt(root, method_id)
        for root, method_id in zip(roots, method_ids)
    )
    by_method = {
        bundle.method_id: (root, bundle, receipt)
        for root, (bundle, receipt) in zip(roots, loaded)
    }
    ordered = (
        by_method["multiscale-v1"],
        by_method["quilting-v1"],
    )
    first_receipt = ordered[0][2]
    second_receipt = ordered[1][2]
    identity_labels = {
        "source_contact_sheet_sha256": "contact-sheet identity",
        "source_selection_sha256": "source-selection identity",
        "source_provenance_sha256": "source-provenance identity",
    }
    for key, label in identity_labels.items():
        if first_receipt.get(key) != second_receipt.get(key):
            raise ValueError(f"method bundles have mismatched {label}")
    staging.mkdir()
    bundles = (ordered[0][1], ordered[1][1])
    overview_path = staging / "cross-method-overview.png"
    _write_rgb_png(overview_path, _render_cross_method_overview(bundles))
    identities_path = staging / "input-identities.json"
    _write_json(
        identities_path,
        {
            "decision": "INCONCLUSIVE",
            "methods": [
                {
                    "method_id": bundle.method_id,
                    "root": str(root),
                    "receipt_sha256": _sha256(root / "receipt.json"),
                }
                for root, bundle, _ in ordered
            ],
            "source_contact_sheet_sha256": first_receipt[
                "source_contact_sheet_sha256"
            ],
            "source_selection_sha256": first_receipt[
                "source_selection_sha256"
            ],
            "source_provenance_sha256": first_receipt[
                "source_provenance_sha256"
            ],
        },
    )
    content_paths = {
        "cross-method-overview.png": overview_path,
        "input-identities.json": identities_path,
    }
    _write_hash_closure(
        staging,
        content_paths,
        {
            "status": "ADJUDICATION_READY",
            "decision": "INCONCLUSIVE",
            "input_identities_sha256": _sha256(identities_path),
        },
    )
    staging.rename(output)
    return "INCONCLUSIVE"
