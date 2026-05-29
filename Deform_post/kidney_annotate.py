"""Kidney pose snapshot + DeformSim annotation generator.

Loads a canonical (lying-flat) PLY, renders verification snapshots, and emits a
DeformSim annotation JSON (z-threshold freeze + farthest-point contact seeds).
"""
import os
import json
import argparse
import numpy as np
import open3d as o3d


def load_mesh(ply_path):
    mesh = o3d.io.read_triangle_mesh(ply_path)
    mesh.compute_vertex_normals()
    mesh.compute_triangle_normals()
    return mesh


def flatness_metric(mesh, angle_deg=30.0):
    """Fraction of faces whose normal aligns with +z (top) and -z (bottom)."""
    cos_t = float(np.cos(np.deg2rad(angle_deg)))
    n = np.asarray(mesh.triangle_normals)
    if n.size == 0:
        return 0.0, 0.0
    nz = n[:, 2]
    top = float(np.mean(nz > cos_t))
    bottom = float(np.mean(nz < -cos_t))
    return top, bottom


def _look_at_extrinsic(eye, center, up):
    """World->camera 4x4 extrinsic (open3d convention: camera looks down +z,
    image y is down). Returns the matrix expected by PinholeCameraParameters."""
    eye = np.asarray(eye, float)
    center = np.asarray(center, float)
    up = np.asarray(up, float)
    f = center - eye
    f /= np.linalg.norm(f)            # forward (camera +z)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)            # right (camera +x)
    # open3d image-y points DOWN, so camera +y (down) = cross(f, s).
    u = np.cross(f, s)                # down (camera +y)
    R = np.stack([s, u, f], axis=0)   # rows = camera axes in world
    t = -R @ eye
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    return M


def _union_bbox(geoms):
    """Axis-aligned bounding box (min, max) enclosing all geometries."""
    mn = np.array([np.inf] * 3)
    mx = np.array([-np.inf] * 3)
    for g in geoms:
        b = g.get_axis_aligned_bounding_box()
        mn = np.minimum(mn, b.get_min_bound())
        mx = np.maximum(mx, b.get_max_bound())
    return mn, mx


def _intrinsic_matrix(w, h, fov_deg):
    f = (h / 2.0) / np.tan(np.deg2rad(fov_deg) / 2.0)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    K = o3d.camera.PinholeCameraIntrinsic()
    K.set_intrinsics(w, h, f, f, cx, cy)
    return K


def render_geoms(geoms, direction, up, path, size=800, fov_deg=60.0, dist_mult=2.0):
    """Render geometries from a camera placed along `direction` from the union
    bbox center, framing them via an EXPLICIT bbox-derived camera extrinsic
    (the legacy Visualizer auto-zoom / origin look-at left side/iso views blank
    when the mesh sat off-origin). Returns pixel std (0 => blank)."""
    mn, mx = _union_bbox(geoms)
    center = (mn + mx) / 2.0
    max_extent = float((mx - mn).max())
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    eye = center + d * (dist_mult * max_extent)
    extr = _look_at_extrinsic(eye, center, up)

    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=size, height=size)
    opt = vis.get_render_option()
    opt.background_color = np.array([1.0, 1.0, 1.0])
    opt.light_on = True
    opt.mesh_show_back_face = True
    for g in geoms:
        vis.add_geometry(g)

    ctr = vis.get_view_control()
    cam = ctr.convert_to_pinhole_camera_parameters()
    cam.intrinsic = _intrinsic_matrix(size, size, fov_deg)
    cam.extrinsic = extr
    ctr.convert_from_pinhole_camera_parameters(cam, allow_arbitrary=True)

    vis.poll_events()
    vis.update_renderer()
    buf = np.asarray(vis.capture_screen_float_buffer(do_render=True))
    arr = (np.clip(buf, 0, 1) * 255).astype(np.uint8)
    o3d.io.write_image(path, o3d.geometry.Image(arr))
    vis.destroy_window()
    return float(buf.std())


