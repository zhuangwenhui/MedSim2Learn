"""Build triangle-interpolated implicit vessel width fields for C1-R23."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from dpost.c1_r16_uv_render import UvSidecar
from dpost.c1_r21_procedural_vessels import (
    GraphSurfaceVesselTree,
    _surface_centerline_distances,
    compute_equal_terminal_diameters,
)
from dpost.c1_r19_triplanar_continuity import (
    compute_area_weighted_vertex_normals,
)


R23_RATIOS = (0.012, 0.020, 0.032)
R23_SCALE_NAMES = ("small", "medium", "large")
R23_BASE_LAB = np.array(
    [66.815185546875, 19.3984375, -4.0078125],
    dtype=np.float64,
)
R23_DELTA_LAB = np.array(
    [-3.5003662109375, 7.6953125, 0.1640625],
    dtype=np.float64,
)
R23_ANTIALIAS_HALF_WIDTH_MM = 0.10
R23_LUT_WIDTH = 16_384
R23_DIFFUSE_AMBIENT = 0.70
R23_DIFFUSE_STRENGTH = 0.30
R23_WORLD_LIGHT_DIRECTION = np.array(
    [0.35, -0.25, 0.90],
    dtype=np.float64,
)
_REPRESENTATION_FILES = frozenset(
    {
        "artifact-hashes.json",
        "identity-uv.npz",
        "luts.npz",
        "receipt.json",
        "signed-fields.npz",
    }
)
_REPRESENTATION_PAYLOAD_FILES = frozenset(
    {"identity-uv.npz", "luts.npz", "signed-fields.npz"}
)
_REPRESENTATION_RECEIPT_KEYS = frozenset(
    {
        "artifact_hashes_sha256",
        "ratios",
        "same_bytes_for_canonical_and_deformed",
        "schema",
    }
)


@dataclass(frozen=True)
class SignedFieldBundle:
    """Hold canonical graph-distance and signed vessel-width fields."""

    ratios: tuple[float, ...]
    root_diameters: np.ndarray
    distances: np.ndarray
    nearest_node_indices: np.ndarray
    node_radii: tuple[np.ndarray, ...]
    signed_fields: tuple[np.ndarray, ...]


def _surface_extent(vertices: np.ndarray) -> float:
    """Return the largest axis-aligned extent in millimetres."""
    if (
        not isinstance(vertices, np.ndarray)
        or vertices.dtype != np.float64
        or vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError("vertices must be finite float64 (N, 3)")
    extent = float(np.max(np.ptp(vertices, axis=0)))
    if extent <= 0.0:
        raise ValueError("surface extent must be positive")
    return extent


def _frozen_tree(
    vertices: np.ndarray,
    node_vertex_indices: np.ndarray,
    parent_node_indices: np.ndarray,
) -> GraphSurfaceVesselTree:
    """Adapt frozen tree arrays to the existing R21 graph-distance API."""
    nodes = np.asarray(node_vertex_indices)
    parents = np.asarray(parent_node_indices)
    if nodes.dtype != np.int64 or parents.dtype != np.int64:
        raise ValueError("tree arrays must be int64")
    if nodes.ndim != 1 or parents.shape != nodes.shape or len(nodes) == 0:
        raise ValueError("tree arrays must be nonempty matching vectors")
    extent = _surface_extent(vertices)
    return GraphSurfaceVesselTree(
        root_vertex_index=int(nodes[0]),
        node_vertex_indices=nodes,
        parent_node_indices=parents,
        attraction_points=np.empty((0, 3), dtype=np.float64),
        attraction_count=0,
        killed_attraction_count=0,
        remaining_attraction_count=0,
        iteration_count=0,
        stop_reason="frozen-r23-input",
        surface_extent=extent,
        seed=2107,
        influence_radius=0.18 * extent,
        kill_radius=0.02 * extent,
        max_iterations=2048,
    )


def build_signed_field_bundle(
    canonical_vertices: np.ndarray,
    faces: np.ndarray,
    node_vertex_indices: np.ndarray,
    parent_node_indices: np.ndarray,
) -> SignedFieldBundle:
    """Build `g = graph_distance - nearest tapered radius` per scale."""
    tree = _frozen_tree(
        canonical_vertices,
        node_vertex_indices,
        parent_node_indices,
    )
    distances, nearest_nodes = _surface_centerline_distances(
        canonical_vertices,
        faces,
        tree,
    )
    root_diameters = np.asarray(R23_RATIOS, dtype=np.float64) * (
        tree.surface_extent
    )
    node_radii = []
    signed_fields = []
    for root_diameter in root_diameters:
        radii = compute_equal_terminal_diameters(
            tree,
            float(root_diameter),
        ) / 2.0
        field = distances - radii[nearest_nodes]
        radii.setflags(write=False)
        field.setflags(write=False)
        node_radii.append(radii)
        signed_fields.append(field)
    root_diameters.setflags(write=False)
    return SignedFieldBundle(
        ratios=R23_RATIOS,
        root_diameters=root_diameters,
        distances=distances,
        nearest_node_indices=nearest_nodes,
        node_radii=tuple(node_radii),
        signed_fields=tuple(signed_fields),
    )


def build_identity_uv_sidecar(
    faces: np.ndarray,
    signed_field: np.ndarray,
) -> UvSidecar:
    """Map one source vertex to one UV vertex using global signed-field `u`."""
    if (
        not isinstance(signed_field, np.ndarray)
        or signed_field.dtype != np.float64
        or signed_field.ndim != 1
        or len(signed_field) == 0
        or not np.isfinite(signed_field).all()
    ):
        raise ValueError("signed field must be a finite float64 vector")
    field_min = float(signed_field.min())
    field_max = float(signed_field.max())
    if field_max <= field_min:
        raise ValueError("signed field must have positive range")
    face_rows = np.asarray(faces)
    if (
        face_rows.dtype != np.int64
        or face_rows.ndim != 2
        or face_rows.shape[1] != 3
        or len(face_rows) == 0
        or np.any(face_rows < 0)
        or np.any(face_rows >= len(signed_field))
    ):
        raise ValueError("faces must be valid int64 triangle rows")
    u = (signed_field - field_min) / (field_max - field_min)
    uv_vertices = np.column_stack((u, np.full(len(u), 0.5)))
    return UvSidecar(
        source_faces=face_rows,
        uv_vertex_to_source_vertex=np.arange(len(u), dtype=np.int64),
        uv_faces=face_rows,
        uv_vertices=uv_vertices,
        generator="c1-r23-identity-signed-field",
        generator_version="1",
    )


def validate_identity_uv_sidecar(
    sidecar: UvSidecar,
    vertices: np.ndarray,
    signed_field: np.ndarray,
) -> dict[str, object]:
    """Validate the special seam-free one-dimensional R23 UV contract."""
    extent = _surface_extent(vertices)
    del extent
    if (
        signed_field.dtype != np.float64
        or signed_field.shape != (len(vertices),)
    ):
        raise ValueError("signed field and vertex count differ")
    mapping = np.arange(len(vertices), dtype=np.int64)
    if not np.array_equal(
        sidecar.uv_vertex_to_source_vertex,
        mapping,
    ):
        raise ValueError("identity UV source mapping differs")
    if not np.array_equal(sidecar.uv_faces, sidecar.source_faces):
        raise ValueError("identity UV faces differ from source faces")
    if np.any(sidecar.source_faces < 0) or np.any(
        sidecar.source_faces >= len(vertices)
    ):
        raise ValueError("identity UV face index is out of range")
    field_min = float(signed_field.min())
    field_max = float(signed_field.max())
    expected_u = (signed_field - field_min) / (field_max - field_min)
    if not np.array_equal(sidecar.uv_vertices[:, 0], expected_u):
        raise ValueError("identity UV signed-field coordinate differs")
    if not np.all(sidecar.uv_vertices[:, 1] == 0.5):
        raise ValueError("identity UV auxiliary coordinate differs")
    return {
        "constant_v": True,
        "face_count": int(len(sidecar.source_faces)),
        "one_uv_per_source_vertex": True,
        "source_vertex_count": int(len(vertices)),
    }


def build_implicit_textured_mesh(
    vertices: np.ndarray,
    sidecar: UvSidecar,
    signed_field: np.ndarray,
    texture_rgb: np.ndarray,
) -> object:
    """Build the special R23 one-dimensional implicit-texture mesh."""
    import open3d as o3d

    validate_identity_uv_sidecar(sidecar, vertices, signed_field)
    if (
        not isinstance(texture_rgb, np.ndarray)
        or texture_rgb.dtype != np.uint8
        or texture_rgb.ndim != 3
        or texture_rgb.shape[2] != 3
        or texture_rgb.shape[0] != 2
        or texture_rgb.shape[1] != R23_LUT_WIDTH
    ):
        raise ValueError("implicit texture must be uint8 (2, 16384, 3)")
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(sidecar.uv_faces),
    )
    triangle_uvs = sidecar.uv_vertices[sidecar.uv_faces].reshape((-1, 2))
    mesh.triangle_uvs = o3d.utility.Vector2dVector(triangle_uvs)
    mesh.textures = [o3d.geometry.Image(texture_rgb)]
    mesh.triangle_material_ids = o3d.utility.IntVector(
        [0] * len(sidecar.uv_faces)
    )
    if len(mesh.triangle_uvs) != 3 * len(mesh.triangles):
        raise ValueError("implicit mesh triangle UV count differs")
    return mesh


def lab_row_to_rgb(lab: np.ndarray) -> np.ndarray:
    """Convert one finite float64 Lab row to rounded uint8 RGB."""
    values = np.asarray(lab)
    if (
        values.dtype != np.float64
        or values.shape != (3,)
        or not np.isfinite(values).all()
    ):
        raise ValueError("Lab must be one finite float64 row")
    rgb = cv2.cvtColor(
        values.astype(np.float32).reshape((1, 1, 3)),
        cv2.COLOR_LAB2RGB,
    )[0, 0]
    return np.floor(np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def build_lab_lut(
    field_min: float,
    field_max: float,
    base_lab: np.ndarray = R23_BASE_LAB,
    delta_lab: np.ndarray = R23_DELTA_LAB,
) -> np.ndarray:
    """Build the fixed two-row LUT evaluated after triangle interpolation."""
    if not np.isfinite(field_min) or not np.isfinite(field_max):
        raise ValueError("field limits must be finite")
    if field_max <= field_min:
        raise ValueError("field limits must have positive range")
    for label, row in (("base", base_lab), ("delta", delta_lab)):
        if (
            not isinstance(row, np.ndarray)
            or row.dtype != np.float64
            or row.shape != (3,)
            or not np.isfinite(row).all()
        ):
            raise ValueError(f"{label} Lab must be one finite float64 row")
    positions = np.linspace(field_min, field_max, R23_LUT_WIDTH)
    normalized = np.clip(
        (positions + R23_ANTIALIAS_HALF_WIDTH_MM)
        / (2.0 * R23_ANTIALIAS_HALF_WIDTH_MM),
        0.0,
        1.0,
    )
    smooth = normalized * normalized * (3.0 - 2.0 * normalized)
    alpha = 1.0 - smooth
    lab = base_lab[np.newaxis, :] + alpha[:, np.newaxis] * delta_lab
    rgb_float = cv2.cvtColor(
        lab.astype(np.float32).reshape((-1, 1, 3)),
        cv2.COLOR_LAB2RGB,
    ).reshape((-1, 3))
    row = np.floor(np.clip(rgb_float, 0.0, 1.0) * 255.0 + 0.5).astype(
        np.uint8
    )
    lut = np.stack((row, row), axis=0)
    lut.setflags(write=False)
    return lut


def build_binary_lut(field_min: float, field_max: float) -> np.ndarray:
    """Build a two-row black/white LUT for the signed vessel interior."""
    if field_max <= field_min:
        raise ValueError("field limits must have positive range")
    positions = np.linspace(field_min, field_max, R23_LUT_WIDTH)
    values = np.where(positions <= 0.0, 255, 0).astype(np.uint8)
    rgb = np.repeat(values[:, np.newaxis], 3, axis=1)
    return np.stack((rgb, rgb), axis=0)


def build_controlled_diffuse_vertex_colors(
    vertices: np.ndarray,
    faces: np.ndarray,
    light_direction: np.ndarray = R23_WORLD_LIGHT_DIRECTION,
) -> np.ndarray:
    """Encode the registered ambient-plus-Lambertian intensity as RGB."""
    direction = np.asarray(light_direction)
    if (
        direction.dtype != np.float64
        or direction.shape != (3,)
        or not np.isfinite(direction).all()
    ):
        raise ValueError("light direction must be one finite float64 row")
    length = float(np.linalg.norm(direction))
    if length <= 0.0:
        raise ValueError("light direction must be nonzero")
    unit_direction = direction / length
    normals = compute_area_weighted_vertex_normals(vertices, faces)
    lambertian = np.maximum(normals @ unit_direction, 0.0)
    intensity = R23_DIFFUSE_AMBIENT + R23_DIFFUSE_STRENGTH * lambertian
    gray = np.floor(np.clip(intensity, 0.0, 1.0) * 255.0 + 0.5).astype(
        np.uint8
    )
    return np.repeat(gray[:, np.newaxis], 3, axis=1)


def composite_controlled_diffuse(
    albedo_rgb: np.ndarray,
    albedo_mask: np.ndarray,
    shading_rgb: np.ndarray,
    shading_mask: np.ndarray,
) -> np.ndarray:
    """Multiply fixed unlit albedo by shading within one exact camera mask."""
    if (
        not isinstance(albedo_rgb, np.ndarray)
        or albedo_rgb.dtype != np.uint8
        or albedo_rgb.ndim != 3
        or albedo_rgb.shape[2] != 3
        or not isinstance(shading_rgb, np.ndarray)
        or shading_rgb.dtype != np.uint8
        or shading_rgb.shape != albedo_rgb.shape
    ):
        raise ValueError("albedo and shading must be matching uint8 RGB images")
    expected_mask_shape = albedo_rgb.shape[:2]
    if (
        not isinstance(albedo_mask, np.ndarray)
        or albedo_mask.dtype != np.bool_
        or albedo_mask.shape != expected_mask_shape
        or not isinstance(shading_mask, np.ndarray)
        or shading_mask.dtype != np.bool_
        or shading_mask.shape != expected_mask_shape
    ):
        raise ValueError("albedo and shading masks must match image shape")
    if not np.array_equal(albedo_mask, shading_mask):
        raise ValueError("albedo and shading masks differ")
    result = albedo_rgb.copy()
    factors = np.clip(
        shading_rgb[albedo_mask].mean(axis=1) / 255.0,
        R23_DIFFUSE_AMBIENT,
        1.0,
    )
    shaded = albedo_rgb[albedo_mask].astype(np.float64) * factors[:, None]
    result[albedo_mask] = np.floor(np.clip(shaded, 0.0, 255.0) + 0.5).astype(
        np.uint8
    )
    return result


def _file_sha256(path: Path) -> str:
    """Return a file SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, value: object) -> None:
    """Write deterministic JSON without overwriting an existing file."""
    with path.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write("\n")


