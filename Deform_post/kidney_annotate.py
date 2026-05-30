"""Kidney pose snapshot + DeformSim annotation generator.

Loads a canonical (lying-flat) PLY, renders verification snapshots, and emits a
DeformSim annotation JSON (z-threshold freeze + accessible convex-zone Poisson-disk contact centers).
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


def render_zone(mesh, freeze, zone, centers, k_ring, out_dir, size=800):
    """Color-code and render BC zones for visual verification, and write a colored PLY.
    gray = free (non-zone), light-blue = accessible zone, red = freeze,
    green = contact patches (centers + their k_ring)."""
    import copy
    mesh.compute_adjacency_list()
    adj = mesh.adjacency_list
    n = len(np.asarray(mesh.vertices))
    color = np.tile(np.array([0.62, 0.62, 0.62]), (n, 1))     # free non-zone: gray
    for i in zone:
        color[i] = [0.40, 0.70, 1.00]                          # accessible zone: light blue
    for i in freeze:
        color[i] = [0.85, 0.10, 0.10]                          # freeze: red
    for i in _bfs_within(adj, list(centers), k_ring):
        color[i] = [0.10, 0.80, 0.20]                          # contact patches: green
    m = copy.deepcopy(mesh)
    m.vertex_colors = o3d.utility.Vector3dVector(color)
    m.compute_vertex_normals()
    os.makedirs(out_dir, exist_ok=True)
    o3d.io.write_triangle_mesh(os.path.join(out_dir, "bc_zone.ply"), m)
    for name, (front, up) in {"top": ([0, 0, 1], [0, 1, 0]),
                              "side": ([0, -1, 0], [0, 0, 1]),
                              "iso": ([1, 1, 1], [0, 0, 1])}.items():
        render_geoms([m], front, up, os.path.join(out_dir, f"zone_{name}.png"), size=size)
    print(f"wrote BC-zone overlay (PLY + 3 PNG) to {out_dir}")


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


def _make_dome(nx=21, ny=21, step=0.5, amp=4.0):
    """Paraboloid cap grid z = amp*(1 - r^2/R^2) (clamped >=0 region). amp>0 convex bump,
    amp<0 concave bowl. Centered at origin in xy; returns (mesh, nx, ny)."""
    cx = (nx - 1) / 2.0
    cy = (ny - 1) / 2.0
    xs = (np.arange(nx) - cx) * step
    ys = (np.arange(ny) - cy) * step
    R = float(max(xs.max(), ys.max()))
    verts = []
    for j in range(ny):
        for i in range(nx):
            r2 = xs[i] ** 2 + ys[j] ** 2
            t = max(0.0, 1.0 - r2 / (R * R))
            verts.append([xs[i], ys[j], amp * t])
    verts = np.array(verts, float)
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


def accessible_zone(mesh, freeze_set, normal_deg=45.0, shoulder_deg=30.0,
                    sharp_max=0.15, concave_max=0.05, support_min_ratio=0.4, k_erode=2):
    """Vertices on the exposed convex top surface, eroded so a k_erode-ring patch stays inside.

    Keep i iff ALL hold (uses surface_descriptors: concavity signed convex<0/concave>0,
    sharpness = curvature magnitude >= 0):
      - up-facing:    n_z(i) >= cos(normal_deg)
      - non-concave:  concavity(i) <= concave_max            (drops the hilum, ANY orientation)
      - not a convex shoulder: NOT( n_z(i) < cos(shoulder_deg) AND sharpness(i) > sharp_max )
                               (drops the tilted+curved lateral wall; keeps a curved top bump)
      - thick enough: local_thickness(i) >= support_min_ratio * median  (skipped if <= 0)
    Then erode: drop any kept vertex within k_erode hops of an excluded vertex OR an open
    mesh boundary (no-op on a closed/watertight mesh), so its k_erode-ring lies in the kept set.
    """
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    n = len(verts)
    nz = norms[:, 2]
    cos_up = float(np.cos(np.deg2rad(normal_deg)))
    cos_sh = float(np.cos(np.deg2rad(shoulder_deg)))

    concavity, sharpness = surface_descriptors(mesh)
    keep = nz >= cos_up
    keep &= concavity <= concave_max
    keep &= ~((nz < cos_sh) & (sharpness > sharp_max))
    for i in freeze_set:
        keep[i] = False

    if support_min_ratio > 0.0 and np.any(keep):
        thick = local_thickness(mesh)
        pos = thick[thick > 0]
        med = float(np.median(pos)) if pos.size else 0.0
        keep &= thick >= support_min_ratio * med

    mesh.compute_adjacency_list()
    adj = mesh.adjacency_list
    nm = np.asarray(mesh.get_non_manifold_edges(allow_boundary_edges=False))
    boundary_verts = set(nm.reshape(-1).tolist()) if nm.size else set()
    excluded = [i for i in range(n) if not keep[i]] + list(boundary_verts)
    near_excluded = _bfs_within(adj, excluded, k_erode)
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
                    shoulder_deg=30.0, sharp_max=0.15, concave_max=0.05, support_min_ratio=0.4,
                    edge_margin_rings=None, center_min_dist=None, rng_seed=42):
    """Return (zone, centers): the accessible convex zone and Poisson-disk patch centers."""
    k_erode = k_ring if edge_margin_rings is None else edge_margin_rings
    zone = accessible_zone(mesh, freeze_set, normal_deg=normal_deg,
                           shoulder_deg=shoulder_deg, sharp_max=sharp_max, concave_max=concave_max,
                           support_min_ratio=support_min_ratio, k_erode=k_erode)
    if not zone:
        raise ValueError("accessible zone is empty; relax --zone-normal-deg / "
                         "--zone-shoulder-deg / --zone-sharp-max / --zone-concave-max / "
                         "--support-min-ratio / --zone-edge-margin-rings")
    verts = np.asarray(mesh.vertices)
    cmd = center_min_dist if center_min_dist is not None else 2.0 * k_ring * mean_edge_length(mesh)
    centers = poisson_disk_centers(verts, zone, cmd, num_centers, rng_seed)
    return zone, centers


def build_annotation(mesh, freeze_ratio, num_centers, k_ring=2, normal_deg=45.0,
                     shoulder_deg=30.0, sharp_max=0.15, concave_max=0.05, support_min_ratio=0.4,
                     edge_margin_rings=None, center_min_dist=None, rng_seed=42):
    """z-threshold freeze + accessible-convex-zone Poisson-disk contact centers.

    Each center becomes one contact {seed, k_ring}. Replaces the old FPS-over-upper-half
    multi-seed selection; DeformSim runs each contact as an independent single-contact sample.
    """
    freeze = compute_freeze(np.asarray(mesh.vertices), freeze_ratio)
    _, centers = select_contacts(mesh, set(freeze), num_centers, k_ring=k_ring,
                                 normal_deg=normal_deg, shoulder_deg=shoulder_deg,
                                 sharp_max=sharp_max, concave_max=concave_max,
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
                           normal_deg=45.0,
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
    # (a) Flat grid: all kept by criteria -> erosion drops the border-2 rings.
    g, gnx, gny = _make_grid(11, 11, 1.0)
    def gvid(i, j): return j * gnx + i
    zf = set(accessible_zone(g, set(), support_min_ratio=0.0, k_erode=2))
    assert gvid(5, 5) in zf, "flat-grid center should be kept"
    assert gvid(0, 0) not in zf and gvid(1, 1) not in zf, "flat-grid border should erode"

    # (b) Convex dome: the convex-shoulder rule drops a tilted+curved flank but keeps it
    #     when the shoulder rule is disabled (shoulder_deg >= normal_deg). Isolate via k_erode=0
    #     and concave_max large (so only the shoulder rule decides). Restrict candidates to
    #     INTERIOR vertices: the cap is an open mesh, and accessible_zone seeds erosion on the
    #     open boundary even at k_erode=0, which would otherwise drop a rim candidate for the
    #     wrong reason (boundary, not shoulder) and mask the rule under test.
    dome, _, _ = _make_dome(21, 21, 0.5, amp=4.0)
    nz = np.asarray(dome.vertex_normals)[:, 2]
    tilt = np.degrees(np.arccos(np.clip(nz, -1.0, 1.0)))
    conc, sharp = surface_descriptors(dome)
    dome.compute_adjacency_list()
    nm_b = np.asarray(dome.get_non_manifold_edges(allow_boundary_edges=False))
    bverts = set(nm_b.reshape(-1).tolist()) if nm_b.size else set()
    cand = np.where((tilt > 32.0) & (tilt < 44.0) & (conc < 0.0))[0]   # up-facing (<45) but tilted, convex
    cand = np.array([c for c in cand.tolist() if c not in bverts], dtype=int)  # interior only
    assert cand.size > 0, "dome should have a tilted convex flank band"
    v = int(cand[int(np.argmax(sharp[cand]))])
    sm = float(sharp[v]) * 0.5                                          # threshold below this flank's curvature
    z_on = set(accessible_zone(dome, set(), normal_deg=45.0, shoulder_deg=30.0, sharp_max=sm,
                               concave_max=1.0, support_min_ratio=0.0, k_erode=0))
    z_off = set(accessible_zone(dome, set(), normal_deg=45.0, shoulder_deg=90.0, sharp_max=sm,
                                concave_max=1.0, support_min_ratio=0.0, k_erode=0))
    assert v not in z_on, "convex shoulder (tilted+curved) must be excluded"
    assert v in z_off, "same vertex must be kept when the shoulder rule is disabled"

    # (c) Concave bowl: the non-concave rule drops the up-facing concave center, but keeps it
    #     when non-concave is disabled (concave_max huge). Shoulder disabled to isolate.
    bowl, bnx, bny = _make_dome(21, 21, 0.5, amp=-4.0)
    center = (bny // 2) * bnx + (bnx // 2)
    nzb = float(np.asarray(bowl.vertex_normals)[center, 2])
    cb, _ = surface_descriptors(bowl)
    assert nzb > 0.7, "bowl center should face +z (up)"
    assert cb[center] > 0.0, "bowl center should be concave"
    cm = float(cb[center]) * 0.5
    out = set(accessible_zone(bowl, set(), concave_max=cm, shoulder_deg=90.0,
                              support_min_ratio=0.0, k_erode=0))
    keep = set(accessible_zone(bowl, set(), concave_max=float(cb[center]) * 2.0, shoulder_deg=90.0,
                               support_min_ratio=0.0, k_erode=0))
    assert center not in out, "up-facing concave center must be excluded by non-concave"
    assert center in keep, "same center must be kept when non-concave is disabled"
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


def _self_test_cli():
    p = _build_parser()
    ns = p.parse_args(["--ply", "x.ply", "--num-centers", "5", "--k-ring", "3",
                       "--zone-normal-deg", "40", "--zone-shoulder-deg", "25",
                       "--zone-sharp-max", "0.2", "--zone-concave-max", "0.1",
                       "--zone-edge-margin-rings", "2", "--center-min-dist", "1.5", "--seed", "7"])
    assert ns.num_centers == 5 and ns.k_ring == 3 and ns.zone_normal_deg == 40.0
    assert ns.zone_shoulder_deg == 25.0 and ns.zone_sharp_max == 0.2 and ns.zone_concave_max == 0.1
    assert ns.center_min_dist == 1.5 and ns.seed == 7
    for removed in (["--num-seeds", "3"], ["--contact-z-floor", "0.5"],
                    ["--zone-curv-percentile", "0.8"]):
        try:
            p.parse_args(["--ply", "x.ply"] + removed)
            raise AssertionError(f"removed flag accepted: {removed}")
        except SystemExit:
            pass
    print("cli self-test PASS")


def _build_parser():
    p = argparse.ArgumentParser(
        description="Kidney pose snapshot + DeformSim annotation generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--ply", type=str, help="Input canonical (posed) PLY")
    p.add_argument("--out", type=str, default="annotation.json", help="Output annotation JSON path")
    p.add_argument("--render-dir", type=str, default="pose_snapshots", help="Directory for PNGs")
    p.add_argument("--freeze-ratio", type=float, default=0.15,
                   help="Freeze vertices with z < z_min + r*(z_max - z_min)")
    p.add_argument("--num-centers", type=int, default=30,
                   help="Target number of Poisson-disk contact centers (one sample each)")
    p.add_argument("--k-ring", type=int, default=2, help="Contact patch radius in BFS rings")
    p.add_argument("--zone-normal-deg", type=float, default=45.0,
                   help="Keep up-facing vertices with normal within this angle of +z")
    p.add_argument("--zone-shoulder-deg", type=float, default=30.0,
                   help="A vertex tilted beyond this angle from +z is a 'shoulder'; drop it "
                        "if also curved (sharpness > --zone-sharp-max), keeping curved top bumps")
    p.add_argument("--zone-sharp-max", type=float, default=0.15,
                   help="Curvature (1-ring sharpness) above which a shoulder vertex is excluded")
    p.add_argument("--zone-concave-max", type=float, default=0.05,
                   help="Max signed concavity to keep (drops concave hilum at any orientation)")
    p.add_argument("--zone-edge-margin-rings", type=int, default=None,
                   help="Erosion rings from excluded vertices (default = --k-ring)")
    p.add_argument("--center-min-dist", type=float, default=None,
                   help="Min Euclidean spacing between centers (default = 2*k_ring*mean_edge_len)")
    p.add_argument("--support-min-ratio", type=float, default=0.4,
                   help="Exclude vertices with local thickness < this*median (0 disables)")
    p.add_argument("--seed", type=int, default=42, help="RNG seed for Poisson-disk sampling")
    p.add_argument("--gate", type=float, default=None,
                   help="If set, fail when top or bottom flatness fraction < gate")
    p.add_argument("--self-test", action="store_true", help="Run internal self-tests and exit")
    return p


def main():
    args = _build_parser().parse_args()

    if args.self_test:
        _self_test()
        _self_test_descriptors()
        _self_test_zone()
        _self_test_poisson()
        _self_test_cli()
        _self_test_annotation()
        return

    if not args.ply:
        raise SystemExit("--ply is required (or use --self-test)")
    if not (0.0 <= args.freeze_ratio < 1.0):
        raise SystemExit("--freeze-ratio must be in [0, 1)")
    if args.num_centers < 1:
        raise SystemExit("--num-centers must be >= 1")
    if args.k_ring < 1:
        raise SystemExit("--k-ring must be >= 1")
    if not (0.0 < args.zone_normal_deg < 90.0):
        raise SystemExit("--zone-normal-deg must be in (0, 90)")
    if not (0.0 < args.zone_shoulder_deg < 90.0):
        raise SystemExit("--zone-shoulder-deg must be in (0, 90)")
    if args.zone_sharp_max < 0.0:
        raise SystemExit("--zone-sharp-max must be >= 0")
    if not (-1.0 <= args.zone_concave_max <= 1.0):
        raise SystemExit("--zone-concave-max must be in [-1, 1]")
    if not (0.0 <= args.support_min_ratio < 1.0):
        raise SystemExit("--support-min-ratio must be in [0, 1)")
    if args.zone_edge_margin_rings is not None and args.zone_edge_margin_rings < 0:
        raise SystemExit("--zone-edge-margin-rings must be >= 0")
    if args.center_min_dist is not None and args.center_min_dist <= 0.0:
        raise SystemExit("--center-min-dist must be > 0")

    mesh = load_mesh(args.ply)
    top, bottom = flatness_metric(mesh)
    print(f"flatness: top(+z)={top:.3f} bottom(-z)={bottom:.3f}")
    render_views(mesh, args.render_dir)
    if args.gate is not None and (top < args.gate or bottom < args.gate):
        raise SystemExit(f"pose gate failed: top={top:.3f} bottom={bottom:.3f} < {args.gate}")

    freeze = compute_freeze(np.asarray(mesh.vertices), args.freeze_ratio)
    zone, centers = select_contacts(
        mesh, set(freeze), args.num_centers, k_ring=args.k_ring,
        normal_deg=args.zone_normal_deg, shoulder_deg=args.zone_shoulder_deg,
        sharp_max=args.zone_sharp_max, concave_max=args.zone_concave_max,
        support_min_ratio=args.support_min_ratio,
        edge_margin_rings=args.zone_edge_margin_rings,
        center_min_dist=args.center_min_dist, rng_seed=args.seed)
    ann = _assemble_annotation(freeze, centers, args.k_ring)
    if not ann["contacts"] or not ann["freeze"]["vertices"]:
        raise SystemExit("annotation has empty contacts or freeze; relax the zone/freeze params")
    render_zone(mesh, freeze, zone, centers, args.k_ring, args.render_dir)
    with open(args.out, "w") as fh:
        json.dump(ann, fh, indent=4)
    print(f"wrote {args.out}: {len(ann['freeze']['vertices'])} freeze, "
          f"{len(ann['contacts'])} contacts; zone={len(zone)} vertices")


if __name__ == "__main__":
    main()
