"""Texel-level texture baking for C1 appearance DR (design v2 + v3 vessels).

One 1024^2 RGB texture per sequence per seed: every texel covered by a UV
chart is mapped back to a surface point of the CANONICAL first frame through
its triangle's barycentric coordinates, the R25 continuous field (plus one
appended texel-scale fine octave) is evaluated at those 3D points, and the
colour formula ``clip(base_rgb * (1 + a * n))`` from the extracted R25 module
produces the texel bytes. A ``gutter_px`` dilation replicates chart-border
texels outward so bilinear filtering cannot bleed the fill colour across
chart boundaries; the sampled field is continuous in OBJECT space, so chart
seams do not exist in the value domain (the R17 lesson) and the gutter only
guards the filter footprint.

Design v3 composites the R23 implicit vessel field over the tissue texels
BEFORE the gutter: a frozen R21 space-colonization tree (only the attraction
seed varies the layout), R23 tapered node radii (root diameter = ratio x
canonical surface extent, cubic equal-terminal taper), and the R23
+-antialias-half-width smoothstep band mixing the drawn vessel colour into
the texture. The signed field keeps the R23 convention ``centerline distance
minus tapered radius`` but is evaluated EXACTLY per texel against the tree's
polyline segments (Euclidean point-to-tapered-segment distances) instead of
being interpolated from R23's per-vertex graph field: vessel radii
(<= ~0.66 mm at the frozen small scale) sit far below the ~3.6 mm mesh edge
length, so per-vertex interpolation would blur the tubes into vertex blobs
while the per-texel evaluation keeps them crisp at texel resolution.

Texture array orientation follows the legacy Open3D sampling convention
verified empirically on 2026-08-10 (_c1_scratch/probe_texture_behavior.py):
UV (u, v) samples ``array[row, col]`` with ``col = u*S - 0.5`` and
``row = v*S - 0.5`` -- v = 0 is array row 0, NO vertical flip.

Everything here is pure numpy and deterministic: identical inputs produce
identical texture bytes.
"""

import numpy as np

from . import c1_r25_procedural_microtexture as r25

