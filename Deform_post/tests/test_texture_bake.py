"""C1 v2 texel-bake tests (rasterization, barycentric mapping, gutter,
determinism, amplitude-zero flatness, fine-octave construction).

Everything runs on tiny synthetic UV charts (pure numpy, no renderer); one
optional test rasterizes the real R16 formal-v2 sidecar when that local
verification bundle exists and reports its texel coverage.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

REAL_SIDECAR = (
    r"D:\MedSim2Learn-C1-verification\r16a-uv-textured-render\formal-v2"
    r"\uv\kidney-anat-xatlas-v1.npz")


def _quad_arrays(scale=2.0):
    """Unit-square UV chart over a planar quad of edge `scale` at z=0."""
    vertices = np.array(
        [[0, 0, 0], [scale, 0, 0], [scale, scale, 0], [0, scale, 0]],
        dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uv_vertices = np.array(
        [[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    mapping = np.arange(4, dtype=np.uint32)
    uv_faces = faces.astype(np.uint32)
    return vertices, faces, uv_vertices, mapping, uv_faces


def _half_quad_arrays():
    """Chart covering only the LEFT half of UV space (u in [0, 0.5])."""
    vertices, faces, _uv, mapping, uv_faces = _quad_arrays()
    uv_vertices = np.array(
        [[0, 0], [0.5, 0], [0.5, 1], [0, 1]], dtype=np.float64)
    return vertices, faces, uv_vertices, mapping, uv_faces


# ---------------------------------------------------------------------------
# Rasterization
# ---------------------------------------------------------------------------

def test_rasterize_full_square_covers_every_texel():
    from dpost.texture_bake import chart_coverage, rasterize_uv_charts

    _v, _f, uv_vertices, _m, uv_faces = _quad_arrays()
    size = 64
    face_index, bary = rasterize_uv_charts(uv_vertices, uv_faces, size)
    assert face_index.shape == (size, size)
    assert bary.shape == (size, size, 3)
    assert int((face_index >= 0).sum()) == size * size
    cov = chart_coverage(face_index, len(uv_faces))
    assert cov["covered_fraction"] == pytest.approx(1.0)
    assert cov["zero_texel_face_count"] == 0
    # Both triangles of the square claim texels.
    assert set(np.unique(face_index)) == {0, 1}
    # Barycentric weights of covered texels are a valid convex combination.
    covered = face_index >= 0
    weights = bary[covered]
    assert float(weights.min()) >= -1e-9
    np.testing.assert_allclose(weights.sum(axis=1), 1.0, atol=1e-9)


def test_rasterize_half_chart_covers_left_columns_only():
    from dpost.texture_bake import rasterize_uv_charts

    _v, _f, uv_vertices, _m, uv_faces = _half_quad_arrays()
    size = 64
    face_index, _bary = rasterize_uv_charts(uv_vertices, uv_faces, size)
    covered = face_index >= 0
    # u = 0.5 maps to pixel x = 31.5: columns 0..31 covered, 32.. empty.
    assert bool(covered[:, :32].all())
    assert not covered[:, 32:].any()


def test_rasterize_zero_texel_face_reported_not_fatal():
    from dpost.texture_bake import chart_coverage, rasterize_uv_charts

    # One normal chart plus a sliver triangle far smaller than one texel.
    uv_vertices = np.array(
        [[0, 0], [0.4, 0], [0.4, 0.4], [0, 0.4],
         [0.9, 0.9], [0.901, 0.9], [0.9, 0.901]], dtype=np.float64)
    uv_faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]], dtype=np.uint32)
    face_index, _bary = rasterize_uv_charts(uv_vertices, uv_faces, 32)
    cov = chart_coverage(face_index, len(uv_faces))
    assert cov["zero_texel_face_count"] == 1
    assert cov["zero_texel_faces"] == [2]
    assert 0.0 < cov["covered_fraction"] < 1.0


# ---------------------------------------------------------------------------
# Barycentric texel -> surface mapping
# ---------------------------------------------------------------------------

def test_surface_points_match_affine_map_on_quad():
    from dpost.texture_bake import rasterize_uv_charts, surface_points_for_texels

    vertices, _f, uv_vertices, mapping, uv_faces = _quad_arrays(scale=2.0)
    size = 32
    face_index, bary = rasterize_uv_charts(uv_vertices, uv_faces, size)
    points = surface_points_for_texels(
        vertices, mapping, uv_faces, face_index, bary)
    ys, xs = np.nonzero(face_index >= 0)
    assert points.shape == (len(ys), 3)
    # UV == vertex xy / 2 on this quad, so the texel center (u, v) must land
    # exactly at (2u, 2v, 0); u = (col + 0.5) / S and v = (row + 0.5) / S.
    expected_u = (xs + 0.5) / size
    expected_v = (ys + 0.5) / size
    np.testing.assert_allclose(points[:, 0], 2.0 * expected_u, atol=1e-9)
    np.testing.assert_allclose(points[:, 1], 2.0 * expected_v, atol=1e-9)
    np.testing.assert_allclose(points[:, 2], 0.0, atol=1e-12)


# ---------------------------------------------------------------------------
# Field construction (R25 variants + appended fine octave)
# ---------------------------------------------------------------------------

def test_variant_field_with_fine_is_normalized_and_differs_from_base():
    from dpost import c1_r25_procedural_microtexture as r25
    from dpost.texture_bake import variant_field_with_fine

    rng = np.random.default_rng(3)
    points = np.ascontiguousarray(rng.uniform(0.1, 0.9, size=(500, 3)))
    for variant in ("candidate-1", "candidate-2", "candidate-3"):
        combined = variant_field_with_fine(variant, points, 0.08)
        base = r25.variant_scalar_field(variant, points)
        assert combined.shape == base.shape
        assert abs(float(combined.mean())) < 1e-9
        assert float(np.abs(combined).max()) == pytest.approx(1.0)
        assert float(np.abs(combined - base).mean()) > 1e-3, variant
        # Same inputs reproduce the same field bytes.
        replay = variant_field_with_fine(variant, points, 0.08)
        assert combined.tobytes() == replay.tobytes()


# ---------------------------------------------------------------------------
# Bake: gutter, determinism, flatness
# ---------------------------------------------------------------------------

def _bake_half(amplitude, size=64, gutter_px=4):
    from dpost.texture_bake import bake_field_texture

    vertices, _f, uv_vertices, mapping, uv_faces = _half_quad_arrays()
    return bake_field_texture(
        vertices, uv_vertices, uv_faces, mapping, "candidate-1",
        (0.84, 0.72, 0.76), amplitude, size=size, gutter_px=gutter_px,
        fine_wavelength=0.08)


def test_gutter_replicates_border_texels_then_base_fill():
    tex = _bake_half(amplitude=0.15)
    base255 = np.floor(np.array([0.84, 0.72, 0.76]) * 255.0 + 0.5).astype(np.uint8)
    # Columns 32..35 replicate the last covered column (31) row by row.
    for k in range(1, 5):
        np.testing.assert_array_equal(tex[:, 31 + k], tex[:, 31])
    # Beyond the 4-texel gutter the texture is the deterministic base fill.
    assert np.array_equal(
        tex[:, 36:], np.broadcast_to(base255, tex[:, 36:].shape))
    # The covered region actually modulates (not flat).
    assert int(np.unique(tex[:, :32].reshape(-1, 3), axis=0).shape[0]) > 1


def test_bake_deterministic_same_bytes():
    a = _bake_half(amplitude=0.18)
    b = _bake_half(amplitude=0.18)
    assert a.tobytes() == b.tobytes()


def test_bake_worley_variant_deterministic():
    from dpost.texture_bake import bake_field_texture

    vertices, _f, uv_vertices, mapping, uv_faces = _quad_arrays()
    kwargs = dict(size=48, gutter_px=2, fine_wavelength=0.08)
    a = bake_field_texture(vertices, uv_vertices, uv_faces, mapping,
                           "candidate-3", (0.83, 0.70, 0.75), 0.12, **kwargs)
    b = bake_field_texture(vertices, uv_vertices, uv_faces, mapping,
                           "candidate-3", (0.83, 0.70, 0.75), 0.12, **kwargs)
    assert a.dtype == np.uint8 and a.shape == (48, 48, 3)
    assert a.tobytes() == b.tobytes()


def test_bake_amplitude_zero_is_flat_base_colour():
    tex = _bake_half(amplitude=0.0)
    base255 = np.floor(np.array([0.84, 0.72, 0.76]) * 255.0 + 0.5).astype(np.uint8)
    assert np.array_equal(tex, np.broadcast_to(base255, tex.shape))


def test_bake_base_colour_plumbs_into_flat_texture():
    from dpost.texture_bake import bake_field_texture

    vertices, _f, uv_vertices, mapping, uv_faces = _quad_arrays()
    tex = bake_field_texture(
        vertices, uv_vertices, uv_faces, mapping, "candidate-1",
        (0.5, 0.25, 1.0), 0.0, size=16, gutter_px=1, fine_wavelength=0.08)
    expected = np.floor(np.array([0.5, 0.25, 1.0]) * 255.0 + 0.5)
    assert np.array_equal(tex, np.broadcast_to(
        expected.astype(np.uint8), tex.shape))


# ---------------------------------------------------------------------------
# Real R16 sidecar (local verification bundle; skipped when absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isfile(REAL_SIDECAR),
                    reason="local R16 formal-v2 sidecar not present")
def test_real_sidecar_every_uv_face_covers_a_texel_at_1024():
    from dpost.texture_bake import chart_coverage, rasterize_uv_charts

    with np.load(REAL_SIDECAR) as archive:
        uv_vertices = archive["uv_vertices"]
        uv_faces = archive["uv_faces"]
    face_index, _bary = rasterize_uv_charts(uv_vertices, uv_faces, 1024)
    cov = chart_coverage(face_index, len(uv_faces))
    print(f"real sidecar 1024^2 coverage: {cov['covered_fraction']:.4f} "
          f"({cov['covered_texels']} texels), zero-texel faces: "
          f"{cov['zero_texel_face_count']}")
    assert cov["zero_texel_face_count"] == 0
    assert cov["covered_fraction"] > 0.3
