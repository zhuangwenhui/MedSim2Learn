"""Production-convention render of a textured kidney obj (visual gate).

Mirrors the dpost sequence renderer's conventions (legacy Open3D
Visualizer, light_on=True, Phong, screen float-buffer capture) so the
gate judges the texture under the SAME shading pipeline the litmus data
would be rendered with. The 0.19 legacy visualizer does not render obj
textures, so the atlas is BAKED to vertex colours on a shared-vertex
midpoint subdivision (x4, ~513k verts) -- which is also the viable
production path for textured sequence renders (deterministic, reuses
the vertex-colour pipeline the C1 appearance line already exercises).
Camera is a matched look-at at ~0.85 organ fraction (V1 framing target
proposal), not the frozen per-sequence production profiles -- those
enter at litmus-render time.

Usage: python render_gate.py <obj_path> <out_dir> [tag]
"""
import os
import sys

import numpy as np
import open3d as o3d
from PIL import Image

RES = 800
VIEWS = ((1.0, 0.35, 0.55), (-0.8, 0.3, 0.75), (0.2, 0.45, -1.0),
         (-1.0, 0.4, -0.5))
ZOOM = 0.39  # tuned toward ~0.85 organ fraction at 800px
SUBDIV = 4


def load_obj_arrays(path):
    verts, uvs, faces, face_uvs = [], [], [], []
    with open(path) as fh:
        for ln in fh:
            p = ln.split()
            if not p:
                continue
            if p[0] == "v":
                verts.append([float(x) for x in p[1:4]])
            elif p[0] == "vt":
                uvs.append([float(x) for x in p[1:3]])
            elif p[0] == "f":
                vi, ti = zip(*(tok.split("/")[:2] for tok in p[1:4]))
                faces.append([int(x) - 1 for x in vi])
                face_uvs.append([int(x) - 1 for x in ti])
    verts = np.asarray(verts, np.float64)
    uvs = np.asarray(uvs, np.float64)
    faces = np.asarray(faces, np.int64)
    uv_corner = uvs[np.asarray(face_uvs, np.int64)]
    return verts, faces, uv_corner


def smooth_vertex_normals(verts, faces):
    """Area-weighted per-vertex normals of the coarse mesh."""
    v0, v1, v2 = (verts[faces[:, k]] for k in range(3))
    fn = np.cross(v1 - v0, v2 - v0)
    normals = np.zeros_like(verts)
    for k in range(3):
        np.add.at(normals, faces[:, k], fn)
    return normals / np.maximum(
        np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)


def subdivide(verts, faces, uv_corner, normals, levels):
    """Shared-vertex midpoint subdivision with per-corner (wedge) UVs.

    Normals are INTERPOLATED from the coarse mesh, not recomputed:
    midpoint subdivision keeps the piecewise-flat geometry, so normals
    recomputed on the dense mesh go face-flat and Phong shading renders
    every coarse face as a hard-edged plate.
    """
    verts = [v for v in verts]
    normals = [n for n in normals]
    for _ in range(levels):
        mid = {}

        def midpoint(a, b):
            key = (a, b) if a < b else (b, a)
            if key not in mid:
                verts.append((np.asarray(verts[a]) + verts[b]) / 2.0)
                n = np.asarray(normals[a]) + normals[b]
                normals.append(n / max(np.linalg.norm(n), 1e-12))
                mid[key] = len(verts) - 1
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
    return (np.asarray(verts, np.float64), faces, uv_corner,
            np.asarray(normals, np.float64))


def bake_vertex_colors(n_verts, faces, uv_corner, atlas):
    """Average per-corner atlas samples into per-vertex colours.

    Bilinear sampling -- nearest-texel baking produced a woven moire
    over the whole surface at ~1 vert/screen-pixel density.
    """
    h, w = atlas.shape[:2]
    px = np.clip(uv_corner[..., 0] * (w - 1), 0, w - 1 - 1e-6).ravel()
    py = np.clip((1.0 - uv_corner[..., 1]) * (h - 1), 0,
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
    np.add.at(colors, faces.ravel(), samples)
    np.add.at(counts, faces.ravel(), 1.0)
    return colors / np.maximum(counts, 1.0)[:, None]


def render_views(obj_path, out_dir, tag):
    os.makedirs(out_dir, exist_ok=True)
    v, f, uvc = load_obj_arrays(obj_path)
    atlas = np.asarray(Image.open(
        os.path.join(os.path.dirname(obj_path), "texture_atlas.png")
    ).convert("RGB"))
    n = smooth_vertex_normals(v, f)
    v, f, uvc, n = subdivide(v, f, uvc, n, SUBDIV)
    colors = bake_vertex_colors(len(v), f, uvc, atlas)
    print(f"subdivided: {len(v)} verts {len(f)} faces", flush=True)
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f))
    mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
    mesh.vertex_normals = o3d.utility.Vector3dVector(n)
    vis = o3d.visualization.Visualizer()
    vis.create_window(width=RES, height=RES, visible=False)
    vis.add_geometry(mesh)
    opt = vis.get_render_option()
    opt.background_color = np.array([1.0, 1.0, 1.0])
    opt.light_on = True
    opt.mesh_color_option = o3d.visualization.MeshColorOption.Color
    paths = []
    for k, front in enumerate(VIEWS):
        ctr = vis.get_view_control()
        ctr.set_lookat([0.0, 0.0, 0.0])
        ctr.set_front(list(front))
        ctr.set_up([0.0, 1.0, 0.0])
        ctr.set_zoom(ZOOM)
        vis.poll_events()
        vis.update_renderer()
        buf = np.asarray(vis.capture_screen_float_buffer(do_render=True))
        img = (buf * 255).astype(np.uint8)
        organ = 1.0 - (img.min(axis=2) > 250).mean()
        path = f"{out_dir}/{tag}_view{k}.png"
        Image.fromarray(img).save(path)
        paths.append(path)
        print(f"view {k}: organ fraction {organ:.3f}", flush=True)
    vis.destroy_window()
    return paths


if __name__ == "__main__":
    obj = sys.argv[1]
    out = sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else "render"
    render_views(obj, out, tag)
    print("RENDER-GATE DONE", flush=True)