def write_representation_bundle(
    root: Path,
    bundle: SignedFieldBundle,
    sidecars: tuple[UvSidecar, ...],
    luts: tuple[np.ndarray, ...],
) -> None:
    """Write a closed representation bundle into a new directory."""
    if root.exists():
        raise FileExistsError(f"bundle root already exists: {root}")
    if len(sidecars) != 3 or len(luts) != 3:
        raise ValueError("representation bundle requires three scales")
    root.mkdir(parents=True)
    np.savez_compressed(
        root / "signed-fields.npz",
        ratios=np.asarray(bundle.ratios, dtype=np.float64),
        root_diameters=bundle.root_diameters,
        distances=bundle.distances,
        nearest_node_indices=bundle.nearest_node_indices,
        **{
            f"node_radii_{name}": values
            for name, values in zip(
                R23_SCALE_NAMES,
                bundle.node_radii,
                strict=True,
            )
        },
        **{
            f"signed_field_{name}": values
            for name, values in zip(
                R23_SCALE_NAMES,
                bundle.signed_fields,
                strict=True,
            )
        },
    )
    np.savez_compressed(
        root / "identity-uv.npz",
        **{
            f"uv_vertices_{name}": sidecar.uv_vertices
            for name, sidecar in zip(
                R23_SCALE_NAMES,
                sidecars,
                strict=True,
            )
        },
        source_faces=sidecars[0].source_faces,
        uv_vertex_to_source_vertex=sidecars[0].uv_vertex_to_source_vertex,
        uv_faces=sidecars[0].uv_faces,
    )
    np.savez_compressed(
        root / "luts.npz",
        **{
            name: lut
            for name, lut in zip(R23_SCALE_NAMES, luts, strict=True)
        },
    )
    payload_names = (
        "identity-uv.npz",
        "luts.npz",
        "signed-fields.npz",
    )
    hashes = {name: _file_sha256(root / name) for name in payload_names}
    _write_json_exclusive(root / "artifact-hashes.json", hashes)
    _write_json_exclusive(
        root / "receipt.json",
        {
            "artifact_hashes_sha256": _file_sha256(
                root / "artifact-hashes.json"
            ),
            "ratios": list(bundle.ratios),
            "same_bytes_for_canonical_and_deformed": True,
            "schema": "c1-r23-representation-v1",
        },
    )