def render_views(mesh, out_dir, size=800):
    """Render top / side / isometric snapshots to PNG using an explicit
    bbox-derived camera so every view frames the mesh (no blank side/iso)."""
    os.makedirs(out_dir, exist_ok=True)
    views = {
        "top":  ([0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
        "side": ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0]),
        "iso":  ([1.0, 1.0, 1.0], [0.0, 0.0, 1.0]),
    }
    mesh.compute_vertex_normals()
    for name, (front, up) in views.items():
        path = os.path.join(out_dir, f"pose_{name}.png")
        std = render_geoms([mesh], front, up, path, size=size)
        print(f"  pose_{name}: std={std:.4f} -> {path}")


def _make_slab():
    """Synthetic thin axis-aligned slab (thin along z) for self-test."""
    mesh = o3d.geometry.TriangleMesh.create_box(width=8.0, height=8.0, depth=0.4)
    mesh.translate(-mesh.get_center())
    mesh.compute_triangle_normals()
    return mesh


def _make_grid(nx=11, ny=11, step=1.0):
    """Flat z=0 triangulated grid centered at origin, normals +z. Returns (mesh, nx, ny)."""
    xs = np.arange(nx) * step
    ys = np.arange(ny) * step
    verts = np.array([[xs[i], ys[j], 0.0] for j in range(ny) for i in range(nx)], float)
    verts[:, :2] -= verts[:, :2].mean(axis=0)
    def vid(i, j): return j * nx + i
    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            tris.append([a, b, c]); tris.append([a, c, d])
    m = o3d.geometry.TriangleMesh()
    m.vertices = o3d.utility.Vector3dVector(verts)
    m.triangles = o3d.utility.Vector3iVector(np.array(tris, dtype=np.int32))
    m.compute_vertex_normals()
    return m, nx, ny


def _self_test():
    # Flat slab: only the top/bottom faces align with +/-z; both positive and symmetric.
    mesh = _make_slab()
    top, bottom = flatness_metric(mesh, angle_deg=30.0)
    assert top > 0.0 and bottom > 0.0, f"flat slab faces should align with +/-z: {top},{bottom}"
    assert abs(top - bottom) < 1e-6, f"top/bottom should be symmetric: {top},{bottom}"
    # Tilt 45 deg about x: no face should align with +/-z within 30 deg.
    a = np.deg2rad(45.0)
    R = np.array([[1.0, 0.0, 0.0],
                  [0.0, np.cos(a), -np.sin(a)],
                  [0.0, np.sin(a),  np.cos(a)]])
    tilted = _make_slab()
    tilted.rotate(R, center=(0.0, 0.0, 0.0))
    tilted.compute_triangle_normals()
    tt, tb = flatness_metric(tilted, angle_deg=30.0)
    assert tt < 1e-9 and tb < 1e-9, f"tilted slab should have no +/-z-aligned faces: {tt},{tb}"
    print(f"flatness self-test PASS: flat top={top:.3f} bottom={bottom:.3f}; tilted top={tt:.3f} bottom={tb:.3f}")


