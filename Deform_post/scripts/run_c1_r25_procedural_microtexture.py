"""Run the sole no-clobber C1-R25 sixteen-image preview action."""

from __future__ import annotations

import os


for _environment_key in (
    "PYTHONDONTWRITEBYTECODE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_environment_key] = "1"


import json
import sys
import time
from pathlib import Path
from typing import Mapping, Sequence


_DEFORM_POST_ROOT = str(Path(__file__).resolve().parents[1])
if _DEFORM_POST_ROOT not in sys.path:
    sys.path.insert(0, _DEFORM_POST_ROOT)


import numpy as np

from dpost.c1_r16_uv_render import (
    FORMAL_CAMERA_NAMES,
    RenderedView,
    build_five_view_cameras,
    load_mesh_arrays,
    render_legacy_view,
    validate_frozen_camera_receipts,
    validate_oriented_face_rows,
)
from dpost.c1_r19_triplanar_continuity import (
    ProgressReporter,
    VertexColorRenderer,
    build_vertex_color_mesh,
)
from dpost.c1_r25_procedural_microtexture import (
    EXPECTED_BASE_RGB,
    FROZEN_R19_MASK_SHA256,
    FROZEN_R19_VERTEX_COLORS_SHA256,
    MESH_NAMES,
    PREVIEW_CAMERA_NAMES,
    derive_base_rgb,
    write_r25_preview_bundle,
)
from scripts import run_c1_r16a_uv_textured_render as r16_runner


VERIFICATION_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r25-procedural-tissue-microtexture"
)
OUTPUT_ROOT = VERIFICATION_ROOT / "development-preview-v1"
# The first attempt root is a preserved C-F010 failure record (design v3 M5
# stop); this rerun under design v4 must not touch it.
ATTEMPT_ROOT = VERIFICATION_ROOT / "development-preview-v1-attempt2"
R19_SCREEN_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r19-triplanar-continuity\screen-v1"
)
CANONICAL_PATH = r16_runner.CANONICAL_PATH
DEFORMED_PATH = r16_runner.DEFORMED_PATH
CANONICAL_SHA256 = r16_runner.CANONICAL_SHA256
DEFORMED_SHA256 = r16_runner.DEFORMED_SHA256
EXPECTED_SHARED_EDGE_COUNT = 6_009
MIN_AVAILABLE_MEMORY_BYTES = 4_000_000_000

_RssSampler = r16_runner._RssSampler


def _available_memory_bytes() -> int:
    """Return system-available bytes through the frozen R16 helper."""
    return r16_runner._available_memory_bytes()


