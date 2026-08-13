"""CPU triplanar-derived vertex colours for the C1-R19 screen."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
from PIL import Image

from dpost.c1_r16_uv_render import (
    FORMAL_CAMERA_NAMES,
    RenderedView,
    validate_oriented_face_rows,
)
from dpost.c1_r16b_source_flatness import (
    _expected_directory_paths,
    _file_sha256,
    _load_png,
    _recursive_directory_paths,
    _recursive_file_paths,
    _write_json_exclusive,
    _write_rgb_exclusive,
)


def _require_geometry(vertices: np.ndarray, faces: np.ndarray) -> None:
    """Require finite float64 vertices and in-range triangle indices."""
    if (
        not isinstance(vertices, np.ndarray)
        or vertices.dtype != np.float64
        or vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError("vertices must be a nonempty finite float64 (N, 3) array")
    if (
        not isinstance(faces, np.ndarray)
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError("faces must be a nonempty integer (N, 3) array")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("face index is out of range")


def _require_atlas(atlas: np.ndarray) -> None:
    """Require the frozen atlas representation without implicit coercion."""
    if (
        not isinstance(atlas, np.ndarray)
        or atlas.dtype != np.uint8
        or atlas.ndim != 3
        or atlas.shape[2] != 3
        or atlas.shape[0] == 0
        or atlas.shape[1] == 0
    ):
        raise ValueError("atlas must be a nonempty uint8 RGB array")


def compute_area_weighted_vertex_normals(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> np.ndarray:
    """Compute deterministic area-weighted canonical vertex normals."""
    _require_geometry(vertices, faces)
    triangles = vertices[faces]
    # Cross products have magnitude twice the triangle area, so accumulating
    # them directly gives an area-weighted normal without extra scaling.
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    vertex_normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(vertex_normals, faces[:, corner], face_normals)

    lengths = np.linalg.norm(vertex_normals, axis=1)
    if np.any(~np.isfinite(lengths)) or np.any(lengths <= 0.0):
        raise ValueError("every vertex must have a nonzero accumulated normal")
    return vertex_normals / lengths[:, np.newaxis]


def compute_triplanar_weights(normals: np.ndarray) -> np.ndarray:
    """Normalize direct absolute normal components into three blend weights."""
    if (
        not isinstance(normals, np.ndarray)
        or normals.dtype != np.float64
        or normals.ndim != 2
        or normals.shape[1] != 3
        or not np.isfinite(normals).all()
    ):
        raise ValueError("normals must be a finite float64 (N, 3) array")
    magnitudes = np.abs(normals)
    totals = magnitudes.sum(axis=1)
    if np.any(totals <= 0.0):
        raise ValueError("every normal must have a nonzero component")
    return magnitudes / totals[:, np.newaxis]


def sample_bilinear_clamped(
    atlas: np.ndarray,
    coordinates: np.ndarray,
) -> np.ndarray:
    """Sample normalized UV coordinates with clamped bilinear filtering."""
    _require_atlas(atlas)
    if (
        not isinstance(coordinates, np.ndarray)
        or coordinates.dtype != np.float64
        or coordinates.ndim != 2
        or coordinates.shape[1] != 2
        or not np.isfinite(coordinates).all()
    ):
        raise ValueError("coordinates must be a finite float64 (N, 2) array")

    clipped = np.clip(coordinates, 0.0, 1.0)
    x_positions = clipped[:, 0] * (atlas.shape[1] - 1)
    y_positions = clipped[:, 1] * (atlas.shape[0] - 1)
    x_low = np.floor(x_positions).astype(np.int64)
    y_low = np.floor(y_positions).astype(np.int64)
    x_high = np.minimum(x_low + 1, atlas.shape[1] - 1)
    y_high = np.minimum(y_low + 1, atlas.shape[0] - 1)
    x_fraction = (x_positions - x_low)[:, np.newaxis]
    y_fraction = (y_positions - y_low)[:, np.newaxis]

    top = (
        atlas[y_low, x_low].astype(np.float64) * (1.0 - x_fraction)
        + atlas[y_low, x_high].astype(np.float64) * x_fraction
    )
    bottom = (
        atlas[y_high, x_low].astype(np.float64) * (1.0 - x_fraction)
        + atlas[y_high, x_high].astype(np.float64) * x_fraction
    )
    return top * (1.0 - y_fraction) + bottom * y_fraction


def compute_triplanar_vertex_colors(
    canonical_vertices: np.ndarray,
    faces: np.ndarray,
    atlas: np.ndarray,
) -> np.ndarray:
    """Map one uint8 RGB colour to every canonical source vertex."""
    _require_geometry(canonical_vertices, faces)
    _require_atlas(atlas)
    bounds_minimum = canonical_vertices.min(axis=0)
    bounds_maximum = canonical_vertices.max(axis=0)
    center = (bounds_minimum + bounds_maximum) / 2.0
    max_extent = float(np.max(bounds_maximum - bounds_minimum))
    if max_extent <= 0.0:
        raise ValueError("canonical bounding box must have positive extent")

    # One extent preserves physical aspect ratios; per-axis normalization
    # would stretch thin dimensions into unrelated source-image structure.
    normalized = (canonical_vertices - center) / max_extent + 0.5
    normals = compute_area_weighted_vertex_normals(canonical_vertices, faces)
    weights = compute_triplanar_weights(normals)

    # The X, Y, and Z projections respectively sample ZY, XZ, and XY planes.
    projected = (
        normalized[:, (2, 1)],
        normalized[:, (0, 2)],
        normalized[:, (0, 1)],
    )
    samples = np.stack(
        [sample_bilinear_clamped(atlas, plane) for plane in projected],
        axis=1,
    )
    blended = np.sum(samples * weights[:, :, np.newaxis], axis=1)
    colors = np.floor(np.clip(blended, 0.0, 255.0) + 0.5).astype(np.uint8)
    colors.setflags(write=False)
    return colors


def shared_edge_color_diagnostics(
    faces: np.ndarray,
    vertex_colors: np.ndarray,
) -> dict[str, int | bool]:
    """Prove shared face edges resolve to identical source-vertex colours."""
    if (
        not isinstance(vertex_colors, np.ndarray)
        or vertex_colors.dtype != np.uint8
        or vertex_colors.ndim != 2
        or vertex_colors.shape[1] != 3
    ):
        raise ValueError("vertex colors must be a uint8 (N, 3) array")
    placeholder_vertices = np.zeros((len(vertex_colors), 3), dtype=np.float64)
    _require_geometry(placeholder_vertices, faces)

    edge_occurrences: dict[
        tuple[int, int], list[tuple[np.ndarray, np.ndarray]]
    ] = defaultdict(list)
    for face in faces:
        for first, second in ((face[0], face[1]),
                              (face[1], face[2]),
                              (face[2], face[0])):
            edge = tuple(sorted((int(first), int(second))))
            edge_occurrences[edge].append(
                (vertex_colors[edge[0]], vertex_colors[edge[1]])
            )

    shared = [values for values in edge_occurrences.values() if len(values) > 1]
    mismatch_count = 0
    for occurrences in shared:
        reference = occurrences[0]
        for occurrence in occurrences[1:]:
            mismatch_count += int(not np.array_equal(reference[0], occurrence[0]))
            mismatch_count += int(not np.array_equal(reference[1], occurrence[1]))
    return {
        "edge_count": len(edge_occurrences),
        "shared_edge_count": len(shared),
        "shared_endpoint_occurrence_count": sum(
            2 * len(occurrences) for occurrences in shared
        ),
        "shared_endpoint_mismatch_count": mismatch_count,
        "shared_edge_colors_identical": mismatch_count == 0,
    }


def build_vertex_color_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    vertex_colors: np.ndarray,
) -> object:
    """Build an Open3D legacy mesh with vertex colours and no UV texture."""
    import open3d as o3d

    _require_geometry(vertices, faces)
    if (
        not isinstance(vertex_colors, np.ndarray)
        or vertex_colors.dtype != np.uint8
        or vertex_colors.shape != (len(vertices), 3)
    ):
        raise ValueError("vertex colors must be one uint8 RGB row per vertex")
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(faces),
    )
    mesh.vertex_colors = o3d.utility.Vector3dVector(
        vertex_colors.astype(np.float64) / 255.0
    )
    mesh.compute_vertex_normals()
    return mesh


_MESHES = ("canonical", "deformed-s0521-v0000")
_MIN_AVAILABLE_MEMORY_BYTES = 4_000_000_000
_MAX_PROCESS_TREE_RSS_BYTES = 500_000_000
R19_SCHEMA = "c1-r19-triplanar-visual-v1"
R19_STATUS = "R19_TRIPLANAR_VISUAL_READY"
_R17_RECEIPT_KEYS = {
    "artifact_hashes_sha256",
    "atlas_sha256",
    "candidates_sha256",
    "comparison_sha256",
    "diagnostics_sha256",
    "inputs_sha256",
    "schema",
    "selected_candidate_sha256",
    "status",
    "telemetry_sha256",
    "validation_sha256",
}
_RECEIPT_KEYS = {
    "artifact_hashes_sha256",
    "comparison_sha256",
    "diagnostics_sha256",
    "inputs_sha256",
    "schema",
    "source_atlas_sha256",
    "status",
    "telemetry_sha256",
    "validation_sha256",
    "vertex_colors_receipt_sha256",
}

VertexColorRenderer = Callable[
    [str, np.ndarray, np.ndarray, np.ndarray],
    Mapping[str, RenderedView],
]
ProgressReporter = Callable[[str], None]


def _report(progress: ProgressReporter | None, stage: str) -> None:
    """Publish one lightweight runner stage when requested."""
    if progress is not None:
        progress(stage)


def _require_digest(value: str, label: str) -> None:
    """Require one lowercase SHA-256 string."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _array_sha256(array: np.ndarray) -> str:
    """Hash one array's logical bytes in C order."""
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _copy_exclusive(source: Path, target: Path) -> None:
    """Copy exact bytes into a new file without replacement."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, target.open("xb") as output_file:
        for block in iter(lambda: input_file.read(1024 * 1024), b""):
            output_file.write(block)


def _write_npy_exclusive(path: Path, array: np.ndarray) -> None:
    """Write one non-pickle NumPy array to a new file."""
    with path.open("xb") as output:
        np.save(output, array, allow_pickle=False)


def _load_r17_atlas(root: Path) -> tuple[np.ndarray, dict[str, object]]:
    """Load the frozen R17 atlas and validate its direct receipt binding."""
    r17_root = Path(root)
    if r17_root.is_symlink() or not r17_root.is_dir():
        raise ValueError("R19 R17 input root differs")
    try:
        receipt = json.loads(
            (r17_root / "receipt.json").read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("R19 cannot read the R17 receipt") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != _R17_RECEIPT_KEYS
        or receipt.get("schema") != "c1-r17-continuous-exemplar-v1"
        or receipt.get("status") != "R17_CONTINUOUS_VISUAL_READY"
        or receipt.get("atlas_sha256")
        != _file_sha256(r17_root / "atlas.png")
    ):
        raise ValueError("R19 R17 input receipt differs")
    return _load_png(r17_root / "atlas.png", "RGB", (512, 512)), receipt


def _content_paths() -> set[str]:
    """Return the exact pre-closure R19 bundle file set."""
    paths = {
        "source-atlas.png",
        "vertex-colors.npy",
        "vertex-colors-receipt.json",
        "comparison-sheet.png",
        "inputs.json",
        "diagnostics.json",
        "validation.json",
        "telemetry.json",
    }
    for mesh_name in _MESHES:
        for view_name in FORMAL_CAMERA_NAMES:
            paths.add(f"controls/{mesh_name}/{view_name}.png")
            paths.add(f"masks/{mesh_name}/{view_name}.png")
            paths.add(f"renders/{mesh_name}/{view_name}.png")
    return paths


def _input_payload(
    *,
    r17_root: Path,
    r17_receipt: Mapping[str, object],
    canonical_file_sha256: str,
    deformed_file_sha256: str,
    vertex_count: int,
    face_count: int,
) -> dict[str, object]:
    """Bind the R17 source, two meshes, cameras, and sole mapping change."""
    return {
        "schema": "c1-r19-inputs-v1",
        "r17_receipt_sha256": _file_sha256(r17_root / "receipt.json"),
        "r17_status": r17_receipt["status"],
        "source_atlas_sha256": _file_sha256(r17_root / "atlas.png"),
        "canonical_file_sha256": canonical_file_sha256,
        "deformed_file_sha256": deformed_file_sha256,
        "vertex_count": vertex_count,
        "face_count": face_count,
        "camera_names": list(FORMAL_CAMERA_NAMES),
        "mapping": "cpu_triplanar_derived_vertex_field",
        "mapping_space": "canonical",
        "deformed_color_policy": "reuse_exact_canonical_bytes",
        "uses_uv": False,
        "worker_count": 1,
    }


def _vertex_color_receipt(
    colors: np.ndarray,
    npy_path: Path,
) -> dict[str, object]:
    """Describe both logical color bytes and the serialized NPY file."""
    return {
        "schema": "c1-r19-vertex-colors-v1",
        "dtype": colors.dtype.name,
        "shape": list(colors.shape),
        "array_sha256": _array_sha256(colors),
        "npy_sha256": _file_sha256(npy_path),
        "allow_pickle": False,
        "canonical_deformed_bytes_identical": True,
    }


def _diagnostics_payload(
    colors: np.ndarray,
    faces: np.ndarray,
) -> dict[str, object]:
    """Describe the one-color-per-source-vertex field without judging it."""
    edge_diagnostics = shared_edge_color_diagnostics(faces, colors)
    return {
        "schema": "c1-r19-diagnostics-v1",
        "interpretation": "mechanical_only_not_an_appearance_gap_metric",
        "mapping": "cpu_triplanar_derived_vertex_field",
        "vertex_color_count": len(colors),
        "channel_minimum": colors.min(axis=0).tolist(),
        "channel_maximum": colors.max(axis=0).tolist(),
        "channel_standard_deviation": [
            float(value) for value in colors.astype(np.float64).std(axis=0)
        ],
        "shared_edges": edge_diagnostics,
    }


def _validation_payload() -> dict[str, object]:
    """Return the exact mechanical screen validation record."""
    return {
        "schema": "c1-r19-validation-v1",
        "source_atlas_replayed": True,
        "vertex_colors_replayed": True,
        "canonical_deformed_color_bytes_identical": True,
        "shared_edge_endpoint_colors_identical": True,
        "r17_masks_equal": True,
        "control_count": 10,
        "mask_count": 10,
        "render_count": 10,
        "uses_uv": False,
        "all_mechanical_gates_passed": True,
    }


def _telemetry_payload(
    available_memory_bytes: int,
    peak_rss_value: int | Callable[[], int],
) -> dict[str, object]:
    """Resolve one honest generation-stage process-tree measurement."""
    peak = peak_rss_value() if callable(peak_rss_value) else peak_rss_value
    if (
        not isinstance(peak, int)
        or isinstance(peak, bool)
        or not 0 <= peak < _MAX_PROCESS_TREE_RSS_BYTES
    ):
        raise MemoryError("R19 RSS peak is outside the required ceiling")
    return {
        "schema": "c1-r19-telemetry-v1",
        "available_memory_bytes_before": available_memory_bytes,
        "peak_process_tree_rss_bytes": peak,
        "rss_limit_bytes": _MAX_PROCESS_TREE_RSS_BYTES,
        "sample_interval_seconds": 0.05,
        "worker_count": 1,
        "measurement_scope": "through_bundle_generation_before_readback",
        "within_limit": True,
    }


def _validate_telemetry(telemetry: Mapping[str, object]) -> None:
    """Require the exact serial R19 resource-policy record."""
    expected = {
        "schema",
        "available_memory_bytes_before",
        "peak_process_tree_rss_bytes",
        "rss_limit_bytes",
        "sample_interval_seconds",
        "worker_count",
        "measurement_scope",
        "within_limit",
    }
    available = telemetry.get("available_memory_bytes_before")
    peak = telemetry.get("peak_process_tree_rss_bytes")
    if (
        set(telemetry) != expected
        or telemetry.get("schema") != "c1-r19-telemetry-v1"
        or not isinstance(available, int)
        or isinstance(available, bool)
        or available < _MIN_AVAILABLE_MEMORY_BYTES
        or not isinstance(peak, int)
        or isinstance(peak, bool)
        or not 0 <= peak < _MAX_PROCESS_TREE_RSS_BYTES
        or telemetry.get("rss_limit_bytes") != _MAX_PROCESS_TREE_RSS_BYTES
        or telemetry.get("sample_interval_seconds") != 0.05
        or telemetry.get("worker_count") != 1
        or telemetry.get("measurement_scope")
        != "through_bundle_generation_before_readback"
        or telemetry.get("within_limit") is not True
    ):
        raise ValueError("R19 bundle telemetry differs")


def _comparison_sheet(
    controls: Mapping[str, Mapping[str, np.ndarray]],
    renders: Mapping[str, Mapping[str, np.ndarray]],
) -> np.ndarray:
    """Stack both R17/R19 five-view pairs without resampling pixels."""
    rows = []
    for mesh_name in _MESHES:
        for source in (controls, renders):
            rows.append(
                np.concatenate(
                    [source[mesh_name][name] for name in FORMAL_CAMERA_NAMES],
                    axis=1,
                )
            )
    return np.concatenate(rows, axis=0)


def _write_closure(root: Path, receipt: Mapping[str, object]) -> None:
    """Hash the exact R19 content tree and write its receipt."""
    expected = _content_paths()
    if _recursive_file_paths(root) != expected:
        raise ValueError("R19 bundle content tree differs before closure")
    manifest = {path: _file_sha256(root / path) for path in sorted(expected)}
    _write_json_exclusive(root / "artifact-hashes.json", manifest)
    closed = dict(receipt)
    closed["artifact_hashes_sha256"] = _file_sha256(
        root / "artifact-hashes.json"
    )
    _write_json_exclusive(root / "receipt.json", closed)


def _require_matching_topology(
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    deformed_vertices: np.ndarray,
    deformed_faces: np.ndarray,
) -> None:
    """Require two finite meshes with exact source-vertex correspondence."""
    _require_geometry(canonical_vertices, canonical_faces)
    _require_geometry(deformed_vertices, deformed_faces)
    if canonical_vertices.shape != deformed_vertices.shape:
        raise ValueError("R19 canonical and deformed topology differs")
    validate_oriented_face_rows(canonical_faces, deformed_faces)


def _render_and_write(
    root: Path,
    *,
    r17_root: Path,
    meshes: Mapping[str, np.ndarray],
    faces: np.ndarray,
    colors: np.ndarray,
    renderer: VertexColorRenderer,
) -> tuple[
    dict[str, dict[str, np.ndarray]],
    dict[str, dict[str, np.ndarray]],
]:
    """Copy R17 controls and write ten mask-matched R19 renders."""
    controls: dict[str, dict[str, np.ndarray]] = {}
    renders: dict[str, dict[str, np.ndarray]] = {}
    for mesh_name in _MESHES:
        controls[mesh_name] = {}
        renders[mesh_name] = {}
        views = renderer(mesh_name, meshes[mesh_name], faces, colors)
        if set(views) != set(FORMAL_CAMERA_NAMES):
            raise ValueError("R19 renderer camera set differs")
        for view_name in FORMAL_CAMERA_NAMES:
            mask_source = r17_root / f"masks/{mesh_name}/{view_name}.png"
            control_source = r17_root / f"renders/{mesh_name}/{view_name}.png"
            mask_target = root / f"masks/{mesh_name}/{view_name}.png"
            control_target = root / f"controls/{mesh_name}/{view_name}.png"
            _copy_exclusive(mask_source, mask_target)
            _copy_exclusive(control_source, control_target)
            mask = _load_png(mask_target, "L", (512, 512)) == 255
            control = _load_png(control_target, "RGB", (512, 512))
            view = views[view_name]
            if (
                not isinstance(view, RenderedView)
                or view.rgb.dtype != np.uint8
                or view.rgb.shape != (512, 512, 3)
                or view.object_mask.dtype != np.bool_
                or not np.array_equal(view.object_mask, mask)
            ):
                raise ValueError("R19 render or depth mask differs")
            _write_rgb_exclusive(
                root / f"renders/{mesh_name}/{view_name}.png",
                view.rgb,
            )
            controls[mesh_name][view_name] = control
            renders[mesh_name][view_name] = view.rgb
    return controls, renders


def write_r19_bundle(
    output_root: Path,
    *,
    r17_root: Path,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    deformed_vertices: np.ndarray,
    deformed_faces: np.ndarray,
    canonical_file_sha256: str,
    deformed_file_sha256: str,
    render_vertex_colors: VertexColorRenderer,
    available_memory_bytes: int = _MIN_AVAILABLE_MEMORY_BYTES,
    peak_process_tree_rss_bytes: int | Callable[[], int] = 0,
    progress: ProgressReporter | None = None,
) -> dict[str, object]:
    """Write and strictly read back one no-clobber R19 screen bundle."""
    root = Path(output_root)
    if root.exists():
        raise FileExistsError("R19 output root already exists")
    if available_memory_bytes < _MIN_AVAILABLE_MEMORY_BYTES:
        raise MemoryError("R19 available memory is below 4000000000 bytes")
    _require_digest(canonical_file_sha256, "canonical file hash")
    _require_digest(deformed_file_sha256, "deformed file hash")
    _require_matching_topology(
        canonical_vertices,
        canonical_faces,
        deformed_vertices,
        deformed_faces,
    )
    r17_root = Path(r17_root)
    atlas, r17_receipt = _load_r17_atlas(r17_root)
    colors = compute_triplanar_vertex_colors(
        canonical_vertices,
        canonical_faces,
        atlas,
    )
    _report(progress, "vertex_colors_computed")

    root.mkdir(parents=True)
    _copy_exclusive(r17_root / "atlas.png", root / "source-atlas.png")
    _write_npy_exclusive(root / "vertex-colors.npy", colors)
    color_receipt = _vertex_color_receipt(
        colors,
        root / "vertex-colors.npy",
    )
    _write_json_exclusive(root / "vertex-colors-receipt.json", color_receipt)
    controls, renders = _render_and_write(
        root,
        r17_root=r17_root,
        meshes={
            "canonical": canonical_vertices,
            "deformed-s0521-v0000": deformed_vertices,
        },
        faces=canonical_faces,
        colors=colors,
        renderer=render_vertex_colors,
    )
    _report(progress, "renders_complete")
    _write_rgb_exclusive(
        root / "comparison-sheet.png",
        _comparison_sheet(controls, renders),
    )
    inputs = _input_payload(
        r17_root=r17_root,
        r17_receipt=r17_receipt,
        canonical_file_sha256=canonical_file_sha256,
        deformed_file_sha256=deformed_file_sha256,
        vertex_count=len(canonical_vertices),
        face_count=len(canonical_faces),
    )
    diagnostics = _diagnostics_payload(colors, canonical_faces)
    validation = _validation_payload()
    telemetry = _telemetry_payload(
        available_memory_bytes,
        peak_process_tree_rss_bytes,
    )
    _write_json_exclusive(root / "inputs.json", inputs)
    _write_json_exclusive(root / "diagnostics.json", diagnostics)
    _write_json_exclusive(root / "validation.json", validation)
    _write_json_exclusive(root / "telemetry.json", telemetry)
    _write_closure(
        root,
        {
            "schema": R19_SCHEMA,
            "status": R19_STATUS,
            "source_atlas_sha256": _file_sha256(root / "source-atlas.png"),
            "vertex_colors_receipt_sha256": _file_sha256(
                root / "vertex-colors-receipt.json"
            ),
            "inputs_sha256": _file_sha256(root / "inputs.json"),
            "comparison_sha256": _file_sha256(root / "comparison-sheet.png"),
            "diagnostics_sha256": _file_sha256(root / "diagnostics.json"),
            "validation_sha256": _file_sha256(root / "validation.json"),
            "telemetry_sha256": _file_sha256(root / "telemetry.json"),
        },
    )
    _report(progress, "bundle_closed")
    result = read_r19_bundle(
        root,
        r17_root=r17_root,
        canonical_vertices=canonical_vertices,
        canonical_faces=canonical_faces,
        deformed_vertices=deformed_vertices,
        deformed_faces=deformed_faces,
        canonical_file_sha256=canonical_file_sha256,
        deformed_file_sha256=deformed_file_sha256,
        render_vertex_colors=render_vertex_colors,
    )
    _report(progress, "strict_readback_complete")
    return result


def read_r19_bundle(
    root: Path,
    *,
    r17_root: Path,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    deformed_vertices: np.ndarray,
    deformed_faces: np.ndarray,
    canonical_file_sha256: str,
    deformed_file_sha256: str,
    render_vertex_colors: VertexColorRenderer,
) -> dict[str, object]:
    """Strictly replay one closed R19 bundle from frozen upstream inputs."""
    bundle_root = Path(root)
    try:
        if bundle_root.is_symlink() or not bundle_root.is_dir() or any(
            path.is_symlink() for path in bundle_root.rglob("*")
        ):
            raise ValueError("R19 bundle root or link contract differs")
        expected = _content_paths() | {"artifact-hashes.json", "receipt.json"}
        if _recursive_file_paths(bundle_root) != expected:
            raise ValueError("R19 bundle recursive file tree differs")
        if _recursive_directory_paths(bundle_root) != _expected_directory_paths(
            _content_paths()
        ):
            raise ValueError("R19 bundle directory tree differs")
        manifest = json.loads(
            (bundle_root / "artifact-hashes.json").read_text(encoding="utf-8")
        )
        receipt = json.loads(
            (bundle_root / "receipt.json").read_text(encoding="utf-8")
        )
        if (
            not isinstance(manifest, dict)
            or set(manifest) != _content_paths()
            or any(
                _file_sha256(bundle_root / path) != digest
                for path, digest in manifest.items()
            )
        ):
            raise ValueError("R19 bundle content hash differs")
        if (
            not isinstance(receipt, dict)
            or set(receipt) != _RECEIPT_KEYS
            or receipt.get("schema") != R19_SCHEMA
            or receipt.get("status") != R19_STATUS
            or receipt.get("artifact_hashes_sha256")
            != _file_sha256(bundle_root / "artifact-hashes.json")
        ):
            raise ValueError("R19 bundle receipt differs")
        _require_digest(canonical_file_sha256, "canonical file hash")
        _require_digest(deformed_file_sha256, "deformed file hash")
        _require_matching_topology(
            canonical_vertices,
            canonical_faces,
            deformed_vertices,
            deformed_faces,
        )
        r17_root = Path(r17_root)
        atlas, r17_receipt = _load_r17_atlas(r17_root)
        saved_atlas = _load_png(
            bundle_root / "source-atlas.png",
            "RGB",
            (512, 512),
        )
        if (
            not np.array_equal(saved_atlas, atlas)
            or (bundle_root / "source-atlas.png").read_bytes()
            != (r17_root / "atlas.png").read_bytes()
        ):
            raise ValueError("R19 bundle source atlas replay differs")
        expected_inputs = _input_payload(
            r17_root=r17_root,
            r17_receipt=r17_receipt,
            canonical_file_sha256=canonical_file_sha256,
            deformed_file_sha256=deformed_file_sha256,
            vertex_count=len(canonical_vertices),
            face_count=len(canonical_faces),
        )
        inputs = json.loads(
            (bundle_root / "inputs.json").read_text(encoding="utf-8")
        )
        if inputs != expected_inputs:
            raise ValueError("R19 bundle input bindings differ")
        with (bundle_root / "vertex-colors.npy").open("rb") as source:
            saved_colors = np.load(source, allow_pickle=False)
        if (
            not isinstance(saved_colors, np.ndarray)
            or saved_colors.dtype != np.uint8
            or saved_colors.shape != (len(canonical_vertices), 3)
        ):
            raise ValueError("R19 bundle vertex color array differs")
        expected_colors = compute_triplanar_vertex_colors(
            canonical_vertices,
            canonical_faces,
            atlas,
        )
        if not np.array_equal(saved_colors, expected_colors):
            raise ValueError("R19 bundle vertex color replay differs")
        saved_colors.setflags(write=False)
        color_receipt = json.loads(
            (bundle_root / "vertex-colors-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if color_receipt != _vertex_color_receipt(
            saved_colors,
            bundle_root / "vertex-colors.npy",
        ):
            raise ValueError("R19 bundle vertex color receipt differs")

        controls: dict[str, dict[str, np.ndarray]] = {}
        masks: dict[str, dict[str, np.ndarray]] = {}
        renders: dict[str, dict[str, np.ndarray]] = {}
        for mesh_name in _MESHES:
            controls[mesh_name] = {}
            masks[mesh_name] = {}
            renders[mesh_name] = {}
            for view_name in FORMAL_CAMERA_NAMES:
                mask_path = bundle_root / f"masks/{mesh_name}/{view_name}.png"
                r17_mask = r17_root / f"masks/{mesh_name}/{view_name}.png"
                if mask_path.read_bytes() != r17_mask.read_bytes():
                    raise ValueError("R19 bundle mask bytes differ from R17")
                mask = _load_png(mask_path, "L", (512, 512)) == 255
                control_path = (
                    bundle_root / f"controls/{mesh_name}/{view_name}.png"
                )
                r17_control = r17_root / f"renders/{mesh_name}/{view_name}.png"
                if control_path.read_bytes() != r17_control.read_bytes():
                    raise ValueError("R19 bundle control bytes differ from R17")
                control = _load_png(control_path, "RGB", (512, 512))
                render = _load_png(
                    bundle_root / f"renders/{mesh_name}/{view_name}.png",
                    "RGB",
                    (512, 512),
                )
                if not np.any(render[mask]):
                    raise ValueError("R19 bundle render is blank")
                controls[mesh_name][view_name] = control
                masks[mesh_name][view_name] = mask
                renders[mesh_name][view_name] = render
        meshes = {
            "canonical": canonical_vertices,
            "deformed-s0521-v0000": deformed_vertices,
        }
        for mesh_name in _MESHES:
            replayed = render_vertex_colors(
                mesh_name,
                meshes[mesh_name],
                canonical_faces,
                saved_colors,
            )
            if set(replayed) != set(FORMAL_CAMERA_NAMES):
                raise ValueError("R19 bundle render replay camera set differs")
            for view_name in FORMAL_CAMERA_NAMES:
                replay = replayed[view_name]
                if (
                    not isinstance(replay, RenderedView)
                    or not np.array_equal(
                        replay.object_mask,
                        masks[mesh_name][view_name],
                    )
                ):
                    raise ValueError("R19 bundle render mask replay differs")
                if not np.array_equal(
                    replay.rgb,
                    renders[mesh_name][view_name],
                ):
                    raise ValueError("R19 bundle render replay differs")
        comparison = _load_png(
            bundle_root / "comparison-sheet.png",
            "RGB",
            (5 * 512, 4 * 512),
        )
        if not np.array_equal(comparison, _comparison_sheet(controls, renders)):
            raise ValueError("R19 bundle comparison replay differs")
        diagnostics = json.loads(
            (bundle_root / "diagnostics.json").read_text(encoding="utf-8")
        )
        if diagnostics != _diagnostics_payload(saved_colors, canonical_faces):
            raise ValueError("R19 bundle diagnostics differ")
        validation = json.loads(
            (bundle_root / "validation.json").read_text(encoding="utf-8")
        )
        if validation != _validation_payload():
            raise ValueError("R19 bundle validation differs")
        telemetry = json.loads(
            (bundle_root / "telemetry.json").read_text(encoding="utf-8")
        )
        _validate_telemetry(telemetry)
        bound = {
            "source_atlas_sha256": "source-atlas.png",
            "vertex_colors_receipt_sha256": "vertex-colors-receipt.json",
            "inputs_sha256": "inputs.json",
            "comparison_sha256": "comparison-sheet.png",
            "diagnostics_sha256": "diagnostics.json",
            "validation_sha256": "validation.json",
            "telemetry_sha256": "telemetry.json",
        }
        if any(
            receipt.get(field) != _file_sha256(bundle_root / path)
            for field, path in bound.items()
        ):
            raise ValueError("R19 bundle receipt binding differs")
        return {
            "receipt": receipt,
            "artifact_hashes": manifest,
            "inputs": inputs,
            "diagnostics": diagnostics,
            "validation": validation,
            "telemetry": telemetry,
            "vertex_colors_receipt": color_receipt,
        }
    except (KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("R19 bundle"):
            raise
        raise ValueError("R19 bundle validation failed") from error
