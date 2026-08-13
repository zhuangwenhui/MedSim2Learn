"""Source appearance and shared mesh refinement for the C1-R21 screen."""

from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from dpost.c1_r19_triplanar_continuity import (
    compute_area_weighted_vertex_normals,
)


R21_SOURCE_SCHEMA = "c1-r21-source-rois-v1"
R21_SEQUENCE_IDS = ("03", "06", "10", "14")
R21_CANDIDATE_FRACTIONS = (0.25, 0.5, 0.75)
R21_ATTRACTION_COUNT = 512
R21_RANDOM_SEED = 2107
R21_INFLUENCE_RATIO = 0.18
R21_KILL_RATIO = 0.02
R21_MAX_GROWTH_ITERATIONS = 2048
R21_ROOT_DIAMETER_RATIOS = (0.012, 0.020, 0.032)
R21_SCALE_NAMES = ("small", "medium", "large")


@dataclass(frozen=True)
class SourceAppearanceSample:
    """Hold one pinned source frame and its three frozen ROI masks."""

    sequence_id: str
    frame_index: int
    video_sha256: str
    rgb: np.ndarray
    organ_mask: np.ndarray
    vessel_mask: np.ndarray
    adjacent_tissue_mask: np.ndarray


@dataclass(frozen=True)
class AppearanceStatistics:
    """Hold sequence-equal CIELAB appearance centers and audit counts."""

    sequence_ids: tuple[str, ...]
    base_appearance_lab: np.ndarray
    vessel_delta_lab: np.ndarray
    per_sequence_base_lab: np.ndarray
    per_sequence_vessel_delta_lab: np.ndarray
    base_valid_pixel_counts: tuple[int, ...]
    vessel_valid_pixel_counts: tuple[int, ...]
    tissue_valid_pixel_counts: tuple[int, ...]


@dataclass(frozen=True)
class MidpointRefinementLevel:
    """Describe one deterministic midpoint insertion step."""

    input_vertex_count: int
    edge_pairs: np.ndarray


@dataclass(frozen=True)
class MidpointRefinementMap:
    """Describe all midpoint insertions derived from canonical faces."""

    base_vertex_count: int
    levels: tuple[MidpointRefinementLevel, ...]
    refined_faces: np.ndarray
    refined_vertex_count: int


@dataclass(frozen=True)
class RefinedPairedGeometry:
    """Hold canonical and deformed coordinates sharing one refinement map."""

    canonical_vertices: np.ndarray
    deformed_vertices: np.ndarray
    faces: np.ndarray
    refinement_map: MidpointRefinementMap


@dataclass(frozen=True)
class GraphSurfaceVesselTree:
    """Hold one deterministic tree grown over mesh-vertex adjacency."""

    root_vertex_index: int
    node_vertex_indices: np.ndarray
    parent_node_indices: np.ndarray
    attraction_points: np.ndarray
    attraction_count: int
    killed_attraction_count: int
    remaining_attraction_count: int
    iteration_count: int
    stop_reason: str
    surface_extent: float
    seed: int
    influence_radius: float
    kill_radius: float
    max_iterations: int


@dataclass(frozen=True)
class VesselColorFields:
    """Hold the base colour and three canonical-derived vessel fields."""

    scale_names: tuple[str, ...]
    root_diameter_ratios: tuple[float, ...]
    root_diameters: np.ndarray
    base_colors: np.ndarray
    blend_fields: tuple[np.ndarray, ...]
    vertex_colors: tuple[np.ndarray, ...]


def _file_sha256(path: Path) -> str:
    """Return one file's SHA-256 without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_rgb_and_masks(sample: SourceAppearanceSample) -> None:
    """Require one source sample to use exact RGB and boolean mask types."""
    rgb = sample.rgb
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or rgb.shape[0] == 0
        or rgb.shape[1] == 0
    ):
        raise ValueError("source RGB must be a nonempty uint8 (H, W, 3) array")
    for name, mask in (
        ("organ", sample.organ_mask),
        ("vessel", sample.vessel_mask),
        ("adjacent tissue", sample.adjacent_tissue_mask),
    ):
        if (
            not isinstance(mask, np.ndarray)
            or mask.dtype != np.bool_
            or mask.shape != rgb.shape[:2]
        ):
            raise ValueError(f"{name} mask must be a boolean RGB-sized array")
    if np.any(sample.vessel_mask & sample.adjacent_tissue_mask):
        raise ValueError("vessel and adjacent-tissue masks overlap")
    if np.any(sample.vessel_mask & ~sample.organ_mask):
        raise ValueError("vessel mask is not contained in the organ mask")
    if np.any(sample.adjacent_tissue_mask & ~sample.organ_mask):
        raise ValueError(
            "adjacent-tissue mask is not contained in the organ mask"
        )


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 RGB into OpenCV float CIELAB coordinates."""
    normalized = rgb.astype(np.float32) / 255.0
    return cv2.cvtColor(normalized, cv2.COLOR_RGB2LAB).astype(np.float64)


