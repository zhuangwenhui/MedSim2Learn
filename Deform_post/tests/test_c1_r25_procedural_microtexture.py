"""Red-first contract tests for the C1-R25 sixteen-image preview."""

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dpost.c1_r16_uv_render import RenderedView
from dpost.c1_r19_triplanar_continuity import shared_edge_color_diagnostics


_BASE_RGB = (140, 99, 117)
_MESH_NAMES = ("canonical", "deformed-s0521-v0000")
_VIEW_NAMES = ("z-plus", "iso-plus")
_VARIANT_NAMES = ("base", "candidate-1", "candidate-2", "candidate-3")
_CANDIDATE_NAMES = ("candidate-1", "candidate-2", "candidate-3")
_FROZEN_CLEAN_NAMES = (
    "base__canonical__z-plus.png",
    "base__canonical__iso-plus.png",
    "base__deformed-s0521-v0000__z-plus.png",
    "base__deformed-s0521-v0000__iso-plus.png",
    "candidate-1__canonical__z-plus.png",
    "candidate-1__canonical__iso-plus.png",
    "candidate-1__deformed-s0521-v0000__z-plus.png",
    "candidate-1__deformed-s0521-v0000__iso-plus.png",
    "candidate-2__canonical__z-plus.png",
    "candidate-2__canonical__iso-plus.png",
    "candidate-2__deformed-s0521-v0000__z-plus.png",
    "candidate-2__deformed-s0521-v0000__iso-plus.png",
    "candidate-3__canonical__z-plus.png",
    "candidate-3__canonical__iso-plus.png",
    "candidate-3__deformed-s0521-v0000__z-plus.png",
    "candidate-3__deformed-s0521-v0000__iso-plus.png",
)
_FROZEN_MASK_SHA256 = {
    "canonical/z-plus":
        "5cdcfe8f818de089018a95fe50730d41923a8ee26755dc827c84429016d5e33d",
    "canonical/iso-plus":
        "8d4f75d71240cbb56ff1e99da76cd9d95ef2288f7fa1f03d581ac5323bdece30",
    "deformed-s0521-v0000/z-plus":
        "7ef2dea7d1725b6fdf537d217c3ae351b4406c593642c3a045e4b4e2dcb76b48",
    "deformed-s0521-v0000/iso-plus":
        "1f87171958c394beb44a2b2add57afeb8b55334b24eaef58fde35d3758c123ad",
}
_FROZEN_VERTEX_COLORS_SHA256 = (
    "af2c92d61b73cf34e3802beef7b85f95cd63b4b47e2d3fb5242dd0d17b20474b"
)


def _module():
    return importlib.import_module("dpost.c1_r25_procedural_microtexture")


def _runner():
    return importlib.import_module("scripts.run_c1_r25_procedural_microtexture")


def _grid_geometry(side: int = 41) -> tuple[np.ndarray, np.ndarray]:
    """Build one dense unit-square grid whose lambda floor is below 0.09."""
    axis = np.linspace(0.0, 1.0, side)
    grid_x, grid_y = np.meshgrid(axis, axis, indexing="xy")
    vertices = np.stack(
        (grid_x.ravel(), grid_y.ravel(), np.zeros(side * side)),
        axis=1,
    )
    faces = []
    for row in range(side - 1):
        for column in range(side - 1):
            first = row * side + column
            faces.append([first, first + 1, first + side])
            faces.append([first + 1, first + side + 1, first + side])
    return vertices, np.array(faces, dtype=np.int64)


def _write_png(path: Path, array: np.ndarray, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, mode=mode).save(path)


def _preview_fixture(tmp_path: Path) -> tuple[Path, np.ndarray]:
    """Write one fake frozen R19 screen root with two preview views."""
    r19_root = tmp_path / "r19-screen-v1"
    mask = np.zeros((512, 512), dtype=np.uint8)
    mask[96:416, 128:448] = 255
    for mesh_index, mesh_name in enumerate(_MESH_NAMES):
        for view_index, view_name in enumerate(_VIEW_NAMES):
            control = np.full((512, 512, 3), 5, dtype=np.uint8)
            control[mask == 255] = (
                60 + 20 * mesh_index,
                90,
                40 + 30 * view_index,
            )
            _write_png(
                r19_root / f"renders/{mesh_name}/{view_name}.png",
                control,
                "RGB",
            )
            _write_png(
                r19_root / f"masks/{mesh_name}/{view_name}.png",
                mask,
                "L",
            )
    return r19_root, mask == 255