def _write_failure(error: BaseException, last_completed_step: str) -> None:
    """Retain one exclusive failure receipt without publishing a bundle."""
    ATTEMPT_ROOT.mkdir(parents=True, exist_ok=True)
    with (ATTEMPT_ROOT / "failure.json").open(
        "x",
        encoding="utf-8",
        newline="\n",
    ) as output:
        json.dump(
            {
                "exception_type": type(error).__name__,
                "message": str(error),
                "last_completed_step": last_completed_step,
            },
            output,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")


def _is_sha256(value: object) -> bool:
    """Return whether a value is one lowercase SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _r19_consumed_paths() -> tuple[str, ...]:
    """Return the exact R19 files consumed by the R25 preview."""
    paths = ["vertex-colors.npy", "inputs.json"]
    for mesh_name in MESH_NAMES:
        for view_name in PREVIEW_CAMERA_NAMES:
            paths.append(f"masks/{mesh_name}/{view_name}.png")
            paths.append(f"renders/{mesh_name}/{view_name}.png")
    return tuple(paths)


def _validate_r19_consumed_artifacts() -> None:
    """Close the frozen R19 manifest over every R25-consumed file."""
    receipt_path = R19_SCREEN_ROOT / "receipt.json"
    manifest_path = R19_SCREEN_ROOT / "artifact-hashes.json"
    if (
        R19_SCREEN_ROOT.is_symlink()
        or receipt_path.is_symlink()
        or manifest_path.is_symlink()
    ):
        raise ValueError("R25 frozen R19 root or closure file is a symlink")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("R25 cannot read the frozen R19 closure") from error
    manifest_sha256 = (
        receipt.get("artifact_hashes_sha256")
        if isinstance(receipt, dict)
        else None
    )
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != "c1-r19-triplanar-visual-v1"
        or receipt.get("status") != "R19_TRIPLANAR_VISUAL_READY"
        or not _is_sha256(manifest_sha256)
        or not isinstance(manifest, dict)
        or r16_runner._file_sha256(manifest_path) != manifest_sha256
    ):
        raise ValueError("R25 frozen R19 closure differs")
    for relative_path in _r19_consumed_paths():
        expected_sha256 = manifest.get(relative_path)
        artifact_path = R19_SCREEN_ROOT / relative_path
        if not _is_sha256(expected_sha256):
            raise ValueError("R25 R19 consumed manifest entry differs")
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise ValueError("R25 R19 consumed artifact path differs")
        if r16_runner._file_sha256(artifact_path) != expected_sha256:
            raise ValueError("R25 R19 consumed artifact SHA-256 differs")
    if (
        r16_runner._file_sha256(R19_SCREEN_ROOT / "vertex-colors.npy")
        != FROZEN_R19_VERTEX_COLORS_SHA256
    ):
        raise ValueError("R25 frozen R19 vertex colours differ")
    for mask_key, frozen_sha256 in FROZEN_R19_MASK_SHA256.items():
        mask_path = R19_SCREEN_ROOT / "masks" / f"{mask_key}.png"
        if r16_runner._file_sha256(mask_path) != frozen_sha256:
            raise ValueError("R25 frozen R19 mask SHA-256 differs")
    inputs = json.loads(
        (R19_SCREEN_ROOT / "inputs.json").read_text(encoding="utf-8")
    )
    if (
        not isinstance(inputs, dict)
        or inputs.get("camera_names") != list(FORMAL_CAMERA_NAMES)
        or inputs.get("canonical_file_sha256") != CANONICAL_SHA256
        or inputs.get("deformed_file_sha256") != DEFORMED_SHA256
        or inputs.get("mapping_space") != "canonical"
        or inputs.get("deformed_color_policy") != "reuse_exact_canonical_bytes"
        or inputs.get("vertex_count") != 2_005
        or inputs.get("face_count") != 4_006
        or inputs.get("worker_count") != 1
    ):
        raise ValueError("R25 frozen R19 input bindings differ")


def _load_base_source_colors() -> np.ndarray:
    """Load the hash-verified R19 vertex colours for base derivation."""
    npy_path = R19_SCREEN_ROOT / "vertex-colors.npy"
    with npy_path.open("rb") as source:
        colors = np.load(source, allow_pickle=False)
    if (
        not isinstance(colors, np.ndarray)
        or colors.dtype != np.uint8
        or colors.shape != (2_005, 3)
    ):
        raise ValueError("R25 R19 vertex colour array differs")
    if derive_base_rgb(colors) != EXPECTED_BASE_RGB:
        raise ValueError(
            "R25 base colour derivation differs from the review-pinned value"
        )
    return colors


def _load_inputs() -> dict[str, object]:
    """Load and validate the two frozen topology-corresponding meshes."""
    _validate_r19_consumed_artifacts()
    r16_runner._verify_input_hash(
        CANONICAL_PATH,
        CANONICAL_SHA256,
        "canonical mesh",
    )
    r16_runner._verify_input_hash(
        DEFORMED_PATH,
        DEFORMED_SHA256,
        "deformed mesh",
    )
    canonical_vertices, canonical_faces = load_mesh_arrays(CANONICAL_PATH)
    deformed_vertices, deformed_faces = load_mesh_arrays(DEFORMED_PATH)
    r16_runner._validate_mesh_counts(
        canonical_vertices,
        canonical_faces,
        "canonical",
    )
    r16_runner._validate_mesh_counts(
        deformed_vertices,
        deformed_faces,
        "deformed",
    )
    validate_oriented_face_rows(canonical_faces, deformed_faces)
    return {
        "canonical_vertices": canonical_vertices,
        "canonical_faces": canonical_faces,
        "deformed_vertices": deformed_vertices,
        "deformed_faces": deformed_faces,
        "canonical_file_sha256": CANONICAL_SHA256,
        "deformed_file_sha256": DEFORMED_SHA256,
    }


def _preview_renderer(
    inputs: Mapping[str, object],
    sampler: object,
    progress: ProgressReporter,
) -> tuple[VertexColorRenderer, list[dict[str, object]]]:
    """Return the serial two-view renderer over the frozen five-camera set."""
    canonical_vertices = inputs["canonical_vertices"]
    deformed_vertices = inputs["deformed_vertices"]
    if not isinstance(canonical_vertices, np.ndarray) or not isinstance(
        deformed_vertices,
        np.ndarray,
    ):
        raise ValueError("R25 runner mesh arrays differ")
    cameras = build_five_view_cameras(canonical_vertices, deformed_vertices)
    camera_receipts = r16_runner._camera_receipts(cameras)
    validate_frozen_camera_receipts(camera_receipts)
    preview_cameras = tuple(
        next(camera for camera in cameras if camera.name == name)
        for name in PREVIEW_CAMERA_NAMES
    )

    def render(
        mesh_name: str,
        vertices: np.ndarray,
        faces: np.ndarray,
        vertex_colors: np.ndarray,
    ) -> dict[str, RenderedView]:
        mesh = build_vertex_color_mesh(vertices, faces, vertex_colors)
        views = {}
        for camera in preview_cameras:
            sampler.check()
            views[camera.name] = render_legacy_view(mesh, camera)
            progress(f"render_view:{mesh_name}/{camera.name}")
        if tuple(views) != PREVIEW_CAMERA_NAMES:
            raise ValueError("R25 runner camera order differs")
        return views

    return render, camera_receipts


def _run_preview_action(available_memory_bytes: int) -> int:
    """Build and publish one serial sixteen-image R25 preview bundle."""
    import open3d

    sampler = _RssSampler()
    last_completed_step = "output_roots_checked"

    def report(stage: str) -> None:
        nonlocal last_completed_step
        last_completed_step = stage

    start_time = time.perf_counter()
    try:
        sampler.start()
        sampler.check()
        if available_memory_bytes < MIN_AVAILABLE_MEMORY_BYTES:
            raise MemoryError(
                "system-available memory is below 4000000000 bytes"
            )
        inputs = _load_inputs()
        last_completed_step = "inputs_loaded"
        base_source_colors = _load_base_source_colors()
        last_completed_step = "base_source_loaded"
        renderer, camera_receipts = _preview_renderer(
            inputs,
            sampler,
            report,
        )
        last_completed_step = "renderer_prepared"
        result = write_r25_preview_bundle(
            ATTEMPT_ROOT,
            r19_screen_root=R19_SCREEN_ROOT,
            **inputs,
            base_source_colors=base_source_colors,
            base_source_sha256=FROZEN_R19_VERTEX_COLORS_SHA256,
            render_vertex_colors=renderer,
            camera_registry_receipts=camera_receipts,
            open3d_version=open3d.__version__,
            rss_check=sampler.check,
            peak_process_tree_rss_bytes=lambda: sampler.peak_bytes,
            expected_shared_edge_count=EXPECTED_SHARED_EDGE_COUNT,
            progress=report,
        )
        last_completed_step = "bundle_written"
        sampler.stop()
        sampler.check()
        ATTEMPT_ROOT.rename(OUTPUT_ROOT)
        print("R25_PREVIEW_PUBLISHED")
        print(
            json.dumps(
                {
                    "base_rgb": list(result["base_rgb"]),
                    "lambda_floor_measured": result["lambda_floor"],
                    "m12_minimum_value": result["m12"]["minimum_value"],
                    "peak_process_tree_rss_bytes": (
                        result["receipt"]["rss"][
                            "peak_process_tree_rss_bytes"
                        ]
                    ),
                    "wall_seconds": time.perf_counter() - start_time,
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception as error:
        print(
            "R25_PREVIEW_FAILED "
            f"step={last_completed_step} "
            f"type={type(error).__name__} message={error}",
            file=sys.stderr,
        )
        try:
            sampler.stop()
        except Exception:
            pass
        try:
            _write_failure(error, last_completed_step)
        except (FileExistsError, OSError) as receipt_error:
            print(
                "R25_FAILURE_RECEIPT_ERROR "
                f"type={type(receipt_error).__name__} "
                f"message={receipt_error}",
                file=sys.stderr,
            )
        return 4
    finally:
        try:
            sampler.stop()
        except Exception:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run only `preview-v1` after no-clobber and memory preflight."""
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments != ("preview-v1",):
        return 2
    if OUTPUT_ROOT.exists() or ATTEMPT_ROOT.exists():
        return 3
    available_memory_bytes = _available_memory_bytes()
    if available_memory_bytes < MIN_AVAILABLE_MEMORY_BYTES:
        error = MemoryError("system-available memory is below 4000000000 bytes")
        try:
            _write_failure(error, "output_roots_checked")
        except (FileExistsError, OSError):
            pass
        return 5
    return _run_preview_action(available_memory_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
