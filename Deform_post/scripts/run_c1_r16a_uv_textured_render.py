"""Run the exact no-clobber C1-R16A UV textured-render action."""

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


import hashlib
import json
import shutil
import sys
import threading
from pathlib import Path
from typing import Sequence


_DEFORM_POST_ROOT = str(Path(__file__).resolve().parents[1])
if _DEFORM_POST_ROOT not in sys.path:
    sys.path.insert(0, _DEFORM_POST_ROOT)


import numpy as np
import psutil
from PIL import Image

from dpost import c1_r16_uv_render as uv_render
from dpost.c1_r16_uv_render import (
    FORMAL_CAMERA_NAMES,
    FORMAL_SCHEMA,
    FORMAL_STATUS,
    CameraSpec,
    RenderedView,
    UvSidecar,
    build_calibration_texture,
    build_five_view_cameras,
    build_textured_mesh,
    generate_xatlas_sidecar,
    load_mesh_arrays,
    read_formal_bundle,
    read_uv_sidecar,
    render_legacy_view,
    validate_oriented_face_rows,
    validate_render_set,
    validate_uv_origin_plane,
    validate_uv_sidecar,
    write_bundle_closure,
    write_uv_sidecar,
)


CANONICAL_PATH = Path(
    r"D:\MedSim2Learn\DataFlow\ShapeReconstruction\meshes\kidney_anat.ply"
)
DEFORMED_PATH = Path(
    r"D:\MedSim2Learn\DataFlow\Deform_post\primary\twin_full\seq01\sim"
    r"\DeformedSample_ComplexObject_26_06_10_223933"
    r"\deformed_s0521_v0000.ply"
)
S1_PATH = Path(
    r"D:\MedSim2Learn-C1-verification\r14-quilting-seam-stage0"
    r"\s1-top-weight-v1\seed-0\atlas-dev-fold-0.png"
)
FORMAL_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r16a-uv-textured-render\formal-v2"
)
ATTEMPT_ROOT = Path(
    r"D:\MedSim2Learn-C1-verification\r16a-uv-textured-render"
    r"\formal-attempt-v2"
)
CANONICAL_SHA256 = (
    "f0a301cf143fcb12b4a92ef6ca8ce326b45a71e393d7f18c806cc4802c5e3e2d"
)
DEFORMED_SHA256 = (
    "82915fe9e0eb1f7e7dec6f29c195fb7ec361fbace55d32f21a80ef601e099493"
)
S1_SHA256 = "2950145e810cf2844e8ec25c87c7474dbd39a6ec9df648b7e5fe9f0390b39a8e"
EXPECTED_VERTEX_COUNT = 2_005
EXPECTED_FACE_COUNT = 4_006
MIN_AVAILABLE_MEMORY_BYTES = 4_000_000_000
MAX_PROCESS_TREE_RSS_BYTES = 500_000_000
RSS_SAMPLE_INTERVAL_SECONDS = 0.05


