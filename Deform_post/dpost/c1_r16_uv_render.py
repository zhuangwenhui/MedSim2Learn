"""Validate and persist external UV sidecars for canonical triangle meshes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


_ARRAY_NAMES = (
    "source_faces",
    "uv_vertex_to_source_vertex",
    "uv_faces",
    "uv_vertices",
)
_NPZ_FILES = frozenset(f"{name}.npy" for name in _ARRAY_NAMES)
_RECEIPT_SCHEMA = "c1-r16a-uv-sidecar-v1"
_CAMERA_VIEWS = (
    ("z-plus", (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ("y-minus", (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ("y-plus", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("iso-plus", (1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
    ("iso-minus", (-1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
)
_CAMERA_VIEW_NAMES = frozenset(name for name, _, _ in _CAMERA_VIEWS)
FORMAL_CAMERA_NAMES = tuple(name for name, _, _ in _CAMERA_VIEWS)
FORMAL_SCHEMA = "c1-r16a-formal-bundle-v2"
FORMAL_STATUS = "R16A_UV_TEXTURED_RENDER_V2_READY"
FROZEN_INPUT_SHA256 = {
    "canonical": "f0a301cf143fcb12b4a92ef6ca8ce326b45a71e393d7f18c806cc4802c5e3e2d",
    "deformed": "82915fe9e0eb1f7e7dec6f29c195fb7ec361fbace55d32f21a80ef601e099493",
    "s1": "2950145e810cf2844e8ec25c87c7474dbd39a6ec9df648b7e5fe9f0390b39a8e",
}
# Derived from the frozen canonical/deformed inputs identified above.
FROZEN_UNION_BBOX_CENTER = (
    1.1190934999999982,
    -2.6871764999999996,
    1.4713895000000008,
)
FROZEN_CAMERA_DISTANCE = 219.829014
_FORMAL_MESH_NAMES = ("canonical", "deformed-s0521-v0000")
_FORMAL_TEXTURE_NAMES = ("checker", "s1")
_FORMAL_RECEIPT_KEYS = {
    "artifact_hashes_sha256",
    "camera_names",
    "cameras",
    "comparison_sheet_sha256",
    "input_sha256",
    "mask_count",
    "render_count",
    "schema",
    "status",
    "telemetry_sha256",
    "uv_receipt_sha256",
    "validation_sha256",
}
_REGISTERED_COLORS = {
    "red": np.array((255, 0, 0), dtype=np.uint8),
    "green": np.array((0, 255, 0), dtype=np.uint8),
    "blue": np.array((0, 0, 255), dtype=np.uint8),
    "yellow": np.array((255, 255, 0), dtype=np.uint8),
}


@dataclass(frozen=True)
class UvSidecar:
    """An immutable UV topology sidecar for one canonical triangle mesh."""

    source_faces: np.ndarray
    uv_vertex_to_source_vertex: np.ndarray
    uv_faces: np.ndarray
    uv_vertices: np.ndarray
    generator: str
    generator_version: str

    def __post_init__(self) -> None:
        """Own the arrays so later caller mutations cannot alter the sidecar."""
        for name in _ARRAY_NAMES:
            owned = np.array(getattr(self, name), copy=True)
            owned.setflags(write=False)
            object.__setattr__(self, name, owned)


@dataclass(frozen=True)
class CameraSpec:
    """One fixed Open3D pinhole camera used for matched texture renders."""

    name: str
    intrinsic: object
    extrinsic: np.ndarray


@dataclass(frozen=True)
class RenderedView:
    """A captured RGB image together with its depth-derived object mask."""

    rgb: np.ndarray
    object_mask: np.ndarray


def build_textured_mesh(
    vertices: np.ndarray,
    sidecar: UvSidecar,
    texture_rgb: np.ndarray,
) -> object:
    """Build a one-material legacy Open3D mesh without altering UV orientation."""
    import open3d as o3d

    validate_uv_sidecar(sidecar, vertices, sidecar.source_faces)
    if (
        not isinstance(texture_rgb, np.ndarray)
        or texture_rgb.dtype != np.uint8
        or texture_rgb.ndim != 3
        or texture_rgb.shape[2] != 3
        or texture_rgb.shape[0] == 0
        or texture_rgb.shape[1] == 0
    ):
        raise ValueError("texture RGB must be a nonempty uint8 (H, W, 3) array")

    render_vertices = vertices[sidecar.uv_vertex_to_source_vertex]
    triangle_uvs = sidecar.uv_vertices[sidecar.uv_faces].reshape(-1, 2)
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(render_vertices),
        o3d.utility.Vector3iVector(sidecar.uv_faces),
    )
    mesh.triangle_uvs = o3d.utility.Vector2dVector(triangle_uvs)
    mesh.textures = [o3d.geometry.Image(texture_rgb)]
    mesh.triangle_material_ids = o3d.utility.IntVector([0] * len(sidecar.uv_faces))
    if (
        len(mesh.triangle_uvs) != 3 * len(mesh.triangles)
        or len(mesh.textures) != 1
        or not mesh.has_triangle_uvs()
        or not mesh.has_textures()
    ):
        raise ValueError("textured mesh does not satisfy the legacy UV contract")
    return mesh


def build_five_view_cameras(
    canonical_vertices: np.ndarray,
    deformed_vertices: np.ndarray,
) -> tuple[CameraSpec, ...]:
    """Create five shared-intrinsic cameras from the canonical/deformed union box."""
    from dpost.camera.geometry import intrinsic_matrix, look_at_extrinsic

    _require_vertices(canonical_vertices, "canonical vertices")
    _require_vertices(deformed_vertices, "deformed vertices")
    all_vertices = np.concatenate((canonical_vertices, deformed_vertices), axis=0)
    bbox_min = all_vertices.min(axis=0)
    bbox_max = all_vertices.max(axis=0)
    center = (bbox_min + bbox_max) / 2.0
    max_extent = float(np.max(bbox_max - bbox_min))
    if max_extent <= 0.0:
        raise ValueError("union bounding box must have positive extent")

    intrinsic = intrinsic_matrix(512, 512, 60.0)
    cameras = []
    for name, front_values, up_values in _CAMERA_VIEWS:
        front = np.asarray(front_values, dtype=np.float64)
        eye = center + front / np.linalg.norm(front) * (2.0 * max_extent)
        cameras.append(
            CameraSpec(
                name=name,
                intrinsic=intrinsic,
                extrinsic=look_at_extrinsic(eye, center, up_values),
            )
        )
    return tuple(cameras)


def render_legacy_view(mesh: object, camera: CameraSpec) -> RenderedView:
    """Capture one unlit textured view and its depth-derived mask in one window."""
    import open3d as o3d

    visualizer = o3d.visualization.Visualizer()
    try:
        created = visualizer.create_window(
            window_name="c1-r16a-legacy-render",
            width=512,
            height=512,
            visible=False,
        )
        if not created:
            raise RuntimeError("legacy Visualizer.create_window returned false")
        render_option = visualizer.get_render_option()
        render_option.background_color = np.array((0.02, 0.02, 0.02))
        render_option.light_on = False
        render_option.mesh_show_back_face = True
        if not visualizer.add_geometry(mesh):
            raise RuntimeError("legacy Visualizer could not add the textured mesh")

        parameters = o3d.camera.PinholeCameraParameters()
        parameters.intrinsic = camera.intrinsic
        parameters.extrinsic = np.asarray(camera.extrinsic, dtype=np.float64)
        view_control = visualizer.get_view_control()
        if not view_control.convert_from_pinhole_camera_parameters(
            parameters,
            allow_arbitrary=True,
        ):
            raise RuntimeError("legacy Visualizer rejected the supplied camera")
        visualizer.poll_events()
        visualizer.update_renderer()
        rgb_float = np.asarray(visualizer.capture_screen_float_buffer(do_render=True))
        depth = np.asarray(visualizer.capture_depth_float_buffer(do_render=False))
    finally:
        visualizer.destroy_window()

    rgb = np.rint(np.clip(rgb_float, 0.0, 1.0) * 255.0).astype(np.uint8)
    return RenderedView(rgb=rgb, object_mask=depth > 0.0)


def validate_uv_origin_plane(view: RenderedView) -> dict[str, object]:
    """Require the calibration-plane color centroids to preserve UV orientation."""
    _validate_rendered_view(view, "calibration view")
    diagnostics = _registered_color_diagnostics(view.rgb, view.object_mask)
    counts = {name: values["count"] for name, values in diagnostics.items()}
    if min(counts.values()) < 10_000:
        raise ValueError("calibration color count is below 10000 pixels")
    centroids = {name: values["centroid_xy"] for name, values in diagnostics.items()}
    if any(centroid is None for centroid in centroids.values()):
        raise ValueError("calibration color centroid is missing")
    red = centroids["red"]
    green = centroids["green"]
    blue = centroids["blue"]
    yellow = centroids["yellow"]
    if red is None or green is None or blue is None or yellow is None:
        raise ValueError("calibration color centroid is missing")
    if not (
        green[0] - red[0] >= 64.0
        and yellow[0] - blue[0] >= 64.0
        and blue[1] - red[1] >= 64.0
        and yellow[1] - green[1] >= 64.0
    ):
        raise ValueError(
            "calibration color centroids do not preserve the UV origin plane"
        )
    return {
        "color_counts": counts,
        "centroids_xy": centroids,
        "tolerance": 2,
        "minimum_color_count": 10_000,
        "minimum_separation_pixels": 64,
        "relations_valid": True,
    }


def validate_render_set(
    checker_views: Mapping[str, RenderedView],
    s1_views: Mapping[str, RenderedView],
) -> dict[str, object]:
    """Apply depth, calibration-color, variation, and paired-texture gates."""
    if (
        set(checker_views) != _CAMERA_VIEW_NAMES
        or set(s1_views) != _CAMERA_VIEW_NAMES
    ):
        raise ValueError("checker and S1 views must use the fixed five camera names")

    results: dict[str, object] = {}
    aggregate_color_counts = {name: 0 for name in _REGISTERED_COLORS}
    any_checker_variation_centroid_gate = False
    for name, checker in checker_views.items():
        s1 = s1_views[name]
        _validate_rendered_view(checker, f"checker view {name}")
        _validate_rendered_view(s1, f"S1 view {name}")
        if checker.rgb.shape != s1.rgb.shape:
            raise ValueError(f"checker and S1 RGB shapes differ for {name}")
        if not np.array_equal(checker.object_mask, s1.object_mask):
            raise ValueError(f"checker and S1 masks differ for {name}")

        mask = checker.object_mask
        occupancy = float(mask.mean())
        if not 0.01 <= occupancy <= 0.90:
            raise ValueError(f"mask occupancy is outside [0.01, 0.90] for {name}")
        color_diagnostics = _registered_color_diagnostics(checker.rgb, mask)
        color_counts = {
            color_name: result["count"]
            for color_name, result in color_diagnostics.items()
        }
        for color_name, count in color_counts.items():
            aggregate_color_counts[color_name] += count
        centroids = {
            color_name: result["centroid_xy"]
            for color_name, result in color_diagnostics.items()
        }
        centroid_values = tuple(
            centroid for centroid in centroids.values() if centroid is not None
        )
        max_centroid_separation = 0.0
        if len(centroid_values) >= 2:
            centroid_array = np.asarray(centroid_values, dtype=np.float64)
            separations = np.linalg.norm(
                centroid_array[:, None, :] - centroid_array[None, :, :],
                axis=2,
            )
            max_centroid_separation = float(np.max(separations))
        checker_std = float(np.std(checker.rgb[mask]))
        s1_std = float(np.std(s1.rgb[mask]))
        if s1_std <= 2.0:
            raise ValueError(f"S1 RGB standard deviation is not above 2 for {name}")
        checker_gate_satisfied = (
            checker_std > 5.0 and max_centroid_separation >= 16.0
        )
        any_checker_variation_centroid_gate |= checker_gate_satisfied
        different = np.any(
            np.abs(checker.rgb.astype(np.int16) - s1.rgb.astype(np.int16)) > 2,
            axis=2,
        ) & mask
        different_pixel_fraction = float(different.sum() / mask.sum())
        if different_pixel_fraction < 0.01:
            raise ValueError(
                f"checker and S1 differ in fewer than 1% of pixels for {name}"
            )
        results[name] = {
            "mask_occupancy": occupancy,
            "masks_equal": True,
            "checker_color_counts": color_counts,
            "checker_centroids_xy": centroids,
            "maximum_centroid_separation_pixels": max_centroid_separation,
            "checker_masked_rgb_std": checker_std,
            "checker_gate_satisfied": checker_gate_satisfied,
            "s1_masked_rgb_std": s1_std,
            "different_pixel_fraction": different_pixel_fraction,
        }

    if min(aggregate_color_counts.values()) < 64:
        raise ValueError("aggregate checker color count is below 64")
    if not any_checker_variation_centroid_gate:
        raise ValueError(
            "no checker view jointly satisfies variation and centroid separation"
        )
    return {
        "view_count": len(results),
        "thresholds": {
            "minimum_occupancy": 0.01,
            "maximum_occupancy": 0.90,
            "color_tolerance": 2,
            "minimum_checker_color_count": 64,
            "minimum_centroid_separation_pixels": 16,
            "minimum_checker_std": 5,
            "minimum_s1_std": 2,
            "minimum_different_pixel_fraction": 0.01,
            "checker_variation_centroid_scope": "at_least_one_view",
        },
        "aggregate_checker_color_counts": aggregate_color_counts,
        "checker_variation_centroid_gate_valid": True,
        "views": results,
    }


def build_calibration_texture() -> np.ndarray:
    """Build the frozen asymmetric four-quadrant UV calibration texture."""
    texture = np.zeros((512, 512, 3), dtype=np.uint8)
    texture[:256, :256] = (255, 0, 0)
    texture[:256, 256:] = (0, 255, 0)
    texture[256:, :256] = (0, 0, 255)
    texture[256:, 256:] = (255, 255, 0)
    texture[252:260, :] = 0
    texture[:, 252:260] = 0
    texture[32:104, 32:48] = 255
    texture[32:104, 96:112] = 255
    texture[88:104, 48:96] = 255
    for offset in range(8):
        y_start = 32 + offset * 8
        texture[
            y_start : y_start + 8,
            384 + offset * 8 : 400 + offset * 8,
        ] = 255
        texture[
            y_start : y_start + 8,
            496 - (offset + 1) * 8 : 512 - offset * 8,
        ] = 255
    return texture


def write_bundle_closure(
    root: Path,
    receipt_fields: Mapping[str, object],
) -> dict[str, str]:
    """Write the no-clobber manifest and receipt for one exact formal tree."""
    bundle_root = Path(root)
    manifest_path = bundle_root / "artifact-hashes.json"
    receipt_path = bundle_root / "receipt.json"
    if manifest_path.exists() or receipt_path.exists():
        raise FileExistsError("formal bundle closure files already exist")
    observed_paths = _recursive_file_paths(bundle_root)
    expected_paths = _formal_content_paths()
    if observed_paths != expected_paths:
        raise ValueError("formal bundle content tree differs before closure")
    artifact_hashes = {
        relative_path: _file_sha256(bundle_root / relative_path)
        for relative_path in sorted(expected_paths)
    }
    _write_json_object_exclusive(manifest_path, artifact_hashes)
    receipt = dict(receipt_fields)
    if "artifact_hashes_sha256" in receipt:
        raise ValueError("formal bundle receipt predefines manifest hash")
    receipt["artifact_hashes_sha256"] = _file_sha256(manifest_path)
    _write_json_object_exclusive(receipt_path, receipt)
    return artifact_hashes


def read_formal_bundle(root: Path) -> dict[str, object]:
    """Read one R16A bundle only after its exact tree and gates close."""
    try:
        return _read_formal_bundle(Path(root))
    except (KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("formal bundle"):
            raise
        raise ValueError("formal bundle validation failed") from error


def _read_formal_bundle(root: Path) -> dict[str, object]:
    """Implement strict formal-bundle validation for the public reader."""
    if not root.is_dir():
        raise ValueError("formal bundle root is not a directory")
    expected_content = _formal_content_paths()
    expected_all = expected_content | {"artifact-hashes.json", "receipt.json"}
    if _recursive_file_paths(root) != expected_all:
        raise ValueError("formal bundle recursive file tree differs")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("formal bundle contains a symbolic link")

    manifest_path = root / "artifact-hashes.json"
    artifact_hashes = _load_json_object(manifest_path, "formal bundle manifest")
    receipt = _load_json_object(root / "receipt.json", "formal bundle receipt")
    if set(artifact_hashes) != expected_content:
        raise ValueError("formal bundle manifest path set differs")
    if set(receipt) != _FORMAL_RECEIPT_KEYS:
        raise ValueError("formal bundle receipt schema differs")
    if receipt["artifact_hashes_sha256"] != _file_sha256(manifest_path):
        raise ValueError("formal bundle manifest hash differs")
    for relative_path, digest in artifact_hashes.items():
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or _file_sha256(root / relative_path) != digest
        ):
            raise ValueError("formal bundle content hash differs")

    _validate_formal_receipt(receipt, artifact_hashes)
    telemetry = _load_json_object(root / "telemetry.json", "formal telemetry")
    validation = _load_json_object(root / "validation.json", "formal validation")
    _, uv_receipt, uv_diagnostics = _read_uv_sidecar_payload(
        root / "uv/kidney-anat-xatlas-v1.npz",
        root / "uv/receipt.json",
        expected_canonical_sha256=FROZEN_INPUT_SHA256["canonical"],
        expected_generator="xatlas",
        expected_generator_version="0.0.11",
    )
    origin_plane = _load_json_object(
        root / "diagnostics/uv-origin-plane.json",
        "formal UV-origin diagnostics",
    )
    _validate_formal_telemetry(telemetry)
    _validate_formal_gates(validation)
    image_diagnostics = _validate_formal_images(root)
    if origin_plane != image_diagnostics["uv_origin_plane"]:
        raise ValueError("formal bundle UV-origin diagnostics differ")
    if uv_diagnostics != validation["uv_sidecar"]:
        raise ValueError("formal bundle UV sidecar diagnostics differ")
    if validation["uv_origin_plane"] != image_diagnostics["uv_origin_plane"]:
        raise ValueError("formal bundle UV-origin validation differs")
    if (
        validation["canonical_render_set"]
        != image_diagnostics["canonical_render_set"]
        or validation["deformed_render_set"]
        != image_diagnostics["deformed_render_set"]
        or validation["deformation_mask_difference"]
        != image_diagnostics["deformation_mask_difference"]
    ):
        raise ValueError("formal bundle saved-image validation differs")
    return {
        "receipt": receipt,
        "artifact_hashes": artifact_hashes,
        "telemetry": telemetry,
        "validation": validation,
        "uv_receipt": uv_receipt,
        "uv_origin_plane": origin_plane,
    }


def _validate_formal_receipt(
    receipt: Mapping[str, object],
    artifact_hashes: Mapping[str, object],
) -> None:
    """Require the final receipt to bind all frozen R16A identities."""
    expected_values = {
        "schema": FORMAL_SCHEMA,
        "status": FORMAL_STATUS,
        "input_sha256": FROZEN_INPUT_SHA256,
        "camera_names": list(FORMAL_CAMERA_NAMES),
        "render_count": 20,
        "mask_count": 10,
        "uv_receipt_sha256": artifact_hashes["uv/receipt.json"],
        "telemetry_sha256": artifact_hashes["telemetry.json"],
        "validation_sha256": artifact_hashes["validation.json"],
        "comparison_sheet_sha256": artifact_hashes["comparison-sheet.png"],
    }
    for key, expected in expected_values.items():
        if receipt[key] != expected:
            raise ValueError(f"formal bundle receipt field differs: {key}")
    if (
        artifact_hashes["textures/s1-seed-0-dev-fold-0.png"]
        != FROZEN_INPUT_SHA256["s1"]
    ):
        raise ValueError("formal bundle frozen S1 content identity differs")
    validate_frozen_camera_receipts(receipt["cameras"])


def validate_frozen_camera_receipts(cameras: object) -> None:
    """Require the frozen intrinsic, rotations, target, and camera distance."""
    if not isinstance(cameras, list) or len(cameras) != 5:
        raise ValueError("formal bundle serialized camera count differs")
    if [camera.get("name") for camera in cameras] != list(FORMAL_CAMERA_NAMES):
        raise ValueError("formal bundle serialized camera names differ")
    focal_length = 256.0 / np.tan(np.deg2rad(60.0) / 2.0)
    expected_intrinsic = np.array(
        [
            [focal_length, 0.0, 255.5],
            [0.0, focal_length, 255.5],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    eyes = []
    forward_vectors = []
    for camera, (_, front_values, up_values) in zip(
        cameras,
        _CAMERA_VIEWS,
        strict=True,
    ):
        if not isinstance(camera, dict) or set(camera) != {
            "name",
            "intrinsic",
            "extrinsic",
        }:
            raise ValueError("formal bundle serialized camera schema differs")
        intrinsic = np.asarray(camera["intrinsic"])
        extrinsic = np.asarray(camera["extrinsic"])
        if (
            intrinsic.shape != (3, 3)
            or extrinsic.shape != (4, 4)
            or not np.issubdtype(intrinsic.dtype, np.number)
            or not np.issubdtype(extrinsic.dtype, np.number)
            or not np.isfinite(intrinsic).all()
            or not np.isfinite(extrinsic).all()
        ):
            raise ValueError("formal bundle serialized camera matrix differs")
        if not np.allclose(intrinsic, expected_intrinsic, rtol=0.0, atol=1e-12):
            raise ValueError("formal bundle camera intrinsic differs")
        if not np.allclose(
            extrinsic[3],
            np.array((0.0, 0.0, 0.0, 1.0)),
            rtol=0.0,
            atol=1e-12,
        ):
            raise ValueError("formal bundle camera homogeneous row differs")
        expected_forward = -np.asarray(front_values, dtype=np.float64)
        expected_forward /= np.linalg.norm(expected_forward)
        up = np.asarray(up_values, dtype=np.float64)
        expected_right = np.cross(expected_forward, up)
        expected_right /= np.linalg.norm(expected_right)
        expected_down = np.cross(expected_forward, expected_right)
        expected_rotation = np.stack(
            (expected_right, expected_down, expected_forward),
            axis=0,
        )
        rotation = extrinsic[:3, :3]
        if not np.allclose(
            rotation,
            expected_rotation,
            rtol=0.0,
            atol=1e-12,
        ):
            raise ValueError("formal bundle camera rotation differs")
        eyes.append(-rotation.T @ extrinsic[:3, 3])
        forward_vectors.append(rotation[2])

    coefficient_rows = []
    for forward in forward_vectors:
        coefficient_rows.append(
            np.concatenate((np.eye(3), -forward[:, None]), axis=1)
        )
    coefficients = np.concatenate(coefficient_rows, axis=0)
    observations = np.concatenate(eyes)
    solution, _, _, _ = np.linalg.lstsq(
        coefficients,
        observations,
        rcond=None,
    )
    target = solution[:3]
    distance = float(solution[3])
    if distance <= 0.0 or not np.allclose(
        coefficients @ solution,
        observations,
        rtol=0.0,
        atol=1e-9,
    ):
        raise ValueError("formal bundle cameras lack a common target and distance")
    if not np.allclose(
        target,
        np.asarray(FROZEN_UNION_BBOX_CENTER, dtype=np.float64),
        rtol=0.0,
        atol=1e-9,
    ):
        raise ValueError("formal bundle camera target differs from frozen union box")
    if not np.isclose(
        distance,
        FROZEN_CAMERA_DISTANCE,
        rtol=0.0,
        atol=1e-9,
    ):
        raise ValueError("formal bundle camera distance differs from frozen union box")
    for eye, forward in zip(eyes, forward_vectors, strict=True):
        if not np.allclose(
            eye + forward * distance,
            target,
            rtol=0.0,
            atol=1e-9,
        ):
            raise ValueError("formal bundle camera target geometry differs")


def _validate_formal_telemetry(telemetry: Mapping[str, object]) -> None:
    """Require one-worker 50-ms telemetry below the frozen RSS ceiling."""
    expected_keys = {
        "available_memory_bytes_before",
        "peak_process_tree_rss_bytes",
        "rss_limit_bytes",
        "sample_interval_seconds",
        "within_limit",
        "worker_count",
    }
    if set(telemetry) != expected_keys:
        raise ValueError("formal bundle telemetry schema differs")
    available = telemetry["available_memory_bytes_before"]
    peak = telemetry["peak_process_tree_rss_bytes"]
    if (
        not isinstance(available, int)
        or isinstance(available, bool)
        or available < 4_000_000_000
        or not isinstance(peak, int)
        or isinstance(peak, bool)
        or peak < 0
        or peak >= 500_000_000
        or telemetry["rss_limit_bytes"] != 500_000_000
        or telemetry["sample_interval_seconds"] != 0.05
        or telemetry["within_limit"] is not True
        or telemetry["worker_count"] != 1
    ):
        raise ValueError("formal bundle telemetry gate differs")


def _validate_formal_gates(validation: Mapping[str, object]) -> None:
    """Require every topology, determinism, render, and deformation gate."""
    expected_keys = {
        "all_gates_passed",
        "canonical_render_set",
        "deformation_mask_difference",
        "deformed_render_set",
        "deformed_topology_oriented_cycles_valid",
        "uv_origin_plane",
        "uv_sidecar",
        "xatlas_deterministic",
    }
    if set(validation) != expected_keys:
        raise ValueError("formal bundle validation schema differs")
    if (
        validation["all_gates_passed"] is not True
        or validation["deformation_mask_difference"] is not True
        or validation["deformed_topology_oriented_cycles_valid"] is not True
        or validation["xatlas_deterministic"] is not True
    ):
        raise ValueError("formal bundle boolean validation gate failed")
    origin = validation["uv_origin_plane"]
    sidecar = validation["uv_sidecar"]
    if not isinstance(origin, dict) or origin.get("relations_valid") is not True:
        raise ValueError("formal bundle UV-origin gate failed")
    if (
        not isinstance(sidecar, dict)
        or sidecar.get("oriented_cycles_valid") is not True
    ):
        raise ValueError("formal bundle UV-sidecar gate failed")
    for key in ("canonical_render_set", "deformed_render_set"):
        render_set = validation[key]
        if (
            not isinstance(render_set, dict)
            or render_set.get("view_count") != 5
            or set(render_set.get("views", {})) != set(FORMAL_CAMERA_NAMES)
            or render_set.get("checker_variation_centroid_gate_valid") is not True
        ):
            raise ValueError("formal bundle render-set summary differs")
        counts = render_set.get("aggregate_checker_color_counts")
        if not isinstance(counts, dict) or min(counts.values(), default=0) < 64:
            raise ValueError("formal bundle checker color gate failed")
        for view in render_set["views"].values():
            if (
                view.get("masks_equal") is not True
                or not 0.01 <= view.get("mask_occupancy", -1.0) <= 0.90
                or view.get("s1_masked_rgb_std", 0.0) <= 2.0
                or view.get("different_pixel_fraction", 0.0) < 0.01
            ):
                raise ValueError("formal bundle per-view validation gate failed")


def _validate_formal_images(root: Path) -> dict[str, object]:
    """Recompute render and origin gates from saved native image artifacts."""
    render_paths = sorted((root / "renders").rglob("*.png"))
    mask_paths = sorted((root / "masks").rglob("*.png"))
    if len(render_paths) != 20 or len(mask_paths) != 10:
        raise ValueError("formal bundle image count differs")
    render_sets = {}
    mesh_masks = {}
    for mesh_name in _FORMAL_MESH_NAMES:
        masks = {}
        checker_views = {}
        s1_views = {}
        for view_name in FORMAL_CAMERA_NAMES:
            mask_values = _require_png(
                root / "masks" / mesh_name / f"{view_name}.png",
                "L",
                (512, 512),
            )
            if not set(np.unique(mask_values)).issubset({0, 255}):
                raise ValueError("formal bundle mask is not binary")
            mask = mask_values == 255
            masks[view_name] = mask
            checker_views[view_name] = RenderedView(
                _require_png(
                    root
                    / "renders"
                    / mesh_name
                    / "checker"
                    / f"{view_name}.png",
                    "RGB",
                    (512, 512),
                ),
                mask,
            )
            s1_views[view_name] = RenderedView(
                _require_png(
                    root
                    / "renders"
                    / mesh_name
                    / "s1"
                    / f"{view_name}.png",
                    "RGB",
                    (512, 512),
                ),
                mask,
            )
        mesh_masks[mesh_name] = masks
        render_sets[mesh_name] = validate_render_set(checker_views, s1_views)
    checker = _require_png(
        root / "textures/checker-orientation-v1.png",
        "RGB",
        (512, 512),
    )
    if not np.array_equal(checker, build_calibration_texture()):
        raise ValueError("formal bundle calibration texture differs")
    _require_png(
        root / "textures/s1-seed-0-dev-fold-0.png",
        "RGB",
        (512, 512),
    )
    plane_rgb = _require_png(
        root / "diagnostics/uv-origin-plane.png",
        "RGB",
        (512, 512),
    )
    plane_mask_values = _require_png(
        root / "diagnostics/uv-origin-plane-mask.png",
        "L",
        (512, 512),
    )
    if not set(np.unique(plane_mask_values)).issubset({0, 255}):
        raise ValueError("formal bundle UV-origin mask is not binary")
    _require_png(root / "comparison-sheet.png", "RGB", (2560, 2048))
    plane_diagnostics = validate_uv_origin_plane(
        RenderedView(
            plane_rgb,
            plane_mask_values == 255,
        )
    )
    deformation_mask_difference = any(
        not np.array_equal(
            mesh_masks["canonical"][name],
            mesh_masks["deformed-s0521-v0000"][name],
        )
        for name in FORMAL_CAMERA_NAMES
    )
    if not deformation_mask_difference:
        raise ValueError("formal bundle saved deformation masks do not differ")
    return {
        "canonical_render_set": render_sets["canonical"],
        "deformed_render_set": render_sets["deformed-s0521-v0000"],
        "deformation_mask_difference": True,
        "uv_origin_plane": plane_diagnostics,
    }


def _require_png(path: Path, mode: str, size: tuple[int, int]) -> np.ndarray:
    """Load one PNG fully and enforce its mode and dimensions."""
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.mode != mode or image.size != size:
            raise ValueError("formal bundle PNG contract differs")
        return np.array(image, copy=True)


def _formal_content_paths() -> set[str]:
    """Return the exact pre-closure file set for one R16A bundle."""
    paths = {
        "uv/kidney-anat-xatlas-v1.npz",
        "uv/receipt.json",
        "textures/checker-orientation-v1.png",
        "textures/s1-seed-0-dev-fold-0.png",
        "diagnostics/uv-origin-plane.png",
        "diagnostics/uv-origin-plane-mask.png",
        "diagnostics/uv-origin-plane.json",
        "comparison-sheet.png",
        "telemetry.json",
        "validation.json",
    }
    for mesh_name in _FORMAL_MESH_NAMES:
        for texture_name in _FORMAL_TEXTURE_NAMES:
            for view_name in FORMAL_CAMERA_NAMES:
                paths.add(
                    f"renders/{mesh_name}/{texture_name}/{view_name}.png"
                )
        for view_name in FORMAL_CAMERA_NAMES:
            paths.add(f"masks/{mesh_name}/{view_name}.png")
    return paths


def _recursive_file_paths(root: Path) -> set[str]:
    """Collect recursive file paths with normalized manifest separators."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    """Load a UTF-8 JSON object for strict bundle validation."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _write_json_object_exclusive(path: Path, value: object) -> None:
    """Write one closure JSON file with an atomic no-clobber open mode."""
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")