# Weight of the appended fine octave: GAIN**3 continues each variant's
# three-octave gain-0.5 ladder one step below its finest frozen wavelength.
FINE_OCTAVE_WEIGHT = 0.125
# SeedSequence([variant seed, salt]) keys the fine octave's permutation
# table so it is deterministic per variant and decorrelated from the frozen
# ladder tables.
FINE_OCTAVE_SEED_SALT = 8
# Fixed 8-neighbour propagation order for the gutter fill; the first
# neighbour (in this order) that already has a colour wins, which makes the
# dilation deterministic.
_GUTTER_NEIGHBOR_ORDER = (
    (0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (-1, 1), (1, -1), (1, 1))
# Barycentric inside-test slack (in normalized barycentric units) so texel
# centers sitting exactly on a shared chart edge are claimed by one face.
_INSIDE_EPS = 1e-9


def _require_uv_arrays(uv_vertices, uv_faces):
    if (
        not isinstance(uv_vertices, np.ndarray)
        or uv_vertices.ndim != 2
        or uv_vertices.shape[1] != 2
        or len(uv_vertices) == 0
        or not np.isfinite(uv_vertices).all()
    ):
        raise ValueError("uv_vertices must be a nonempty finite (N, 2) array")
    if (
        not isinstance(uv_faces, np.ndarray)
        or uv_faces.ndim != 2
        or uv_faces.shape[1] != 3
        or len(uv_faces) == 0
        or not np.issubdtype(uv_faces.dtype, np.integer)
    ):
        raise ValueError("uv_faces must be a nonempty integer (N, 3) array")
    if np.any(uv_faces < 0) or np.any(np.asarray(uv_faces) >= len(uv_vertices)):
        raise ValueError("uv_faces index outside uv_vertices")


def rasterize_uv_charts(uv_vertices, uv_faces, size):
    """Rasterize every UV triangle onto a size x size texel grid.

    Returns ``(face_index, bary)``: ``face_index`` is (S, S) int32 with the
    claiming UV face per texel (-1 where no chart covers the texel center)
    and ``bary`` is (S, S, 3) float64 barycentric weights of the texel
    center inside that face. Faces are scanned in order and the first face
    to claim a texel keeps it, so the result is deterministic.
    """
    _require_uv_arrays(uv_vertices, uv_faces)
    size = int(size)
    if size < 1:
        raise ValueError(f"texture size {size} must be >= 1")

    # Texel center i sits at pixel coordinate i; UV (u, v) lands at
    # (u*S - 0.5, v*S - 0.5) per the verified legacy sampling convention.
    px = np.asarray(uv_vertices, dtype=np.float64) * float(size) - 0.5
    face_index = np.full((size, size), -1, dtype=np.int32)
    bary = np.zeros((size, size, 3), dtype=np.float64)

    for f, (ia, ib, ic) in enumerate(np.asarray(uv_faces)):
        (xa, ya), (xb, yb), (xc, yc) = px[ia], px[ib], px[ic]
        d = (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya)
        if abs(d) < 1e-30:
            continue  # degenerate UV face: never claims a texel
        x_lo = max(0, int(np.ceil(min(xa, xb, xc) - 1e-9)))
        x_hi = min(size - 1, int(np.floor(max(xa, xb, xc) + 1e-9)))
        y_lo = max(0, int(np.ceil(min(ya, yb, yc) - 1e-9)))
        y_hi = min(size - 1, int(np.floor(max(ya, yb, yc) + 1e-9)))
        if x_lo > x_hi or y_lo > y_hi:
            continue
        xs = np.arange(x_lo, x_hi + 1, dtype=np.float64)
        ys = np.arange(y_lo, y_hi + 1, dtype=np.float64)
        grid_x = xs[None, :]
        grid_y = ys[:, None]
        w0 = ((xb - grid_x) * (yc - grid_y) - (xc - grid_x) * (yb - grid_y)) / d
        w1 = ((xc - grid_x) * (ya - grid_y) - (xa - grid_x) * (yc - grid_y)) / d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -_INSIDE_EPS) & (w1 >= -_INSIDE_EPS) & (w2 >= -_INSIDE_EPS)
        window = face_index[y_lo:y_hi + 1, x_lo:x_hi + 1]
        claim = inside & (window == -1)
        if not claim.any():
            continue
        window[claim] = f
        bary_window = bary[y_lo:y_hi + 1, x_lo:x_hi + 1]
        bary_window[claim] = np.stack(
            (np.broadcast_to(w0, claim.shape)[claim],
             np.broadcast_to(w1, claim.shape)[claim],
             np.broadcast_to(w2, claim.shape)[claim]), axis=1)
    return face_index, bary


def chart_coverage(face_index, n_faces):
    """Texel-coverage diagnostics for one rasterized chart layout."""
    covered = face_index >= 0
    counts = np.bincount(face_index[covered].astype(np.int64),
                         minlength=int(n_faces))
    zero_faces = [int(i) for i in np.flatnonzero(counts[:int(n_faces)] == 0)]
    return {
        "covered_texels": int(covered.sum()),
        "covered_fraction": float(covered.mean()),
        "zero_texel_faces": zero_faces,
        "zero_texel_face_count": len(zero_faces),
    }


def surface_points_for_texels(vertices, uv_to_source, uv_faces, face_index, bary):
    """Map covered texels to 3D surface points by barycentric interpolation.

    ``vertices`` are per-SOURCE-vertex 3D positions (any affine frame: raw or
    normalized coordinates interpolate identically); rows come back in the
    grid's row-major covered-texel order, matching boolean-mask assignment.
    """
    corners = np.asarray(vertices, dtype=np.float64)[
        np.asarray(uv_to_source)[np.asarray(uv_faces)]]
    ys, xs = np.nonzero(face_index >= 0)
    faces = face_index[ys, xs].astype(np.int64)
    weights = bary[ys, xs]
    return np.einsum("nk,nkd->nd", weights, corners[faces])


def variant_field_with_fine(variant, points, fine_wavelength):
    """R25 variant field plus the appended fine octave, renormalized.

    The frozen module's field is peak-normalized; one improved-noise octave
    at ``fine_wavelength`` (weight ``FINE_OCTAVE_WEIGHT``) is added and the
    sum is recentred and peak-normalized again with the module's semantics,
    so the combined field keeps the [-1, 1] contract of the colour formula.
    """
    if not float(fine_wavelength) > 0.0:
        raise ValueError(f"fine wavelength {fine_wavelength} must be > 0")
    base = r25.variant_scalar_field(variant, points)
    table = r25.permutation_table(np.random.SeedSequence(
        [r25.CANDIDATE_SEEDS[variant], FINE_OCTAVE_SEED_SALT]))
    fine = r25.improved_gradient_noise(points / float(fine_wavelength), table)
    raw = base + FINE_OCTAVE_WEIGHT * fine
    recentred = raw - raw.mean()
    peak = float(np.abs(recentred).max())
    if not np.isfinite(peak) or peak <= 0.0:
        raise ValueError("combined field peak magnitude must be positive")
    return recentred / peak


