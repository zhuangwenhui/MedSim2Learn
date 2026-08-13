"""Per-vertex procedural volumetric microtexture fields for C1-R25.

Implements the frozen R25 design: an improved-gradient-noise fBm family
evaluated at normalized canonical vertex positions, three frozen candidate
constructions plus the amplitude-zero base control, and the sixteen-image
preview bundle writer with its mechanical gates.  Only the per-vertex colour
generator differs from R19; geometry, cameras, background, lighting, base
colour, resolution, and the mapping path stay frozen.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw

from dpost.c1_r16b_source_flatness import (
    _file_sha256,
    _load_png,
    _recursive_file_paths,
    _write_json_exclusive,
    _write_rgb_exclusive,
)
from dpost.c1_r19_triplanar_continuity import (
    ProgressReporter,
    VertexColorRenderer,
    _copy_exclusive,
    _report,
    _require_digest,
    _require_geometry,
    _require_matching_topology,
    _write_npy_exclusive,
    shared_edge_color_diagnostics,
)


R25_SCHEMA = "c1-r25-preview-v1"
METHOD_NAME = "per_vertex_sampled_procedural_volumetric_microtexture_field"
VARIANT_NAMES = ("base", "candidate-1", "candidate-2", "candidate-3")
CANDIDATE_NAMES = ("candidate-1", "candidate-2", "candidate-3")
MESH_NAMES = ("canonical", "deformed-s0521-v0000")
PREVIEW_CAMERA_NAMES = ("z-plus", "iso-plus")
RESOLUTION = (512, 512)

# Frozen engineering adaptations from the approved R25 design (section 4).
AMPLITUDE = 0.2
GAIN = 0.5
LACUNARITY = 2.0
CANDIDATE_SEEDS = {
    "candidate-1": 20260809,
    "candidate-2": 20260810,
    "candidate-3": 20260811,
}
CANDIDATE_1_OCTAVE_WAVELENGTHS = (0.64, 0.32, 0.16)
CANDIDATE_2_OCTAVE_WAVELENGTHS = (0.48, 0.24, 0.12)
CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS = (0.5, 0.25)
CANDIDATE_2_WARP_STRENGTH = 0.08
CANDIDATE_2_WARP_SEED = 20260812
CANDIDATE_3_OCTAVE_WAVELENGTHS = (0.64, 0.32, 0.16)
CANDIDATE_3_FBM_WEIGHT = 0.65
CANDIDATE_3_WORLEY_WEIGHT = 0.35
WORLEY_CELL_SIZE = 0.09

# Frozen mechanical-gate parameters (design section 6).
MEAN_DRIFT_TOLERANCE = 2.0
MAE_THRESHOLD = 4.0
RSS_LIMIT_BYTES = 500_000_000
RSS_SAMPLE_INTERVAL_SECONDS = 0.05
MAE_PAIRS = (
    ("base", "candidate-1"),
    ("base", "candidate-2"),
    ("base", "candidate-3"),
    ("candidate-1", "candidate-2"),
    ("candidate-1", "candidate-3"),
    ("candidate-2", "candidate-3"),
)

# Review-verified base colour and frozen R19 input anchors (design section 3).
EXPECTED_BASE_RGB = (140, 99, 117)
# Fixed legacy-renderer clear colour behind the frozen masks (design v4 M5).
BACKGROUND_CLEAR_RGB = (5, 5, 5)
FROZEN_R19_VERTEX_COLORS_SHA256 = (
    "af2c92d61b73cf34e3802beef7b85f95cd63b4b47e2d3fb5242dd0d17b20474b"
)
FROZEN_R19_MASK_SHA256 = {
    "canonical/z-plus":
        "5cdcfe8f818de089018a95fe50730d41923a8ee26755dc827c84429016d5e33d",
    "canonical/iso-plus":
        "8d4f75d71240cbb56ff1e99da76cd9d95ef2288f7fa1f03d581ac5323bdece30",
    "deformed-s0521-v0000/z-plus":
        "7ef2dea7d1725b6fdf537d217c3ae351b4406c593642c3a045e4b4e2dcb76b48",
    "deformed-s0521-v0000/iso-plus":
        "1f87171958c394beb44a2b2add57afeb8b55334b24eaef58fde35d3758c123ad",
}

_BANDWIDTH_NOTE = (
    "Domain-warp composition raises the effective bandwidth above the "
    "accounted component scales; the lambda accounting covers component "
    "scales only and the final appearance is bounded jointly by the "
    "measured lambda floor and the visual gates."
)
_GOLDEN_GAMMA = np.uint64(0x9E3779B97F4A7C15)
_PSD_CURVE_COLORS = {
    "base": (110, 110, 110),
    "candidate-1": (200, 60, 60),
    "candidate-2": (50, 140, 60),
    "candidate-3": (60, 80, 200),
}


def _require_points(points: np.ndarray) -> None:
    """Require finite float64 evaluation points without coercion."""
    if (
        not isinstance(points, np.ndarray)
        or points.dtype != np.float64
        or points.ndim != 2
        or points.shape[1] != 3
        or len(points) == 0
        or not np.isfinite(points).all()
    ):
        raise ValueError("points must be a nonempty finite float64 (N, 3) array")


def _require_vertex_colors(colors: np.ndarray) -> None:
    """Require one uint8 RGB row per vertex without coercion."""
    if (
        not isinstance(colors, np.ndarray)
        or colors.dtype != np.uint8
        or colors.ndim != 2
        or colors.shape[1] != 3
        or len(colors) == 0
    ):
        raise ValueError("vertex colors must be a nonempty uint8 (N, 3) array")


def normalize_canonical_coordinates(vertices: np.ndarray) -> np.ndarray:
    """Map vertices through the frozen R19 bbox-center normalization."""
    if (
        not isinstance(vertices, np.ndarray)
        or vertices.dtype != np.float64
        or vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError("vertices must be a nonempty finite float64 (N, 3) array")
    bounds_minimum = vertices.min(axis=0)
    bounds_maximum = vertices.max(axis=0)
    center = (bounds_minimum + bounds_maximum) / 2.0
    max_extent = float(np.max(bounds_maximum - bounds_minimum))
    if max_extent <= 0.0:
        raise ValueError("canonical bounding box must have positive extent")
    # One shared extent preserves aspect ratios exactly as R19 did; the
    # half-unit shift keeps the frozen R19 sampling frame unchanged.
    return (vertices - center) / max_extent + 0.5


def permutation_table(seed_sequence: np.random.SeedSequence) -> np.ndarray:
    """Build one doubled 256-entry hash permutation from a seed sequence."""
    generator = np.random.Generator(np.random.PCG64(seed_sequence))
    table = generator.permutation(256).astype(np.int64)
    return np.concatenate((table, table))


def _quintic_fade(values: np.ndarray) -> np.ndarray:
    """Apply the standard quintic fade of improved gradient noise."""
    return values * values * values * (values * (values * 6.0 - 15.0) + 10.0)


def _gradient_dot(
    hashes: np.ndarray,
    x_offsets: np.ndarray,
    y_offsets: np.ndarray,
    z_offsets: np.ndarray,
) -> np.ndarray:
    """Dot hashed corner gradients with offsets via the reference bit form."""
    low = hashes & 15
    first = np.where(low < 8, x_offsets, y_offsets)
    second = np.where(
        low < 4,
        y_offsets,
        np.where((low == 12) | (low == 14), x_offsets, z_offsets),
    )
    return (
        np.where(low & 1, -first, first) + np.where(low & 2, -second, second)
    )


def improved_gradient_noise(
    points: np.ndarray,
    table: np.ndarray,
) -> np.ndarray:
    """Evaluate improved gradient noise at float64 lattice coordinates."""
    _require_points(points)
    if (
        not isinstance(table, np.ndarray)
        or table.dtype != np.int64
        or table.shape != (512,)
    ):
        raise ValueError("table must be one doubled 512-entry permutation")
    floors = np.floor(points)
    fractions = points - floors
    cells = floors.astype(np.int64) & 255
    fades = _quintic_fade(fractions)

    corner_dots = {}
    for x_step, y_step, z_step in itertools.product((0, 1), repeat=3):
        hashes = table[
            table[table[cells[:, 0] + x_step] + cells[:, 1] + y_step]
            + cells[:, 2]
            + z_step
        ]
        corner_dots[(x_step, y_step, z_step)] = _gradient_dot(
            hashes,
            fractions[:, 0] - x_step,
            fractions[:, 1] - y_step,
            fractions[:, 2] - z_step,
        )

    def lerp(start: np.ndarray, end: np.ndarray, t: np.ndarray) -> np.ndarray:
        return start + t * (end - start)

    x_low_low = lerp(corner_dots[0, 0, 0], corner_dots[1, 0, 0], fades[:, 0])
    x_high_low = lerp(corner_dots[0, 1, 0], corner_dots[1, 1, 0], fades[:, 0])
    x_low_high = lerp(corner_dots[0, 0, 1], corner_dots[1, 0, 1], fades[:, 0])
    x_high_high = lerp(corner_dots[0, 1, 1], corner_dots[1, 1, 1], fades[:, 0])
    y_low = lerp(x_low_low, x_high_low, fades[:, 1])
    y_high = lerp(x_low_high, x_high_high, fades[:, 1])
    return lerp(y_low, y_high, fades[:, 2])


def _validate_octave_wavelengths(wavelengths: Sequence[float]) -> None:
    """Require a frozen lacunarity-two descending wavelength ladder."""
    if len(wavelengths) == 0:
        raise ValueError("octave wavelengths must be nonempty")
    for previous, current in zip(wavelengths, wavelengths[1:], strict=False):
        if abs(previous / current - LACUNARITY) > 1e-12:
            raise ValueError("octave wavelengths must follow lacunarity two")


def fbm_scalar(
    points: np.ndarray,
    wavelengths: Sequence[float],
    table: np.ndarray,
    gain: float = GAIN,
) -> np.ndarray:
    """Sum gain-weighted improved-noise octaves at frozen wavelengths."""
    _validate_octave_wavelengths(wavelengths)
    total = np.zeros(len(points), dtype=np.float64)
    amplitude = 1.0
    for wavelength in wavelengths:
        total += amplitude * improved_gradient_noise(points / wavelength, table)
        amplitude *= gain
    return total


def fbm_vector(
    points: np.ndarray,
    wavelengths: Sequence[float],
    seed_sequence: np.random.SeedSequence,
    gain: float = GAIN,
) -> np.ndarray:
    """Stack three decorrelated scalar fBm components from spawned seeds."""
    children = seed_sequence.spawn(3)
    components = [
        fbm_scalar(points, wavelengths, permutation_table(child), gain)
        for child in children
    ]
    return np.stack(components, axis=1)


def _splitmix64(values: np.ndarray) -> np.ndarray:
    """Mix uint64 lattice words with the splitmix64 finalizer."""
    with np.errstate(over="ignore"):
        mixed = (values + _GOLDEN_GAMMA).astype(np.uint64)
        mixed = (mixed ^ (mixed >> np.uint64(30))) * np.uint64(
            0xBF58476D1CE4E5B9
        )
        mixed = (mixed ^ (mixed >> np.uint64(27))) * np.uint64(
            0x94D049BB133111EB
        )
        return mixed ^ (mixed >> np.uint64(31))


def _cell_uniform(
    cells: np.ndarray,
    seed: np.uint64,
    axis: int,
) -> np.ndarray:
    """Hash integer cells into one deterministic uniform per cell and axis."""
    state = np.full(len(cells), seed, dtype=np.uint64)
    for column in range(3):
        state = _splitmix64(state ^ cells[:, column].astype(np.uint64))
    state = _splitmix64(state ^ np.uint64(axis + 1))
    return state.astype(np.float64) / float(2**64)


def worley_f1(
    points: np.ndarray,
    cell_size: float,
    seed_sequence: np.random.SeedSequence,
) -> np.ndarray:
    """Return nearest-feature distances for hash-jittered grid points."""
    _require_points(points)
    if not cell_size > 0.0:
        raise ValueError("cell size must be positive")
    seed = np.uint64(seed_sequence.generate_state(1, np.uint64)[0])
    cells = np.floor(points / cell_size).astype(np.int64)
    offsets = np.array(
        list(itertools.product((-1, 0, 1), repeat=3)),
        dtype=np.int64,
    )
    neighbors = (cells[:, None, :] + offsets[None, :, :]).reshape(-1, 3)
    jitter = np.stack(
        [_cell_uniform(neighbors, seed, axis) for axis in range(3)],
        axis=1,
    )
    features = (neighbors.astype(np.float64) + jitter) * cell_size
    distances = np.linalg.norm(
        points[:, None, :] - features.reshape(len(points), 27, 3),
        axis=2,
    )
    return distances.min(axis=1)


def _worley_signed(
    points: np.ndarray,
    cell_size: float,
    seed_sequence: np.random.SeedSequence,
) -> np.ndarray:
    """Map Worley F1 distances into the signed frozen W construction."""
    f1 = worley_f1(points, cell_size, seed_sequence)
    return 2.0 * (1.0 - np.minimum(f1 / cell_size, 1.0)) - 1.0


def variant_scalar_field(name: str, points: np.ndarray) -> np.ndarray:
    """Evaluate one frozen candidate field, recentred and peak-normalized."""
    _require_points(points)
    if name == "candidate-1":
        table = permutation_table(
            np.random.SeedSequence(CANDIDATE_SEEDS[name])
        )
        raw = fbm_scalar(points, CANDIDATE_1_OCTAVE_WAVELENGTHS, table)
    elif name == "candidate-2":
        table = permutation_table(
            np.random.SeedSequence(CANDIDATE_SEEDS[name])
        )
        warp = fbm_vector(
            points,
            CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS,
            np.random.SeedSequence(CANDIDATE_2_WARP_SEED),
        )
        warped = points + CANDIDATE_2_WARP_STRENGTH * warp
        raw = fbm_scalar(warped, CANDIDATE_2_OCTAVE_WAVELENGTHS, table)
    elif name == "candidate-3":
        fbm_child, worley_child = np.random.SeedSequence(
            CANDIDATE_SEEDS[name]
        ).spawn(2)
        raw = CANDIDATE_3_FBM_WEIGHT * fbm_scalar(
            points,
            CANDIDATE_3_OCTAVE_WAVELENGTHS,
            permutation_table(fbm_child),
        ) + CANDIDATE_3_WORLEY_WEIGHT * _worley_signed(
            points,
            WORLEY_CELL_SIZE,
            worley_child,
        )
    else:
        raise ValueError(
            "the base variant has no scalar field (amplitude is zero)"
        )
    recentred = raw - raw.mean()
    peak = float(np.abs(recentred).max())
    if not np.isfinite(peak) or peak <= 0.0:
        raise ValueError("variant field peak magnitude must be positive")
    return recentred / peak


def derive_base_rgb(colors: np.ndarray) -> tuple[int, int, int]:
    """Round per-channel means of the frozen source colours half up."""
    _require_vertex_colors(colors)
    means = colors.astype(np.float64).mean(axis=0)
    rounded = np.floor(means + 0.5).astype(np.int64)
    return (int(rounded[0]), int(rounded[1]), int(rounded[2]))


def base_variant_colors(
    base_rgb: Sequence[int],
    vertex_count: int,
) -> np.ndarray:
    """Tile the frozen base colour over every vertex for the control."""
    if vertex_count <= 0:
        raise ValueError("vertex count must be positive")
    return np.tile(np.array(base_rgb, dtype=np.uint8), (vertex_count, 1))


def apply_colour_field(
    base_rgb: Sequence[int],
    field: np.ndarray,
    amplitude: float = AMPLITUDE,
) -> np.ndarray:
    """Map one scalar field through the frozen half-up colour formula."""
    if (
        not isinstance(field, np.ndarray)
        or field.dtype != np.float64
        or field.ndim != 1
        or len(field) == 0
        or not np.isfinite(field).all()
    ):
        raise ValueError("field must be a nonempty finite float64 vector")
    base = np.asarray(base_rgb, dtype=np.float64)
    scaled = base[None, :] * (1.0 + amplitude * field[:, None])
    return np.clip(np.floor(scaled + 0.5), 0.0, 255.0).astype(np.uint8)


def validate_base_exactness(
    colors: np.ndarray,
    base_rgb: Sequence[int],
) -> None:
    """Require every control vertex to carry exactly the base colour."""
    _require_vertex_colors(colors)
    expected = np.array(base_rgb, dtype=np.uint8)
    if not np.array_equal(colors, np.tile(expected, (len(colors), 1))):
        raise ValueError("R25 base variant colours differ from base_rgb")


def validate_mean_preservation(
    colors: np.ndarray,
    base_rgb: Sequence[int],
    tolerance: float = MEAN_DRIFT_TOLERANCE,
) -> tuple[float, float, float]:
    """Require per-channel colour means to stay within the frozen drift."""
    _require_vertex_colors(colors)
    means = colors.astype(np.float64).mean(axis=0)
    drifts = tuple(
        float(abs(mean - float(base)))
        for mean, base in zip(means, base_rgb, strict=True)
    )
    if any(drift > tolerance for drift in drifts):
        raise ValueError(
            "R25 candidate channel mean drift exceeds the frozen tolerance"
        )
    return drifts


def validate_amplitude_bound(
    colors: np.ndarray,
    base_rgb: Sequence[int],
    amplitude: float = AMPLITUDE,
) -> tuple[int, int, int]:
    """Require per-vertex deviations within ceil(amplitude times base)."""
    _require_vertex_colors(colors)
    amplitude_fraction = Fraction(str(amplitude))
    bounds = tuple(
        int(math.ceil(Fraction(int(base)) * amplitude_fraction))
        for base in base_rgb
    )
    differences = np.abs(
        colors.astype(np.int64)
        - np.asarray(base_rgb, dtype=np.int64)[None, :]
    )
    if np.any(differences > np.asarray(bounds, dtype=np.int64)[None, :]):
        raise ValueError(
            "R25 vertex colour exceeds the frozen amplitude bound"
        )
    return bounds


def measure_lambda_floor(vertices: np.ndarray, faces: np.ndarray) -> float:
    """Measure twice the median normalized canonical edge length."""
    _require_geometry(vertices, faces)
    edges = np.sort(
        np.concatenate(
            (faces[:, (0, 1)], faces[:, (1, 2)], faces[:, (2, 0)]),
            axis=0,
        ),
        axis=1,
    )
    unique_edges = np.unique(edges, axis=0)
    bounds_minimum = vertices.min(axis=0)
    bounds_maximum = vertices.max(axis=0)
    max_extent = float(np.max(bounds_maximum - bounds_minimum))
    if max_extent <= 0.0:
        raise ValueError("canonical bounding box must have positive extent")
    lengths = (
        np.linalg.norm(
            vertices[unique_edges[:, 0]] - vertices[unique_edges[:, 1]],
            axis=1,
        )
        / max_extent
    )
    return float(2.0 * np.median(lengths))


def checked_scale_values() -> tuple[float, ...]:
    """Enumerate the frozen checked-scale set from design section 4.2."""
    return (
        CANDIDATE_1_OCTAVE_WAVELENGTHS
        + CANDIDATE_2_OCTAVE_WAVELENGTHS
        + CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS
        + CANDIDATE_3_OCTAVE_WAVELENGTHS
        + (WORLEY_CELL_SIZE,)
    )


def checked_scale_set() -> dict[str, object]:
    """Return the structured checked-scale record for the receipt."""
    return {
        "candidate-1": list(CANDIDATE_1_OCTAVE_WAVELENGTHS),
        "candidate-2": {
            "fbm": list(CANDIDATE_2_OCTAVE_WAVELENGTHS),
            "warp": list(CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS),
        },
        "candidate-3": {
            "fbm": list(CANDIDATE_3_OCTAVE_WAVELENGTHS),
            "worley_cell": WORLEY_CELL_SIZE,
        },
    }


def validate_scale_floor(lambda_floor: float) -> None:
    """Require every frozen checked scale to reach the lambda floor."""
    if (
        not isinstance(lambda_floor, float)
        or not np.isfinite(lambda_floor)
        or lambda_floor <= 0.0
    ):
        raise ValueError("lambda floor must be a positive finite float")
    violations = [
        scale for scale in checked_scale_values() if scale < lambda_floor
    ]
    if violations:
        raise ValueError(
            f"R25 checked scale {min(violations)} is below the measured "
            f"lambda floor {lambda_floor}"
        )


def masked_mae(
    first_rgb: np.ndarray,
    second_rgb: np.ndarray,
    mask: np.ndarray,
) -> float:
    """Average channel-mean absolute differences over foreground pixels."""
    if (
        not isinstance(first_rgb, np.ndarray)
        or not isinstance(second_rgb, np.ndarray)
        or first_rgb.shape != second_rgb.shape
        or first_rgb.ndim != 3
        or first_rgb.shape[2] != 3
    ):
        raise ValueError("images must be two aligned (H, W, 3) arrays")
    if (
        not isinstance(mask, np.ndarray)
        or mask.dtype != np.bool_
        or mask.shape != first_rgb.shape[:2]
        or not mask.any()
    ):
        raise ValueError("mask must be an aligned nonempty boolean array")
    differences = np.abs(
        first_rgb.astype(np.float64) - second_rgb.astype(np.float64)
    )
    return float(differences.mean(axis=2)[mask].mean())


def mae_gate_passed(values: Sequence[float]) -> bool:
    """Apply the strictly-greater frozen M12 threshold to all values."""
    return all(value > MAE_THRESHOLD for value in values)


def clean_image_names() -> tuple[str, ...]:
    """Enumerate the sixteen frozen clean preview file names in order."""
    return tuple(
        f"{variant}__{mesh}__{view}.png"
        for variant in VARIANT_NAMES
        for mesh in MESH_NAMES
        for view in PREVIEW_CAMERA_NAMES
    )


def _content_paths() -> set[str]:
    """Return the exact pre-manifest R25 preview bundle file set."""
    paths = {
        "receipt.json",
        "diagnostics/comparison-sheet.png",
        "diagnostics/radial-psd.png",
        "diagnostics/m12-mae.json",
        "fields/base__vertex-colors.npy",
    }
    for name in CANDIDATE_NAMES:
        paths.add(f"fields/{name}__field.npy")
        paths.add(f"fields/{name}__vertex-colors.npy")
    for image_name in clean_image_names():
        paths.add(f"clean/{image_name}")
    for mesh_name in MESH_NAMES:
        for view_name in PREVIEW_CAMERA_NAMES:
            paths.add(f"masks/{mesh_name}/{view_name}.png")
            paths.add(f"controls/{mesh_name}/{view_name}.png")
    return paths


def _write_mask_exclusive(path: Path, mask: np.ndarray) -> None:
    """Write one new binary L-mode mask PNG exactly as R16A/R19 did."""
    if (
        not isinstance(mask, np.ndarray)
        or mask.dtype != np.bool_
        or mask.ndim != 2
    ):
        raise ValueError("mask must be a two-dimensional boolean array")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("R25 output mask already exists")
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(path)


def dilate_mask_once(mask: np.ndarray) -> np.ndarray:
    """Grow one boolean mask by one pixel over the eight-neighbourhood."""
    if (
        not isinstance(mask, np.ndarray)
        or mask.dtype != np.bool_
        or mask.ndim != 2
    ):
        raise ValueError("mask must be a two-dimensional boolean array")
    grown = mask.copy()
    grown[1:, :] |= mask[:-1, :]
    grown[:-1, :] |= mask[1:, :]
    grown[:, 1:] |= mask[:, :-1]
    grown[:, :-1] |= mask[:, 1:]
    grown[1:, 1:] |= mask[:-1, :-1]
    grown[:-1, :-1] |= mask[1:, 1:]
    grown[1:, :-1] |= mask[:-1, 1:]
    grown[:-1, 1:] |= mask[1:, :-1]
    return grown


def _validate_rendered_view(view: object) -> None:
    """Require one frozen-resolution RGB view with a boolean depth mask."""
    rgb = getattr(view, "rgb", None)
    object_mask = getattr(view, "object_mask", None)
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.shape != (RESOLUTION[1], RESOLUTION[0], 3)
        or not isinstance(object_mask, np.ndarray)
        or object_mask.dtype != np.bool_
        or object_mask.shape != (RESOLUTION[1], RESOLUTION[0])
    ):
        raise ValueError("rendered view differs from the frozen contract")


def _masked_grayscale(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Flatten background to the foreground mean and window the result."""
    gray = rgb.astype(np.float64).mean(axis=2)
    foreground_mean = float(gray[mask].mean())
    flattened = np.full(gray.shape, foreground_mean, dtype=np.float64)
    flattened[mask] = gray[mask]
    flattened -= flattened.mean()
    window = np.hanning(gray.shape[0])
    return flattened * window[:, None] * window[None, :]