def compute_sequence_equal_lab_statistics(
    samples: Sequence[SourceAppearanceSample],
    *,
    dark_max_rgb: int,
    highlight_min_rgb: int,
) -> AppearanceStatistics:
    """Compute robust appearance centers with one equal vote per sequence.

    These image-space statistics include illumination and camera response.
    They are appearance references, not physical albedo measurements.
    """
    if not samples:
        raise ValueError("at least one source appearance sample is required")
    if not (0 <= dark_max_rgb < highlight_min_rgb <= 255):
        raise ValueError(
            "pixel thresholds must satisfy 0 <= dark < highlight <= 255"
        )
    sequence_ids = tuple(sample.sequence_id for sample in samples)
    if len(set(sequence_ids)) != len(sequence_ids):
        raise ValueError("source appearance sequence IDs must be unique")

    base_centers = []
    vessel_deltas = []
    base_counts = []
    vessel_counts = []
    tissue_counts = []
    for sample in samples:
        _require_rgb_and_masks(sample)
        rgb = sample.rgb
        # Dark pixels require every channel to be dark; neutral highlights
        # require every channel to be bright. Saturated tissue remains valid.
        valid = (
            (rgb.max(axis=2) > dark_max_rgb)
            & (rgb.min(axis=2) < highlight_min_rgb)
        )
        annotated_pair = sample.vessel_mask | sample.adjacent_tissue_mask
        base_mask = sample.organ_mask & ~annotated_pair & valid
        vessel_mask = sample.vessel_mask & valid
        tissue_mask = sample.adjacent_tissue_mask & valid
        counts = tuple(
            int(np.count_nonzero(mask))
            for mask in (base_mask, vessel_mask, tissue_mask)
        )
        if min(counts) == 0:
            raise ValueError(
                f"source sequence {sample.sequence_id} has an empty valid ROI"
            )
        lab = _rgb_to_lab(rgb)
        base_center = np.median(lab[base_mask], axis=0)
        vessel_center = np.median(lab[vessel_mask], axis=0)
        tissue_center = np.median(lab[tissue_mask], axis=0)
        base_centers.append(base_center)
        vessel_deltas.append(vessel_center - tissue_center)
        base_counts.append(counts[0])
        vessel_counts.append(counts[1])
        tissue_counts.append(counts[2])

    per_sequence_base = np.stack(base_centers).astype(np.float64)
    per_sequence_delta = np.stack(vessel_deltas).astype(np.float64)
    base_appearance = np.median(per_sequence_base, axis=0)
    vessel_delta = np.median(per_sequence_delta, axis=0)
    for value in (
        per_sequence_base,
        per_sequence_delta,
        base_appearance,
        vessel_delta,
    ):
        value.setflags(write=False)
    return AppearanceStatistics(
        sequence_ids=sequence_ids,
        base_appearance_lab=base_appearance,
        vessel_delta_lab=vessel_delta,
        per_sequence_base_lab=per_sequence_base,
        per_sequence_vessel_delta_lab=per_sequence_delta,
        base_valid_pixel_counts=tuple(base_counts),
        vessel_valid_pixel_counts=tuple(vessel_counts),
        tissue_valid_pixel_counts=tuple(tissue_counts),
    )