def build_vessel_tree(vertices, faces, tree_seed):
    """Grow the frozen R21 space-colonization tree from seeded attractors.

    Every growth parameter stays at the R21 frozen module constants
    (attraction count 512, influence 0.18 x extent, kill 0.02 x extent, max
    2048 iterations, deterministic root vertex); ONLY the attraction-point
    seed varies the layout (design v3-2). The returned tree's ``seed`` field
    still records the frozen R21 constant -- the caller records the actual
    attraction seed in its own provenance.
    """
    from . import c1_r21_procedural_vessels as r21

    points = r21.sample_equal_area_surface_points(
        vertices, faces, count=r21.R21_ATTRACTION_COUNT, seed=int(tree_seed))
    return r21.grow_graph_surface_vessel_tree(
        vertices, faces, attraction_points=points)


def vessel_polyline_segments(vertices, tree, node_radii):
    """Tree polyline as ``(start, end, r_start, r_end)`` segment arrays.

    One row per non-root node: the segment from its parent node's vertex to
    its own vertex, with the tapered radii of both endpoints. All quantities
    are in the vertices' own (millimetre) frame.
    """
    nodes = np.asarray(tree.node_vertex_indices)
    parents = np.asarray(tree.parent_node_indices)
    if len(nodes) < 2:
        raise ValueError("vessel tree has no segments (single-node tree)")
    radii = np.asarray(node_radii, dtype=np.float64)
    if radii.shape != nodes.shape:
        raise ValueError("node radii must align with the tree nodes")
    positions = np.asarray(vertices, dtype=np.float64)[nodes]
    return (positions[parents[1:]], positions[1:],
            radii[parents[1:]], radii[1:])


def _dot3(points, rows):
    """(C, 3) x (S, 3) -> (C, S) via three explicit outer terms.

    The fixed three-term summation avoids BLAS reduction paths so the bake
    stays bitwise deterministic across runs.
    """
    return (points[:, :1] * rows[:, 0] + points[:, 1:2] * rows[:, 1]
            + points[:, 2:3] * rows[:, 2])


def evaluate_vessel_signed_field(points, seg_start, seg_end, seg_r_start,
                                 seg_r_end, chunk_size=8192):
    """Signed tapered-polyline distance per point (mm), exact and vectorized.

    For each query point: min over tree segments of ``|p - closest point on
    segment| - lerp(r_start, r_end, t)`` with t the clamped projection
    parameter -- the R23 signed-field convention (distance minus tapered
    radius, c1_r23 ``build_signed_field_bundle``) carried from the per-vertex
    graph metric to exact per-texel Euclidean centerline distances. Chunked
    over points to bound peak memory; chunk size does not change the bytes.
    """
    p = np.ascontiguousarray(points, dtype=np.float64)
    a = np.ascontiguousarray(seg_start, dtype=np.float64)
    b = np.ascontiguousarray(seg_end, dtype=np.float64)
    r0 = np.asarray(seg_r_start, dtype=np.float64)
    dr = np.asarray(seg_r_end, dtype=np.float64) - r0
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("points must be an (N, 3) array")
    if not (a.shape == b.shape and a.ndim == 2 and a.shape[1] == 3
            and len(a) > 0 and r0.shape == (len(a),)):
        raise ValueError("segments must be matching (S, 3) + (S,) arrays")
    d = b - a
    len_sq = (d * d).sum(axis=1)
    if not np.all(len_sq > 0.0):
        raise ValueError("degenerate zero-length vessel segment")
    ad = (a * d).sum(axis=1)
    aa = (a * a).sum(axis=1)

    signed = np.empty(len(p), dtype=np.float64)
    for lo in range(0, len(p), int(chunk_size)):
        q = p[lo:lo + int(chunk_size)]
        qd = _dot3(q, d)
        qa = _dot3(q, a)
        qq = (q * q).sum(axis=1)
        t = np.clip((qd - ad[None, :]) / len_sq[None, :], 0.0, 1.0)
        # |q - (a + t d)|^2 expanded so no (C, S, 3) intermediate is built.
        dist_sq = (qq[:, None] - 2.0 * (qa + t * qd) + aa[None, :]
                   + t * (2.0 * ad[None, :] + t * len_sq[None, :]))
        np.maximum(dist_sq, 0.0, out=dist_sq)
        signed[lo:lo + int(chunk_size)] = (
            np.sqrt(dist_sq) - (r0[None, :] + t * dr[None, :])).min(axis=1)
    return signed