def read_representation_bundle(root: Path) -> dict[str, object]:
    """Strictly replay the exact closed representation inventory and hashes."""
    if not root.is_dir():
        raise ValueError("representation bundle root is absent")
    actual = frozenset(path.name for path in root.iterdir() if path.is_file())
    if actual != _REPRESENTATION_FILES:
        raise ValueError("representation bundle inventory mismatch")
    with (root / "receipt.json").open(encoding="utf-8") as source:
        receipt = json.load(source)
    with (root / "artifact-hashes.json").open(encoding="utf-8") as source:
        hashes = json.load(source)
    if (
        not isinstance(receipt, dict)
        or frozenset(receipt) != _REPRESENTATION_RECEIPT_KEYS
    ):
        raise ValueError("representation receipt keys differ")
    if receipt["schema"] != "c1-r23-representation-v1":
        raise ValueError("representation receipt schema mismatch")
    if receipt["ratios"] != list(R23_RATIOS):
        raise ValueError("representation receipt ratios differ")
    if receipt["same_bytes_for_canonical_and_deformed"] is not True:
        raise ValueError("representation receipt byte-reuse flag differs")
    if receipt["artifact_hashes_sha256"] != _file_sha256(
        root / "artifact-hashes.json"
    ):
        raise ValueError("representation receipt artifact-hashes hash mismatch")
    if (
        not isinstance(hashes, dict)
        or frozenset(hashes) != _REPRESENTATION_PAYLOAD_FILES
    ):
        raise ValueError("representation payload digest keys differ")
    for name in sorted(_REPRESENTATION_PAYLOAD_FILES):
        expected = hashes[name]
        if _file_sha256(root / name) != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
    with np.load(root / "signed-fields.npz", allow_pickle=False) as payload:
        ratios = payload["ratios"].tolist()
    if ratios != list(R23_RATIOS):
        raise ValueError("representation ratios mismatch")
    return dict(receipt)
