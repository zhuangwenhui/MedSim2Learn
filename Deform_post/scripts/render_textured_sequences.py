"""Textured sequence renderer for the T-B-G litmus production.

Renders every deformed PLY of the selected twin sequences with a
kidney texture from the T-B-G pool, through the SAME production
conventions as the white renders: legacy Open3D Visualizer, 800x800,
white background, light on, frozen per-sequence camera.json (framing
stays at the c2-baseline geometry so gap-closed numbers remain
comparable).

The legacy visualizer does not render obj textures, so each texture is
baked to vertex colours on a shared-vertex midpoint subdivision (x4,
~517k verts) of the xatlas-expanded topology (uv_mapping.npz, exported
by the same parametrize call that authored the pool). Per frame only
VERTEX POSITIONS change: fine positions are rebuilt from the deformed
coarse vertices through precomputed midpoint edge chains, and normals
are smooth coarse normals propagated through the same chains
(recomputing normals on the fine mesh renders each coarse face as a
flat plate -- diagnosed in the sample round).

Texture assignment is a fixed shifted permutation (seq index + shift
mod pool size) so appearance decorrelates from geometry/forces.
seq04 is permanently excluded by the repository owner.

Usage (pilot):
  python render_textured_sequences.py --seqs 01 --limit 40
Full batch: no --seqs/--limit.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time

import numpy as np
import open3d as o3d
from PIL import Image

DEFAULT_TWIN_ROOT = (
    "D:/MedSim2Learn/DataFlow/Deform_post/primary/twin_full")
DEFAULT_OUT_ROOT = (
    "D:/MedSim2Learn/DataFlow/Deform_post/primary/tex_full_v1")
DEFAULT_TEXTURES = "D:/MedSim2Learn-archive/tbg-texpool-v1"
DEFAULT_UV_NPZ = (
    "D:/MedSim2Learn/DataFlow/Deform_post/inputs/uv_mapping.npz")
RES = 800
SUBDIV = 4
EXCLUDED = {"04"}
ASSIGN_SHIFT = 11


def subdivide_topology(faces, uv_corner, levels):
    """Precompute midpoint edge chains, fine faces, fine corner UVs.

    Returns (chains, faces_fine, uv_corner_fine, n_verts_fine) where
    chains is a list of (ea, eb) index arrays: level L's new vertices
    are the midpoints of existing vertices ea[i], eb[i].
    """
    n_verts = int(faces.max()) + 1
    chains = []
    for _ in range(levels):
        mid = {}
        ea, eb = [], []

        def midpoint(a, b):
            nonlocal n_verts
            key = (a, b) if a < b else (b, a)
            if key not in mid:
                ea.append(key[0])
                eb.append(key[1])
                mid[key] = n_verts
                n_verts += 1
            return mid[key]

        new_faces, new_uv = [], []
        for (a, b, c), (ua, ub, uc) in zip(faces, uv_corner):
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            uab, ubc, uca = (ua + ub) / 2, (ub + uc) / 2, (uc + ua) / 2
            new_faces += [(a, ab, ca), (ab, b, bc), (ca, bc, c),
                          (ab, bc, ca)]
            new_uv += [(ua, uab, uca), (uab, ub, ubc), (uca, ubc, uc),
                       (uab, ubc, uca)]
        faces = np.asarray(new_faces, np.int64)
        uv_corner = np.asarray(new_uv, np.float64)
        chains.append((np.asarray(ea, np.int64),
                       np.asarray(eb, np.int64)))
    return chains, faces, uv_corner, n_verts


def apply_chains(coarse, chains):
    """Rebuild fine vertex attributes from coarse ones (positions or
    normals) through the midpoint chains."""
    out = coarse
    for ea, eb in chains:
        out = np.concatenate([out, (out[ea] + out[eb]) * 0.5], axis=0)
    return out


def smooth_vertex_normals(verts, faces):
    v0, v1, v2 = (verts[faces[:, k]] for k in range(3))
    fn = np.cross(v1 - v0, v2 - v0)
    normals = np.zeros_like(verts)
    for k in range(3):
        np.add.at(normals, faces[:, k], fn)
    return normals / np.maximum(
        np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)


def bake_vertex_colors(n_verts, faces_fine, uv_corner_fine, atlas):
    """Bilinear-bake atlas samples into per-vertex colours."""
    h, w = atlas.shape[:2]
    px = np.clip(uv_corner_fine[..., 0] * (w - 1), 0,
                 w - 1 - 1e-6).ravel()
    py = np.clip((1.0 - uv_corner_fine[..., 1]) * (h - 1), 0,
                 h - 1 - 1e-6).ravel()
    x0, y0 = px.astype(int), py.astype(int)
    fx, fy = (px - x0)[:, None], (py - y0)[:, None]
    a = atlas.astype(np.float64) / 255.0
    samples = (a[y0, x0] * (1 - fx) * (1 - fy)
               + a[y0, x0 + 1] * fx * (1 - fy)
               + a[y0 + 1, x0] * (1 - fx) * fy
               + a[y0 + 1, x0 + 1] * fx * fy)
    colors = np.zeros((n_verts, 3))
    counts = np.zeros(n_verts)
    np.add.at(colors, faces_fine.ravel(), samples)
    np.add.at(counts, faces_fine.ravel(), 1.0)
    return colors / np.maximum(counts, 1.0)[:, None]


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_sequence(seq, tex_name, atlas_path, ctx, args):
    twin_seq = os.path.join(args.twin_root, f"seq{seq}")
    cam_path = os.path.join(twin_seq, "camera.json")
    plys = sorted(glob.glob(os.path.join(twin_seq, "sim", "*",
                                         "deformed_*.ply")))
    if args.limit:
        plys = plys[:args.limit]
    if not plys:
        raise RuntimeError(f"seq{seq}: no deformed PLYs found")
    out_png = os.path.join(args.out_root, f"seq{seq}", "png")
    os.makedirs(out_png, exist_ok=True)

    chains, faces_fine, uvc_fine, n_fine = ctx["topology"]
    atlas = np.asarray(Image.open(atlas_path).convert("RGB"))
    colors = bake_vertex_colors(n_fine, faces_fine, uvc_fine, atlas)

    cam = o3d.io.read_pinhole_camera_parameters(cam_path)
    vis = o3d.visualization.Visualizer()
    vis.create_window(width=RES, height=RES, visible=False)
    # the mesh is added lazily on the first frame with REAL positions:
    # seeding add_geometry with zero vertices produced blank captures
    # even after update_geometry (degenerate initial bounds)
    mesh = None

    vmap, faces_coarse = ctx["vmap"], ctx["faces_coarse"]
    t0 = time.time()
    rendered = 0
    for ply in plys:
        stem = os.path.splitext(os.path.basename(ply))[0]
        dst = os.path.join(out_png, f"{stem}.png")
        if os.path.exists(dst):
            rendered += 1
            continue
        src = o3d.io.read_triangle_mesh(ply)
        coarse = np.asarray(src.vertices)[vmap]
        fine = apply_chains(coarse, chains)
        nrm = smooth_vertex_normals(coarse, faces_coarse)
        nrm_fine = apply_chains(nrm, chains)
        nrm_fine /= np.maximum(
            np.linalg.norm(nrm_fine, axis=1, keepdims=True), 1e-12)
        if mesh is None:
            mesh = o3d.geometry.TriangleMesh(
                o3d.utility.Vector3dVector(fine),
                o3d.utility.Vector3iVector(faces_fine))
            mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
            mesh.vertex_normals = o3d.utility.Vector3dVector(nrm_fine)
            vis.add_geometry(mesh)
            opt = vis.get_render_option()
            opt.background_color = np.array([1.0, 1.0, 1.0])
            opt.light_on = True
            opt.mesh_color_option = \
                o3d.visualization.MeshColorOption.Color
        else:
            mesh.vertices = o3d.utility.Vector3dVector(fine)
            mesh.vertex_normals = o3d.utility.Vector3dVector(nrm_fine)
            vis.update_geometry(mesh)
        ctr = vis.get_view_control()
        ctr.convert_from_pinhole_camera_parameters(
            cam, allow_arbitrary=True)
        vis.poll_events()
        vis.update_renderer()
        buf = np.asarray(vis.capture_screen_float_buffer(do_render=True))
        img = (buf * 255).astype(np.uint8)
        if float(img.std()) < 1.0:
            vis.destroy_window()
            raise RuntimeError(f"seq{seq}: blank frame at {stem}")
        Image.fromarray(img).save(dst)
        rendered += 1
    vis.destroy_window()
    dt = time.time() - t0
    print(f"seq{seq}: {rendered}/{len(plys)} frames tex={tex_name} "
          f"{dt:.0f}s ({dt / max(len(plys), 1):.2f}s/frame)", flush=True)
    return rendered


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--twin-root", default=DEFAULT_TWIN_ROOT)
    ap.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    ap.add_argument("--textures-dir", default=DEFAULT_TEXTURES)
    ap.add_argument("--uv-npz", default=None)
    ap.add_argument("--seqs", nargs="*", default=None,
                    help="two-digit ids; default = all except excluded")
    ap.add_argument("--limit", type=int, default=0,
                    help="pilot: render only the first N frames")
    args = ap.parse_args()

    uv_npz = args.uv_npz or DEFAULT_UV_NPZ
    data = np.load(uv_npz)
    vmap = data["vmap"]
    faces = data["faces"]
    uvs = data["uvs"].astype(np.float64)
    uv_corner = uvs[faces]
    print(f"uv mapping: {len(vmap)} verts {len(faces)} faces",
          flush=True)
    topology = subdivide_topology(faces, uv_corner, SUBDIV)
    print(f"subdivided topology: {topology[3]} verts "
          f"{len(topology[1])} faces", flush=True)
    ctx = {"topology": topology, "vmap": vmap, "faces_coarse": faces}

    seq_dirs = sorted(glob.glob(os.path.join(args.twin_root, "seq*")))
    seqs = [os.path.basename(d)[3:] for d in seq_dirs]
    seqs = [s for s in seqs if s not in EXCLUDED]
    if args.seqs:
        seqs = [s for s in seqs if s in set(args.seqs)]
    pool = sorted(glob.glob(os.path.join(args.textures_dir, "tex_k*",
                                         "texture_atlas.png")))
    if not pool:
        raise SystemExit(f"no pool textures under {args.textures_dir}")
    os.makedirs(args.out_root, exist_ok=True)
    assignment = {}
    for j, seq in enumerate(seqs):
        atlas_path = pool[(j + ASSIGN_SHIFT) % len(pool)]
        tex_name = os.path.basename(os.path.dirname(atlas_path))
        assignment[f"seq{seq}"] = {
            "texture": tex_name,
            "atlas_sha256": file_sha256(atlas_path),
        }
        render_sequence(seq, tex_name, atlas_path, ctx, args)
    manifest = {
        "uv_npz": os.path.abspath(uv_npz),
        "subdiv_levels": SUBDIV,
        "assign_shift": ASSIGN_SHIFT,
        "limit": args.limit,
        "assignment": assignment,
    }
    with open(os.path.join(args.out_root, "texture_assignment.json"),
              "w") as fh:
        json.dump(manifest, fh, indent=2)
    print("RENDER-TEXTURED DONE", flush=True)


if __name__ == "__main__":
    main()
