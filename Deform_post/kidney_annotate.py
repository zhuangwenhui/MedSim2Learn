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


def farthest_point_sampling(vertices, candidate_idx, num_seeds, rng_seed=42):
    """Pick num_seeds indices from candidate_idx with even spatial coverage (FPS)."""
    cand = np.asarray(list(candidate_idx), dtype=np.int64)
    if num_seeds >= len(cand):
        return cand.tolist()
    rng = np.random.default_rng(rng_seed)
    first = int(cand[rng.integers(len(cand))])
    selected = [first]
    dist = np.linalg.norm(vertices[cand] - vertices[first], axis=1)
    while len(selected) < num_seeds:
        nxt = int(cand[int(np.argmax(dist))])
        selected.append(nxt)
        d = np.linalg.norm(vertices[cand] - vertices[nxt], axis=1)
        dist = np.minimum(dist, d)
    return selected


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


def build_annotation(mesh, freeze_ratio, num_seeds, k_ring=1, contact_z_floor=0.5,
                     support_min_ratio=0.4):
    """Build the DeformSim annotation: z-threshold freeze + FPS contact seeds.

    Contact seeds are drawn only from free vertices in the upper region
    (z >= z_min + contact_z_floor*(z_max - z_min)), biasing them toward the
    accessible +z surface rather than the sides/bottom.

    Thin / poorly-supported candidates (local thickness < support_min_ratio *
    median thickness) are excluded so seeds do not land on hilum flaps and
    over-deform. Set support_min_ratio <= 0 to disable the filter.
    """
    vertices = np.asarray(mesh.vertices)
    z = vertices[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    z_range = z_max - z_min
    freeze = compute_freeze(vertices, freeze_ratio)
    freeze_set = set(freeze)
    contact_floor = z_min + contact_z_floor * z_range
    candidate_idx = [i for i in range(len(vertices))
                     if i not in freeze_set and z[i] >= contact_floor]

    if support_min_ratio > 0.0 and candidate_idx:
        thick = local_thickness(mesh)
        pos = thick[thick > 0]
        med = float(np.median(pos)) if pos.size else 0.0
        thr = support_min_ratio * med
        filtered = [i for i in candidate_idx if thick[i] >= thr]
        if filtered:
            candidate_idx = filtered
        else:
            print("WARNING: support/thickness filter emptied the candidate set "
                  f"(threshold={thr:.4g}); falling back to unfiltered upper candidates")

    seeds = farthest_point_sampling(vertices, candidate_idx, num_seeds)
    return {
        "freeze": {"vertices": [int(i) for i in freeze]},
        "contacts": [{"seed": int(s), "k_ring": int(k_ring)} for s in seeds],
    }


def _self_test_annotation():
    mesh = _make_slab()
    # Disable the support filter here: the slab is roughly uniform thickness, but
    # tiny-box raycasting can be flaky. The filter is exercised on the real kidney.
    ann = build_annotation(mesh, freeze_ratio=0.15, num_seeds=3, contact_z_floor=0.5,
                           support_min_ratio=0.0)
    fset = set(ann["freeze"]["vertices"])
    seeds = [c["seed"] for c in ann["contacts"]]
    verts = np.asarray(mesh.vertices)
    assert len(seeds) == 3 and len(set(seeds)) == 3, "seeds must be distinct"
    assert all(s not in fset for s in seeds), "seeds must be in the free set"
    assert len(fset) > 0, "freeze set should be non-empty for the slab"
    assert all(verts[s][2] > 0.0 for s in seeds), "biased seeds must be in the upper (+z) region"
    print("annotation self-test PASS:", len(fset), seeds)


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