def _radial_power_spectrum(image: np.ndarray) -> np.ndarray:
    """Average two-dimensional FFT power into integer radial bins."""
    power = np.abs(np.fft.fft2(image)) ** 2
    frequencies_y = np.fft.fftfreq(image.shape[0]) * image.shape[0]
    frequencies_x = np.fft.fftfreq(image.shape[1]) * image.shape[1]
    radius = np.sqrt(
        frequencies_y[:, None] ** 2 + frequencies_x[None, :] ** 2
    )
    bins = np.rint(radius).astype(np.int64)
    highest_bin = image.shape[0] // 2
    sums = np.bincount(
        bins.ravel(),
        weights=power.ravel(),
        minlength=highest_bin + 1,
    )
    counts = np.bincount(bins.ravel(), minlength=highest_bin + 1)
    return (
        sums[1 : highest_bin + 1]
        / np.maximum(counts[1 : highest_bin + 1], 1)
    )


def _draw_radial_psd_chart(
    curves: Mapping[str, np.ndarray],
) -> np.ndarray:
    """Draw the diagnostic-only radial power spectrum aid with Pillow."""
    width, height = 768, 512
    margin_left, margin_right = 64, 24
    margin_top, margin_bottom = 40, 48
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    log_curves = {
        name: np.log10(curve + 1e-12) for name, curve in curves.items()
    }
    low = min(float(curve.min()) for curve in log_curves.values())
    high = max(float(curve.max()) for curve in log_curves.values())
    if high <= low:
        high = low + 1.0
    frequency_span = math.log10(len(next(iter(log_curves.values()))))
    for name in VARIANT_NAMES:
        curve = log_curves[name]
        points = []
        for index, value in enumerate(curve):
            x_fraction = math.log10(index + 1) / frequency_span
            y_fraction = (float(value) - low) / (high - low)
            points.append(
                (
                    margin_left + x_fraction * plot_width,
                    margin_top + (1.0 - y_fraction) * plot_height,
                )
            )
        draw.line(points, fill=_PSD_CURVE_COLORS[name], width=2)

    axis_color = (0, 0, 0)
    draw.line(
        (
            (margin_left, margin_top),
            (margin_left, height - margin_bottom),
            (width - margin_right, height - margin_bottom),
        ),
        fill=axis_color,
        width=1,
    )
    draw.text(
        (margin_left, 12),
        "R25 radial power spectrum aid "
        "(canonical z-plus, masked grayscale, Hann window)",
        fill=axis_color,
    )
    draw.text(
        (margin_left, height - 28),
        "log10 radial frequency (cycles per image, 1..256)",
        fill=axis_color,
    )
    draw.text((8, margin_top), "log10", fill=axis_color)
    draw.text((8, margin_top + 14), "power", fill=axis_color)
    for index, name in enumerate(VARIANT_NAMES):
        y_position = margin_top + 12 + 16 * index
        draw.rectangle(
            (width - 190, y_position, width - 176, y_position + 10),
            fill=_PSD_CURVE_COLORS[name],
        )
        draw.text((width - 170, y_position - 2), name, fill=axis_color)
    return np.asarray(canvas, dtype=np.uint8)


