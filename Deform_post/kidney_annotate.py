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


def render_views(mesh, out_dir, size=800):
    """Render top / side / isometric snapshots of the (centered) mesh to PNG."""
    os.makedirs(out_dir, exist_ok=True)
    views = {
        "top":  ([0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
        "side": ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0]),
        "iso":  ([1.0, 1.0, 1.0], [0.0, 0.0, 1.0]),
    }
    for name, (front, up) in views.items():
        vis = o3d.visualization.Visualizer()
        vis.create_window(visible=False, width=size, height=size)
        vis.add_geometry(mesh)
        ctr = vis.get_view_control()
        ctr.set_lookat([0.0, 0.0, 0.0])
        ctr.set_front(front)
        ctr.set_up(up)
        ctr.set_zoom(0.7)
        vis.poll_events()
        vis.update_renderer()
        vis.capture_screen_image(os.path.join(out_dir, f"pose_{name}.png"))
        vis.destroy_window()


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


def build_annotation(mesh, freeze_ratio, num_seeds, k_ring=1):
    """Build the DeformSim annotation: z-threshold freeze + FPS contact seeds."""
    vertices = np.asarray(mesh.vertices)
    freeze = compute_freeze(vertices, freeze_ratio)
    freeze_set = set(freeze)
    free_idx = [i for i in range(len(vertices)) if i not in freeze_set]
    seeds = farthest_point_sampling(vertices, free_idx, num_seeds)
    return {
        "freeze": {"vertices": [int(i) for i in freeze]},
        "contacts": [{"seed": int(s), "k_ring": int(k_ring)} for s in seeds],
    }


def _self_test_annotation():
    mesh = _make_slab()
    ann = build_annotation(mesh, freeze_ratio=0.15, num_seeds=3)
    fset = set(ann["freeze"]["vertices"])
    seeds = [c["seed"] for c in ann["contacts"]]
    assert len(seeds) == 3 and len(set(seeds)) == 3, "seeds must be distinct"
    assert all(s not in fset for s in seeds), "seeds must be in the free set"
    assert len(fset) > 0, "freeze set should be non-empty for the slab"
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

    mesh = load_mesh(args.ply)
    top, bottom = flatness_metric(mesh)
    print(f"flatness: top(+z)={top:.3f} bottom(-z)={bottom:.3f}")
    render_views(mesh, args.render_dir)
    if args.gate is not None and (top < args.gate or bottom < args.gate):
        raise SystemExit(
            f"pose gate failed: top={top:.3f} bottom={bottom:.3f} < {args.gate}")
    ann = build_annotation(mesh, args.freeze_ratio, args.num_seeds)
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