def compute_freeze(vertices, ratio):
    """Freeze vertices with z < z_min + ratio*(z_max - z_min) (the resting band)."""
    z = vertices[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    thr = z_min + ratio * (z_max - z_min)
    return np.where(z < thr)[0].tolist()


def local_thickness(mesh, cone_half_angle_deg=30.0, cone_rays=6):
    """Per-vertex local thickness (Shape-Diameter-Function style): cast inward rays
    and measure distance to the opposite surface. Thin protrusions -> small thickness.

    We cast the inward normal (-vertex normal) PLUS a small cone of rays tilted
    `cone_half_angle_deg` off that axis and take the MINIMUM hit distance. A single
    inward ray alone is fooled by protrusion *tips* (a hilum flap tip's normal ray
    runs lengthwise down the flap into the body, reading falsely thick); the cone's
    off-axis rays strike the near opposite wall and correctly report the small local
    thickness. Set `cone_rays=0` to recover the plain single-ray behaviour.
    """
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    diag = float(np.linalg.norm(mesh.get_max_bound() - mesh.get_min_bound()))
    eps = 1e-4 * diag
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    origins = verts - norms * eps           # start just inside the surface
    inward = -norms

    directions = [inward]
    if cone_rays > 0:
        # per-vertex orthonormal basis perpendicular to the inward axis
        ref = np.tile(np.array([0.0, 0.0, 1.0]), (len(verts), 1))
        ref[np.abs((inward * ref).sum(1)) > 0.9] = np.array([1.0, 0.0, 0.0])
        t1 = np.cross(inward, ref)
        t1 /= np.linalg.norm(t1, axis=1, keepdims=True)
        t2 = np.cross(inward, t1)
        ha = np.deg2rad(cone_half_angle_deg)
        for k in range(cone_rays):
            phi = 2.0 * np.pi * k / cone_rays
            d = (np.cos(ha) * inward
                 + np.sin(ha) * (np.cos(phi) * t1 + np.sin(phi) * t2))
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            directions.append(d)

    best = np.full(len(verts), diag, dtype=np.float64)
    for d in directions:
        rays = np.concatenate([origins, d], axis=1).astype(np.float32)
        t = scene.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
        t[~np.isfinite(t)] = diag           # ray that escapes -> treat as 'thick'
        best = np.minimum(best, t)
    return best


def surface_descriptors(mesh):
    """Per-vertex concavity and sharpness from the 1-ring.

    concavity[i] = mean over 1-ring neighbors j of dot((v_j - v_i)/|v_j - v_i|, n_i)
      with n_i the OUTWARD vertex normal. Convex bump -> neighbors fall away from n_i
      -> negative; concave dip (hilum) -> neighbors rise toward n_i -> positive.
    sharpness[i] = mean over neighbors j of (1 - dot(n_i, n_j)); high at sharp edges.
    """
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    mesh.compute_adjacency_list()
    adj = mesh.adjacency_list
    n = len(verts)
    concavity = np.zeros(n)
    sharpness = np.zeros(n)
    for i in range(n):
        nbrs = list(adj[i])
        if not nbrs:
            continue
        d = verts[nbrs] - verts[i]
        norm_d = np.linalg.norm(d, axis=1)
        ok = norm_d > 1e-12
        if not np.any(ok):
            continue
        dirs = d[ok] / norm_d[ok, None]
        concavity[i] = float(np.mean(dirs @ norms[i]))
        sharpness[i] = float(np.mean(1.0 - (norms[nbrs] @ norms[i])))
    return concavity, sharpness


def _bfs_within(adj, sources, max_hops):
    """Set of vertices within max_hops BFS hops of any source (inclusive of sources)."""
    from collections import deque
    visited = set(int(s) for s in sources)
    frontier = deque((int(s), 0) for s in sources)
    while frontier:
        v, h = frontier.popleft()
        if h >= max_hops:
            continue
        for u in adj[v]:
            if u not in visited:
                visited.add(u)
                frontier.append((u, h + 1))
    return visited


def accessible_zone(mesh, freeze_set, normal_deg=45.0, curv_percentile=0.75,
                    support_min_ratio=0.4, k_erode=2):
    """Vertices on the exposed convex surface, eroded so a k_erode-ring patch stays inside.

    Keep i iff: i not frozen; n_z(i) >= cos(normal_deg) (up-facing); curvature-badness
    in the smoothest `curv_percentile` fraction (badness = sharpness + max(0, concavity),
    so sharp edges and concave hilum are dropped); local thickness >= support_min_ratio *
    median (skipped if support_min_ratio <= 0). Then erode: drop any kept vertex within
    k_erode hops of an excluded OR open-boundary vertex, guaranteeing its k_erode-ring
    lies in the kept interior (open-mesh boundary vertices seed the erosion because their
    ring would otherwise spill past the mesh edge).
    """
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    n = len(verts)
    cos_t = float(np.cos(np.deg2rad(normal_deg)))

    keep = norms[:, 2] >= cos_t
    for i in freeze_set:
        keep[i] = False

    concavity, sharpness = surface_descriptors(mesh)
    badness = sharpness + np.maximum(0.0, concavity)
    if np.any(keep):
        thr = float(np.quantile(badness[keep], curv_percentile))
        keep &= badness <= thr

    if support_min_ratio > 0.0 and np.any(keep):
        thick = local_thickness(mesh)
        pos = thick[thick > 0]
        med = float(np.median(pos)) if pos.size else 0.0
        keep &= thick >= support_min_ratio * med

    mesh.compute_adjacency_list()
    adj = mesh.adjacency_list
    boundary_edges = np.asarray(mesh.get_non_manifold_edges(allow_boundary_edges=False))
    boundary_verts = set(int(v) for v in boundary_edges.reshape(-1))
    sources = [i for i in range(n) if not keep[i]] + list(boundary_verts)
    near_excluded = _bfs_within(adj, sources, k_erode)
    return [i for i in range(n) if keep[i] and i not in near_excluded]


def mean_edge_length(mesh):
    """Mean undirected triangle-edge length (used to size the default Poisson spacing)."""
    v = np.asarray(mesh.vertices)
    t = np.asarray(mesh.triangles)
    if t.size == 0:
        return 0.0
    e = np.vstack([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    d = np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1)
    return float(np.mean(d)) if d.size else 0.0


def poisson_disk_centers(vertices, candidate_idx, min_dist, num_centers, rng_seed=42):
    """Greedy Poisson-disk over a discrete candidate vertex set.

    Scan candidates in a seeded random order; accept one if it is >= min_dist
    (Euclidean) from every already-accepted center; stop at num_centers or when
    candidates are exhausted. Deterministic given rng_seed. Logs a shortfall.
    """
    cand = np.asarray(list(candidate_idx), dtype=np.int64)
    if cand.size == 0:
        return []
    rng = np.random.default_rng(rng_seed)
    order = rng.permutation(cand.size)
    selected = []
    sel_pts = np.empty((0, 3))
    for k in order:
        if len(selected) >= num_centers:
            break
        p = vertices[cand[k]]
        if sel_pts.shape[0] == 0 or np.all(np.linalg.norm(sel_pts - p, axis=1) >= min_dist):
            selected.append(int(cand[k]))
            sel_pts = np.vstack([sel_pts, p])
    if len(selected) < num_centers:
        print(f"WARNING: Poisson-disk fit only {len(selected)}/{num_centers} centers "
              f"at min_dist={min_dist:.4g}; zone may be too small or min_dist too large")
    return selected


def _assemble_annotation(freeze, centers, k_ring):
    return {
        "freeze": {"vertices": [int(i) for i in freeze]},
        "contacts": [{"seed": int(c), "k_ring": int(k_ring)} for c in centers],
    }


def select_contacts(mesh, freeze_set, num_centers, k_ring=2, normal_deg=45.0,
                    curv_percentile=0.75, support_min_ratio=0.4,
                    edge_margin_rings=None, center_min_dist=None, rng_seed=42):
    """Return (zone, centers): the accessible convex zone and Poisson-disk patch centers."""
    k_erode = k_ring if edge_margin_rings is None else edge_margin_rings
    zone = accessible_zone(mesh, freeze_set, normal_deg=normal_deg,
                           curv_percentile=curv_percentile,
                           support_min_ratio=support_min_ratio, k_erode=k_erode)
    if not zone:
        raise ValueError("accessible zone is empty; relax --zone-normal-deg / "
                         "--zone-curv-percentile / --support-min-ratio / "
                         "--zone-edge-margin-rings")
    verts = np.asarray(mesh.vertices)
    cmd = center_min_dist if center_min_dist is not None else 2.0 * k_ring * mean_edge_length(mesh)
    centers = poisson_disk_centers(verts, zone, cmd, num_centers, rng_seed)
    return zone, centers


def build_annotation(mesh, freeze_ratio, num_centers, k_ring=2, normal_deg=45.0,
                     curv_percentile=0.75, support_min_ratio=0.4,
                     edge_margin_rings=None, center_min_dist=None, rng_seed=42):
    """z-threshold freeze + accessible-convex-zone Poisson-disk contact centers.

    Each center becomes one contact {seed, k_ring}. Replaces the old FPS-over-upper-half
    multi-seed selection; DeformSim runs each contact as an independent single-contact sample.
    """
    freeze = compute_freeze(np.asarray(mesh.vertices), freeze_ratio)
    _, centers = select_contacts(mesh, set(freeze), num_centers, k_ring=k_ring,
                                 normal_deg=normal_deg, curv_percentile=curv_percentile,
                                 support_min_ratio=support_min_ratio,
                                 edge_margin_rings=edge_margin_rings,
                                 center_min_dist=center_min_dist, rng_seed=rng_seed)
    return _assemble_annotation(freeze, centers, k_ring)


def _self_test_annotation():
    # Subdivided slab: thickness along z so freeze (bottom band) and an up-facing top exist.
    mesh = o3d.geometry.TriangleMesh.create_box(width=8.0, height=8.0, depth=2.0)
    mesh.translate(-mesh.get_center())
    mesh = mesh.subdivide_midpoint(number_of_iterations=3)
    mesh.compute_vertex_normals()
    ann = build_annotation(mesh, freeze_ratio=0.15, num_centers=5, k_ring=2,
                           normal_deg=45.0, curv_percentile=0.9,
                           support_min_ratio=0.0, rng_seed=3)
    fset = set(ann["freeze"]["vertices"])
    contacts = ann["contacts"]
    verts = np.asarray(mesh.vertices)
    assert len(fset) > 0, "freeze band should be non-empty"
    assert len(contacts) >= 1, "should produce at least one contact center"
    seeds = [c["seed"] for c in contacts]
    assert len(seeds) == len(set(seeds)), "centers must be distinct"
    assert all(c["k_ring"] == 2 for c in contacts), "each contact is a single k_ring=2 patch"
    assert all(s not in fset for s in seeds), "centers must not be frozen"
    assert all(verts[s][2] > 0.0 for s in seeds), "centers must be on the up-facing top"
    print("annotation self-test PASS:", len(fset), seeds)


def _self_test_descriptors():
    # Convex sphere: outward normals; neighbors fall away from the normal -> concavity < 0.
    sph = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=20)
    conc, sharp = surface_descriptors(sph)
    assert float(np.mean(conc)) < -1e-3, f"convex sphere should be concavity<0, got {np.mean(conc)}"
    assert float(np.mean(sharp)) > 0.0, "curved surface should have sharpness>0"
    # Flip winding -> inward normals -> same surface now reads concave (concavity>0).
    flip = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=20)
    flip.triangles = o3d.utility.Vector3iVector(np.asarray(flip.triangles)[:, ::-1])
    fconc, _ = surface_descriptors(flip)
    assert float(np.mean(fconc)) > 1e-3, f"flipped sphere should be concavity>0, got {np.mean(fconc)}"
    # Flat grid: near-zero concavity and sharpness.
    g, _, _ = _make_grid(11, 11, 1.0)
    gconc, gsharp = surface_descriptors(g)
    assert abs(float(np.mean(gconc))) < 1e-6 and float(np.mean(gsharp)) < 1e-6, "flat grid ~0"
    print("descriptors self-test PASS")