def _dilate8(mask: np.ndarray) -> np.ndarray:
    """Grow a mask one pixel over eight neighbours, independently coded."""
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


def _fake_preview_renderer(mask: np.ndarray, mask_shift: int = 0):
    """Cycle vertex colours through rim-painted pixels without Open3D.

    Mirrors the legacy renderer's silhouette behaviour: RGB coverage
    extends one pixel beyond the depth-derived mask (design v4 M5 ring).
    """
    color_bytes: list[tuple[str, bytes]] = []

    def render(
        mesh_name: str,
        vertices: np.ndarray,
        faces: np.ndarray,
        vertex_colors: np.ndarray,
    ) -> dict[str, RenderedView]:
        del vertices, faces
        color_bytes.append((mesh_name, vertex_colors.tobytes()))
        rendered_mask = np.roll(mask, mask_shift, axis=1)
        painted = _dilate8(rendered_mask)
        index_field = (
            np.arange(512 * 512) % len(vertex_colors)
        ).reshape(512, 512)
        views = {}
        for view_name in _VIEW_NAMES:
            rgb = np.full((512, 512, 3), 5, dtype=np.uint8)
            rgb[painted] = vertex_colors[index_field[painted]]
            views[view_name] = RenderedView(rgb, rendered_mask.copy())
        return views

    render.color_bytes = color_bytes
    return render


def _poking_renderer(mask: np.ndarray, position: tuple[int, int], value):
    """Wrap the fake renderer and overwrite one output pixel per view."""
    inner = _fake_preview_renderer(mask)

    def render(*arguments) -> dict[str, RenderedView]:
        views = inner(*arguments)
        poked = {}
        for view_name, view in views.items():
            rgb = view.rgb.copy()
            rgb[position] = value
            poked[view_name] = RenderedView(rgb, view.object_mask)
        return poked

    render.color_bytes = inner.color_bytes
    return render


def _base_source_colors() -> np.ndarray:
    return np.tile(np.array(_BASE_RGB, dtype=np.uint8), (300, 1))


def _write_preview_bundle(module, output_root, r19_root, renderer, **overrides):
    vertices, faces = _grid_geometry()
    deformed = vertices.copy()
    deformed[:, 2] += 0.1 * vertices[:, 0]
    arguments = {
        "r19_screen_root": r19_root,
        "canonical_vertices": vertices,
        "canonical_faces": faces,
        "deformed_vertices": deformed,
        "deformed_faces": faces.copy(),
        "canonical_file_sha256": "a" * 64,
        "deformed_file_sha256": "b" * 64,
        "base_source_colors": _base_source_colors(),
        "base_source_sha256": "c" * 64,
        "render_vertex_colors": renderer,
        "camera_registry_receipts": [{"name": "z-plus"}, {"name": "iso-plus"}],
        "open3d_version": "0.19.0",
        "rss_check": lambda: None,
        "peak_process_tree_rss_bytes": 123_456,
    }
    arguments.update(overrides)
    return module.write_r25_preview_bundle(output_root, **arguments)


