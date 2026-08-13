"""Headless fixed-camera sequence rendering (PLY -> PNG).

Two render invariants in this module are load-bearing and fragile (regressing
either silently produces blank/black PNGs that still pair with real forces):

1. ``vis.add_geometry(mesh, reset_bounding_box=(i == 0))`` -- the bounding box
   is reset ONLY on frame 0 to seed the visualizer's z-near/z-far clip range;
   every later frame must pass ``reset_bounding_box=False`` so geometry never
   re-centers the camera.
2. The fixed intrinsic/extrinsic are merged onto the visualizer's OWN baseline
   camera object and applied with ``allow_arbitrary=True``; passing a
   disk-loaded ``PinholeCameraParameters`` straight into ``convert_from``
   yields a blank frame even when bit-identical.

The F1 blank-frame guard (pixel std must exceed ``BLANK_STD_TOL``) turns any
regression of these invariants into an immediate error instead of silent black
PNGs; the F2 per-frame isolation logs failures to ``render_errors/
error_log.csv`` and keeps going so one corrupt PLY cannot abort a sequence.
"""

import csv
import os

import numpy as np
import open3d as o3d

# F1: minimum pixel std for a frame to count as non-blank. A correct render of
# the kidney against the white background has std ~0.2-0.4; a blank/black
# frame is exactly 0.0.
BLANK_STD_TOL = 1e-4


def _assert_not_blank(buf, stem, blank_std_tol):
    """Raise on a blank captured buffer (the F1 guard); returns the pixel std."""
    std = float(buf.std())
    if blank_std_tol is not None and not std > float(blank_std_tol):
        raise AssertionError(
            f"blank render at {stem} (pixel std {std:.3g} <= "
            f"{float(blank_std_tol):g}): camera invariant regressed")
    return std