def _load_json_object(path: Path) -> Mapping[str, object]:
    """Load one UTF-8 JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source ROI configuration must be a JSON object")
    return value


def _polygon_mask(
    points_value: object,
    *,
    width: int,
    height: int,
    name: str,
) -> np.ndarray:
    """Rasterize one in-bounds polygon into an immutable boolean mask."""
    points = np.asarray(points_value)
    if (
        points.ndim != 2
        or points.shape[1] != 2
        or len(points) < 3
        or not np.issubdtype(points.dtype, np.integer)
    ):
        raise ValueError(
            f"{name} polygon must contain at least three XY points"
        )
    if (
        np.any(points[:, 0] < 0)
        or np.any(points[:, 0] >= width)
        or np.any(points[:, 1] < 0)
        or np.any(points[:, 1] >= height)
    ):
        raise ValueError(f"{name} polygon point is outside the video frame")
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [points.astype(np.int32)], 1)
    result = mask.astype(bool)
    result.setflags(write=False)
    return result


def _require_source_config(config: Mapping[str, object]) -> Sequence[object]:
    """Require the R21 sequence and first-eligible selection contract."""
    if config.get("schema") != R21_SOURCE_SCHEMA:
        raise ValueError("source ROI configuration schema differs")
    if tuple(config.get("required_sequence_ids", ())) != R21_SEQUENCE_IDS:
        raise ValueError("source ROI sequence IDs differ from 03/06/10/14")
    rule = config.get("selection_rule")
    if not isinstance(rule, dict):
        raise ValueError("source ROI selection rule is missing")
    if tuple(rule.get("candidate_fractions_in_order", ())) != (
        R21_CANDIDATE_FRACTIONS
    ):
        raise ValueError("source frame candidate fractions differ")
    if rule.get("first_eligible_only") is not True:
        raise ValueError("source selection is not first-eligible-only")
    if rule.get("statistics_seen_before_selection") is not False:
        raise ValueError("source frames were selected after seeing statistics")
    sequences = config.get("sequences")
    if not isinstance(sequences, list) or len(sequences) != len(
        R21_SEQUENCE_IDS
    ):
        raise ValueError("source sequence records differ from the frozen set")
    return sequences


def _require_selection_record(
    record: Mapping[str, object],
    *,
    sequence_id: str,
) -> None:
    """Require one record to freeze the first 25% candidate as accepted."""
    frame_count = record.get("frame_count")
    candidates = record.get("selection_candidates")
    if not isinstance(frame_count, int) or frame_count <= 0:
        raise ValueError(f"frame count is invalid for sequence {sequence_id}")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError(
            f"selection candidates differ for sequence {sequence_id}"
        )
    for index, (candidate, fraction) in enumerate(
        zip(candidates, R21_CANDIDATE_FRACTIONS, strict=True)
    ):
        if not isinstance(candidate, dict):
            raise ValueError(
                f"selection candidate is invalid for sequence {sequence_id}"
            )
        expected_index = min(frame_count - 1, int(frame_count * fraction))
        if (
            candidate.get("fraction") != fraction
            or candidate.get("frame_index") != expected_index
        ):
            raise ValueError(
                f"selection candidate index differs for sequence {sequence_id}"
            )
        expected_decision = (
            "accepted" if index == 0 else "not_evaluated_after_first_accept"
        )
        if candidate.get("decision") != expected_decision:
            raise ValueError(
                f"selection decision differs for sequence {sequence_id}"
            )
    if record.get("frame_index") != candidates[0]["frame_index"]:
        raise ValueError(f"selected frame differs for sequence {sequence_id}")


def load_frozen_source_samples(
    config_path: Path,
    source_root: Path,
) -> tuple[SourceAppearanceSample, ...]:
    """Replay source frames only after validating all frozen provenance."""
    config = _load_json_object(Path(config_path))
    sequence_values = _require_source_config(config)
    samples = []
    for expected_id, value in zip(
        R21_SEQUENCE_IDS,
        sequence_values,
        strict=True,
    ):
        if (
            not isinstance(value, dict)
            or value.get("sequence_id") != expected_id
        ):
            raise ValueError(
                f"source record order differs at sequence {expected_id}"
            )
        _require_selection_record(value, sequence_id=expected_id)
        video_file = value.get("video_file")
        if (
            not isinstance(video_file, str)
            or Path(video_file).name != video_file
            or Path(video_file).stem != expected_id
        ):
            raise ValueError(f"video file differs for sequence {expected_id}")
        video_path = Path(source_root) / video_file
        observed_sha256 = _file_sha256(video_path)
        if observed_sha256 != value.get("video_sha256"):
            raise ValueError(
                f"video SHA-256 differs for sequence {expected_id}"
            )

        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                raise ValueError(
                    f"could not open video for sequence {expected_id}"
                )
            observed_properties = (
                int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
                float(capture.get(cv2.CAP_PROP_FPS)),
                int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            expected_properties = (
                value.get("frame_count"),
                value.get("fps"),
                value.get("width"),
                value.get("height"),
            )
            if (
                observed_properties[0] != expected_properties[0]
                or not np.isclose(
                    observed_properties[1],
                    expected_properties[1],
                    rtol=0.0,
                    atol=1e-9,
                )
                or observed_properties[2:] != expected_properties[2:]
            ):
                raise ValueError(
                    f"video properties differ for sequence {expected_id}"
                )
            frame_index = value.get("frame_index")
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                raise ValueError(
                    f"could not seek video for sequence {expected_id}"
                )
            position_before = float(
                capture.get(cv2.CAP_PROP_POS_FRAMES)
            )
            if (
                not np.isfinite(position_before)
                or not np.isclose(
                    position_before,
                    frame_index,
                    rtol=0.0,
                    atol=1e-6,
                )
            ):
                raise ValueError(
                    "video position differs before decode for sequence "
                    f"{expected_id}"
                )
            ok, bgr = capture.read()
            if not ok:
                raise ValueError(
                    f"could not decode frame for sequence {expected_id}"
                )
            position_after = float(capture.get(cv2.CAP_PROP_POS_FRAMES))
            if (
                not np.isfinite(position_after)
                or not np.isclose(
                    position_after,
                    frame_index + 1,
                    rtol=0.0,
                    atol=1e-6,
                )
            ):
                raise ValueError(
                    "video position differs after decode for sequence "
                    f"{expected_id}"
                )
        finally:
            capture.release()
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        width = int(value["width"])
        height = int(value["height"])
        rgb.setflags(write=False)
        sample = SourceAppearanceSample(
            sequence_id=expected_id,
            frame_index=int(frame_index),
            video_sha256=observed_sha256,
            rgb=rgb,
            organ_mask=_polygon_mask(
                value.get("organ_polygon_xy"),
                width=width,
                height=height,
                name="organ",
            ),
            vessel_mask=_polygon_mask(
                value.get("vessel_polygon_xy"),
                width=width,
                height=height,
                name="vessel",
            ),
            adjacent_tissue_mask=_polygon_mask(
                value.get("adjacent_tissue_polygon_xy"),
                width=width,
                height=height,
                name="adjacent tissue",
            ),
        )
        _require_rgb_and_masks(sample)
        samples.append(sample)
    return tuple(samples)


def _require_vertices(vertices: np.ndarray, name: str) -> None:
    """Require finite float64 triangle-mesh coordinates."""
    if (
        not isinstance(vertices, np.ndarray)
        or vertices.dtype != np.float64
        or vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError(
            f"{name} must be a nonempty finite float64 (N, 3) array"
        )


def _require_faces(faces: np.ndarray, vertex_count: int, name: str) -> None:
    """Require in-range integer triangle rows."""
    if (
        not isinstance(faces, np.ndarray)
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError(f"{name} must be a nonempty integer (N, 3) array")
    if np.any(faces < 0) or np.any(faces >= vertex_count):
        raise ValueError(f"{name} index is outside the vertex array")


def _validate_cyclic_face_rows(
    reference: np.ndarray,
    candidate: np.ndarray,
) -> None:
    """Require candidate rows to be orientation-preserving cyclic rotations."""
    if reference.shape != candidate.shape:
        raise ValueError("deformed faces have a different shape")
    cyclic_rows = np.stack(
        (
            reference,
            np.roll(reference, -1, axis=1),
            np.roll(reference, -2, axis=1),
        ),
        axis=1,
    )
    matches = np.any(
        np.all(cyclic_rows == candidate[:, np.newaxis, :], axis=2),
        axis=1,
    )
    if not np.all(matches):
        row_index = int(np.flatnonzero(~matches)[0])
        raise ValueError(f"deformed face row differs at row {row_index}")


def build_midpoint_refinement_map(
    canonical_faces: np.ndarray,
    *,
    vertex_count: int,
    levels: int = 2,
) -> MidpointRefinementMap:
    """Build deterministic edge insertions from canonical faces only."""
    if (
        isinstance(vertex_count, bool)
        or not isinstance(vertex_count, Integral)
        or vertex_count <= 0
    ):
        raise ValueError("vertex_count must be a positive integer")
    vertex_count = int(vertex_count)
    _require_faces(canonical_faces, vertex_count, "canonical faces")
    if not isinstance(levels, int) or isinstance(levels, bool) or levels < 1:
        raise ValueError(
            "midpoint refinement levels must be a positive integer"
        )
    current_faces = canonical_faces.astype(np.int64, copy=True)
    current_vertex_count = vertex_count
    level_records = []
    for _ in range(levels):
        edges = np.concatenate(
            (
                current_faces[:, (0, 1)],
                current_faces[:, (1, 2)],
                current_faces[:, (2, 0)],
            ),
            axis=0,
        )
        edges.sort(axis=1)
        edge_pairs = np.unique(edges, axis=0).astype(np.int64)
        edge_to_index = {
            (int(first), int(second)): current_vertex_count + index
            for index, (first, second) in enumerate(edge_pairs)
        }
        refined_faces = np.empty((len(current_faces) * 4, 3), dtype=np.int64)
        for face_index, (first, second, third) in enumerate(current_faces):
            midpoint_first_second = edge_to_index[
                tuple(sorted((int(first), int(second))))
            ]
            midpoint_second_third = edge_to_index[
                tuple(sorted((int(second), int(third))))
            ]
            midpoint_third_first = edge_to_index[
                tuple(sorted((int(third), int(first))))
            ]
            start = face_index * 4
            refined_faces[start:start + 4] = (
                (first, midpoint_first_second, midpoint_third_first),
                (midpoint_first_second, second, midpoint_second_third),
                (midpoint_third_first, midpoint_second_third, third),
                (
                    midpoint_first_second,
                    midpoint_second_third,
                    midpoint_third_first,
                ),
            )
        edge_pairs.setflags(write=False)
        level_records.append(
            MidpointRefinementLevel(
                input_vertex_count=current_vertex_count,
                edge_pairs=edge_pairs,
            )
        )
        current_vertex_count += len(edge_pairs)
        current_faces = refined_faces
    current_faces.setflags(write=False)
    return MidpointRefinementMap(
        base_vertex_count=vertex_count,
        levels=tuple(level_records),
        refined_faces=current_faces,
        refined_vertex_count=current_vertex_count,
    )


def apply_midpoint_refinement(
    vertices: np.ndarray,
    refinement_map: MidpointRefinementMap,
) -> np.ndarray:
    """Apply one canonical-derived refinement map to a coordinate array."""
    _require_vertices(vertices, "vertices")
    if len(vertices) != refinement_map.base_vertex_count:
        raise ValueError("vertices do not match refinement-map base count")
    refined = vertices.copy()
    for level in refinement_map.levels:
        if len(refined) != level.input_vertex_count:
            raise ValueError("refinement level input count differs")
        midpoints = refined[level.edge_pairs].mean(axis=1)
        refined = np.concatenate((refined, midpoints), axis=0)
    refined.setflags(write=False)
    return refined


def refine_paired_geometry(
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    deformed_vertices: np.ndarray,
    deformed_faces: np.ndarray,
    *,
    levels: int = 2,
) -> RefinedPairedGeometry:
    """Refine canonical and deformed coordinates with one shared map."""
    _require_vertices(canonical_vertices, "canonical vertices")
    _require_vertices(deformed_vertices, "deformed vertices")
    if len(canonical_vertices) != len(deformed_vertices):
        raise ValueError("canonical and deformed vertex counts differ")
    _require_faces(canonical_faces, len(canonical_vertices), "canonical faces")
    _require_faces(deformed_faces, len(deformed_vertices), "deformed faces")
    _validate_cyclic_face_rows(canonical_faces, deformed_faces)

    refinement_map = build_midpoint_refinement_map(
        canonical_faces,
        vertex_count=len(canonical_vertices),
        levels=levels,
    )
    return RefinedPairedGeometry(
        canonical_vertices=apply_midpoint_refinement(
            canonical_vertices,
            refinement_map,
        ),
        deformed_vertices=apply_midpoint_refinement(
            deformed_vertices,
            refinement_map,
        ),
        faces=refinement_map.refined_faces,
        refinement_map=refinement_map,
    )


def _surface_extent(vertices: np.ndarray) -> float:
    """Return the largest axis-aligned canonical bounding-box extent."""
    extent = float(np.max(vertices.max(axis=0) - vertices.min(axis=0)))
    if not np.isfinite(extent) or extent <= 0.0:
        raise ValueError("surface bounding box must have positive extent")
    return extent


def _vertex_neighbors(
    faces: np.ndarray,
    vertex_count: int,
) -> tuple[np.ndarray, ...]:
    """Build sorted one-ring vertex adjacency from triangle rows."""
    neighbors = [set() for _ in range(vertex_count)]
    for first, second, third in faces:
        first = int(first)
        second = int(second)
        third = int(third)
        neighbors[first].update((second, third))
        neighbors[second].update((first, third))
        neighbors[third].update((first, second))
    result = []
    for values in neighbors:
        array = np.asarray(sorted(values), dtype=np.int64)
        array.setflags(write=False)
        result.append(array)
    return tuple(result)


def sample_equal_area_surface_points(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    count: int = R21_ATTRACTION_COUNT,
    seed: int = R21_RANDOM_SEED,
) -> np.ndarray:
    """Sample deterministic triangle-area-weighted surface points."""
    _require_vertices(vertices, "surface vertices")
    _require_faces(faces, len(vertices), "surface faces")
    if isinstance(count, bool) or not isinstance(count, Integral) or count < 1:
        raise ValueError("surface sample count must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, Integral):
        raise ValueError("surface sample seed must be an integer")

    triangles = vertices[faces]
    double_areas = np.linalg.norm(
        np.cross(
            triangles[:, 1] - triangles[:, 0],
            triangles[:, 2] - triangles[:, 0],
        ),
        axis=1,
    )
    total_area = float(double_areas.sum())
    if not np.isfinite(total_area) or total_area <= 0.0:
        raise ValueError("surface faces must have positive total area")

    generator = np.random.default_rng(int(seed))
    cumulative = np.cumsum(double_areas, dtype=np.float64)
    face_samples = generator.random(int(count)) * cumulative[-1]
    face_indices = np.searchsorted(
        cumulative,
        face_samples,
        side="right",
    )
    square_root = np.sqrt(generator.random(int(count)))
    second_fraction = generator.random(int(count))
    weights = np.stack(
        (
            1.0 - square_root,
            square_root * (1.0 - second_fraction),
            square_root * second_fraction,
        ),
        axis=1,
    )
    points = np.sum(
        triangles[face_indices] * weights[:, :, np.newaxis],
        axis=1,
    ).astype(np.float64)
    points.setflags(write=False)
    return points


def _require_attraction_points(points: np.ndarray) -> None:
    """Require finite float64 attraction coordinates."""
    if (
        not isinstance(points, np.ndarray)
        or points.dtype != np.float64
        or points.ndim != 2
        or points.shape[1] != 3
        or not np.isfinite(points).all()
    ):
        raise ValueError(
            "attraction points must be a finite float64 (N, 3) array"
        )


def _nearest_root_vertex(vertices: np.ndarray, extent: float) -> int:
    """Resolve the frozen engineering root target with lowest-index ties."""
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    target = center + np.array((-0.35, 0.0, 0.35)) * extent
    squared_distances = np.sum((vertices - target) ** 2, axis=1)
    return int(np.argmin(squared_distances))


def _kill_reached_attractors(
    attraction_points: np.ndarray,
    active: np.ndarray,
    node_positions: np.ndarray,
    kill_radius: float,
) -> None:
    """Deactivate points within the frozen Euclidean kill radius."""
    active_indices = np.flatnonzero(active)
    if len(active_indices) == 0:
        return
    deltas = (
        attraction_points[active_indices, np.newaxis, :]
        - node_positions[np.newaxis, :, :]
    )
    minimum_squared = np.min(np.sum(deltas * deltas, axis=2), axis=1)
    reached = minimum_squared <= kill_radius * kill_radius
    active[active_indices[reached]] = False


def grow_graph_surface_vessel_tree(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    attraction_points: np.ndarray | None = None,
) -> GraphSurfaceVesselTree:
    """Grow the fixed R21 graph-surface space-colonization tree."""
    _require_vertices(vertices, "surface vertices")
    _require_faces(faces, len(vertices), "surface faces")
    extent = _surface_extent(vertices)
    if attraction_points is None:
        points = sample_equal_area_surface_points(vertices, faces)
    else:
        _require_attraction_points(attraction_points)
        points = attraction_points.copy()
        points.setflags(write=False)

    root_vertex = _nearest_root_vertex(vertices, extent)
    influence_radius = R21_INFLUENCE_RATIO * extent
    kill_radius = R21_KILL_RATIO * extent
    normals = compute_area_weighted_vertex_normals(vertices, faces)
    neighbors = _vertex_neighbors(faces, len(vertices))
    node_vertices = [root_vertex]
    parent_nodes = [-1]
    visited_vertices = {root_vertex}
    active = np.ones(len(points), dtype=bool)
    stop_reason = "max_iterations"
    iteration_count = 0

    for iteration in range(1, R21_MAX_GROWTH_ITERATIONS + 1):
        iteration_count = iteration
        node_positions = vertices[np.asarray(node_vertices)]
        _kill_reached_attractors(
            points,
            active,
            node_positions,
            kill_radius,
        )
        active_indices = np.flatnonzero(active)
        if len(active_indices) == 0:
            stop_reason = "all_attractors_killed"
            break

        deltas = (
            points[active_indices, np.newaxis, :]
            - node_positions[np.newaxis, :, :]
        )
        squared_distances = np.sum(deltas * deltas, axis=2)
        assigned_nodes = np.argmin(squared_distances, axis=1)
        minimum_squared = squared_distances[
            np.arange(len(active_indices)),
            assigned_nodes,
        ]
        within_influence = minimum_squared <= influence_radius ** 2
        assigned_attractors = active_indices[within_influence]
        assigned_nodes = assigned_nodes[within_influence]

        additions: list[tuple[int, int]] = []
        reserved_targets: set[int] = set()
        for parent_node in range(len(node_vertices)):
            assigned = assigned_attractors[
                assigned_nodes == parent_node
            ]
            if len(assigned) == 0:
                continue
            parent_vertex = node_vertices[parent_node]
            directions = points[assigned] - vertices[parent_vertex]
            lengths = np.linalg.norm(directions, axis=1)
            directions = directions[lengths > 0.0]
            lengths = lengths[lengths > 0.0]
            if len(directions) == 0:
                continue
            mean_direction = np.mean(
                directions / lengths[:, np.newaxis],
                axis=0,
            )
            tangent = mean_direction - (
                np.dot(mean_direction, normals[parent_vertex])
                * normals[parent_vertex]
            )
            tangent_length = float(np.linalg.norm(tangent))
            if tangent_length <= 0.0:
                continue
            tangent /= tangent_length

            candidates = np.asarray(
                [
                    int(candidate)
                    for candidate in neighbors[parent_vertex]
                    if int(candidate) not in visited_vertices
                    and int(candidate) not in reserved_targets
                ],
                dtype=np.int64,
            )
            if len(candidates) == 0:
                continue
            candidate_directions = vertices[candidates] - vertices[
                parent_vertex
            ]
            candidate_lengths = np.linalg.norm(
                candidate_directions,
                axis=1,
            )
            scores = (
                candidate_directions / candidate_lengths[:, np.newaxis]
            ) @ tangent
            order = np.lexsort((candidates, -scores))
            target_vertex = int(candidates[int(order[0])])
            additions.append((parent_node, target_vertex))
            reserved_targets.add(target_vertex)

        if not additions:
            stop_reason = "no_growth"
            break
        for parent_node, target_vertex in additions:
            visited_vertices.add(target_vertex)
            node_vertices.append(target_vertex)
            parent_nodes.append(parent_node)

    node_array = np.asarray(node_vertices, dtype=np.int64)
    parent_array = np.asarray(parent_nodes, dtype=np.int64)
    node_array.setflags(write=False)
    parent_array.setflags(write=False)
    return GraphSurfaceVesselTree(
        root_vertex_index=root_vertex,
        node_vertex_indices=node_array,
        parent_node_indices=parent_array,
        attraction_points=points,
        attraction_count=len(points),
        killed_attraction_count=int(len(points) - np.count_nonzero(active)),
        remaining_attraction_count=int(np.count_nonzero(active)),
        iteration_count=iteration_count,
        stop_reason=stop_reason,
        surface_extent=extent,
        seed=R21_RANDOM_SEED,
        influence_radius=influence_radius,
        kill_radius=kill_radius,
        max_iterations=R21_MAX_GROWTH_ITERATIONS,
    )


def _require_tree_topology(tree: GraphSurfaceVesselTree) -> None:
    """Require one root-first, connected, acyclic tree-node order."""
    nodes = tree.node_vertex_indices
    parents = tree.parent_node_indices
    if (
        not isinstance(nodes, np.ndarray)
        or nodes.dtype != np.int64
        or nodes.ndim != 1
        or len(nodes) == 0
        or not isinstance(parents, np.ndarray)
        or parents.dtype != np.int64
        or parents.shape != nodes.shape
        or parents[0] != -1
        or len(np.unique(nodes)) != len(nodes)
        or np.any(parents[1:] < 0)
        or np.any(parents[1:] >= np.arange(1, len(parents)))
    ):
        raise ValueError("surface vessel tree topology is invalid")


def lift_tree_through_midpoints(
    tree: GraphSurfaceVesselTree,
    refinement_level: MidpointRefinementLevel,
) -> GraphSurfaceVesselTree:
    """Split every existing tree edge at its unique refinement midpoint."""
    _require_tree_topology(tree)
    edge_pairs = refinement_level.edge_pairs
    input_vertex_count = refinement_level.input_vertex_count
    if (
        isinstance(input_vertex_count, bool)
        or not isinstance(input_vertex_count, Integral)
        or input_vertex_count <= 0
    ):
        raise ValueError("refinement input vertex count must be positive")
    if (
        not isinstance(edge_pairs, np.ndarray)
        or edge_pairs.dtype != np.int64
        or edge_pairs.ndim != 2
        or edge_pairs.shape[1] != 2
        or len(edge_pairs) == 0
        or np.any(edge_pairs < 0)
        or np.any(edge_pairs >= input_vertex_count)
        or np.any(edge_pairs[:, 0] >= edge_pairs[:, 1])
        or len(np.unique(edge_pairs, axis=0)) != len(edge_pairs)
    ):
        raise ValueError("refinement edge pairs are invalid")
    if np.any(tree.node_vertex_indices >= input_vertex_count):
        raise ValueError("tree vertex is outside the refinement input")

    edge_to_midpoint = {
        (int(first), int(second)): input_vertex_count + edge_index
        for edge_index, (first, second) in enumerate(edge_pairs)
    }
    node_count = 2 * len(tree.node_vertex_indices) - 1
    lifted_nodes = np.empty(node_count, dtype=np.int64)
    lifted_parents = np.empty(node_count, dtype=np.int64)
    original_to_lifted = np.empty(
        len(tree.node_vertex_indices),
        dtype=np.int64,
    )
    lifted_nodes[0] = tree.node_vertex_indices[0]
    lifted_parents[0] = -1
    original_to_lifted[0] = 0
    output_index = 1
    for child_node in range(1, len(tree.node_vertex_indices)):
        parent_node = int(tree.parent_node_indices[child_node])
        parent_vertex = int(tree.node_vertex_indices[parent_node])
        child_vertex = int(tree.node_vertex_indices[child_node])
        edge = tuple(sorted((parent_vertex, child_vertex)))
        midpoint_vertex = edge_to_midpoint.get(edge)
        if midpoint_vertex is None:
            raise ValueError(f"tree edge is absent from refinement: {edge!r}")
        lifted_nodes[output_index] = midpoint_vertex
        lifted_parents[output_index] = original_to_lifted[parent_node]
        lifted_nodes[output_index + 1] = child_vertex
        lifted_parents[output_index + 1] = output_index
        original_to_lifted[child_node] = output_index + 1
        output_index += 2

    attraction_points = tree.attraction_points.copy()
    lifted_nodes.setflags(write=False)
    lifted_parents.setflags(write=False)
    attraction_points.setflags(write=False)
    return GraphSurfaceVesselTree(
        root_vertex_index=tree.root_vertex_index,
        node_vertex_indices=lifted_nodes,
        parent_node_indices=lifted_parents,
        attraction_points=attraction_points,
        attraction_count=tree.attraction_count,
        killed_attraction_count=tree.killed_attraction_count,
        remaining_attraction_count=tree.remaining_attraction_count,
        iteration_count=tree.iteration_count,
        stop_reason=tree.stop_reason,
        surface_extent=tree.surface_extent,
        seed=tree.seed,
        influence_radius=tree.influence_radius,
        kill_radius=tree.kill_radius,
        max_iterations=tree.max_iterations,
    )


def compute_equal_terminal_diameters(
    tree: GraphSurfaceVesselTree,
    root_diameter: float,
) -> np.ndarray:
    """Apply cubic taper under the equal-terminal-demand assumption."""
    _require_tree_topology(tree)
    if not np.isfinite(root_diameter) or root_diameter <= 0.0:
        raise ValueError("root diameter must be positive and finite")
    parents = tree.parent_node_indices
    child_counts = np.bincount(
        parents[1:],
        minlength=len(parents),
    )
    terminal_counts = (child_counts == 0).astype(np.int64)
    for child in range(len(parents) - 1, 0, -1):
        terminal_counts[parents[child]] += terminal_counts[child]
    diameters = root_diameter * np.cbrt(
        terminal_counts.astype(np.float64) / terminal_counts[0]
    )
    diameters.setflags(write=False)
    return diameters


def _surface_centerline_distances(
    vertices: np.ndarray,
    faces: np.ndarray,
    tree: GraphSurfaceVesselTree,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute deterministic multi-source graph distances to the tree."""
    _require_vertices(vertices, "surface vertices")
    _require_faces(faces, len(vertices), "surface faces")
    _require_tree_topology(tree)
    if np.any(tree.node_vertex_indices >= len(vertices)):
        raise ValueError("surface vessel tree vertex is out of range")
    neighbors = _vertex_neighbors(faces, len(vertices))
    distances = np.full(len(vertices), np.inf, dtype=np.float64)
    nearest_nodes = np.full(len(vertices), -1, dtype=np.int64)
    queue: list[tuple[float, int, int]] = []
    for node_index, vertex_index in enumerate(tree.node_vertex_indices):
        vertex_index = int(vertex_index)
        distances[vertex_index] = 0.0
        nearest_nodes[vertex_index] = node_index
        heapq.heappush(queue, (0.0, node_index, vertex_index))

    while queue:
        distance, source_node, vertex_index = heapq.heappop(queue)
        if (
            distance != distances[vertex_index]
            or source_node != nearest_nodes[vertex_index]
        ):
            continue
        for neighbor in neighbors[vertex_index]:
            neighbor = int(neighbor)
            candidate_distance = distance + float(
                np.linalg.norm(vertices[neighbor] - vertices[vertex_index])
            )
            if candidate_distance < distances[neighbor] or (
                candidate_distance == distances[neighbor]
                and source_node < nearest_nodes[neighbor]
            ):
                distances[neighbor] = candidate_distance
                nearest_nodes[neighbor] = source_node
                heapq.heappush(
                    queue,
                    (candidate_distance, source_node, neighbor),
                )
    if not np.isfinite(distances).all() or np.any(nearest_nodes < 0):
        raise ValueError("surface graph is disconnected from the vessel tree")
    distances.setflags(write=False)
    nearest_nodes.setflags(write=False)
    return distances, nearest_nodes


