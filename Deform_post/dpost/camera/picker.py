"""Interactive viewpoint picking (windowed Open3D preview).

The picker opens the mesh in a normal Open3D window, pre-positioned at the
contact-centered auto camera so the user starts from a sensible default and
only fine-tunes. When the window is closed, the final view is captured and
returned as PinholeCameraParameters; callers decide whether to persist it as
a contact-frame profile (follows the contact across sequences) or an absolute
camera JSON (fixed world pose). Requires a desktop session; headless hosts
must use the auto or absolute camera modes instead.
"""

import numpy as np
import open3d as o3d


def pick_camera(mesh_path, init_cam=None, window_name="Camera picker"):
    """Open an interactive preview and return the user's final camera.

    The returned PinholeCameraParameters reflects the view at the moment the
    user closes the window. Raises RuntimeError when no GUI window can be
    created (headless session).
    """
    mesh = o3d.io.read_triangle_mesh(mesh_path)
    mesh.compute_vertex_normals()

    width = init_cam.intrinsic.width if init_cam is not None else 800
    height = init_cam.intrinsic.height if init_cam is not None else 800

    vis = o3d.visualization.Visualizer()
    if not vis.create_window(window_name=window_name, width=width, height=height):
        raise RuntimeError(
            "cannot create a GUI window (headless session?); use the auto or "
            "absolute camera modes instead")
    try:
        vis.add_geometry(mesh)
        ctr = vis.get_view_control()
        if init_cam is not None:
            # Mutate the visualizer's own baseline camera object; applying a
            # foreign PinholeCameraParameters directly does not take effect
            # (same Open3D quirk the offscreen renderer works around).
            baseline = ctr.convert_to_pinhole_camera_parameters()
            baseline.intrinsic = init_cam.intrinsic
            baseline.extrinsic = init_cam.extrinsic
            ctr.convert_from_pinhole_camera_parameters(baseline, allow_arbitrary=True)
        print("Adjust the view with the mouse; close the window to capture it.")
        vis.run()
        cam = ctr.convert_to_pinhole_camera_parameters()
        # Detach from the live visualizer before destroying the window.
        out = o3d.camera.PinholeCameraParameters()
        out.intrinsic = cam.intrinsic
        out.extrinsic = np.asarray(cam.extrinsic).copy()
        return out
    finally:
        vis.destroy_window()