def vessel_blend_weight(signed_mm, antialias_mm):
    """Vessel mix weight over the R23 antialias band (1 inside, 0 outside).

    Matches the R23 LUT construction exactly (c1_r23 ``build_lab_lut``):
    ``normalized = clip((s + h) / 2h, 0, 1)``, cubic smoothstep, weight =
    ``1 - smoothstep`` -- so w = 1 at s <= -h, 0.5 on the boundary s = 0 and
    0 at s >= +h.
    """
    h = float(antialias_mm)
    if not h > 0.0:
        raise ValueError(f"antialias half-width {antialias_mm} must be > 0")
    normalized = np.clip(
        (np.asarray(signed_mm, dtype=np.float64) + h) / (2.0 * h), 0.0, 1.0)
    return 1.0 - normalized * normalized * (3.0 - 2.0 * normalized)


def _composite_vessel_layer(texture, covered, vertices, source_faces,
                            uv_to_source, uv_faces, face_index, bary, vessel):
    """Mix the seeded vessel layer over the covered texels; returns stats.

    Mutates ``texture`` in place (only texels with a positive blend weight
    are rewritten, so the tissue bytes outside the band stay bit-identical
    to the vessel-free bake). Must run BEFORE the gutter dilation so the
    gutter replicates composited colours.
    """
    from .c1_r21_procedural_vessels import compute_equal_terminal_diameters

    if source_faces is None:
        raise ValueError(
            "source_faces (canonical mesh triangles) are required to grow "
            "the vessel tree")
    ratio = float(vessel["ratio"])
    antialias_mm = float(vessel["antialias_mm"])
    rgb255 = np.asarray(vessel["rgb255"], dtype=np.float64)
    if rgb255.shape != (3,) or np.any(rgb255 < 0) or np.any(rgb255 > 255):
        raise ValueError("vessel rgb255 must be three byte values")

    vertices = np.asarray(vertices, dtype=np.float64)
    tree = build_vessel_tree(vertices, np.asarray(source_faces),
                             int(vessel["tree_seed"]))
    root_diameter = ratio * tree.surface_extent
    # R23 radius derivation verbatim (build_signed_field_bundle per scale).
    node_radii = compute_equal_terminal_diameters(
        tree, float(root_diameter)) / 2.0
    seg_start, seg_end, seg_r0, seg_r1 = vessel_polyline_segments(
        vertices, tree, node_radii)

    # RAW-frame surface points: the vessel field lives in millimetres, not
    # in the R19-normalized frame the R25 tissue field samples.
    points = surface_points_for_texels(
        vertices, uv_to_source, uv_faces, face_index, bary)
    signed = evaluate_vessel_signed_field(
        points, seg_start, seg_end, seg_r0, seg_r1)
    weight = vessel_blend_weight(signed, antialias_mm)

    band = weight > 0.0
    if band.any():
        tissue = texture[covered].astype(np.float64)
        w = weight[band][:, None]
        mixed = tissue[band] * (1.0 - w) + rgb255[None, :] * w
        tissue[band] = np.clip(np.floor(mixed + 0.5), 0.0, 255.0)
        texture[covered] = tissue.astype(np.uint8)

    segment_lengths = np.linalg.norm(seg_end - seg_start, axis=1)
    return {
        "tree_seed": int(vessel["tree_seed"]),
        "node_count": int(len(tree.node_vertex_indices)),
        "segment_count": int(len(seg_start)),
        "total_length_mm": float(segment_lengths.sum()),
        "surface_extent_mm": float(tree.surface_extent),
        "root_diameter_mm": float(root_diameter),
        "ratio": ratio,
        "antialias_mm": antialias_mm,
        "stop_reason": tree.stop_reason,
        "iteration_count": int(tree.iteration_count),
        "covered_texels": int(covered.sum()),
        "vessel_texels": int((weight > 0.5).sum()),
        "vessel_texel_fraction": float((weight > 0.5).mean()),
        "band_texels": int(band.sum()),
        "evaluation": "per-texel-exact-tapered-segment",
    }


