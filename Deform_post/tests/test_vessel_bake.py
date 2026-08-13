"""C1 v3 vessel-layer tests (signed field, blend band, compositing, tree).

The v3 increment composites the R23 implicit vessel field into the v2
texel-baked texture: a frozen R21 space-colonization tree (only the
attraction seed varies), R23 tapered radii (ratio x surface extent, cubic
taper), an exact per-texel tapered-segment signed distance field (per-vertex
interpolation would blur sub-millimetre vessels across ~3.6 mm mesh edges),
and the R23 +-antialias smoothstep band mixing the drawn vessel colour over
the tissue texels BEFORE the gutter dilation. Everything here is pure numpy
on synthetic geometry; the real-mesh gates run outside pytest (smoke_v3).
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

QUAD_VERTS = np.array(
    [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], dtype=np.float64)
QUAD_FACES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
QUAD_UV = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
QUAD_MAPPING = np.arange(4, dtype=np.uint32)


def _single_segment(r0=1.0, r1=1.0):
    a = np.array([[0.0, 0.0, 0.0]])
    b = np.array([[10.0, 0.0, 0.0]])
    return a, b, np.array([r0]), np.array([r1])


# ---------------------------------------------------------------------------
# Signed tapered-segment field
# ---------------------------------------------------------------------------

def test_signed_field_matches_analytic_capsule():
    from dpost.texture_bake import evaluate_vessel_signed_field

    a, b, r0, r1 = _single_segment(r0=1.0, r1=1.0)
    points = np.array([
        [5.0, 2.0, 0.0],    # beside the middle: dist 2 - r 1 = 1
        [5.0, 0.5, 0.0],    # inside: 0.5 - 1 = -0.5
        [12.0, 0.0, 0.0],   # beyond the end cap: 2 - 1 = 1
        [-3.0, 4.0, 0.0],   # beyond the start cap: 5 - 1 = 4
        [5.0, 0.0, 0.0],    # on the centerline: -1
    ])
    expected = np.array([1.0, -0.5, 1.0, 4.0, -1.0])
    signed = evaluate_vessel_signed_field(points, a, b, r0, r1)
    np.testing.assert_allclose(signed, expected, atol=1e-9)


def test_signed_field_tapered_radius_interpolates():
    from dpost.texture_bake import evaluate_vessel_signed_field

    a, b, r0, r1 = _single_segment(r0=2.0, r1=0.0)
    points = np.array([
        [5.0, 1.0, 0.0],    # t = 0.5 -> r = 1 -> 1 - 1 = 0
        [0.0, 3.0, 0.0],    # t = 0 -> r = 2 -> 3 - 2 = 1
        [10.0, 1.0, 0.0],   # t = 1 -> r = 0 -> 1 - 0 = 1
        [-4.0, 0.0, 0.0],   # clamped t = 0 -> 4 - 2 = 2
    ])
    expected = np.array([0.0, 1.0, 1.0, 2.0])
    signed = evaluate_vessel_signed_field(points, a, b, r0, r1)
    np.testing.assert_allclose(signed, expected, atol=1e-9)


def test_signed_field_takes_min_over_segments():
    from dpost.texture_bake import evaluate_vessel_signed_field

    a = np.array([[0.0, 0.0, 0.0], [0.0, 5.0, 0.0]])
    b = np.array([[10.0, 0.0, 0.0], [10.0, 5.0, 0.0]])
    r = np.array([0.5, 1.0])
    points = np.array([
        [5.0, 4.0, 0.0],   # 1 from seg2 (r 1) -> 0; 4 from seg1 -> 3.5
        [5.0, 1.0, 0.0],   # 1 from seg1 (r 0.5) -> 0.5; 4 from seg2 -> 3
    ])
    signed = evaluate_vessel_signed_field(points, a, b, r, r)
    np.testing.assert_allclose(signed, [0.0, 0.5], atol=1e-9)


def test_signed_field_chunking_invariant():
    from dpost.texture_bake import evaluate_vessel_signed_field

    rng = np.random.default_rng(7)
    a = rng.uniform(0, 10, size=(9, 3))
    b = a + rng.uniform(0.5, 3.0, size=(9, 3))
    r0 = rng.uniform(0.1, 1.0, size=9)
    r1 = rng.uniform(0.1, 1.0, size=9)
    points = rng.uniform(-2, 12, size=(1000, 3))
    full = evaluate_vessel_signed_field(points, a, b, r0, r1)
    chunked = evaluate_vessel_signed_field(points, a, b, r0, r1, chunk_size=64)
    assert full.tobytes() == chunked.tobytes()


def test_signed_field_rejects_degenerate_segment():
    from dpost.texture_bake import evaluate_vessel_signed_field

    a = np.array([[1.0, 1.0, 1.0]])
    with pytest.raises(ValueError, match="degenerate"):
        evaluate_vessel_signed_field(np.zeros((2, 3)), a, a.copy(),
                                     np.array([0.5]), np.array([0.5]))


def test_signed_field_resolves_subedge_tube_crisply():
    # A 0.66 mm-radius tube sampled on a 0.1 mm grid: the w > 0.5 cross
    # section must span ~2r (per-texel evaluation), not the ~3.6 mm blur a
    # per-vertex interpolation across mesh edges would give.
    from dpost.texture_bake import evaluate_vessel_signed_field, vessel_blend_weight

    a, b, _r0, _r1 = _single_segment()
    radius = np.array([0.66])
    ys = np.arange(-2.0, 2.0 + 1e-9, 0.1)
    points = np.column_stack(
        [np.full_like(ys, 5.0), ys, np.zeros_like(ys)])
    signed = evaluate_vessel_signed_field(points, a, b, radius, radius)
    w = vessel_blend_weight(signed, 0.10)
    inside = ys[w > 0.5]
    width = float(inside.max() - inside.min())
    # The sampled span underestimates the true 2r cross section by at most
    # one grid step per side (w > 0.5 exactly on the s < 0 interior).
    assert 2 * 0.66 - 2 * 0.1 - 1e-9 <= width <= 2 * 0.66 + 1e-9


# ---------------------------------------------------------------------------
# Antialias blend band (R23 smoothstep convention)
# ---------------------------------------------------------------------------

def test_blend_weight_band_math():
    from dpost.texture_bake import vessel_blend_weight

    h = 0.10
    signed = np.array([-3 * h, -h, -0.5 * h, 0.0, 0.5 * h, h, 3 * h])
    w = vessel_blend_weight(signed, h)
    # R23 build_lab_lut: normalized = clip((s + h) / 2h), cubic smoothstep,
    # alpha = 1 - smooth. At s = -h/2: n = 0.25 -> smooth = 0.15625.
    np.testing.assert_allclose(
        w, [1.0, 1.0, 0.84375, 0.5, 0.15625, 0.0, 0.0], atol=1e-12)
    assert np.all(np.diff(w) <= 0.0), "weight must fall monotonically"


def test_blend_weight_rejects_nonpositive_halfwidth():
    from dpost.texture_bake import vessel_blend_weight

    with pytest.raises(ValueError, match="antialias"):
        vessel_blend_weight(np.zeros(3), 0.0)


# ---------------------------------------------------------------------------
# Tree growth wrapper (frozen R21 parameters, seeded attractors)
# ---------------------------------------------------------------------------

def test_build_vessel_tree_deterministic_and_seed_sensitive():
    from dpost.texture_bake import build_vessel_tree

    tree_a = build_vessel_tree(QUAD_VERTS, QUAD_FACES, 11)
    tree_b = build_vessel_tree(QUAD_VERTS, QUAD_FACES, 11)
    np.testing.assert_array_equal(
        tree_a.node_vertex_indices, tree_b.node_vertex_indices)
    np.testing.assert_array_equal(
        tree_a.parent_node_indices, tree_b.parent_node_indices)
    np.testing.assert_array_equal(
        tree_a.attraction_points, tree_b.attraction_points)
    tree_c = build_vessel_tree(QUAD_VERTS, QUAD_FACES, 12)
    assert not np.array_equal(tree_a.attraction_points, tree_c.attraction_points)


def test_build_vessel_tree_uses_frozen_r21_parameters():
    from dpost import c1_r21_procedural_vessels as r21
    from dpost.texture_bake import build_vessel_tree

    tree = build_vessel_tree(QUAD_VERTS, QUAD_FACES, 3)
    extent = float(np.max(np.ptp(QUAD_VERTS, axis=0)))
    assert tree.attraction_count == r21.R21_ATTRACTION_COUNT
    assert tree.influence_radius == pytest.approx(r21.R21_INFLUENCE_RATIO * extent)
    assert tree.kill_radius == pytest.approx(r21.R21_KILL_RATIO * extent)
    assert tree.max_iterations == r21.R21_MAX_GROWTH_ITERATIONS
    assert tree.surface_extent == pytest.approx(extent)


def test_vessel_polyline_segments_layout():
    from dpost.texture_bake import build_vessel_tree, vessel_polyline_segments

    tree = build_vessel_tree(QUAD_VERTS, QUAD_FACES, 11)
    radii = np.linspace(1.0, 0.2, len(tree.node_vertex_indices))
    start, end, r_start, r_end = vessel_polyline_segments(
        QUAD_VERTS, tree, radii)
    n_seg = len(tree.node_vertex_indices) - 1
    assert start.shape == (n_seg, 3) and end.shape == (n_seg, 3)
    nodes = tree.node_vertex_indices
    parents = tree.parent_node_indices
    np.testing.assert_array_equal(start, QUAD_VERTS[nodes[parents[1:]]])
    np.testing.assert_array_equal(end, QUAD_VERTS[nodes[1:]])
    np.testing.assert_array_equal(r_start, radii[parents[1:]])
    np.testing.assert_array_equal(r_end, radii[1:])


# ---------------------------------------------------------------------------
# Bake compositing (mix before gutter, determinism, byte bounds)
# ---------------------------------------------------------------------------

VESSEL_KWARGS = dict(
    tree_seed=21, ratio=0.2, antialias_mm=0.10, rgb255=(180, 120, 135))


def _bake_quad(vessel=None, amplitude=0.15, size=64):
    from dpost.texture_bake import bake_field_texture

    return bake_field_texture(
        QUAD_VERTS, QUAD_UV, QUAD_FACES.astype(np.uint32), QUAD_MAPPING,
        "candidate-1", (0.84, 0.72, 0.76), amplitude, size=size, gutter_px=2,
        fine_wavelength=0.08, vessel=vessel, source_faces=QUAD_FACES)


def test_bake_vessel_returns_texture_and_stats():
    texture, stats = _bake_quad(vessel=dict(VESSEL_KWARGS))
    assert texture.dtype == np.uint8 and texture.shape == (64, 64, 3)
    assert stats["tree_seed"] == 21
    assert stats["segment_count"] >= 1
    assert stats["node_count"] == stats["segment_count"] + 1
    assert stats["total_length_mm"] > 0.0
    assert stats["root_diameter_mm"] == pytest.approx(
        0.2 * 10.0)  # ratio x quad extent
    assert 0.0 < stats["vessel_texel_fraction"] < 1.0
    assert stats["vessel_texels"] > 0
    assert stats["covered_texels"] == 64 * 64
    assert stats["evaluation"] == "per-texel-exact-tapered-segment"


def test_bake_vessel_deterministic_bytes():
    tex_a, stats_a = _bake_quad(vessel=dict(VESSEL_KWARGS))
    tex_b, stats_b = _bake_quad(vessel=dict(VESSEL_KWARGS))
    assert tex_a.tobytes() == tex_b.tobytes()
    assert stats_a == stats_b
    tex_c, _stats_c = _bake_quad(vessel=dict(VESSEL_KWARGS, tree_seed=22))
    assert tex_a.tobytes() != tex_c.tobytes()


def test_bake_vessel_changes_texture_and_stays_in_byte_hull():
    plain = _bake_quad(vessel=None)
    texture, _stats = _bake_quad(vessel=dict(VESSEL_KWARGS))
    assert texture.tobytes() != plain.tobytes()
    # Compositing is a convex mix: every texel stays inside the per-channel
    # hull of the tissue texture and the vessel colour.
    vessel_rgb = np.array(VESSEL_KWARGS["rgb255"], dtype=np.uint8)
    lo = np.minimum(plain, vessel_rgb[None, None, :])
    hi = np.maximum(plain, vessel_rgb[None, None, :])
    assert bool(np.all(texture >= lo) and np.all(texture <= hi))


def test_bake_vessel_composites_on_flat_amplitude_zero_texture():
    # The vessel layer is independent of the R25 amplitude: an amplitude-0
    # (flat tissue) bake must still carry the vessel texels.
    flat_plain = _bake_quad(vessel=None, amplitude=0.0)
    flat_vessel, stats = _bake_quad(vessel=dict(VESSEL_KWARGS), amplitude=0.0)
    assert stats["vessel_texels"] > 0
    assert flat_vessel.tobytes() != flat_plain.tobytes()
    # Away from the vessel band the flat bake is untouched.
    diff_mask = np.any(flat_vessel != flat_plain, axis=2)
    assert 0 < int(diff_mask.sum()) < diff_mask.size


def test_bake_vessel_interior_texels_carry_exact_vessel_colour():
    from dpost.c1_r21_procedural_vessels import compute_equal_terminal_diameters
    from dpost.texture_bake import (
        build_vessel_tree, evaluate_vessel_signed_field, rasterize_uv_charts,
        surface_points_for_texels, vessel_blend_weight,
        vessel_polyline_segments)

    size = 64
    vessel = dict(VESSEL_KWARGS)
    texture, _stats = _bake_quad(vessel=vessel, size=size)
    # Recompute w on the same texel grid; w = 1 texels must equal the vessel
    # colour bytes exactly and w = 0 texels the tissue bytes exactly.
    face_index, bary = rasterize_uv_charts(
        QUAD_UV, QUAD_FACES.astype(np.uint32), size)
    points = surface_points_for_texels(
        QUAD_VERTS, QUAD_MAPPING, QUAD_FACES.astype(np.uint32),
        face_index, bary)
    tree = build_vessel_tree(QUAD_VERTS, QUAD_FACES, vessel["tree_seed"])
    radii = compute_equal_terminal_diameters(
        tree, vessel["ratio"] * tree.surface_extent) / 2.0
    start, end, r0, r1 = vessel_polyline_segments(QUAD_VERTS, tree, radii)
    signed = evaluate_vessel_signed_field(points, start, end, r0, r1)
    w = vessel_blend_weight(signed, vessel["antialias_mm"])
    plain = _bake_quad(vessel=None, size=size)
    covered = face_index >= 0
    tex_cov = texture[covered]
    plain_cov = plain[covered]
    interior = w >= 1.0
    outside = w <= 0.0
    assert interior.any() and outside.any()
    assert np.array_equal(
        tex_cov[interior],
        np.broadcast_to(np.array(vessel["rgb255"], dtype=np.uint8),
                        (int(interior.sum()), 3)))
    assert np.array_equal(tex_cov[outside], plain_cov[outside])


def test_bake_vessel_requires_source_faces():
    from dpost.texture_bake import bake_field_texture

    with pytest.raises(ValueError, match="source_faces"):
        bake_field_texture(
            QUAD_VERTS, QUAD_UV, QUAD_FACES.astype(np.uint32), QUAD_MAPPING,
            "candidate-1", (0.84, 0.72, 0.76), 0.15, size=32, gutter_px=2,
            fine_wavelength=0.08, vessel=dict(VESSEL_KWARGS))


def test_bake_without_vessel_keeps_v2_return_contract():
    from dpost.texture_bake import bake_field_texture

    out = bake_field_texture(
        QUAD_VERTS, QUAD_UV, QUAD_FACES.astype(np.uint32), QUAD_MAPPING,
        "candidate-1", (0.84, 0.72, 0.76), 0.15, size=32, gutter_px=2,
        fine_wavelength=0.08)
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.uint8 and out.shape == (32, 32, 3)