def load_mesh_arrays(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load owned vertex and triangle arrays from an Open3D-supported mesh."""
    import open3d as o3d

    mesh_path = Path(path)
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices = np.array(np.asarray(mesh.vertices), copy=True)
    faces = np.array(np.asarray(mesh.triangles), copy=True)
    _require_vertices(vertices, "mesh vertices")
    _require_face_rows(faces, "mesh faces")
    return vertices, faces


def validate_oriented_face_rows(
    reference: np.ndarray,
    candidate: np.ndarray,
) -> None:
    """Require each candidate row to preserve its reference triangle winding."""
    _require_face_rows(reference, "reference faces")
    _require_face_rows(candidate, "candidate faces")
    if reference.shape != candidate.shape:
        raise ValueError("UV face rows have a different shape")

    cyclic_rows = np.stack(
        (
            reference,
            np.roll(reference, -1, axis=1),
            np.roll(reference, -2, axis=1),
        ),
        axis=1,
    )
    matches = np.any(np.all(cyclic_rows == candidate[:, None, :], axis=2), axis=1)
    if not np.all(matches):
        row_index = int(np.flatnonzero(~matches)[0])
        raise ValueError(f"UV face row differs at row {row_index}")


def generate_xatlas_sidecar(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> UvSidecar:
    """Generate a UV sidecar with the pinned xatlas Python binding."""
    import xatlas

    mapping, uv_faces, uv_vertices = xatlas.parametrize(vertices, faces)
    return UvSidecar(
        source_faces=faces,
        uv_vertex_to_source_vertex=mapping,
        uv_faces=uv_faces,
        uv_vertices=np.asarray(uv_vertices, dtype=np.float64),
        generator="xatlas",
        generator_version=importlib.metadata.version("xatlas"),
    )


def validate_uv_sidecar(
    sidecar: UvSidecar,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
) -> dict[str, object]:
    """Validate closure, topology, UV bounds, and non-degenerate UV areas."""
    _require_vertices(canonical_vertices, "canonical vertices")
    _require_face_rows(canonical_faces, "canonical faces")
    _require_face_rows(sidecar.source_faces, "source faces")
    _require_integer_vector(
        sidecar.uv_vertex_to_source_vertex,
        "UV source mapping",
    )
    _require_face_rows(sidecar.uv_faces, "UV faces")
    _require_uv_vertices(sidecar.uv_vertices)

    if (
        sidecar.source_faces.dtype != canonical_faces.dtype
        or not np.array_equal(sidecar.source_faces, canonical_faces)
    ):
        raise ValueError("source faces differ from canonical faces")
    if np.any(canonical_faces < 0) or np.any(
        canonical_faces >= len(canonical_vertices)
    ):
        raise ValueError("canonical source face index is out of range")
    if sidecar.uv_faces.shape[0] != sidecar.source_faces.shape[0]:
        raise ValueError("UV face count differs from source face count")

    mapping = sidecar.uv_vertex_to_source_vertex
    if np.any(mapping < 0) or np.any(mapping >= len(canonical_vertices)):
        raise ValueError("UV source vertex index is out of range")
    if np.any(sidecar.uv_faces < 0) or np.any(sidecar.uv_faces >= len(mapping)):
        raise ValueError("UV face index is out of range")

    recovered_faces = mapping[sidecar.uv_faces]
    validate_oriented_face_rows(sidecar.source_faces, recovered_faces)

    source_triangles = canonical_vertices[canonical_faces]
    uv_triangles = sidecar.uv_vertices[sidecar.uv_faces]
    source_area_twice = np.linalg.norm(
        np.cross(
            source_triangles[:, 1] - source_triangles[:, 0],
            source_triangles[:, 2] - source_triangles[:, 0],
        ),
        axis=1,
    )
    uv_area_twice = np.abs(
        (uv_triangles[:, 1, 0] - uv_triangles[:, 0, 0])
        * (uv_triangles[:, 2, 1] - uv_triangles[:, 0, 1])
        - (uv_triangles[:, 1, 1] - uv_triangles[:, 0, 1])
        * (uv_triangles[:, 2, 0] - uv_triangles[:, 0, 0])
    )
    nondegenerate_source = source_area_twice > 0.0
    if np.any(uv_area_twice[nondegenerate_source] == 0.0):
        raise ValueError("non-degenerate source face has zero UV area")

    used_uv_vertices = int(np.unique(sidecar.uv_faces).size)
    return {
        "source_face_count": int(sidecar.source_faces.shape[0]),
        "uv_face_count": int(sidecar.uv_faces.shape[0]),
        "uv_vertex_count": int(sidecar.uv_vertices.shape[0]),
        "used_uv_vertex_count": used_uv_vertices,
        "uv_vertex_utilization": float(used_uv_vertices / len(sidecar.uv_vertices)),
        "uv_bounds": [
            [float(value) for value in sidecar.uv_vertices.min(axis=0)],
            [float(value) for value in sidecar.uv_vertices.max(axis=0)],
        ],
        "nondegenerate_source_face_count": int(np.count_nonzero(nondegenerate_source)),
        "nonzero_uv_face_count": int(np.count_nonzero(uv_area_twice > 0.0)),
        "oriented_cycles_valid": True,
    }


def write_uv_sidecar(
    sidecar: UvSidecar,
    canonical_path: Path,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    npz_path: Path,
    receipt_path: Path,
) -> dict[str, object]:
    """Write the fixed NPZ payload and its hash-closed JSON receipt."""
    diagnostics = validate_uv_sidecar(
        sidecar,
        canonical_vertices,
        canonical_faces,
    )
    canonical_file = Path(canonical_path)
    sidecar_path = Path(npz_path)
    receipt_file = Path(receipt_path)
    np.savez(
        sidecar_path,
        source_faces=sidecar.source_faces,
        uv_vertex_to_source_vertex=sidecar.uv_vertex_to_source_vertex,
        uv_faces=sidecar.uv_faces,
        uv_vertices=sidecar.uv_vertices,
    )
    receipt = {
        "schema": _RECEIPT_SCHEMA,
        "canonical_file_sha256": _file_sha256(canonical_file),
        "arrays": {
            name: _array_receipt(getattr(sidecar, name)) for name in _ARRAY_NAMES
        },
        "generator": sidecar.generator,
        "generator_version": sidecar.generator_version,
        "chart_diagnostics": diagnostics,
        "recovered_source_faces_sha256": _array_sha256(
            sidecar.uv_vertex_to_source_vertex[sidecar.uv_faces]
        ),
        "oriented_cycles_valid": True,
        "npz_sha256": _file_sha256(sidecar_path),
    }
    receipt_file.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def read_uv_sidecar(
    npz_path: Path,
    receipt_path: Path,
    canonical_path: Path,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
) -> UvSidecar:
    """Read a sidecar only when its payload and receipt close exactly."""
    sidecar_path = Path(npz_path)
    receipt_file = Path(receipt_path)
    sidecar, receipt, _ = _read_uv_sidecar_payload(
        sidecar_path,
        receipt_file,
        expected_canonical_sha256=_file_sha256(Path(canonical_path)),
    )
    diagnostics = validate_uv_sidecar(
        sidecar,
        canonical_vertices,
        canonical_faces,
    )
    recovered_hash = _array_sha256(
        sidecar.uv_vertex_to_source_vertex[sidecar.uv_faces]
    )
    if receipt["recovered_source_faces_sha256"] != recovered_hash:
        raise ValueError("recovered source face hash differs from receipt")
    if receipt["chart_diagnostics"] != diagnostics:
        raise ValueError("chart diagnostics differ from receipt")
    return sidecar


def _read_uv_sidecar_payload(
    npz_path: Path,
    receipt_path: Path,
    *,
    expected_canonical_sha256: str,
    expected_generator: str | None = None,
    expected_generator_version: str | None = None,
) -> tuple[UvSidecar, dict[str, object], dict[str, object]]:
    """Close one UV payload and receipt without external mesh coordinates."""
    sidecar_path = Path(npz_path)
    receipt = _read_receipt(Path(receipt_path))
    if receipt["canonical_file_sha256"] != expected_canonical_sha256:
        raise ValueError("canonical file hash differs from receipt")
    if receipt["npz_sha256"] != _file_sha256(sidecar_path):
        raise ValueError("NPZ hash differs from receipt")
    if (
        expected_generator is not None
        and receipt["generator"] != expected_generator
    ):
        raise ValueError("UV generator differs from the frozen contract")
    if (
        expected_generator_version is not None
        and receipt["generator_version"] != expected_generator_version
    ):
        raise ValueError("UV generator version differs from the frozen contract")

    _validate_npz_files(sidecar_path)
    with np.load(sidecar_path, allow_pickle=False) as archive:
        if set(archive.files) != set(_ARRAY_NAMES):
            raise ValueError("NPZ keys differ from sidecar schema")
        arrays = {name: archive[name] for name in _ARRAY_NAMES}
    for name, array in arrays.items():
        if receipt["arrays"][name] != _array_receipt(array):
            raise ValueError(f"array receipt differs for {name}")

    sidecar = UvSidecar(
        source_faces=arrays["source_faces"],
        uv_vertex_to_source_vertex=arrays["uv_vertex_to_source_vertex"],
        uv_faces=arrays["uv_faces"],
        uv_vertices=arrays["uv_vertices"],
        generator=receipt["generator"],
        generator_version=receipt["generator_version"],
    )
    diagnostics = _validate_uv_sidecar_payload_diagnostics(
        sidecar,
        receipt["chart_diagnostics"],
    )
    recovered_hash = _array_sha256(
        sidecar.uv_vertex_to_source_vertex[sidecar.uv_faces]
    )
    if receipt["recovered_source_faces_sha256"] != recovered_hash:
        raise ValueError("recovered source face hash differs from receipt")
    if receipt["oriented_cycles_valid"] is not True:
        raise ValueError("oriented-cycle receipt result is not true")
    return sidecar, receipt, diagnostics


def _validate_uv_sidecar_payload_diagnostics(
    sidecar: UvSidecar,
    claimed_diagnostics: object,
) -> dict[str, object]:
    """Recompute every UV diagnostic available without source coordinates."""
    _require_face_rows(sidecar.source_faces, "source faces")
    _require_integer_vector(
        sidecar.uv_vertex_to_source_vertex,
        "UV source mapping",
    )
    _require_face_rows(sidecar.uv_faces, "UV faces")
    _require_uv_vertices(sidecar.uv_vertices)
    if not isinstance(claimed_diagnostics, dict):
        raise ValueError("chart diagnostics must be a JSON object")
    expected_keys = {
        "source_face_count",
        "uv_face_count",
        "uv_vertex_count",
        "used_uv_vertex_count",
        "uv_vertex_utilization",
        "uv_bounds",
        "nondegenerate_source_face_count",
        "nonzero_uv_face_count",
        "oriented_cycles_valid",
    }
    if set(claimed_diagnostics) != expected_keys:
        raise ValueError("chart diagnostic keys differ from the sidecar schema")
    if sidecar.uv_faces.shape[0] != sidecar.source_faces.shape[0]:
        raise ValueError("UV face count differs from source face count")
    mapping = sidecar.uv_vertex_to_source_vertex
    if np.any(mapping < 0):
        raise ValueError("UV source vertex index is negative")
    if np.any(sidecar.uv_faces < 0) or np.any(sidecar.uv_faces >= len(mapping)):
        raise ValueError("UV face index is out of range")
    recovered_faces = mapping[sidecar.uv_faces]
    validate_oriented_face_rows(sidecar.source_faces, recovered_faces)

    uv_triangles = sidecar.uv_vertices[sidecar.uv_faces]
    uv_area_twice = np.abs(
        (uv_triangles[:, 1, 0] - uv_triangles[:, 0, 0])
        * (uv_triangles[:, 2, 1] - uv_triangles[:, 0, 1])
        - (uv_triangles[:, 1, 1] - uv_triangles[:, 0, 1])
        * (uv_triangles[:, 2, 0] - uv_triangles[:, 0, 0])
    )
    used_uv_vertices = int(np.unique(sidecar.uv_faces).size)
    nondegenerate_count = claimed_diagnostics["nondegenerate_source_face_count"]
    if (
        not isinstance(nondegenerate_count, int)
        or isinstance(nondegenerate_count, bool)
        or not 0 <= nondegenerate_count <= len(sidecar.source_faces)
    ):
        raise ValueError("non-degenerate source-face count is invalid")
    diagnostics = {
        "source_face_count": int(sidecar.source_faces.shape[0]),
        "uv_face_count": int(sidecar.uv_faces.shape[0]),
        "uv_vertex_count": int(sidecar.uv_vertices.shape[0]),
        "used_uv_vertex_count": used_uv_vertices,
        "uv_vertex_utilization": float(used_uv_vertices / len(sidecar.uv_vertices)),
        "uv_bounds": [
            [float(value) for value in sidecar.uv_vertices.min(axis=0)],
            [float(value) for value in sidecar.uv_vertices.max(axis=0)],
        ],
        "nondegenerate_source_face_count": nondegenerate_count,
        "nonzero_uv_face_count": int(np.count_nonzero(uv_area_twice > 0.0)),
        "oriented_cycles_valid": True,
    }
    if diagnostics["nonzero_uv_face_count"] < nondegenerate_count:
        raise ValueError("non-degenerate source face has zero UV area")
    if claimed_diagnostics != diagnostics:
        raise ValueError("chart diagnostics differ from sidecar payload")
    return diagnostics


def _validate_rendered_view(view: RenderedView, label: str) -> None:
    """Require an RGB uint8 image and aligned boolean depth mask."""
    if not isinstance(view, RenderedView):
        raise ValueError(f"{label} must be a RenderedView")
    if (
        not isinstance(view.rgb, np.ndarray)
        or view.rgb.dtype != np.uint8
        or view.rgb.ndim != 3
        or view.rgb.shape[2] != 3
    ):
        raise ValueError(f"{label} RGB must be a uint8 (H, W, 3) array")
    if (
        not isinstance(view.object_mask, np.ndarray)
        or view.object_mask.dtype != np.bool_
        or view.object_mask.shape != view.rgb.shape[:2]
    ):
        raise ValueError(f"{label} object mask must be an aligned boolean array")


def _registered_color_diagnostics(
    rgb: np.ndarray,
    object_mask: np.ndarray,
) -> dict[str, dict[str, object]]:
    """Measure registered calibration colors within an already-validated mask."""
    diagnostics: dict[str, dict[str, object]] = {}
    rgb_signed = rgb.astype(np.int16)
    for name, color in _REGISTERED_COLORS.items():
        matches = np.all(np.abs(rgb_signed - color.astype(np.int16)) <= 2, axis=2)
        matches &= object_mask
        ys, xs = np.nonzero(matches)
        count = int(len(xs))
        diagnostics[name] = {
            "count": count,
            "centroid_xy": (
                None
                if count == 0
                else [float(xs.mean()), float(ys.mean())]
            ),
        }
    return diagnostics


def _require_vertices(vertices: np.ndarray, label: str) -> None:
    """Require finite three-dimensional numeric vertex rows without casting."""
    if (
        not isinstance(vertices, np.ndarray)
        or vertices.ndim != 2
        or vertices.shape[1] != 3
        or vertices.dtype != np.float64
        or not np.isfinite(vertices).all()
    ):
        raise ValueError(f"{label} must be a finite float64 (N, 3) array")


def _require_face_rows(faces: np.ndarray, label: str) -> None:
    """Require triangle-index rows without coercing topology values or dtype."""
    if (
        not isinstance(faces, np.ndarray)
        or faces.ndim != 2
        or faces.shape[1] != 3
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError(f"{label} must be an integer (N, 3) array")


def _require_integer_vector(values: np.ndarray, label: str) -> None:
    """Require a one-dimensional integer index mapping without casting."""
    if (
        not isinstance(values, np.ndarray)
        or values.ndim != 1
        or not np.issubdtype(values.dtype, np.integer)
    ):
        raise ValueError(f"{label} must be a one-dimensional integer array")


def _require_uv_vertices(uv_vertices: np.ndarray) -> None:
    """Require finite normalized UV coordinate rows without coercion."""
    if (
        not isinstance(uv_vertices, np.ndarray)
        or uv_vertices.ndim != 2
        or uv_vertices.shape[1] != 2
        or uv_vertices.dtype != np.float64
        or not np.isfinite(uv_vertices).all()
    ):
        raise ValueError("UV vertices must be a finite float64 (N, 2) array")
    if np.any(uv_vertices < 0.0) or np.any(uv_vertices > 1.0):
        raise ValueError("UV vertices must lie in [0, 1]")


def _array_receipt(array: np.ndarray) -> dict[str, object]:
    """Return the shape, dtype, and byte hash used by the JSON receipt."""
    return {
        "shape": list(array.shape),
        "dtype": array.dtype.str,
        "sha256": _array_sha256(array),
    }


def _array_sha256(array: np.ndarray) -> str:
    """Hash a C-order representation so array hashes are layout-independent."""
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    """Hash a file's exact bytes using bounded streaming reads."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_receipt(receipt_path: Path) -> dict[str, object]:
    """Load and reject JSON receipts that do not match the fixed schema."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read sidecar receipt") from error
    expected_keys = {
        "schema",
        "canonical_file_sha256",
        "arrays",
        "generator",
        "generator_version",
        "chart_diagnostics",
        "recovered_source_faces_sha256",
        "oriented_cycles_valid",
        "npz_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise ValueError("receipt keys differ from sidecar schema")
    if receipt["schema"] != _RECEIPT_SCHEMA:
        raise ValueError("receipt schema differs from sidecar schema")
    if not isinstance(receipt["arrays"], dict) or set(receipt["arrays"]) != set(
        _ARRAY_NAMES
    ):
        raise ValueError("receipt array keys differ from sidecar schema")
    if (
        not isinstance(receipt["generator"], str)
        or not receipt["generator"]
        or not isinstance(receipt["generator_version"], str)
        or not receipt["generator_version"]
    ):
        raise ValueError("receipt generator metadata must be nonempty strings")
    return receipt


def _validate_npz_files(npz_path: Path) -> None:
    """Reject archive members beyond the four fixed NumPy array payloads."""
    try:
        with zipfile.ZipFile(npz_path) as archive:
            members = archive.namelist()
            if len(members) != len(_NPZ_FILES) or set(members) != _NPZ_FILES:
                raise ValueError("NPZ files differ from sidecar schema")
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("cannot read sidecar NPZ") from error