def _self_test_zone():
    # Flat grid, no freeze, thickness disabled: zone = interior eroded by k_erode rings.
    g, nx, ny = _make_grid(11, 11, 1.0)
    def vid(i, j): return j * nx + i
    zone = accessible_zone(g, set(), normal_deg=45.0, curv_percentile=1.0,
                           support_min_ratio=0.0, k_erode=2)
    zset = set(zone)
    assert vid(5, 5) in zset, "center of flat grid should be in zone"
    assert vid(0, 0) not in zset, "corner should be eroded out (boundary margin)"
    assert vid(1, 1) not in zset, "1-ring-from-corner should be eroded out (k_erode=2)"
    # Freeze an interior vertex -> it and its k_erode neighborhood are excluded.
    zone_fz = set(accessible_zone(g, {vid(5, 5)}, normal_deg=45.0, curv_percentile=1.0,
                                  support_min_ratio=0.0, k_erode=2))
    assert vid(5, 5) not in zone_fz and vid(6, 5) not in zone_fz, "freeze island must erode"
    # Tilt the whole grid 60 deg about x -> normals exceed 45 deg from +z -> empty zone.
    a = np.deg2rad(60.0)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    g2, _, _ = _make_grid(11, 11, 1.0)
    g2.rotate(R, center=(0, 0, 0)); g2.compute_vertex_normals()
    assert accessible_zone(g2, set(), normal_deg=45.0, curv_percentile=1.0,
                           support_min_ratio=0.0, k_erode=1) == [], "tilted grid -> empty zone"
    print("zone self-test PASS")