def test_frozen_parameters_match_the_approved_design() -> None:
    """Catch any drift from the review-approved frozen R25 numerics."""
    r25 = _module()

    assert r25.R25_SCHEMA == "c1-r25-preview-v1"
    assert r25.METHOD_NAME == (
        "per_vertex_sampled_procedural_volumetric_microtexture_field"
    )
    assert r25.VARIANT_NAMES == _VARIANT_NAMES
    assert r25.MESH_NAMES == _MESH_NAMES
    assert r25.PREVIEW_CAMERA_NAMES == _VIEW_NAMES
    assert r25.AMPLITUDE == 0.2
    assert r25.GAIN == 0.5
    assert r25.LACUNARITY == 2.0
    assert r25.CANDIDATE_SEEDS == {
        "candidate-1": 20260809,
        "candidate-2": 20260810,
        "candidate-3": 20260811,
    }
    assert r25.CANDIDATE_2_WARP_SEED == 20260812
    assert r25.CANDIDATE_1_OCTAVE_WAVELENGTHS == (0.64, 0.32, 0.16)
    assert r25.CANDIDATE_2_OCTAVE_WAVELENGTHS == (0.48, 0.24, 0.12)
    assert r25.CANDIDATE_2_WARP_OCTAVE_WAVELENGTHS == (0.5, 0.25)
    assert r25.CANDIDATE_2_WARP_STRENGTH == 0.08
    assert r25.CANDIDATE_3_OCTAVE_WAVELENGTHS == (0.64, 0.32, 0.16)
    assert r25.CANDIDATE_3_FBM_WEIGHT == 0.65
    assert r25.CANDIDATE_3_WORLEY_WEIGHT == 0.35
    assert r25.WORLEY_CELL_SIZE == 0.09
    assert r25.MEAN_DRIFT_TOLERANCE == 2.0
    assert r25.MAE_THRESHOLD == 4.0
    assert r25.RSS_LIMIT_BYTES == 500_000_000
    assert r25.EXPECTED_BASE_RGB == _BASE_RGB
    assert r25.BACKGROUND_CLEAR_RGB == (5, 5, 5)
    assert r25.MAE_PAIRS == (
        ("base", "candidate-1"),
        ("base", "candidate-2"),
        ("base", "candidate-3"),
        ("candidate-1", "candidate-2"),
        ("candidate-1", "candidate-3"),
        ("candidate-2", "candidate-3"),
    )
    with pytest.raises(ValueError, match="base"):
        r25.variant_scalar_field("base", np.zeros((4, 3), dtype=np.float64))


def test_frozen_r19_anchor_hashes_match_the_approved_design() -> None:
    """Catch mistyped or reordered frozen R19 input anchors."""
    r25 = _module()

    assert r25.FROZEN_R19_MASK_SHA256 == _FROZEN_MASK_SHA256
    assert r25.FROZEN_R19_VERTEX_COLORS_SHA256 == _FROZEN_VERTEX_COLORS_SHA256


def test_m1_clean_image_names_enumerate_the_sixteen_frozen_files() -> None:
    """Catch naming or ordering drift from the design section 5 list."""
    r25 = _module()

    names = r25.clean_image_names()

    assert names == _FROZEN_CLEAN_NAMES
    assert len(set(names)) == 16


def test_normalization_uses_bbox_center_and_single_max_extent() -> None:
    """Catch per-axis stretching or a dropped half-unit lattice offset."""
    r25 = _module()
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    normalized = r25.normalize_canonical_coordinates(vertices)

    np.testing.assert_allclose(
        normalized[1],
        np.array([1.0, 0.25, 0.375]),
        atol=1e-15,
    )
    np.testing.assert_allclose(
        normalized[2],
        np.array([0.0, 0.75, 0.375]),
        atol=1e-15,
    )


def test_improved_noise_is_zero_on_lattice_points_and_bounded() -> None:
    """Catch a broken fade, hash, or gradient-dot implementation."""
    r25 = _module()
    table = r25.permutation_table(np.random.SeedSequence(20260809))
    lattice = np.array(
        [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [5.0, 5.0, 5.0]],
        dtype=np.float64,
    )
    cloud = np.random.Generator(np.random.PCG64(3)).random((1000, 3)) * 8.0

    on_lattice = r25.improved_gradient_noise(lattice, table)
    off_lattice = r25.improved_gradient_noise(cloud, table)

    np.testing.assert_array_equal(on_lattice, np.zeros(3))
    assert np.all(np.abs(off_lattice) <= 1.0)
    assert float(np.abs(off_lattice).max()) > 0.0


def test_m9_candidate_fields_replay_byte_identical_and_differ() -> None:
    """Catch hidden nondeterminism or shared state between variants."""
    r25 = _module()
    points = np.random.Generator(np.random.PCG64(7)).random((500, 3))

    fields = {}
    for name in _CANDIDATE_NAMES:
        first = r25.variant_scalar_field(name, points)
        second = r25.variant_scalar_field(name, points)
        assert first.dtype == np.float64
        assert first.shape == (500,)
        assert first.tobytes() == second.tobytes()
        fields[name] = first
    assert fields["candidate-1"].tobytes() != fields["candidate-2"].tobytes()
    assert fields["candidate-1"].tobytes() != fields["candidate-3"].tobytes()
    assert fields["candidate-2"].tobytes() != fields["candidate-3"].tobytes()


