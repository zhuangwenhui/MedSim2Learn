"""Headless fixed-camera sequence rendering (PLY -> PNG)."""

import os

import numpy as np
import open3d as o3d


def render_fixed_camera_sequence(
    ply_dir,
    camera_json_path,
    out_png_dir,
    size=None,
    background=(1.0, 1.0, 1.0),
    light_on=True,
):
    """Render one PNG per PLY in `ply_dir` with the SINGLE fixed camera.

    Keeps one offscreen window for the whole sequence and re-applies the same
    fixed extrinsic every frame, so the camera stays a stationary laparoscope
    and only the surface deforms. The camera is loaded verbatim from
    `camera_json_path`; the bounding box is reset ONLY on the first frame to
    seed the visualizer's z-near/z-far clip range (without it the offscreen
    frame is blank), and the fixed intrinsic/extrinsic are merged onto the
    visualizer's own baseline camera object then applied with
    allow_arbitrary=True (passing a disk-loaded PinholeCameraParameters
    straight into convert_from yields a blank frame even when bit-identical).
    PNG stem == PLY stem == SampleID for downstream pairing. Returns the
    number of PNGs written.
    """
    os.makedirs(out_png_dir, exist_ok=True)
    cam = o3d.io.read_pinhole_camera_parameters(camera_json_path)
    w = cam.intrinsic.width if size is None else size
    h = cam.intrinsic.height if size is None else size

    ply_files = sorted(
        f for f in os.listdir(ply_dir) if f.lower().endswith(".ply")
    )
    if not ply_files:
        raise ValueError(f"no PLY files in {ply_dir}")

    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=w, height=h)
    opt = vis.get_render_option()
    opt.background_color = np.array(list(background))
    opt.light_on = light_on
    opt.mesh_show_back_face = True

    ctr = vis.get_view_control()
    n_ok = 0
    for i, fname in enumerate(ply_files):
        mesh = o3d.io.read_triangle_mesh(os.path.join(ply_dir, fname))
        mesh.compute_vertex_normals()
        # Reset the bounding box ONLY on the first frame: this seeds the
        # visualizer's internal z-near/z-far clip range from a real geometry
        # (without it the offscreen frame is blank). For every later frame
        # reset_bounding_box=False so the geometry never re-centers the
        # camera. The fixed extrinsic is re-applied identically each frame
        # regardless, so the camera stays a stationary laparoscope and only
        # the surface deforms; the one-time clip seed does not move the view.
        vis.add_geometry(mesh, reset_bounding_box=(i == 0))
        # Merge our intrinsic/extrinsic onto the visualizer's own baseline
        # camera object. Passing a disk-loaded PinholeCameraParameters
        # straight into convert_from yields a blank offscreen frame even when
        # the matrices are bit-identical; mutating the baseline object is
        # what actually applies the view.
        baseline = ctr.convert_to_pinhole_camera_parameters()
        baseline.intrinsic = cam.intrinsic
        baseline.extrinsic = cam.extrinsic
        ctr.convert_from_pinhole_camera_parameters(
            baseline, allow_arbitrary=True
        )
        vis.poll_events()
        vis.update_renderer()
        buf = np.asarray(vis.capture_screen_float_buffer(do_render=True))
        arr = (np.clip(buf, 0, 1) * 255).astype(np.uint8)
        stem = os.path.splitext(fname)[0]
        out_png = os.path.join(out_png_dir, stem + ".png")
        o3d.io.write_image(out_png, o3d.geometry.Image(arr))
        vis.remove_geometry(mesh, reset_bounding_box=False)
        n_ok += 1
    vis.destroy_window()
    return n_ok