def _frozen_parameter_payload() -> dict[str, object]:
    """Serialize every frozen generator parameter for the receipt."""
    return {
        "amplitude": AMPLITUDE,
        "gain": GAIN,
        "lacunarity": LACUNARITY,
        "mean_drift_tolerance_grey_levels": MEAN_DRIFT_TOLERANCE,
        "mae_threshold_grey_levels": MAE_THRESHOLD,
        "variants": {
            "base": {"amplitude": 0.0},
            "candidate-1": {
                "construction": "fbm",
                "octave_wavelengths": list(CANDIDATE_1_OCTAVE_WAVELENGTHS),
                "seed": CANDIDATE_SEEDS["candidate-1"],
            },
            "candidate-2": {
                "construction": "fbm_with_single_step_domain_warp",
                "octave_wavelengths": list(CANDIDATE_2_OCTAVE_WAVELENGTHS),
                "warp_octave_wavelengths": list(
                    CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS
                ),
                "warp_strength": CANDIDATE_2_WARP_STRENGTH,
                "seed": CANDIDATE_SEEDS["candidate-2"],
                "warp_seed": CANDIDATE_2_WARP_SEED,
            },
            "candidate-3": {
                "construction": "fbm_worley_f1_mix",
                "octave_wavelengths": list(CANDIDATE_3_OCTAVE_WAVELENGTHS),
                "fbm_weight": CANDIDATE_3_FBM_WEIGHT,
                "worley_weight": CANDIDATE_3_WORLEY_WEIGHT,
                "worley_cell_size": WORLEY_CELL_SIZE,
                "seed": CANDIDATE_SEEDS["candidate-3"],
            },
        },
    }