def _self_test_poisson():
    pts = np.zeros((100, 3)); pts[:, 0] = np.arange(100) * 1.0   # colinear, spacing 1.0
    sel = poisson_disk_centers(pts, list(range(100)), min_dist=2.5, num_centers=10, rng_seed=1)
    P = pts[sel]
    for a in range(len(sel)):
        for b in range(a + 1, len(sel)):
            assert np.linalg.norm(P[a] - P[b]) >= 2.5 - 1e-9, "centers must be >= min_dist apart"
    assert sel == poisson_disk_centers(pts, list(range(100)), 2.5, 10, rng_seed=1), "deterministic"
    assert all(0 <= s < 100 for s in sel), "selected indices must be valid candidates"
    assert len(sel) <= 10
    # mean_edge_length on a unit grid ~ 1.0 (axis edges) .. sqrt(2) (diagonals); in (0, 2).
    g, _, _ = _make_grid(6, 6, 1.0)
    mel = mean_edge_length(g)
    assert 0.0 < mel < 2.0, f"unit-grid mean edge length out of range: {mel}"
    print("poisson self-test PASS")


def main():
    p = argparse.ArgumentParser(
        description="Kidney pose snapshot + DeformSim annotation generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--ply", type=str, help="Input canonical (posed) PLY")
    p.add_argument("--out", type=str, default="annotation.json",
                   help="Output annotation JSON path")
    p.add_argument("--render-dir", type=str, default="pose_snapshots",
                   help="Directory for verification PNGs")
    p.add_argument("--freeze-ratio", type=float, default=0.15,
                   help="Freeze vertices with z < z_min + r*(z_max - z_min)")
    p.add_argument("--num-seeds", type=int, default=3,
                   help="Number of contact seeds (farthest-point sampled)")
    p.add_argument("--contact-z-floor", type=float, default=0.5,
                   help="Contact seeds only from free vertices with z >= z_min + this*(z_max-z_min) (bias toward +z)")
    p.add_argument("--support-min-ratio", type=float, default=0.4,
                   help="Exclude contact candidates whose local thickness < this * median thickness "
                        "(filters thin/poorly-supported protrusions; 0 disables)")
    p.add_argument("--gate", type=float, default=None,
                   help="If set, fail when the top or bottom flatness fraction < gate")
    p.add_argument("--self-test", action="store_true",
                   help="Run internal self-tests and exit")
    args = p.parse_args()

    if args.self_test:
        _self_test()
        _self_test_descriptors()
        _self_test_zone()
        _self_test_poisson()
        _self_test_annotation()
        return

    if not args.ply:
        p.error("--ply is required (or use --self-test)")

    if args.freeze_ratio < 0.0 or args.freeze_ratio >= 1.0:
        p.error("--freeze-ratio must be in [0, 1)")
    if args.num_seeds < 1:
        p.error("--num-seeds must be >= 1")
    if args.contact_z_floor < 0.0 or args.contact_z_floor >= 1.0:
        p.error("--contact-z-floor must be in [0, 1)")
    if args.support_min_ratio < 0.0 or args.support_min_ratio >= 1.0:
        p.error("--support-min-ratio must be in [0, 1) (0 disables the filter)")

    mesh = load_mesh(args.ply)
    top, bottom = flatness_metric(mesh)
    print(f"flatness: top(+z)={top:.3f} bottom(-z)={bottom:.3f}")
    render_views(mesh, args.render_dir)
    if args.gate is not None and (top < args.gate or bottom < args.gate):
        raise SystemExit(
            f"pose gate failed: top={top:.3f} bottom={bottom:.3f} < {args.gate}")
    ann = build_annotation(mesh, args.freeze_ratio, args.num_seeds,
                           contact_z_floor=args.contact_z_floor,
                           support_min_ratio=args.support_min_ratio)
    if not ann["contacts"] or not ann["freeze"]["vertices"]:
        raise SystemExit(
            "annotation has empty contacts or freeze; check the mesh, "
            "--freeze-ratio, and --num-seeds")
    with open(args.out, "w") as fh:
        json.dump(ann, fh, indent=4)
    print(f"wrote {args.out}: {len(ann['freeze']['vertices'])} freeze, "
          f"{len(ann['contacts'])} contacts")


if __name__ == "__main__":
    main()