def _shifted(array, dy, dx):
    """Same-shape copy where [y, x] holds array[y - dy, x - dx] (zero edges)."""
    out = np.zeros_like(array)
    h, w = array.shape[:2]
    dst_y = slice(max(dy, 0), h + min(dy, 0))
    src_y = slice(max(-dy, 0), h + min(-dy, 0))
    dst_x = slice(max(dx, 0), w + min(dx, 0))
    src_x = slice(max(-dx, 0), w + min(-dx, 0))
    out[dst_y, dst_x] = array[src_y, src_x]
    return out


def gutter_fill(texture, covered, gutter_px):
    """Dilate covered texel colours ``gutter_px`` steps into uncovered texels.

    Each pass copies, for every still-uncovered texel with at least one
    coloured 8-neighbour, the first such neighbour's colour in the fixed
    ``_GUTTER_NEIGHBOR_ORDER``. Returns ``(texture, mask)`` where ``mask``
    marks covered-or-gutter texels; the input texture is not modified.
    """
    tex = texture.copy()
    mask = covered.copy()
    for _ in range(int(gutter_px)):
        filled = np.zeros_like(mask)
        new_tex = tex.copy()
        for dy, dx in _GUTTER_NEIGHBOR_ORDER:
            neighbor_has = _shifted(mask, dy, dx)
            target = neighbor_has & ~mask & ~filled
            if target.any():
                new_tex[target] = _shifted(tex, dy, dx)[target]
                filled |= target
        if not filled.any():
            break
        tex = new_tex
        mask = mask | filled
    return tex, mask


def bake_field_texture(vertices, uv_vertices, uv_faces, uv_to_source, variant,
                       base_rgb01, amplitude, size=1024, gutter_px=4,
                       fine_wavelength=0.08, vessel=None, source_faces=None):
    """Bake one deterministic (size, size, 3) uint8 texture.

    ``vertices`` is the canonical first-frame geometry (one row per SOURCE
    vertex); texel colours come from the R25 field family evaluated at the
    barycentric surface points after the frozen R19 bbox normalization.
    ``amplitude`` 0 short-circuits to a flat base-colour texture (exactly
    what the colour formula yields at zero amplitude). Uncovered texels
    beyond the gutter carry the base colour as a neutral deterministic fill.

    ``vessel`` (v3; None keeps the v2 contract and return type) is a mapping
    with keys ``tree_seed`` / ``ratio`` / ``antialias_mm`` / ``rgb255``:
    the seeded R23 vessel layer is composited over the tissue texels (mix
    weight from the antialias smoothstep band, independent of ``amplitude``)
    BEFORE the gutter dilation, and the return value becomes the pair
    ``(texture, vessel_stats)``. ``source_faces`` (the canonical mesh
    triangles) are required with ``vessel`` to grow the surface tree.
    """
    base01 = np.clip(np.asarray(base_rgb01, dtype=np.float64), 0.0, 1.0)
    if base01.shape != (3,):
        raise ValueError("base_rgb01 must be three channel values")
    if not float(amplitude) >= 0.0:
        raise ValueError(f"amplitude {amplitude} must be >= 0")
    base255 = tuple(int(v) for v in np.floor(base01 * 255.0 + 0.5))

    face_index, bary = rasterize_uv_charts(uv_vertices, uv_faces, size)
    covered = face_index >= 0
    if not covered.any():
        raise ValueError("UV charts cover no texel at this texture size")

    texture = np.full((int(size), int(size), 3),
                      np.asarray(base255, dtype=np.uint8), dtype=np.uint8)
    if float(amplitude) > 0.0:
        normalized = r25.normalize_canonical_coordinates(
            np.asarray(vertices, dtype=np.float64))
        points = surface_points_for_texels(
            normalized, uv_to_source, uv_faces, face_index, bary)
        field = variant_field_with_fine(variant, points, fine_wavelength)
        texture[covered] = r25.apply_colour_field(
            base255, field, amplitude=float(amplitude))
    vessel_stats = None
    if vessel is not None:
        vessel_stats = _composite_vessel_layer(
            texture, covered, vertices, source_faces, uv_to_source, uv_faces,
            face_index, bary, vessel)
    texture, _mask = gutter_fill(texture, covered, gutter_px)
    if vessel is not None:
        return texture, vessel_stats
    return texture