def write_r25_preview_bundle(
    output_root: Path,
    *,
    r19_screen_root: Path,
    canonical_vertices: np.ndarray,
    canonical_faces: np.ndarray,
    deformed_vertices: np.ndarray,
    deformed_faces: np.ndarray,
    canonical_file_sha256: str,
    deformed_file_sha256: str,
    base_source_colors: np.ndarray,
    base_source_sha256: str,
    render_vertex_colors: VertexColorRenderer,
    camera_registry_receipts: Sequence[Mapping[str, object]],
    open3d_version: str,
    rss_check: Callable[[], None],
    peak_process_tree_rss_bytes: int | Callable[[], int],
    expected_shared_edge_count: int | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, object]:
    """Write one no-clobber sixteen-image R25 preview bundle."""
    root = Path(output_root)
    if root.exists():
        raise FileExistsError("R25 output root already exists")
    rss_check()
    _require_digest(canonical_file_sha256, "canonical file hash")
    _require_digest(deformed_file_sha256, "deformed file hash")
    _require_digest(base_source_sha256, "base source hash")
    _require_matching_topology(
        canonical_vertices,
        canonical_faces,
        deformed_vertices,
        deformed_faces,
    )
    _require_vertex_colors(base_source_colors)
    base_rgb = derive_base_rgb(base_source_colors)
    if base_rgb != EXPECTED_BASE_RGB:
        raise ValueError(
            "R25 base colour derivation differs from the review-pinned value"
        )

    total_start = time.perf_counter()
    normalized = normalize_canonical_coordinates(canonical_vertices)
    lambda_floor = measure_lambda_floor(canonical_vertices, canonical_faces)
    validate_scale_floor(lambda_floor)

    fields: dict[str, np.ndarray] = {}
    colors: dict[str, np.ndarray] = {
        "base": base_variant_colors(base_rgb, len(canonical_vertices))
    }
    validate_base_exactness(colors["base"], base_rgb)
    mean_drifts: dict[str, tuple[float, float, float]] = {}
    for name in CANDIDATE_NAMES:
        field = variant_scalar_field(name, normalized)
        replay = variant_scalar_field(name, normalized)
        if field.tobytes() != replay.tobytes():
            raise ValueError("R25 seeded field replay differs")
        variant_colors = apply_colour_field(base_rgb, field)
        mean_drifts[name] = validate_mean_preservation(variant_colors, base_rgb)
        validate_amplitude_bound(variant_colors, base_rgb)
        fields[name] = field
        colors[name] = variant_colors
    edge_diagnostics: dict[str, dict[str, int | bool]] = {}
    for name in VARIANT_NAMES:
        diagnostics = shared_edge_color_diagnostics(
            canonical_faces,
            colors[name],
        )
        if diagnostics["shared_endpoint_mismatch_count"] != 0:
            raise ValueError("R25 shared-edge endpoint colours differ")
        if expected_shared_edge_count is not None and (
            diagnostics["edge_count"] != expected_shared_edge_count
            or diagnostics["shared_edge_count"] != expected_shared_edge_count
        ):
            raise ValueError("R25 shared-edge count differs from the contract")
        edge_diagnostics[name] = diagnostics
    field_seconds = time.perf_counter() - total_start
    _report(progress, "fields_computed")

    root.mkdir(parents=True)
    (root / "fields").mkdir()
    _write_npy_exclusive(
        root / "fields/base__vertex-colors.npy",
        colors["base"],
    )
    for name in CANDIDATE_NAMES:
        _write_npy_exclusive(root / f"fields/{name}__field.npy", fields[name])
        _write_npy_exclusive(
            root / f"fields/{name}__vertex-colors.npy",
            colors[name],
        )

    r19_root = Path(r19_screen_root)
    mask_bytes: dict[tuple[str, str], bytes] = {}
    masks: dict[tuple[str, str], np.ndarray] = {}
    true_backgrounds: dict[tuple[str, str], np.ndarray] = {}
    background_counts: dict[str, dict[str, int]] = {}
    control_arrays: dict[tuple[str, str], np.ndarray] = {}
    control_hashes: dict[str, str] = {}
    mask_hashes: dict[str, str] = {}
    for mesh_name in MESH_NAMES:
        for view_name in PREVIEW_CAMERA_NAMES:
            mask_path = r19_root / f"masks/{mesh_name}/{view_name}.png"
            frozen_bytes = mask_path.read_bytes()
            mask_bytes[(mesh_name, view_name)] = frozen_bytes
            mask_hashes[f"{mesh_name}/{view_name}"] = hashlib.sha256(
                frozen_bytes
            ).hexdigest()
            mask_values = _load_png(mask_path, "L", RESOLUTION)
            if not set(np.unique(mask_values)).issubset({0, 255}):
                raise ValueError("R25 frozen R19 mask is not binary")
            frozen_mask = mask_values == 255
            masks[(mesh_name, view_name)] = frozen_mask
            dilated = dilate_mask_once(frozen_mask)
            true_backgrounds[(mesh_name, view_name)] = ~dilated
            background_counts[f"{mesh_name}/{view_name}"] = {
                "true_background_pixels": int((~dilated).sum()),
                "silhouette_ring_pixels": int(
                    (dilated & ~frozen_mask).sum()
                ),
            }
            control_source = r19_root / f"renders/{mesh_name}/{view_name}.png"
            control_target = root / f"controls/{mesh_name}/{view_name}.png"
            _copy_exclusive(control_source, control_target)
            control_hashes[f"{mesh_name}/{view_name}"] = _file_sha256(
                control_target
            )
            control_arrays[(mesh_name, view_name)] = _load_png(
                control_target,
                "RGB",
                RESOLUTION,
            )
    _report(progress, "controls_copied")

    vertices_by_mesh = {
        "canonical": canonical_vertices,
        "deformed-s0521-v0000": deformed_vertices,
    }
    renders: dict[tuple[str, str, str], np.ndarray] = {}
    render_calls: list[dict[str, object]] = []
    render_start = time.perf_counter()
    for variant_name in VARIANT_NAMES:
        for mesh_name in MESH_NAMES:
            rss_check()
            call_start = time.perf_counter()
            views = render_vertex_colors(
                mesh_name,
                vertices_by_mesh[mesh_name],
                canonical_faces,
                colors[variant_name],
            )
            if tuple(views) != PREVIEW_CAMERA_NAMES:
                raise ValueError("R25 renderer camera set differs")
            for view_name in PREVIEW_CAMERA_NAMES:
                view = views[view_name]
                _validate_rendered_view(view)
                frozen_mask = masks[(mesh_name, view_name)]
                if not np.array_equal(view.object_mask, frozen_mask):
                    raise ValueError(
                        "R25 rendered depth mask differs from the frozen "
                        "R19 mask"
                    )
                # Design v4 M5(b)/(c): the one-pixel silhouette ring is
                # renderer-inherent and exempt; the true background must
                # equal the fixed clear colour and the frozen R19 pixels.
                true_background = true_backgrounds[(mesh_name, view_name)]
                region = view.rgb[true_background]
                if np.any(
                    region != np.array(BACKGROUND_CLEAR_RGB, dtype=np.uint8)
                ):
                    raise ValueError(
                        "R25 true background differs from the fixed clear "
                        "colour"
                    )
                if not np.array_equal(
                    region,
                    control_arrays[(mesh_name, view_name)][true_background],
                ):
                    raise ValueError(
                        "R25 true background differs from the frozen R19 "
                        "render"
                    )
                if variant_name == "base":
                    mask_target = root / f"masks/{mesh_name}/{view_name}.png"
                    _write_mask_exclusive(mask_target, view.object_mask)
                    if (
                        mask_target.read_bytes()
                        != mask_bytes[(mesh_name, view_name)]
                    ):
                        raise ValueError(
                            "R25 written mask bytes differ from the frozen "
                            "R19 mask"
                        )
                _write_rgb_exclusive(
                    root / f"clean/{variant_name}__{mesh_name}__"
                    f"{view_name}.png",
                    view.rgb,
                )
                renders[(variant_name, mesh_name, view_name)] = view.rgb
            render_calls.append(
                {
                    "variant": variant_name,
                    "mesh": mesh_name,
                    "seconds": time.perf_counter() - call_start,
                }
            )
            _report(progress, f"render:{variant_name}/{mesh_name}")
    render_seconds = time.perf_counter() - render_start

    expected_names = clean_image_names()
    observed_names = sorted(
        path.name for path in (root / "clean").glob("*.png")
    )
    if observed_names != sorted(expected_names):
        raise ValueError("R25 clean image inventory differs")
    for image_name in expected_names:
        _load_png(root / f"clean/{image_name}", "RGB", RESOLUTION)

    rss_check()
    diagnostics_start = time.perf_counter()
    pair_payload: dict[str, dict[str, float]] = {}
    all_values: list[float] = []
    for first_name, second_name in MAE_PAIRS:
        values: dict[str, float] = {}
        for mesh_name in MESH_NAMES:
            for view_name in PREVIEW_CAMERA_NAMES:
                value = masked_mae(
                    renders[(first_name, mesh_name, view_name)],
                    renders[(second_name, mesh_name, view_name)],
                    masks[(mesh_name, view_name)],
                )
                values[f"{mesh_name}__{view_name}"] = value
        values["minimum"] = min(values.values())
        pair_payload[f"{first_name}_vs_{second_name}"] = values
        all_values.extend(
            value for key, value in values.items() if key != "minimum"
        )
    m12_payload = {
        "schema": "c1-r25-m12-mae-v1",
        "definition": (
            "channel_mean_absolute_difference_averaged_over_frozen_mask_"
            "foreground"
        ),
        "unit": "8bit_grey_levels",
        "threshold": MAE_THRESHOLD,
        "comparison": "strictly_greater",
        "pairs": pair_payload,
        "minimum_value": min(all_values),
        "all_values_above_threshold": mae_gate_passed(all_values),
    }
    _write_json_exclusive(root / "diagnostics/m12-mae.json", m12_payload)
    if not m12_payload["all_values_above_threshold"]:
        raise ValueError(
            "R25 M12 distinguishability pre-gate failed; the twenty-four "
            "values are preserved in diagnostics"
        )

    sheet_rows = []
    for mesh_name in MESH_NAMES:
        for view_name in PREVIEW_CAMERA_NAMES:
            cells = [control_arrays[(mesh_name, view_name)]]
            cells.extend(
                renders[(variant_name, mesh_name, view_name)]
                for variant_name in VARIANT_NAMES
            )
            sheet_rows.append(np.concatenate(cells, axis=1))
    _write_rgb_exclusive(
        root / "diagnostics/comparison-sheet.png",
        np.concatenate(sheet_rows, axis=0),
    )
    psd_curves = {
        variant_name: _radial_power_spectrum(
            _masked_grayscale(
                renders[(variant_name, "canonical", "z-plus")],
                masks[("canonical", "z-plus")],
            )
        )
        for variant_name in VARIANT_NAMES
    }
    _write_rgb_exclusive(
        root / "diagnostics/radial-psd.png",
        _draw_radial_psd_chart(psd_curves),
    )
    diagnostics_seconds = time.perf_counter() - diagnostics_start
    _report(progress, "diagnostics_written")

    rss_check()
    peak = (
        peak_process_tree_rss_bytes()
        if callable(peak_process_tree_rss_bytes)
        else peak_process_tree_rss_bytes
    )
    if (
        not isinstance(peak, int)
        or isinstance(peak, bool)
        or not 0 <= peak < RSS_LIMIT_BYTES
    ):
        raise MemoryError("R25 RSS peak is outside the required ceiling")
    receipt = {
        "schema": R25_SCHEMA,
        "method": METHOD_NAME,
        "mapping_space": "canonical",
        "deformed_color_policy": "reuse_exact_canonical_bytes",
        "colour_rounding": "floor_plus_one_half_then_clip",
        "normalization": "bbox_center_single_max_extent_plus_half",
        "base_rgb": list(base_rgb),
        "base_rgb_source": {
            "derivation": (
                "per_channel_half_up_rounded_mean_of_r19_vertex_colors"
            ),
            "vertex_colors_npy_sha256": base_source_sha256,
            "channel_means": [
                float(value)
                for value in base_source_colors.astype(np.float64).mean(
                    axis=0
                )
            ],
        },
        "frozen_parameters": _frozen_parameter_payload(),
        "seed_derivation": {
            "scalar_fbm": "numpy_seed_sequence_of_variant_seed",
            "candidate-2_warp_components": (
                "numpy_seed_sequence_of_warp_seed_spawn_3"
            ),
            "candidate-3_primitives": (
                "numpy_seed_sequence_of_seed_spawn_2_fbm_then_worley"
            ),
        },
        "lambda_floor_measured": lambda_floor,
        "lambda_floor_rule": (
            "two_times_median_normalized_canonical_edge_length"
        ),
        "checked_scale_set": checked_scale_set(),
        "bandwidth_note": _BANDWIDTH_NOTE,
        "m5_background": {
            "clear_colour_rgb": list(BACKGROUND_CLEAR_RGB),
            "dilation": "one_pixel_eight_neighbourhood",
            "silhouette_ring_exempt": True,
            "region_pixel_counts": background_counts,
        },
        "input_anchors": {
            "canonical_file_sha256": canonical_file_sha256,
            "deformed_file_sha256": deformed_file_sha256,
            "vertex_count": len(canonical_vertices),
            "face_count": len(canonical_faces),
            "r19_mask_sha256": mask_hashes,
            "r19_control_render_sha256": control_hashes,
            "camera_registry_sha256": hashlib.sha256(
                json.dumps(
                    list(camera_registry_receipts),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "preview_camera_names": list(PREVIEW_CAMERA_NAMES),
        },
        "shared_edge_diagnostics": edge_diagnostics,
        "mean_preservation_max_abs_drift": {
            name: list(drifts) for name, drifts in mean_drifts.items()
        },
        "renderer": {
            "open3d_version": open3d_version,
            "resolution": list(RESOLUTION),
            "unlit": True,
            "worker_count": 1,
            "serial": True,
        },
        "rss": {
            "peak_process_tree_rss_bytes": peak,
            "rss_limit_bytes": RSS_LIMIT_BYTES,
            "sample_interval_seconds": RSS_SAMPLE_INTERVAL_SECONDS,
        },
        "timings": {
            "field_generation_seconds": field_seconds,
            "render_seconds_total": render_seconds,
            "render_calls": render_calls,
            "diagnostics_seconds": diagnostics_seconds,
            "total_seconds": time.perf_counter() - total_start,
        },
    }
    _write_json_exclusive(root / "receipt.json", receipt)

    expected_paths = _content_paths()
    if _recursive_file_paths(root) != expected_paths:
        raise ValueError("R25 bundle content tree differs before closure")
    manifest = {
        relative_path: _file_sha256(root / relative_path)
        for relative_path in sorted(expected_paths)
    }
    _write_json_exclusive(root / "manifest.json", manifest)
    _report(progress, "bundle_closed")
    return {
        "receipt": receipt,
        "manifest": manifest,
        "m12": m12_payload,
        "base_rgb": base_rgb,
        "lambda_floor": lambda_floor,
        "edge_diagnostics": edge_diagnostics,
        "mean_drifts": mean_drifts,
        "clean_names": list(expected_names),
    }