def _smooth_blend_from_distances(
    distances: np.ndarray,
    nearest_nodes: np.ndarray,
    node_diameters: np.ndarray,
) -> np.ndarray:
    """Blend from vessel to tissue with a cubic smoothstep boundary."""
    radii = node_diameters[nearest_nodes] / 2.0
    normalized = np.clip(distances / radii, 0.0, 1.0)
    blend = 1.0 - normalized * normalized * (3.0 - 2.0 * normalized)
    blend.setflags(write=False)
    return blend


def _lab_rows_to_rgb(lab: np.ndarray) -> np.ndarray:
    """Convert float CIELAB rows into rounded uint8 RGB rows."""
    converted = cv2.cvtColor(
        lab.astype(np.float32).reshape((-1, 1, 3)),
        cv2.COLOR_LAB2RGB,
    ).reshape((-1, 3))
    colors = np.floor(np.clip(converted, 0.0, 1.0) * 255.0 + 0.5).astype(
        np.uint8
    )
    colors.setflags(write=False)
    return colors


def build_vessel_color_fields(
    canonical_vertices: np.ndarray,
    faces: np.ndarray,
    tree: GraphSurfaceVesselTree,
    base_appearance_lab: np.ndarray,
    vessel_delta_lab: np.ndarray,
) -> VesselColorFields:
    """Build one base and three shared continuous vertex-colour fields."""
    _require_vertices(canonical_vertices, "canonical vertices")
    _require_faces(faces, len(canonical_vertices), "canonical faces")
    for name, value in (
        ("base appearance Lab", base_appearance_lab),
        ("vessel delta Lab", vessel_delta_lab),
    ):
        if (
            not isinstance(value, np.ndarray)
            or value.dtype != np.float64
            or value.shape != (3,)
            or not np.isfinite(value).all()
        ):
            raise ValueError(f"{name} must be a finite float64 RGB-sized row")
    extent = _surface_extent(canonical_vertices)
    if not np.isclose(tree.surface_extent, extent, rtol=0.0, atol=1e-12):
        raise ValueError("tree and canonical surface extents differ")

    distances, nearest_nodes = _surface_centerline_distances(
        canonical_vertices,
        faces,
        tree,
    )
    base_lab = np.repeat(
        base_appearance_lab[np.newaxis, :],
        len(canonical_vertices),
        axis=0,
    )
    base_colors = _lab_rows_to_rgb(base_lab)
    root_diameters = np.asarray(
        R21_ROOT_DIAMETER_RATIOS,
        dtype=np.float64,
    ) * extent
    blend_fields = []
    color_fields = []
    for root_diameter in root_diameters:
        node_diameters = compute_equal_terminal_diameters(
            tree,
            float(root_diameter),
        )
        blend = _smooth_blend_from_distances(
            distances,
            nearest_nodes,
            node_diameters,
        )
        lab = base_lab + blend[:, np.newaxis] * vessel_delta_lab
        blend_fields.append(blend)
        color_fields.append(_lab_rows_to_rgb(lab))
    root_diameters.setflags(write=False)
    return VesselColorFields(
        scale_names=R21_SCALE_NAMES,
        root_diameter_ratios=R21_ROOT_DIAMETER_RATIOS,
        root_diameters=root_diameters,
        base_colors=base_colors,
        blend_fields=tuple(blend_fields),
        vertex_colors=tuple(color_fields),
    )