def test_candidate_fields_are_zero_mean_with_unit_peak_magnitude() -> None:
    """Catch missing recentring or a skipped peak normalization step."""
    r25 = _module()
    points = np.random.Generator(np.random.PCG64(11)).random((800, 3))

    for name in _CANDIDATE_NAMES:
        field = r25.variant_scalar_field(name, points)
        assert abs(float(field.mean())) < 1e-12
        assert float(np.abs(field).max()) == 1.0


def test_colour_formula_rounds_half_up_and_clips_to_uint8() -> None:
    """Catch banker's rounding or a missing clip in the colour map."""
    r25 = _module()

    colors = r25.apply_colour_field(
        (250, 5, 128),
        np.array([1.0, -1.0, 0.0], dtype=np.float64),
    )
    half_up = r25.apply_colour_field(
        (10, 10, 10),
        np.array([0.25], dtype=np.float64),
    )

    np.testing.assert_array_equal(
        colors,
        np.array(
            [[255, 6, 154], [200, 4, 102], [250, 5, 128]],
            dtype=np.uint8,
        ),
    )
    np.testing.assert_array_equal(
        half_up,
        np.array([[11, 11, 11]], dtype=np.uint8),
    )
    assert colors.dtype == np.uint8


def test_m6_base_variant_colors_are_exactly_base_rgb() -> None:
    """Catch any nonzero-amplitude leakage into the control variant."""
    r25 = _module()

    colors = r25.base_variant_colors(_BASE_RGB, 7)

    assert colors.shape == (7, 3)
    assert colors.dtype == np.uint8
    np.testing.assert_array_equal(
        colors,
        np.tile(np.array(_BASE_RGB, dtype=np.uint8), (7, 1)),
    )
    r25.validate_base_exactness(colors, _BASE_RGB)
    perturbed = colors.copy()
    perturbed[3, 1] += 1
    with pytest.raises(ValueError, match="base"):
        r25.validate_base_exactness(perturbed, _BASE_RGB)


def test_m7_mean_preservation_gate_measures_and_rejects() -> None:
    """Catch a mean-drift gate that uses the wrong unit or tolerance."""
    r25 = _module()
    points = np.random.Generator(np.random.PCG64(13)).random((600, 3))
    field = r25.variant_scalar_field("candidate-1", points)
    colors = r25.apply_colour_field(_BASE_RGB, field)

    drifts = r25.validate_mean_preservation(colors, _BASE_RGB)

    assert len(drifts) == 3
    assert all(0.0 <= drift <= 2.0 for drift in drifts)
    shifted = np.tile(
        np.array(
            [_BASE_RGB[0] + 3, _BASE_RGB[1], _BASE_RGB[2]],
            dtype=np.uint8,
        ),
        (600, 1),
    )
    with pytest.raises(ValueError, match="mean"):
        r25.validate_mean_preservation(shifted, _BASE_RGB)


def test_m8_amplitude_bound_gate_uses_ceil_of_scaled_base() -> None:
    """Catch a bound computed with floor, round, or the wrong amplitude."""
    r25 = _module()
    points = np.random.Generator(np.random.PCG64(17)).random((600, 3))
    for name in _CANDIDATE_NAMES:
        field = r25.variant_scalar_field(name, points)
        colors = r25.apply_colour_field(_BASE_RGB, field)
        bounds = r25.validate_amplitude_bound(colors, _BASE_RGB)
        assert bounds == (28, 20, 24)

    violating = np.tile(np.array(_BASE_RGB, dtype=np.uint8), (4, 1))
    violating[2, 2] += 25
    with pytest.raises(ValueError, match="amplitude"):
        r25.validate_amplitude_bound(violating, _BASE_RGB)


def test_m10_lambda_floor_is_twice_median_edge_and_gates_scales() -> None:
    """Catch a lambda floor from faces, means, or unnormalized lengths."""
    r25 = _module()
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)

    lambda_floor = r25.measure_lambda_floor(vertices, faces)

    assert lambda_floor == 2.0
    assert set(r25.checked_scale_values()) == {
        0.64, 0.32, 0.16, 0.48, 0.24, 0.12, 0.5, 0.25, 0.09,
    }
    assert min(r25.checked_scale_values()) == 0.09
    r25.validate_scale_floor(0.06)
    r25.validate_scale_floor(0.09)
    with pytest.raises(ValueError, match="lambda"):
        r25.validate_scale_floor(0.0901)