def _append_render_error(error_log_path, fname, exc):
    """Append one ``filename,error_message`` row (header on first write)."""
    os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
    is_new = not os.path.isfile(error_log_path)
    with open(error_log_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(["filename", "error_message"])
        writer.writerow([fname, f"{type(exc).__name__}: {exc}"])


def render_fixed_camera_sequence(
    ply_dir,
    camera_json_path,
    out_png_dir,
    size=None,
    background=(1.0, 1.0, 1.0),
    light_on=True,
    blank_std_tol=BLANK_STD_TOL,
    error_log_dir=None,
    appearance=None,
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
    PNG stem == PLY stem == SampleID for downstream pairing.

    Per-frame guards: a captured buffer whose pixel std does not exceed
    `blank_std_tol` raises instead of writing a black PNG (F1; None disables),
    and any per-frame failure is logged as ``filename,error_message`` to
    ``error_log.csv`` under `error_log_dir` (default: ``render_errors/`` next
    to `out_png_dir`) before continuing with the next frame (F2). A frame-0
    failure usually cascades: the clip range is never seeded, so later frames
    render blank and fail too. Raises when no frame succeeds; otherwise
    returns ``(n_ok, n_failed)``.

    `appearance` (an ``dpost.diversity.AppearancePainter``; None keeps the
    legacy byte-identical behavior) applies the C1 v2 appearance
    randomization: a drawn cavity background replaces `background`, the
    painter is primed (UV basis + one baked texture) from the sorted
    listing's FIRST PLY if the caller has not primed it already, each
    frame's mesh is rebuilt after ``compute_vertex_normals()`` onto the
    locked UV with the sequence texture (R16 ``triangle_uvs + textures``
    path; a vertex-count or topology mismatch raises into the F2
    isolation), and the per-frame photometric chain runs on the captured
    buffer after the F1 blank guard, before the PNG write. Both fragile
    camera invariants above are untouched.
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

    if error_log_dir is None:
        error_log_dir = os.path.join(
            os.path.dirname(os.path.abspath(out_png_dir)), "render_errors")
    error_log_path = os.path.join(error_log_dir, "error_log.csv")
    # The log documents THIS run only; drop any stale one from a prior run.
    if os.path.isfile(error_log_path):
        os.remove(error_log_path)

    # open3d's type stub omits .visualization (it exists at runtime).
    vis = o3d.visualization.Visualizer()  # type: ignore[attr-defined]
    vis.create_window(visible=False, width=w, height=h)
    opt = vis.get_render_option()
    opt.background_color = np.array(list(background))
    opt.light_on = light_on
    opt.mesh_show_back_face = True
    if appearance is not None:
        # C1 appearance DR: drawn cavity background. MeshColorOption.Color
        # is required for textured meshes too -- the legacy visualizer drops
        # the texture under MeshColorOption.Default (verified empirically,
        # _c1_scratch/probe_texture_behavior.py, 2026-08-10).
        opt.background_color = np.array(list(appearance.background_rgb))
        opt.mesh_color_option = o3d.visualization.MeshColorOption.Color
        if not appearance.primed:
            # The texture bakes from the sequence's canonical FIRST frame;
            # a prime failure is a sequence-level error, not a frame one.
            appearance.prime_from_ply(os.path.join(ply_dir, ply_files[0]))

    ctr = vis.get_view_control()
    n_ok = 0
    n_failed = 0
    for i, fname in enumerate(ply_files):
        added_mesh = None
        try:
            mesh = o3d.io.read_triangle_mesh(os.path.join(ply_dir, fname))
            if not mesh.has_vertices():
                raise ValueError("empty mesh (unreadable or corrupt PLY)")
            mesh.compute_vertex_normals()
            if appearance is not None:
                # Rebuild the frame onto the locked UV with the sequence's
                # baked texture (R16 triangle_uvs + textures path); a
                # vertex-count or topology mismatch raises here and the F2
                # isolation logs the frame instead of writing a
                # wrongly-textured PNG.
                mesh = appearance.textured_mesh(mesh)
            # Reset the bounding box ONLY on the first frame: this seeds the
            # visualizer's internal z-near/z-far clip range from a real geometry
            # (without it the offscreen frame is blank). For every later frame
            # reset_bounding_box=False so the geometry never re-centers the
            # camera. The fixed extrinsic is re-applied identically each frame
            # regardless, so the camera stays a stationary laparoscope and only
            # the surface deforms; the one-time clip seed does not move the view.
            vis.add_geometry(mesh, reset_bounding_box=(i == 0))
            added_mesh = mesh
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
            stem = os.path.splitext(fname)[0]
            _assert_not_blank(buf, stem, blank_std_tol)
            if appearance is not None:
                # Per-frame photometric chain, seeded by this frame's index
                # in the sorted PLY listing (after the F1 blank guard so a
                # camera regression can never hide behind the post-process).
                buf = appearance.postprocess(buf, i)
            arr = (np.clip(buf, 0, 1) * 255).astype(np.uint8)
            out_png = os.path.join(out_png_dir, stem + ".png")
            o3d.io.write_image(out_png, o3d.geometry.Image(arr))
            n_ok += 1
        except Exception as exc:  # F2: isolate the frame, keep the sequence.
            n_failed += 1
            _append_render_error(error_log_path, fname, exc)
        finally:
            # Always detach the frame's mesh so a failure cannot leak stale
            # geometry into every subsequent frame of the shared window.
            if added_mesh is not None:
                vis.remove_geometry(added_mesh, reset_bounding_box=False)
    vis.destroy_window()
    if n_ok == 0:
        raise RuntimeError(
            f"render produced 0 PNGs from {len(ply_files)} PLYs in {ply_dir} "
            f"({n_failed} failed); see {error_log_path}")
    return n_ok, n_failed


def render_preview_frame(
    ply_path,
    camera_json_path,
    out_png_path,
    size=None,
    background=(1.0, 1.0, 1.0),
    light_on=True,
    blank_std_tol=BLANK_STD_TOL,
    appearance=None,
    appearance_frame_index=0,
):
    """Render ONE deformed PLY through the fixed camera to a preview PNG (F1).

    Single-frame mirror of ``render_fixed_camera_sequence`` (same fragile
    invariants: the one frame is frame 0, so the bounding-box reset seeds the
    clip range, and the camera is merged onto the visualizer's baseline object
    with allow_arbitrary=True). Used by the ``main.py render`` confirm gate to
    show a real mid-sequence deformation before batch rendering. Raises on a
    blank frame instead of writing it; returns the captured pixel std.

    `appearance` mirrors the sequence renderer so the human gate sees the
    real randomized look; `appearance_frame_index` selects the previewed
    frame's own post-process draw (its index in the sorted PLY listing).
    The painter must already be primed (the preview shows a MID-sequence
    deformation, and the texture may only bake from the sequence's first
    frame), so an unprimed painter raises instead of baking silently from
    the wrong geometry.
    """
    cam = o3d.io.read_pinhole_camera_parameters(camera_json_path)
    w = cam.intrinsic.width if size is None else size
    h = cam.intrinsic.height if size is None else size

    mesh = o3d.io.read_triangle_mesh(ply_path)
    if not mesh.has_vertices():
        raise ValueError(f"empty mesh (unreadable or corrupt PLY): {ply_path}")
    mesh.compute_vertex_normals()
    if appearance is not None:
        appearance.require_primed()
        mesh = appearance.textured_mesh(mesh)

    # open3d's type stub omits .visualization (it exists at runtime).
    vis = o3d.visualization.Visualizer()  # type: ignore[attr-defined]
    vis.create_window(visible=False, width=w, height=h)
    try:
        opt = vis.get_render_option()
        opt.background_color = np.array(list(background))
        opt.light_on = light_on
        opt.mesh_show_back_face = True
        if appearance is not None:
            opt.background_color = np.array(list(appearance.background_rgb))
            opt.mesh_color_option = o3d.visualization.MeshColorOption.Color

        ctr = vis.get_view_control()
        # The single preview frame is frame 0: reset the bounding box to seed
        # the z-near/z-far clip range (invariant 1).
        vis.add_geometry(mesh, reset_bounding_box=True)
        # Baseline-camera merge (invariant 2).
        baseline = ctr.convert_to_pinhole_camera_parameters()
        baseline.intrinsic = cam.intrinsic
        baseline.extrinsic = cam.extrinsic
        ctr.convert_from_pinhole_camera_parameters(
            baseline, allow_arbitrary=True
        )
        vis.poll_events()
        vis.update_renderer()
        buf = np.asarray(vis.capture_screen_float_buffer(do_render=True))
        stem = os.path.splitext(os.path.basename(ply_path))[0]
        std = _assert_not_blank(buf, stem, blank_std_tol)
        if appearance is not None:
            buf = appearance.postprocess(buf, appearance_frame_index)
        arr = (np.clip(buf, 0, 1) * 255).astype(np.uint8)
        o3d.io.write_image(out_png_path, o3d.geometry.Image(arr))
        vis.remove_geometry(mesh, reset_bounding_box=False)
    finally:
        vis.destroy_window()
    return std


def interactive_render_confirmation():
    """Ask whether to proceed with the batch render after the F1 preview.

    Mirrors the legacy sim2vfp gate; returns 'y' (proceed), 'n' or 'q'
    (abort). Re-prompts on any other input.
    """
    while True:
        choice = input(
            "Proceed to batch-render this sequence? (y/n/q): "
        ).strip().lower()
        if choice in ("y", "n", "q"):
            return choice
        print("Invalid input. Enter 'y' to proceed, 'n' or 'q' to abort.")