class _RssSampler:
    """Sample current-process and recursive-child RSS with one monitor thread."""

    def __init__(self) -> None:
        self.peak_bytes = 0
        self._exceeded = threading.Event()
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._error: BaseException | None = None
        self._final_sampled = False
        self._thread = threading.Thread(
            target=self._sample_loop,
            name="c1-r16a-rss-sampler",
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        """Record an initial sample and start the 50-ms monitor."""
        self._sample_protected()
        self.check()
        self._thread.start()
        self._started = True

    def check(self) -> None:
        """Fail the action after any sampled ceiling violation."""
        with self._state_lock:
            error = self._error
        if error is not None:
            raise error
        if self._exceeded.is_set():
            raise MemoryError("process-tree RSS reached the 500000000-byte ceiling")

    def stop(self) -> int:
        """Stop and join the sampler on every action exit."""
        if self._started:
            self._stop.set()
            self._thread.join()
            self._started = False
        if not self._final_sampled:
            self._final_sampled = True
            self._sample_protected()
        self.check()
        return self.peak_bytes

    def _sample_loop(self) -> None:
        while not self._stop.wait(RSS_SAMPLE_INTERVAL_SECONDS):
            if not self._sample_protected():
                self._stop.set()
                return

    def _read_process_tree_rss(self) -> int:
        """Return one current-process plus recursive-child RSS total."""
        process = psutil.Process()
        children = process.children(recursive=True)
        total = process.memory_info().rss
        for child in children:
            try:
                total += child.memory_info().rss
            except psutil.NoSuchProcess:
                continue
        return total

    def _sample_protected(self) -> bool:
        """Record one sample or retain the first unexpected sampler error."""
        try:
            total = self._read_process_tree_rss()
        except BaseException as error:
            with self._state_lock:
                if self._error is None:
                    self._error = error
            return False
        with self._state_lock:
            self.peak_bytes = max(self.peak_bytes, total)
            if total >= MAX_PROCESS_TREE_RSS_BYTES:
                self._exceeded.set()
        return True


def _available_memory_bytes() -> int:
    """Return system-available memory for the formal preflight."""
    return int(psutil.virtual_memory().available)


def _file_sha256(path: Path) -> str:
    """Hash exact file bytes using bounded reads."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    """Write one new UTF-8 JSON artifact without overwriting."""
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")


def _write_rgb_png(path: Path, rgb: np.ndarray) -> None:
    """Write one new RGB PNG and reject accidental clobbering."""
    if path.exists():
        raise FileExistsError(f"output PNG already exists: {path}")
    Image.fromarray(rgb, mode="RGB").save(path)


def _write_mask_png(path: Path, mask: np.ndarray) -> None:
    """Write one new depth-derived binary mask PNG."""
    if path.exists():
        raise FileExistsError(f"output mask already exists: {path}")
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(path)


def _load_rgb(path: Path) -> np.ndarray:
    """Load one exact 512-square RGB texture."""
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.mode != "RGB" or image.size != (512, 512):
            raise ValueError("input atlas must be a 512 x 512 RGB PNG")
        return np.array(image, dtype=np.uint8, copy=True)


def _verify_input_hash(path: Path, expected_sha256: str, label: str) -> None:
    """Fail closed if one frozen input identity differs."""
    if _file_sha256(path) != expected_sha256:
        raise ValueError(f"frozen {label} SHA-256 differs")


def _validate_mesh_counts(vertices: np.ndarray, faces: np.ndarray, label: str) -> None:
    """Require the frozen source vertex and face counts."""
    if len(vertices) != EXPECTED_VERTEX_COUNT or len(faces) != EXPECTED_FACE_COUNT:
        raise ValueError(f"{label} mesh shape differs from the frozen contract")


def _sidecars_equal(first: UvSidecar, second: UvSidecar) -> bool:
    """Compare every deterministic xatlas output array exactly."""
    return all(
        np.array_equal(getattr(first, name), getattr(second, name))
        for name in (
            "source_faces",
            "uv_vertex_to_source_vertex",
            "uv_faces",
            "uv_vertices",
        )
    )


def _calibration_plane() -> tuple[np.ndarray, UvSidecar]:
    """Return the known two-triangle square and corner-UV contract."""
    vertices = np.array(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    sidecar = UvSidecar(
        source_faces=faces,
        uv_vertex_to_source_vertex=np.array([0, 1, 2, 0, 2, 3], dtype=np.int64),
        uv_faces=np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64),
        uv_vertices=np.array(
            [
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 0.0],
                [0.0, 0.0],
            ],
            dtype=np.float64,
        ),
        generator="known-plane",
        generator_version="v1",
    )
    return vertices, sidecar


def _camera_receipts(cameras: Sequence[CameraSpec]) -> list[dict[str, object]]:
    """Serialize the shared intrinsic and five exact extrinsics."""
    return [
        {
            "name": camera.name,
            "intrinsic": np.asarray(
                camera.intrinsic.intrinsic_matrix,
                dtype=np.float64,
            ).tolist(),
            "extrinsic": np.asarray(camera.extrinsic, dtype=np.float64).tolist(),
        }
        for camera in cameras
    ]


def _render_mesh_texture_set(
    mesh_name: str,
    vertices: np.ndarray,
    sidecar: UvSidecar,
    cameras: Sequence[CameraSpec],
    checker_rgb: np.ndarray,
    s1_rgb: np.ndarray,
    sampler: _RssSampler,
) -> tuple[dict[str, RenderedView], dict[str, RenderedView]]:
    """Render and persist both textures for one mesh in fixed camera order."""
    texture_views: dict[str, dict[str, RenderedView]] = {}
    for texture_name, texture in (("checker", checker_rgb), ("s1", s1_rgb)):
        mesh = build_textured_mesh(vertices, sidecar, texture)
        views: dict[str, RenderedView] = {}
        render_root = ATTEMPT_ROOT / "renders" / mesh_name / texture_name
        render_root.mkdir(parents=True)
        for camera in cameras:
            sampler.check()
            view = render_legacy_view(mesh, camera)
            _write_rgb_png(render_root / f"{camera.name}.png", view.rgb)
            views[camera.name] = view
        texture_views[texture_name] = views
    mask_root = ATTEMPT_ROOT / "masks" / mesh_name
    mask_root.mkdir(parents=True)
    for camera in cameras:
        _write_mask_png(
            mask_root / f"{camera.name}.png",
            texture_views["checker"][camera.name].object_mask,
        )
    return texture_views["checker"], texture_views["s1"]


def _comparison_sheet(
    all_views: dict[str, tuple[dict[str, RenderedView], dict[str, RenderedView]]],
) -> np.ndarray:
    """Compose four rows by five columns without resampling native pixels."""
    rows = []
    for mesh_name in ("canonical", "deformed-s0521-v0000"):
        checker_views, s1_views = all_views[mesh_name]
        for views in (checker_views, s1_views):
            rows.append(
                np.concatenate(
                    [views[name].rgb for name in FORMAL_CAMERA_NAMES],
                    axis=1,
                )
            )
    return np.concatenate(rows, axis=0)


def _write_failure(error: BaseException, last_completed_step: str) -> None:
    """Retain one no-clobber failure receipt inside the attempt root."""
    ATTEMPT_ROOT.mkdir(parents=True, exist_ok=True)
    _write_json(
        ATTEMPT_ROOT / "failure.json",
        {
            "exception_type": type(error).__name__,
            "message": str(error),
            "last_completed_step": last_completed_step,
        },
    )


def _run_formal_action(available_memory_bytes: int) -> int:
    """Execute one monitored formal attempt and retain any failure root."""
    try:
        ATTEMPT_ROOT.mkdir(parents=True)
    except FileExistsError:
        return 3
    sampler = _RssSampler()
    last_completed_step = "attempt_created"
    try:
        sampler.start()
        sampler.check()
        _verify_input_hash(CANONICAL_PATH, CANONICAL_SHA256, "canonical mesh")
        _verify_input_hash(DEFORMED_PATH, DEFORMED_SHA256, "deformed mesh")
        _verify_input_hash(S1_PATH, S1_SHA256, "S1 atlas")
        canonical_vertices, canonical_faces = load_mesh_arrays(CANONICAL_PATH)
        deformed_vertices, deformed_faces = load_mesh_arrays(DEFORMED_PATH)
        _validate_mesh_counts(canonical_vertices, canonical_faces, "canonical")
        _validate_mesh_counts(deformed_vertices, deformed_faces, "deformed")
        last_completed_step = "inputs_loaded"

        validate_oriented_face_rows(canonical_faces, deformed_faces)
        last_completed_step = "topology_validated"
        first_sidecar = generate_xatlas_sidecar(canonical_vertices, canonical_faces)
        second_sidecar = generate_xatlas_sidecar(canonical_vertices, canonical_faces)
        if not _sidecars_equal(first_sidecar, second_sidecar):
            raise ValueError("xatlas output differs across two frozen runs")
        sidecar_diagnostics = validate_uv_sidecar(
            first_sidecar,
            canonical_vertices,
            canonical_faces,
        )
        last_completed_step = "xatlas_determinism_validated"

        uv_root = ATTEMPT_ROOT / "uv"
        uv_root.mkdir()
        npz_path = uv_root / "kidney-anat-xatlas-v1.npz"
        uv_receipt_path = uv_root / "receipt.json"
        write_uv_sidecar(
            first_sidecar,
            CANONICAL_PATH,
            canonical_vertices,
            canonical_faces,
            npz_path,
            uv_receipt_path,
        )
        sidecar = read_uv_sidecar(
            npz_path,
            uv_receipt_path,
            CANONICAL_PATH,
            canonical_vertices,
            canonical_faces,
        )
        last_completed_step = "sidecar_written_and_read"

        textures_root = ATTEMPT_ROOT / "textures"
        textures_root.mkdir()
        copied_s1_path = textures_root / "s1-seed-0-dev-fold-0.png"
        shutil.copyfile(S1_PATH, copied_s1_path)
        if _file_sha256(copied_s1_path) != S1_SHA256:
            raise ValueError("copied S1 atlas SHA-256 differs")
        s1_rgb = _load_rgb(copied_s1_path)
        checker_rgb = build_calibration_texture()
        _write_rgb_png(textures_root / "checker-orientation-v1.png", checker_rgb)
        last_completed_step = "textures_written"

        diagnostics_root = ATTEMPT_ROOT / "diagnostics"
        diagnostics_root.mkdir()
        plane_vertices, plane_sidecar = _calibration_plane()
        plane_mesh = build_textured_mesh(
            plane_vertices,
            plane_sidecar,
            checker_rgb,
        )
        plane_camera = build_five_view_cameras(plane_vertices, plane_vertices)[0]
        plane_view = render_legacy_view(plane_mesh, plane_camera)
        plane_diagnostics = validate_uv_origin_plane(plane_view)
        _write_rgb_png(diagnostics_root / "uv-origin-plane.png", plane_view.rgb)
        _write_mask_png(
            diagnostics_root / "uv-origin-plane-mask.png",
            plane_view.object_mask,
        )
        _write_json(
            diagnostics_root / "uv-origin-plane.json",
            plane_diagnostics,
        )
        last_completed_step = "uv_origin_plane_validated"

        cameras = build_five_view_cameras(canonical_vertices, deformed_vertices)
        uv_render.validate_frozen_camera_receipts(_camera_receipts(cameras))
        all_views = {}
        render_diagnostics = {}
        for mesh_name, vertices in (
            ("canonical", canonical_vertices),
            ("deformed-s0521-v0000", deformed_vertices),
        ):
            checker_views, s1_views = _render_mesh_texture_set(
                mesh_name,
                vertices,
                sidecar,
                cameras,
                checker_rgb,
                s1_rgb,
                sampler,
            )
            all_views[mesh_name] = (checker_views, s1_views)
            render_diagnostics[mesh_name] = validate_render_set(
                checker_views,
                s1_views,
            )
        canonical_masks = all_views["canonical"][0]
        deformed_masks = all_views["deformed-s0521-v0000"][0]
        deformation_mask_difference = any(
            not np.array_equal(
                canonical_masks[name].object_mask,
                deformed_masks[name].object_mask,
            )
            for name in FORMAL_CAMERA_NAMES
        )
        if not deformation_mask_difference:
            raise ValueError("canonical and deformed masks do not differ")
        last_completed_step = "kidney_renders_validated"

        sheet = _comparison_sheet(all_views)
        _write_rgb_png(ATTEMPT_ROOT / "comparison-sheet.png", sheet)
        last_completed_step = "comparison_sheet_written"

        peak_rss_bytes = sampler.stop()
        sampler.check()
        telemetry = {
            "available_memory_bytes_before": available_memory_bytes,
            "peak_process_tree_rss_bytes": peak_rss_bytes,
            "rss_limit_bytes": MAX_PROCESS_TREE_RSS_BYTES,
            "sample_interval_seconds": RSS_SAMPLE_INTERVAL_SECONDS,
            "within_limit": peak_rss_bytes < MAX_PROCESS_TREE_RSS_BYTES,
            "worker_count": 1,
        }
        validation = {
            "all_gates_passed": True,
            "canonical_render_set": render_diagnostics["canonical"],
            "deformation_mask_difference": True,
            "deformed_render_set": render_diagnostics["deformed-s0521-v0000"],
            "deformed_topology_oriented_cycles_valid": True,
            "uv_origin_plane": plane_diagnostics,
            "uv_sidecar": sidecar_diagnostics,
            "xatlas_deterministic": True,
        }
        _write_json(ATTEMPT_ROOT / "telemetry.json", telemetry)
        _write_json(ATTEMPT_ROOT / "validation.json", validation)
        last_completed_step = "diagnostics_written"

        receipt_fields = {
            "schema": FORMAL_SCHEMA,
            "status": FORMAL_STATUS,
            "input_sha256": {
                "canonical": CANONICAL_SHA256,
                "deformed": DEFORMED_SHA256,
                "s1": S1_SHA256,
            },
            "camera_names": list(FORMAL_CAMERA_NAMES),
            "cameras": _camera_receipts(cameras),
            "render_count": 20,
            "mask_count": 10,
            "uv_receipt_sha256": _file_sha256(uv_receipt_path),
            "telemetry_sha256": _file_sha256(ATTEMPT_ROOT / "telemetry.json"),
            "validation_sha256": _file_sha256(ATTEMPT_ROOT / "validation.json"),
            "comparison_sheet_sha256": _file_sha256(
                ATTEMPT_ROOT / "comparison-sheet.png"
            ),
        }
        write_bundle_closure(ATTEMPT_ROOT, receipt_fields)
        last_completed_step = "bundle_closed"
        read_formal_bundle(ATTEMPT_ROOT)
        last_completed_step = "bundle_read_back"
        ATTEMPT_ROOT.rename(FORMAL_ROOT)
        return 0
    except Exception as error:
        try:
            sampler.stop()
        except Exception:
            pass
        try:
            _write_failure(error, last_completed_step)
        except (FileExistsError, OSError):
            pass
        return 4
    finally:
        try:
            sampler.stop()
        except Exception:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run only the exact `render-formal` action with no-clobber preflight."""
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments != ("render-formal",):
        return 2
    if FORMAL_ROOT.exists() or ATTEMPT_ROOT.exists():
        return 3
    available_memory_bytes = _available_memory_bytes()
    if available_memory_bytes < MIN_AVAILABLE_MEMORY_BYTES:
        try:
            ATTEMPT_ROOT.mkdir(parents=True)
            _write_failure(
                MemoryError("system-available memory is below 4000000000 bytes"),
                "output_roots_checked",
            )
        except (FileExistsError, OSError):
            pass
        return 4
    return _run_formal_action(available_memory_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