def test_m12_masked_mae_matches_hand_value_and_strict_threshold() -> None:
    """Catch channel-after-pixel averaging or a non-strict threshold."""
    r25 = _module()
    mask = np.array([[True, False], [True, True]])
    first = np.zeros((2, 2, 3), dtype=np.uint8)
    second = np.zeros((2, 2, 3), dtype=np.uint8)
    second[0, 0] = (3, 6, 9)
    second[1, 0] = (0, 0, 3)
    second[1, 1] = (12, 0, 0)
    second[0, 1] = (255, 255, 255)

    value = r25.masked_mae(first, second, mask)

    assert value == pytest.approx((6.0 + 1.0 + 4.0) / 3.0)
    assert r25.mae_gate_passed([4.0001, 5.0]) is True
    assert r25.mae_gate_passed([4.0, 5.0]) is False


def test_m4_per_vertex_colours_keep_shared_edges_identical() -> None:
    """Catch a colour representation that splits shared-edge endpoints."""
    r25 = _module()
    vertices, faces = _grid_geometry(9)
    normalized = r25.normalize_canonical_coordinates(vertices)
    field = r25.variant_scalar_field("candidate-1", normalized)
    colors = r25.apply_colour_field(_BASE_RGB, field)

    diagnostics = shared_edge_color_diagnostics(faces, colors)

    assert diagnostics["shared_endpoint_mismatch_count"] == 0
    assert diagnostics["shared_edge_colors_identical"] is True


def test_m4_real_canonical_mesh_has_6009_clean_shared_edges() -> None:
    """Catch an edge count or continuity break on the frozen geometry."""
    r25 = _module()
    runner = _runner()
    canonical_path = Path(runner.CANONICAL_PATH)
    digest = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    assert digest == runner.CANONICAL_SHA256

    from dpost.c1_r16_uv_render import load_mesh_arrays

    vertices, faces = load_mesh_arrays(canonical_path)
    assert vertices.shape == (2005, 3)
    assert faces.shape == (4006, 3)
    normalized = r25.normalize_canonical_coordinates(vertices)
    field = r25.variant_scalar_field("candidate-1", normalized)
    colors = r25.apply_colour_field(_BASE_RGB, field)

    diagnostics = shared_edge_color_diagnostics(faces, colors)

    assert diagnostics["edge_count"] == 6009
    assert diagnostics["shared_edge_count"] == 6009
    assert diagnostics["shared_endpoint_mismatch_count"] == 0


def test_base_rgb_derivation_matches_review_pinned_value() -> None:
    """Catch a mean, rounding, or source drift in the base colour rule."""
    r25 = _module()
    runner = _runner()

    pure = r25.derive_base_rgb(
        np.array([[1, 2, 3], [2, 3, 4]], dtype=np.uint8)
    )
    assert pure == (2, 3, 4)

    npy_path = Path(runner.R19_SCREEN_ROOT) / "vertex-colors.npy"
    digest = hashlib.sha256(npy_path.read_bytes()).hexdigest()
    assert digest == _FROZEN_VERTEX_COLORS_SHA256
    with npy_path.open("rb") as source:
        colors = np.load(source, allow_pickle=False)

    assert r25.derive_base_rgb(colors) == _BASE_RGB
    assert runner.EXPECTED_BASE_RGB == _BASE_RGB


def test_bundle_writer_writes_exact_tree_receipt_and_manifest(
    tmp_path: Path,
) -> None:
    """Catch missing artifacts, colour divergence, or loose closure."""
    r25 = _module()
    r19_root, mask = _preview_fixture(tmp_path)
    renderer = _fake_preview_renderer(mask)
    output_root = tmp_path / "preview"

    result = _write_preview_bundle(r25, output_root, r19_root, renderer)

    observed = {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*")
        if path.is_file()
    }
    expected = {f"clean/{name}" for name in _FROZEN_CLEAN_NAMES}
    expected |= {"fields/base__vertex-colors.npy"}
    for name in _CANDIDATE_NAMES:
        expected |= {
            f"fields/{name}__field.npy",
            f"fields/{name}__vertex-colors.npy",
        }
    for mesh_name in _MESH_NAMES:
        for view_name in _VIEW_NAMES:
            expected |= {
                f"masks/{mesh_name}/{view_name}.png",
                f"controls/{mesh_name}/{view_name}.png",
            }
    expected |= {
        "diagnostics/comparison-sheet.png",
        "diagnostics/radial-psd.png",
        "diagnostics/m12-mae.json",
        "receipt.json",
        "manifest.json",
    }
    assert observed == expected

    # M3: each variant hands byte-identical colours to both mesh renders.
    assert len(renderer.color_bytes) == 8
    for index in range(0, 8, 2):
        assert renderer.color_bytes[index][0] == "canonical"
        assert renderer.color_bytes[index + 1][0] == "deformed-s0521-v0000"
        assert (
            renderer.color_bytes[index][1] == renderer.color_bytes[index + 1][1]
        )
    assert len({entry[1] for entry in renderer.color_bytes}) == 4

    # Field artifacts replay the frozen derivation exactly.
    vertices, _ = _grid_geometry()
    normalized = r25.normalize_canonical_coordinates(vertices)
    for name in _CANDIDATE_NAMES:
        with (output_root / f"fields/{name}__field.npy").open("rb") as source:
            saved_field = np.load(source, allow_pickle=False)
        expected_field = r25.variant_scalar_field(name, normalized)
        assert saved_field.tobytes() == expected_field.tobytes()
        with (
            output_root / f"fields/{name}__vertex-colors.npy"
        ).open("rb") as source:
            saved_colors = np.load(source, allow_pickle=False)
        np.testing.assert_array_equal(
            saved_colors,
            r25.apply_colour_field(_BASE_RGB, expected_field),
        )
    with (
        output_root / "fields/base__vertex-colors.npy"
    ).open("rb") as source:
        saved_base = np.load(source, allow_pickle=False)
    np.testing.assert_array_equal(
        saved_base,
        r25.base_variant_colors(_BASE_RGB, len(vertices)),
    )

    # M5 stand-in: written masks and controls replay the R19 root bytes.
    for mesh_name in _MESH_NAMES:
        for view_name in _VIEW_NAMES:
            written = output_root / f"masks/{mesh_name}/{view_name}.png"
            frozen = r19_root / f"masks/{mesh_name}/{view_name}.png"
            assert written.read_bytes() == frozen.read_bytes()
            control = output_root / f"controls/{mesh_name}/{view_name}.png"
            source = r19_root / f"renders/{mesh_name}/{view_name}.png"
            assert control.read_bytes() == source.read_bytes()

    # M12 diagnostics carry all twenty-four strictly passing values.
    m12 = json.loads(
        (output_root / "diagnostics/m12-mae.json").read_text(encoding="utf-8")
    )
    assert m12["threshold"] == 4.0
    assert len(m12["pairs"]) == 6
    values = []
    for first, second in (
        ("base", "candidate-1"),
        ("base", "candidate-2"),
        ("base", "candidate-3"),
        ("candidate-1", "candidate-2"),
        ("candidate-1", "candidate-3"),
        ("candidate-2", "candidate-3"),
    ):
        pair = m12["pairs"][f"{first}_vs_{second}"]
        combos = [
            f"{mesh_name}__{view_name}"
            for mesh_name in _MESH_NAMES
            for view_name in _VIEW_NAMES
        ]
        assert set(pair) == set(combos) | {"minimum"}
        pair_values = [pair[combo] for combo in combos]
        assert pair["minimum"] == min(pair_values)
        values.extend(pair_values)
    assert len(values) == 24
    assert all(value > 4.0 for value in values)
    assert m12["all_values_above_threshold"] is True

    # M13: the manifest covers every file except itself and verifies.
    manifest = json.loads(
        (output_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert set(manifest) == expected - {"manifest.json"}
    for relative_path, digest in manifest.items():
        observed_digest = hashlib.sha256(
            (output_root / relative_path).read_bytes()
        ).hexdigest()
        assert observed_digest == digest

    receipt = json.loads(
        (output_root / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["schema"] == "c1-r25-preview-v1"
    assert tuple(receipt["base_rgb"]) == _BASE_RGB
    assert receipt["base_rgb_source"]["vertex_colors_npy_sha256"] == "c" * 64
    assert receipt["lambda_floor_measured"] > 0.0
    assert receipt["checked_scale_set"] == {
        "candidate-1": [0.64, 0.32, 0.16],
        "candidate-2": {"fbm": [0.48, 0.24, 0.12], "warp": [0.5, 0.25]},
        "candidate-3": {"fbm": [0.64, 0.32, 0.16], "worley_cell": 0.09},
    }
    assert receipt["renderer"]["open3d_version"] == "0.19.0"
    assert receipt["renderer"]["worker_count"] == 1
    assert receipt["rss"]["peak_process_tree_rss_bytes"] == 123_456
    assert receipt["rss"]["rss_limit_bytes"] == 500_000_000
    assert receipt["m5_background"]["clear_colour_rgb"] == [5, 5, 5]
    assert (
        receipt["m5_background"]["dilation"]
        == "one_pixel_eight_neighbourhood"
    )
    assert receipt["m5_background"]["silhouette_ring_exempt"] is True
    region_counts = receipt["m5_background"]["region_pixel_counts"]
    assert set(region_counts) == {
        f"{mesh_name}/{view_name}"
        for mesh_name in _MESH_NAMES
        for view_name in _VIEW_NAMES
    }
    # The fixture mask is a filled 320 x 320 block: its one-pixel ring
    # holds 322*322 - 320*320 pixels and the true background the rest.
    for entry in region_counts.values():
        assert entry["silhouette_ring_pixels"] == 322 * 322 - 320 * 320
        assert entry["true_background_pixels"] == 512 * 512 - 322 * 322
    variants = receipt["frozen_parameters"]["variants"]
    assert variants["candidate-1"]["seed"] == 20260809
    assert variants["candidate-2"]["seed"] == 20260810
    assert variants["candidate-2"]["warp_seed"] == 20260812
    assert variants["candidate-3"]["seed"] == 20260811
    assert len(receipt["timings"]["render_calls"]) == 8
    assert result["m12"]["all_values_above_threshold"] is True

    with Image.open(
        output_root / "clean/candidate-1__canonical__z-plus.png"
    ) as image:
        image.load()
        assert image.size == (512, 512)
        assert image.mode == "RGB"


def test_bundle_writer_refuses_existing_output_root_first(
    tmp_path: Path,
) -> None:
    """Catch clobber checks that run after upstream reads or writes."""
    r25 = _module()
    output_root = tmp_path / "preview"
    output_root.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        r25.write_r25_preview_bundle(
            output_root,
            r19_screen_root=tmp_path / "missing-r19",
            canonical_vertices=np.empty((0, 3), dtype=np.float64),
            canonical_faces=np.empty((0, 3), dtype=np.int64),
            deformed_vertices=np.empty((0, 3), dtype=np.float64),
            deformed_faces=np.empty((0, 3), dtype=np.int64),
            canonical_file_sha256="a" * 64,
            deformed_file_sha256="b" * 64,
            base_source_colors=_base_source_colors(),
            base_source_sha256="c" * 64,
            render_vertex_colors=lambda *args: {},
            camera_registry_receipts=[],
            open3d_version="0.19.0",
            rss_check=lambda: None,
            peak_process_tree_rss_bytes=0,
        )


def test_bundle_writer_stops_when_rendered_mask_differs(
    tmp_path: Path,
) -> None:
    """Catch a run that keeps rendering after an M5 mask mismatch."""
    r25 = _module()
    r19_root, mask = _preview_fixture(tmp_path)
    renderer = _fake_preview_renderer(mask, mask_shift=4)
    output_root = tmp_path / "preview"

    with pytest.raises(ValueError, match="mask"):
        _write_preview_bundle(r25, output_root, r19_root, renderer)

    assert (output_root / "fields").is_dir()
    assert not list((output_root / "clean").glob("*.png"))


def test_dilate_mask_once_uses_eight_neighbourhood() -> None:
    """Catch a four-neighbour or multi-pixel dilation implementation."""
    r25 = _module()
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True

    dilated = r25.dilate_mask_once(mask)

    assert dilated.sum() == 9
    assert dilated[1:4, 1:4].all()
    corner = np.zeros((4, 4), dtype=bool)
    corner[0, 0] = True
    corner_dilated = r25.dilate_mask_once(corner)
    assert corner_dilated.sum() == 4
    assert corner_dilated[:2, :2].all()


def test_m5_v4_ring_exempt_but_true_background_gated(
    tmp_path: Path,
) -> None:
    """Catch a background gate that compares or forgives the wrong region."""
    r25 = _module()
    r19_root, mask = _preview_fixture(tmp_path)

    # A non-clear pixel in the true background must stop the run even
    # though the foreground-coloured silhouette ring stays exempt.
    with pytest.raises(ValueError, match="clear colour"):
        _write_preview_bundle(
            r25,
            tmp_path / "preview-poked",
            r19_root,
            _poking_renderer(mask, (0, 0), (77, 0, 0)),
        )

    # A true-background pixel that matches R19 but not the clear colour
    # must still fail: the clear-colour clause is independent.
    for mesh_name in _MESH_NAMES:
        for view_name in _VIEW_NAMES:
            path = r19_root / f"renders/{mesh_name}/{view_name}.png"
            with Image.open(path) as image:
                image.load()
                pixels = np.array(image, copy=True)
            pixels[0, 0] = (9, 9, 9)
            Image.fromarray(pixels, mode="RGB").save(path)
    with pytest.raises(ValueError, match="clear colour"):
        _write_preview_bundle(
            r25,
            tmp_path / "preview-nonclear",
            r19_root,
            _poking_renderer(mask, (0, 0), (9, 9, 9)),
        )

    # A clear-colour pixel that no longer matches the R19 render must
    # fail the R19 identity clause.
    with pytest.raises(ValueError, match="frozen R19 render"):
        _write_preview_bundle(
            r25,
            tmp_path / "preview-mismatch",
            r19_root,
            _fake_preview_renderer(mask),
        )


def test_bundle_writer_stops_when_base_rgb_differs_from_pin(
    tmp_path: Path,
) -> None:
    """Catch a run that proceeds on a drifted base colour derivation."""
    r25 = _module()
    r19_root, mask = _preview_fixture(tmp_path)
    output_root = tmp_path / "preview"

    with pytest.raises(ValueError, match="base colour"):
        _write_preview_bundle(
            r25,
            output_root,
            r19_root,
            _fake_preview_renderer(mask),
            base_source_colors=np.tile(
                np.array([10, 10, 10], dtype=np.uint8),
                (300, 1),
            ),
        )

    assert not output_root.exists()


def test_rss_check_wiring_counts_and_aborts_mid_run(tmp_path: Path) -> None:
    """Catch a writer that renders without consulting the RSS monitor."""
    r25 = _module()
    r19_root, mask = _preview_fixture(tmp_path)
    calls: list[int] = []

    def counting_check() -> None:
        calls.append(len(calls))

    _write_preview_bundle(
        r25,
        tmp_path / "preview-counted",
        r19_root,
        _fake_preview_renderer(mask),
        rss_check=counting_check,
    )
    assert len(calls) >= 10

    aborts: list[int] = []

    def aborting_check() -> None:
        aborts.append(len(aborts))
        if len(aborts) == 2:
            raise MemoryError("process-tree RSS reached the ceiling")

    aborted_root = tmp_path / "preview-aborted"
    with pytest.raises(MemoryError, match="RSS"):
        _write_preview_bundle(
            r25,
            aborted_root,
            r19_root,
            _fake_preview_renderer(mask),
            rss_check=aborting_check,
        )
    assert not list((aborted_root / "clean").glob("*.png"))


def test_runner_checks_output_roots_before_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a runner that touches resources before its no-clobber gate."""
    runner = _runner()
    published_root = tmp_path / "development-preview-v1"
    published_root.mkdir()
    monkeypatch.setattr(runner, "OUTPUT_ROOT", published_root)
    monkeypatch.setattr(runner, "ATTEMPT_ROOT", tmp_path / "attempt")
    monkeypatch.setattr(
        runner,
        "_available_memory_bytes",
        lambda: (_ for _ in ()).throw(AssertionError("memory touched")),
    )

    assert runner.main(["preview-v1"]) == 3
    assert runner.main(["wrong-action"]) == 2
