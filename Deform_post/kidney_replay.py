"""Digital-twin force-replay pipeline for the kidney FEM project.

Drives a fixed single-contact DeformSim replay from real per-frame sensor
forces and produces a vision-force dataset (rendered PNGs + serialized .pt).

Pipeline stages (CLI subcommands):

  prep      real sensor CSV -> forces_model.csv (rotated, for FORCE_LIST_CSV)
            + labels.csv (real sensor Newtons, the supervision target)
            + camera.json (fixed oblique laparoscope) + replay_meta.json
  render    deformed PLYs -> one PNG per frame with the SINGLE fixed camera
  serialize PNG dir + labels.csv -> preprocessed_batch_*.pt via DataPreprocessor

The exe call + Intel MKL setup live in run_replay.ps1 (PowerShell stays the only
MKL-aware layer); this module is pure Python and needs no MKL.

The sensor->model rotation R is derived authoritatively and reproducibly from
the mesh + contact seed: it maps a +Fx sensor push onto pressing into the
surface (-n) and lateral sensor components onto tangential shear. R preserves
magnitude, so |F_model| == |F_sensor|; the label remains the raw sensor force.

Comments/identifiers in English by project convention.
"""
import os
import csv
import json
import argparse

import numpy as np
import open3d as o3d

# Reuse the established camera helpers and headless render conventions.
from kidney_annotate import _look_at_extrinsic, _intrinsic_matrix, load_mesh

# Fixed material decision for the kidney digital twin.
DEFAULT_YOUNG_MPA = 0.03
DEFAULT_POISSON = 0.49
DEFAULT_FPS = 30.0

# Fixed laparoscope intrinsics for every replay frame.
CAM_WIDTH = 800
CAM_HEIGHT = 800
CAM_FOV_DEG = 60.0
# Side-grazing close-up standoff: tight contact-region framing (not the whole
# organ) so the contact indent breaks the top silhouette and is maximally
# perceptible across the force range (laparoscope-like).
CAM_STANDOFF_MM = 70.0
# Eye offset direction: ~70 deg from +z (the rest-surface normal), azimuth
# ~240 deg, so the camera grazes the contact region from the side and the
# dimple shows as a silhouette break rather than a faint top-surface shade.
CAM_EYE_DIR = np.array([-0.47, -0.81, 0.34], dtype=float)
# Up MUST be +z for a grazing view: with the eye dir only ~20 deg above the
# table, a +y up would be nearly parallel to the view direction and the
# camera basis would degenerate. +z keeps a stable, well-conditioned frame.
CAM_UP = np.array([0.0, 0.0, 1.0], dtype=float)


# --------------------------------------------------------------------------
# Geometry / force mapping
# --------------------------------------------------------------------------
def contact_normal(mesh, seed):
    """Return (world_coords, outward_unit_normal) at the contact seed vertex."""
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    if not (0 <= seed < len(verts)):
        raise ValueError(f"contact seed {seed} out of range [0, {len(verts)})")
    p = verts[seed].astype(float)
    n = norms[seed].astype(float)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        raise ValueError(f"degenerate normal at seed {seed}")
    return p, n / nn


def sensor_to_model_rotation(normal):
    """Fixed sensor->model rotation R (columns [press | t1 | t2]).

    press = -n maps sensor +Fx into pressing into the surface; t1/t2 span the
    tangent plane so lateral sensor components become tangential shear. R is
    right-handed and orthonormal; F_model = R @ F_sensor preserves magnitude.
    """
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    press = -n
    world_x = np.array([1.0, 0.0, 0.0])
    t1 = world_x - (world_x @ n) * n
    if np.linalg.norm(t1) < 1e-6:
        world_y = np.array([0.0, 1.0, 0.0])
        t1 = world_y - (world_y @ n) * n
    t1 = t1 / np.linalg.norm(t1)
    t2 = np.cross(press, t1)
    t2 = t2 / np.linalg.norm(t2)
    R = np.stack([press, t1, t2], axis=1)
    # Self-checks: orthonormal, proper rotation, presses along -n.
    assert np.abs(R.T @ R - np.eye(3)).max() < 1e-9, "R not orthonormal"
    assert abs(np.linalg.det(R) - 1.0) < 1e-9, "det(R) != +1"
    assert np.allclose(R @ np.array([1.0, 0.0, 0.0]), -n, atol=1e-9), "R@x != -n"
    return R


def map_forces(F_sensor, R):
    """F_model = (R @ F_sensor.T).T. Magnitude-preserving by construction."""
    F_sensor = np.asarray(F_sensor, float).reshape(-1, 3)
    return (R @ F_sensor.T).T


def sample_id(seed, frame_index):
    """SampleID matching the exe's deformed_s%04d_v%04d filename stem."""
    return f"deformed_s{int(seed):04d}_v{int(frame_index):04d}"


# --------------------------------------------------------------------------
# Real force loading
# --------------------------------------------------------------------------
def load_real_forces(real_csv):
    """Load a bare 'Fx,Fy,Fz' Newton CSV (no header, CRLF tolerated) -> (N, 3)."""
    rows = []
    with open(real_csv, "r", newline="") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            parts = s.split(",")
            if len(parts) < 3:
                raise ValueError(f"malformed force row in {real_csv}: {line!r}")
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    if not rows:
        raise ValueError(f"no force rows in {real_csv}")
    return np.asarray(rows, dtype=float)


def subsample_indices(n_total, n_keep):
    """Evenly-spaced indices across [0, n_total) (inclusive endpoints when possible)."""
    if n_keep >= n_total:
        return np.arange(n_total)
    return np.linspace(0, n_total - 1, n_keep).round().astype(int)


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
def build_camera_params(center):
    """Fixed oblique laparoscope o3d PinholeCameraParameters centered on `center`."""
    center = np.asarray(center, float)
    d = CAM_EYE_DIR / np.linalg.norm(CAM_EYE_DIR)
    eye = center + d * CAM_STANDOFF_MM
    extr = _look_at_extrinsic(eye, center, CAM_UP)
    intr = _intrinsic_matrix(CAM_WIDTH, CAM_HEIGHT, CAM_FOV_DEG)
    cam = o3d.camera.PinholeCameraParameters()
    cam.intrinsic = intr
    cam.extrinsic = extr
    return cam, eye


# --------------------------------------------------------------------------
# prep
# --------------------------------------------------------------------------
def prep(real_csv, mesh_path, annotation_path, out_dir, seed=None,
         subsample=None, young=DEFAULT_YOUNG_MPA, poisson=DEFAULT_POISSON):
    """Build forces_model.csv / labels.csv / camera.json / replay_meta.json.

    If `subsample` is given, evenly sample that many frames; SampleID v-fields
    are renumbered v0000.. in subset order so PLY/PNG stems still pair with
    labels.csv (the original frame indices are recorded in replay_meta.json).
    """
    os.makedirs(out_dir, exist_ok=True)

    with open(annotation_path, "r") as fh:
        ann = json.load(fh)
    if seed is None:
        if not ann.get("contacts"):
            raise ValueError("annotation has no contacts; pass --seed explicitly")
        seed = int(ann["contacts"][0]["seed"])

    mesh = load_mesh(mesh_path)
    p_world, n_unit = contact_normal(mesh, seed)
    R = sensor_to_model_rotation(n_unit)

    F_sensor_all = load_real_forces(real_csv)
    if subsample is not None and subsample > 0:
        idx = subsample_indices(len(F_sensor_all), subsample)
    else:
        idx = np.arange(len(F_sensor_all))
    F_sensor = F_sensor_all[idx]
    F_model = map_forces(F_sensor, R)
    n_frames = len(F_sensor)

    # forces_model.csv: bare fx,fy,fz for SIM2LEARN_PARAM_FORCE_LIST_CSV, frame order.
    forces_model_path = os.path.join(out_dir, "forces_model.csv")
    with open(forces_model_path, "w", newline="") as fh:
        w = csv.writer(fh)
        for fx, fy, fz in F_model:
            w.writerow([f"{fx:.8g}", f"{fy:.8g}", f"{fz:.8g}"])

    # labels.csv: SampleID + REAL sensor Newtons (the supervision target).
    labels_path = os.path.join(out_dir, "labels.csv")
    with open(labels_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["SampleID", "force_x", "force_y", "force_z"])
        for i, (fx, fy, fz) in enumerate(F_sensor):
            w.writerow([sample_id(seed, i), f"{fx:.8g}", f"{fy:.8g}", f"{fz:.8g}"])

    # camera.json: fixed oblique laparoscope, identical for every frame.
    cam, eye = build_camera_params(p_world)
    camera_path = os.path.join(out_dir, "camera.json")
    o3d.io.write_pinhole_camera_parameters(camera_path, cam)

    # replay_meta.json: full provenance for reproducibility.
    meta = {
        "real_csv": os.path.abspath(real_csv),
        "mesh": os.path.abspath(mesh_path),
        "annotation": os.path.abspath(annotation_path),
        "seq_id": os.path.splitext(os.path.basename(real_csv))[0],
        "seed": int(seed),
        "frame_count": int(n_frames),
        "total_frames_in_seq": int(len(F_sensor_all)),
        "subsample": int(subsample) if subsample else None,
        "original_frame_indices": [int(i) for i in idx],
        "contact_world": [float(x) for x in p_world],
        "contact_normal": [float(x) for x in n_unit],
        "R": [[float(x) for x in row] for row in R],
        "young_mpa": float(young),
        "poisson": float(poisson),
        "fps": DEFAULT_FPS,
        "camera": {
            "width": CAM_WIDTH, "height": CAM_HEIGHT, "fov_deg": CAM_FOV_DEG,
            "standoff_mm": CAM_STANDOFF_MM,
            "eye": [float(x) for x in eye],
            "center": [float(x) for x in p_world],
            "up": [float(x) for x in CAM_UP],
        },
    }
    meta_path = os.path.join(out_dir, "replay_meta.json")
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)

    print(f"prep: seq={meta['seq_id']} seed={seed} frames={n_frames}"
          f"{' (subsampled from %d)' % len(F_sensor_all) if subsample else ''}")
    print(f"  forces_model.csv -> {forces_model_path}")
    print(f"  labels.csv       -> {labels_path}")
    print(f"  camera.json      -> {camera_path}")
    print(f"  replay_meta.json -> {meta_path}")
    return meta


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def render(ply_dir, camera_path, out_png_dir, size=None):
    """Render one PNG per PLY in `ply_dir` with the SINGLE fixed camera.

    The camera is loaded verbatim from camera.json and applied with
    reset_bounding_box=False so it never auto-refits across frames; the camera
    stays a stationary laparoscope and the indentation appears as the surface
    deforming away. PNG stem == PLY stem == SampleID for downstream pairing.
    """
    os.makedirs(out_png_dir, exist_ok=True)
    cam = o3d.io.read_pinhole_camera_parameters(camera_path)
    w = cam.intrinsic.width if size is None else size
    h = cam.intrinsic.height if size is None else size

    ply_files = sorted(f for f in os.listdir(ply_dir) if f.lower().endswith(".ply"))
    if not ply_files:
        raise ValueError(f"no PLY files in {ply_dir}")

    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=w, height=h)
    opt = vis.get_render_option()
    opt.background_color = np.array([1.0, 1.0, 1.0])
    opt.light_on = True
    opt.mesh_show_back_face = True

    ctr = vis.get_view_control()
    n_ok = 0
    for i, fname in enumerate(ply_files):
        mesh = o3d.io.read_triangle_mesh(os.path.join(ply_dir, fname))
        mesh.compute_vertex_normals()
        # Reset the bounding box ONLY on the first frame: this seeds the
        # visualizer's internal z-near/z-far clip range from a real geometry
        # (without it the offscreen frame is blank). For every later frame
        # reset_bounding_box=False so the geometry never re-centers the camera.
        # The fixed extrinsic is re-applied identically each frame regardless,
        # so the camera stays a stationary laparoscope and only the surface
        # deforms; the one-time clip seed does not move the view.
        vis.add_geometry(mesh, reset_bounding_box=(i == 0))
        # Merge our intrinsic/extrinsic onto the visualizer's own baseline camera
        # object (matches kidney_annotate.render_geoms). Passing a disk-loaded
        # PinholeCameraParameters straight into convert_from yields a blank
        # offscreen frame even when the matrices are bit-identical; mutating the
        # baseline object is what actually applies the view.
        baseline = ctr.convert_to_pinhole_camera_parameters()
        baseline.intrinsic = cam.intrinsic
        baseline.extrinsic = cam.extrinsic
        ctr.convert_from_pinhole_camera_parameters(baseline, allow_arbitrary=True)
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
    print(f"render: {n_ok} PNGs -> {out_png_dir}")
    return n_ok


# --------------------------------------------------------------------------
# serialize
# --------------------------------------------------------------------------
def serialize(png_dir, labels_csv, out_data_dir, resize=None):
    """Serialize PNG dir + labels.csv to preprocessed_batch_*.pt via DataPreprocessor.

    DataPreprocessor._load_force_data() expects exactly ONE CSV in dataset_dir
    with columns SampleID,force_x,force_y,force_z. We point dataset_dir at the
    directory holding labels.csv (must be the only CSV there) and image_dir at
    png_dir, pairing PNG stem == SampleID.
    """
    from sim2vfp import DataPreprocessor

    dataset_dir = os.path.dirname(os.path.abspath(labels_csv))
    csvs = [f for f in os.listdir(dataset_dir) if f.endswith(".csv")]
    if csvs != [os.path.basename(labels_csv)]:
        raise ValueError(
            f"DataPreprocessor needs exactly one CSV in {dataset_dir}; found {csvs}. "
            f"Keep only labels.csv there (forces_model.csv belongs elsewhere)."
        )
    os.makedirs(out_data_dir, exist_ok=True)

    dp = DataPreprocessor()
    dp.set_dataset_directory(dataset_dir)
    dp.set_image_directory(png_dir)
    dp.set_output_directory(out_data_dir)
    # Non-interactive config: optional resize (WxH tuple), normalize off so the
    # serialized images stay raw /255 floats (matching DataPreprocessor default).
    dp.set_resize(bool(resize), tuple(resize) if resize else None)
    dp.set_image_normalization(False)
    dp.set_force_normalization(False)
    dp.serialize()
    res = dp.get_results()
    print(f"serialize: {res['total_samples']} samples, {res['batches']} batch(es) -> {out_data_dir}")
    return res


# --------------------------------------------------------------------------
# artifacts  (waveform PNG + force-synced MP4 + montage + rest_vs_peak)
# --------------------------------------------------------------------------
# Kidney rest thickness used for the %thickness annotation (matches the proven
# _tools scripts). Fixed organ geometry, not a per-sequence quantity.
THICKNESS_MM = 52.0


def _find_sim_ply_dir(seq_dir):
    """Return the latest DeformedSample_ComplexObject* dir under <seq_dir>/sim."""
    import glob
    cands = sorted(glob.glob(os.path.join(seq_dir, "sim", "DeformedSample_ComplexObject*")))
    if not cands:
        raise FileNotFoundError(
            f"no sim/DeformedSample_ComplexObject* dir under {seq_dir}")
    return cands[-1]


def _load_labels(labels_csv):
    """Load labels.csv -> (sample_ids list, F array (N,3), |F| array (N,)).

    labels.csv is the REAL sensor force in Newtons (the supervision target),
    in frame order; SampleID == PLY stem == PNG stem.
    """
    sids, F = [], []
    with open(labels_csv, "r", newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            sids.append(row["SampleID"])
            F.append([float(row["force_x"]), float(row["force_y"]), float(row["force_z"])])
    if not sids:
        raise ValueError(f"no rows in {labels_csv}")
    F = np.asarray(F, float)
    return sids, F, np.linalg.norm(F, axis=1)


def compute_maxu(seq_dir, mesh_path, sample_ids):
    """Per-frame max|u| (mm) = max vertex |deformed - rest| over all frames.

    Loads each deformed PLY once (in `sample_ids` order, which is frame order),
    subtracts the rest mesh vertices, and takes the max L2 displacement.
    Returns a float array (N,). Raises on vertex-count mismatch so a corrupt
    PLY set is caught rather than silently mis-paired.
    """
    rest = np.asarray(load_mesh(mesh_path).vertices, float)
    nrest = len(rest)
    ply_dir = _find_sim_ply_dir(seq_dir)
    maxu = np.empty(len(sample_ids), float)
    for k, sid in enumerate(sample_ids):
        ply = os.path.join(ply_dir, sid + ".ply")
        v = np.asarray(o3d.io.read_triangle_mesh(ply).vertices, float)
        if len(v) != nrest:
            raise ValueError(
                f"vertex count mismatch in {sid}.ply: {len(v)} != rest {nrest}")
        maxu[k] = float(np.linalg.norm(v - rest, axis=1).max())
    return maxu


def _save_maxu_csv(seq_dir, maxu):
    """Persist per-frame max|u| to <seq_dir>/maxu.csv (frame_index,max_u_mm)."""
    path = os.path.join(seq_dir, "maxu.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_index", "max_u_mm"])
        for i, mu in enumerate(maxu):
            w.writerow([i, f"{mu:.6f}"])
    return path


def _update_meta_maxu(seq_dir, maxu, fmag):
    """Fold max|u| summary stats into replay_meta.json so they survive PLY deletion.

    Adds maxu_max_mm, maxu_at_frame, maxu_pearson_vs_F. Returns the loaded meta
    dict (with seq_id/seed/young/poisson/fps for downstream labelling).
    """
    meta_path = os.path.join(seq_dir, "replay_meta.json")
    with open(meta_path, "r") as fh:
        meta = json.load(fh)
    at = int(np.argmax(maxu))
    if len(maxu) >= 2 and np.std(fmag) > 0 and np.std(maxu) > 0:
        pearson = float(np.corrcoef(fmag, maxu)[0, 1])
    else:
        pearson = float("nan")
    meta["maxu_max_mm"] = round(float(maxu[at]), 6)
    meta["maxu_at_frame"] = at
    meta["maxu_pearson_vs_F"] = None if np.isnan(pearson) else round(pearson, 6)
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def _waveform_png(seq_dir, fmag, F, maxu, meta, fps):
    """Write <seq_dir>/force_waveform.png: |F|+max|u| twin axes (top), components (bottom)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(fmag)
    t = np.arange(n) / float(fps)
    peak_i = int(np.argmax(fmag))
    seq_id = meta.get("seq_id", "?")
    seed = int(meta.get("seed", -1))
    young = meta.get("young_mpa", DEFAULT_YOUNG_MPA)
    poisson = meta.get("poisson", DEFAULT_POISSON)
    pearson = meta.get("maxu_pearson_vs_F")

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(11.0, 7.0), dpi=110)
    fig.suptitle(
        f"Twin temporal correspondence  seq {seq_id}  "
        f"N={n} frames @ {fps:g} fps  E={young:g} v={poisson:g}  "
        f"contact seed {seed}"
        + (f"  (|F| vs max|u| Pearson r={pearson:.4f})" if pearson is not None else ""),
        fontsize=10)

    # Top: |F|(t) and max|u|(t) on twin y-axes.
    l1, = ax_top.plot(t, fmag, color="tab:blue", lw=0.8, label="|F| (N)")
    ax_top.set_xlabel("time (s)")
    ax_top.set_ylabel("|F| (N)", color="tab:blue")
    ax_top.tick_params(axis="y", labelcolor="tab:blue")
    ax_top.set_xlim(t[0], t[-1])
    ax_u = ax_top.twinx()
    l2, = ax_u.plot(t, maxu, color="tab:red", lw=0.8, label="max|u| (mm)")
    ax_u.set_ylabel("max|u| (mm)", color="tab:red")
    ax_u.tick_params(axis="y", labelcolor="tab:red")
    ax_top.axvline(t[peak_i], color="k", ls="--", lw=0.7)
    ax_top.legend(handles=[l1, l2], loc="upper left", fontsize=8)
    txt = (f"peak |F| @ frame {peak_i} (t={t[peak_i]:.2f}s)\n"
           f"|F|={fmag[peak_i]:.4f} N   max|u|={maxu[peak_i]:.3f} mm "
           f"({maxu[peak_i] / THICKNESS_MM * 100:.1f}% thick)")
    ax_top.text(0.5, 0.97, txt, transform=ax_top.transAxes, fontsize=8,
                va="top", ha="center",
                bbox=dict(boxstyle="round", fc="white", ec="0.6", alpha=0.85))

    # Bottom: directional components Fx/Fy/Fz.
    ax_bot.set_title("Directional force components", fontsize=9)
    ax_bot.plot(t, F[:, 0], color="tab:red", lw=0.7, label="Fx")
    ax_bot.plot(t, F[:, 1], color="tab:green", lw=0.7, label="Fy")
    ax_bot.plot(t, F[:, 2], color="tab:orange", lw=0.7, label="Fz")
    ax_bot.set_xlabel("time (s)")
    ax_bot.set_ylabel("force component (N)")
    ax_bot.set_xlim(t[0], t[-1])
    ax_bot.legend(loc="upper left", ncol=3, fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = os.path.join(seq_dir, "force_waveform.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def _render_plot_background(fmag, F, maxu, meta, fps, plot_size):
    """Pre-render the static force plot once -> (rgb_uint8, cursor_x_per_frame, ax_data).

    The expensive matplotlib draw happens a single time; per-frame we only blit a
    vertical cursor + text, which is what makes the video writer fast.
    Returns the background RGB image (H, W, 3), an (N,) array of cursor pixel-x
    positions (one per frame), and the (left, right, top, bottom) data->pixel
    mapping needed to place the cursor.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    pw, ph = plot_size
    n = len(fmag)
    t = np.arange(n) / float(fps)
    seq_id = meta.get("seq_id", "?")
    seed = int(meta.get("seed", -1))
    young = meta.get("young_mpa", DEFAULT_YOUNG_MPA)
    poisson = meta.get("poisson", DEFAULT_POISSON)

    dpi = 100.0
    fig = plt.figure(figsize=(pw / dpi, ph / dpi), dpi=dpi)
    ax = fig.add_axes([0.10, 0.12, 0.78, 0.78])
    ax.set_title(f"seq {seq_id}  |F|(t) & max|u|(t)  E={young:g}MPa v={poisson:g} seed{seed}",
                 fontsize=9)
    l1, = ax.plot(t, fmag, color="tab:blue", lw=0.8, label="|F| (N)")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("|F| (N)", color="tab:blue")
    ax.tick_params(axis="y", labelcolor="tab:blue")
    ax.set_xlim(t[0], t[-1])
    ax_u = ax.twinx()
    l2, = ax_u.plot(t, maxu, color="tab:red", lw=0.8, label="max|u| (mm)")
    ax_u.set_ylabel("max|u| (mm)", color="tab:red")
    ax_u.tick_params(axis="y", labelcolor="tab:red")
    ax.legend(handles=[l1, l2], loc="upper right", fontsize=7)
    ax.grid(True, alpha=0.25)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    buf = np.asarray(canvas.buffer_rgba())[:, :, :3].copy()  # (H, W, 3) uint8 RGB

    # Map each frame's time to a pixel x in the rendered figure using the axes
    # transform, so the cursor lands exactly on the curve regardless of margins.
    fig_h = buf.shape[0]
    xs = np.empty(n, float)
    for i in range(n):
        px, _py = ax.transData.transform((t[i], 0.0))
        xs[i] = px
    # Axes vertical span in pixel coords (top/bottom), y-flip from mpl to image.
    (x0, y0) = ax.transAxes.transform((0, 0))
    (x1, y1) = ax.transAxes.transform((1, 1))
    cursor_top = int(round(fig_h - y1))
    cursor_bot = int(round(fig_h - y0))
    plt.close(fig)
    return buf, xs, (cursor_top, cursor_bot)


def _twin_sync_mp4(seq_dir, fmag, F, maxu, meta, fps, sample_ids):
    """Write <seq_dir>/twin_sync.mp4: side-by-side render | force-cursor plot.

    Left = the rendered PNG for the frame; right = the pre-rendered static force
    plot with a moving vertical cursor and a live text overlay. cv2 'mp4v' at
    `fps`. Returns (path, n_frames_written).
    """
    import cv2

    png_dir = os.path.join(seq_dir, "png")
    n = len(sample_ids)

    # Probe the first render to fix the panel height; force a square left panel.
    first_png = os.path.join(png_dir, sample_ids[0] + ".png")
    img0 = cv2.imread(first_png)
    if img0 is None:
        raise FileNotFoundError(f"cannot read render PNG {first_png}")
    panel = 560  # left/right panel height (and left width), matches proven layout
    plot_w = 620
    plot_size = (plot_w, panel)

    bg, cursor_x, (cur_top, cur_bot) = _render_plot_background(
        fmag, F, maxu, meta, fps, plot_size)
    # bg is RGB; cv2 wants BGR.
    bg_bgr = cv2.cvtColor(bg, cv2.COLOR_RGB2BGR)
    bg_h, bg_w = bg_bgr.shape[:2]

    total_w = panel + bg_w
    total_h = max(panel, bg_h)
    out_path = os.path.join(seq_dir, "twin_sync.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_path, fourcc, float(fps), (total_w, total_h))
    if not vw.isOpened():
        raise RuntimeError(f"cv2 VideoWriter failed to open {out_path}")

    t = np.arange(n) / float(fps)
    font = cv2.FONT_HERSHEY_SIMPLEX
    n_written = 0
    try:
        for i, sid in enumerate(sample_ids):
            frame = np.zeros((total_h, total_w, 3), np.uint8)
            # Left: render, resized to the square panel.
            render = cv2.imread(os.path.join(png_dir, sid + ".png"))
            if render is None:
                # Skip a missing render rather than abort the whole video.
                continue
            render = cv2.resize(render, (panel, panel))
            frame[0:panel, 0:panel] = render
            # Right: static plot background + moving cursor (blit only).
            plot = bg_bgr.copy()
            cx = int(round(cursor_x[i]))
            cx = max(0, min(bg_w - 1, cx))
            cv2.line(plot, (cx, cur_top), (cx, cur_bot), (0, 0, 0), 1)
            frame[0:bg_h, panel:panel + bg_w] = plot
            # Live text overlay (top-left of the plot panel).
            fx, fy, fz = F[i]
            lines = [
                f"Frame {i:5d}/{n}",
                f"t   = {t[i]:7.3f} s",
                f"Fx  = {fx:+.4f}",
                f"Fy  = {fy:+.4f}",
                f"Fz  = {fz:+.4f}",
                f"|F| = {fmag[i]:.4f} N",
                f"max|u|= {maxu[i]:.3f} mm",
            ]
            ty = 20
            for ln in lines:
                cv2.putText(frame, ln, (panel + 8, ty), font, 0.42,
                            (0, 0, 0), 1, cv2.LINE_AA)
                ty += 16
            vw.write(frame)
            n_written += 1
    finally:
        vw.release()
    return out_path, n_written


def _label_tile(png_path, lines, scale=1.0):
    """Open a render PNG and burn yellow-on-black label lines (PIL)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(png_path).convert("RGB")
    d = ImageDraw.Draw(im)
    fs = int(26 * scale)
    try:
        font = ImageFont.truetype("arial.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    y = 6
    for ln in lines:
        d.rectangle([4, y, 4 + int(0.55 * fs) * len(ln), y + fs + 6], fill=(0, 0, 0))
        d.text((8, y + 2), ln, fill=(255, 255, 0), font=font)
        y += fs + 10
    return im


def _montage(imgs, cols, pad=6):
    """Lay out PIL images in a grid on a white canvas."""
    from PIL import Image
    cw = max(i.width for i in imgs)
    ch = max(i.height for i in imgs)
    rows = (len(imgs) + cols - 1) // cols
    cv = Image.new("RGB", (cols * cw + (cols + 1) * pad, rows * ch + (rows + 1) * pad),
                   (255, 255, 255))
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        cv.paste(im, (pad + c * (cw + pad), pad + r * (ch + pad)))
    return cv


def _montage_pngs(seq_dir, fmag, maxu, sample_ids):
    """Write montage.png (8 frames spanning |F|) and rest_vs_peak.png."""
    png_dir = os.path.join(seq_dir, "png")
    order = np.argsort(fmag)  # ascending |F|
    n = len(order)

    def tile(idx, extra=None):
        sid = sample_ids[idx]
        lines = [f"|F|={fmag[idx]:.2f} N",
                 f"max|u|={maxu[idx]:.2f} mm ({maxu[idx] / THICKNESS_MM * 100:.1f}%)"]
        if extra:
            lines = [extra] + lines
        return _label_tile(os.path.join(png_dir, sid + ".png"), lines)

    pick = np.linspace(0, n - 1, 8).round().astype(int)
    mont = _montage([tile(int(order[k])) for k in pick], cols=4)
    montage_path = os.path.join(seq_dir, "montage.png")
    mont.save(montage_path)

    rest_idx = int(order[0])
    peak_idx = int(order[-1])
    rvp = _montage([tile(rest_idx, extra="REST (min |F|)"),
                    tile(peak_idx, extra="PEAK (max |F|)")], cols=2, pad=10)
    rvp_path = os.path.join(seq_dir, "rest_vs_peak.png")
    rvp.save(rvp_path)
    return montage_path, rvp_path


def artifacts(seq_dir, mesh_path, fps=DEFAULT_FPS, seq_id=None):
    """Produce all per-sequence visual artifacts from a completed replay dir.

    Reads <seq_dir>/labels.csv + png/ + sim/DeformedSample_*/ and writes:
      maxu.csv, force_waveform.png, twin_sync.mp4, montage.png, rest_vs_peak.png.
    Also folds max|u| summary stats into replay_meta.json so they survive PLY
    deletion. max|u| is computed once and reused across every artifact.
    """
    labels_csv = os.path.join(seq_dir, "labels.csv")
    sample_ids, F, fmag = _load_labels(labels_csv)

    # Compute per-frame max|u| ONCE (loads each deformed PLY a single time).
    maxu = compute_maxu(seq_dir, mesh_path, sample_ids)
    maxu_csv = _save_maxu_csv(seq_dir, maxu)
    meta = _update_meta_maxu(seq_dir, maxu, fmag)
    if seq_id is not None:
        meta = dict(meta)
        meta["seq_id"] = seq_id

    wf = _waveform_png(seq_dir, fmag, F, maxu, meta, fps)
    mp4, n_vid = _twin_sync_mp4(seq_dir, fmag, F, maxu, meta, fps, sample_ids)
    montage_path, rvp_path = _montage_pngs(seq_dir, fmag, maxu, sample_ids)

    at = int(np.argmax(maxu))
    print(f"artifacts: seq={meta.get('seq_id')} frames={len(sample_ids)} fps={fps:g}")
    print(f"  maxu max = {maxu[at]:.3f} mm @ frame {at} "
          f"({maxu[at] / THICKNESS_MM * 100:.1f}% thickness)  -> {maxu_csv}")
    print(f"  force_waveform.png -> {wf}")
    print(f"  twin_sync.mp4 ({n_vid} frames) -> {mp4}")
    print(f"  montage.png        -> {montage_path}")
    print(f"  rest_vs_peak.png   -> {rvp_path}")
    return {
        "frames": len(sample_ids),
        "maxu_max_mm": float(maxu[at]),
        "maxu_at_frame": at,
        "video_frames": n_vid,
        "waveform": wf,
        "video": mp4,
        "montage": montage_path,
        "rest_vs_peak": rvp_path,
        "maxu_csv": maxu_csv,
    }


# --------------------------------------------------------------------------
# Self-tests
# --------------------------------------------------------------------------
def _self_test():
    failures = 0

    def check(name, cond):
        nonlocal failures
        if cond:
            print(f"PASS: {name}")
        else:
            print(f"FAIL: {name}")
            failures += 1

    # (1) R orthonormal, det=+1, R@(1,0,0) ~= -n for a synthetic normal.
    n = np.array([0.2, -0.3, 0.93])
    n = n / np.linalg.norm(n)
    R = sensor_to_model_rotation(n)
    check("R orthonormal", np.abs(R.T @ R - np.eye(3)).max() < 1e-9)
    check("det(R) == +1", abs(np.linalg.det(R) - 1.0) < 1e-9)
    check("R@(1,0,0) ~= -n", np.allclose(R @ np.array([1.0, 0.0, 0.0]), -n, atol=1e-9))

    # Degenerate +z normal must fall back cleanly (t1 not collinear with n).
    Rz = sensor_to_model_rotation(np.array([0.0, 0.0, 1.0]))
    check("R(+z) orthonormal (fallback)", np.abs(Rz.T @ Rz - np.eye(3)).max() < 1e-9)
    check("R(+z) det == +1 (fallback)", abs(np.linalg.det(Rz) - 1.0) < 1e-9)

    # (2) Force map preserves magnitude.
    rng = np.random.default_rng(0)
    F = rng.normal(size=(50, 3))
    Fm = map_forces(F, R)
    check("|F_model| == |F_sensor|",
          np.allclose(np.linalg.norm(Fm, axis=1), np.linalg.norm(F, axis=1), atol=1e-9))

    # (3) sample_id formatting round-trips.
    check("sample_id format", sample_id(521, 7) == "deformed_s0521_v0007")
    check("sample_id format hi", sample_id(521, 29) == "deformed_s0521_v0029")

    # (3b) --resize parsing: WxH, single int, None, and validation.
    check("parse_resize None", parse_resize(None) is None)
    check("parse_resize int", parse_resize("224") == (224, 224))
    check("parse_resize WxH", parse_resize("320x240") == (320, 240))
    check("parse_resize WxH spaces", parse_resize(" 224X224 ") == (224, 224))
    bad_resize = False
    try:
        parse_resize("0")
    except ValueError:
        bad_resize = True
    check("parse_resize rejects 0", bad_resize)
    bad_resize2 = False
    try:
        parse_resize("1x2x3")
    except ValueError:
        bad_resize2 = True
    check("parse_resize rejects 1x2x3", bad_resize2)

    # (4) labels.csv has real sensor force, forces_model.csv has rotated force,
    #     row counts equal frame count.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        real = os.path.join(td, "synthetic.csv")
        Fr = rng.normal(size=(12, 3))
        with open(real, "w", newline="") as fh:
            for r in Fr:
                fh.write(f"{r[0]},{r[1]},{r[2]}\n")
        # Minimal synthetic mesh + annotation so prep runs without the real assets.
        sph = o3d.geometry.TriangleMesh.create_sphere(radius=10.0, resolution=10)
        sph.compute_vertex_normals()
        mp = os.path.join(td, "m.ply")
        o3d.io.write_triangle_mesh(mp, sph)
        ap = os.path.join(td, "a.json")
        with open(ap, "w") as fh:
            json.dump({"freeze": {"vertices": []}, "contacts": [{"seed": 0, "k_ring": 2}]}, fh)
        meta = prep(real, mp, ap, td, seed=0)
        check("frame_count == rows", meta["frame_count"] == 12)

        fm = load_real_forces(os.path.join(td, "forces_model.csv"))
        check("forces_model rowcount", len(fm) == 12)
        # forces_model should equal R @ real (rotated), NOT the raw sensor force.
        Rseed = np.array(meta["R"])
        check("forces_model == R@real", np.allclose(fm, map_forces(Fr, Rseed), atol=1e-5))
        check("forces_model != real (rotated)", not np.allclose(fm, Fr, atol=1e-3))

        # labels.csv holds the REAL sensor force, keyed by SampleID.
        lab = {}
        with open(os.path.join(td, "labels.csv")) as fh:
            rd = csv.DictReader(fh)
            for row in rd:
                lab[row["SampleID"]] = np.array(
                    [float(row["force_x"]), float(row["force_y"]), float(row["force_z"])])
        check("labels rowcount", len(lab) == 12)
        sid = sample_id(0, 5)
        check("labels SampleID present", sid in lab)
        check("labels == real sensor force", np.allclose(lab[sid], Fr[5], atol=1e-5))
        check("labels != rotated force", not np.allclose(lab[sid], fm[5], atol=1e-3))

    # (5) artifacts helpers: max|u| computed from a synthetic deformed PLY set,
    #     persisted to maxu.csv + replay_meta.json, and the waveform/montage
    #     plotting paths exercised on a tiny synthetic sequence.
    with tempfile.TemporaryDirectory() as td:
        seq = os.path.join(td, "seqXX")
        png_dir = os.path.join(seq, "png")
        sim_dir = os.path.join(seq, "sim", "DeformedSample_ComplexObject_test")
        os.makedirs(png_dir)
        os.makedirs(sim_dir)
        # Rest mesh (the artifacts code subtracts these vertices).
        rest = o3d.geometry.TriangleMesh.create_sphere(radius=10.0, resolution=8)
        rest.compute_vertex_normals()
        rest_ply = os.path.join(seq, "rest.ply")
        o3d.io.write_triangle_mesh(rest_ply, rest)
        rest_v = np.asarray(rest.vertices)

        # 5 frames; known max|u| = frame_index in +z so argmax is the last frame.
        nfr = 5
        seed = 7
        sids = [sample_id(seed, i) for i in range(nfr)]
        for i, sid in enumerate(sids):
            dm = o3d.geometry.TriangleMesh(rest)
            dv = rest_v.copy()
            dv[:, 2] += float(i)  # uniform +z shift => max|u| == i
            dm.vertices = o3d.utility.Vector3dVector(dv)
            o3d.io.write_triangle_mesh(os.path.join(sim_dir, sid + ".ply"), dm)
            # 1x1 white PNG stand-in so montage/video have a render to open.
            o3d.io.write_image(os.path.join(png_dir, sid + ".png"),
                               o3d.geometry.Image(np.full((8, 8, 3), 255, np.uint8)))
        # labels.csv: |F| increasing so peak == last frame too.
        with open(os.path.join(seq, "labels.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["SampleID", "force_x", "force_y", "force_z"])
            for i, sid in enumerate(sids):
                w.writerow([sid, f"{0.1 * (i + 1):.6f}", "0", "0"])
        # minimal replay_meta.json (artifacts updates it in place).
        with open(os.path.join(seq, "replay_meta.json"), "w") as fh:
            json.dump({"seq_id": "XX", "seed": seed, "young_mpa": 0.03,
                       "poisson": 0.49, "fps": 30.0}, fh)

        mu = compute_maxu(seq, rest_ply, sids)
        check("compute_maxu values", np.allclose(mu, np.arange(nfr), atol=1e-6))
        res = artifacts(seq, rest_ply, fps=30.0)
        check("artifacts maxu_at_frame == last", res["maxu_at_frame"] == nfr - 1)
        for name in ("maxu.csv", "force_waveform.png", "twin_sync.mp4",
                     "montage.png", "rest_vs_peak.png"):
            check(f"artifact written: {name}", os.path.isfile(os.path.join(seq, name)))
        # maxu.csv round-trips and replay_meta.json gained the summary fields.
        mu_rows = []
        with open(os.path.join(seq, "maxu.csv")) as fh:
            rd = csv.DictReader(fh)
            for row in rd:
                mu_rows.append(float(row["max_u_mm"]))
        check("maxu.csv rowcount", len(mu_rows) == nfr)
        meta_after = json.load(open(os.path.join(seq, "replay_meta.json")))
        check("meta has maxu_max_mm", abs(meta_after["maxu_max_mm"] - (nfr - 1)) < 1e-6)
        check("meta has maxu_at_frame", meta_after["maxu_at_frame"] == nfr - 1)
        check("meta has maxu_pearson_vs_F", "maxu_pearson_vs_F" in meta_after)

    if failures:
        print(f"\n{failures} self-test(s) FAILED")
        raise SystemExit(1)
    print("\nAll self-tests PASSED")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _build_parser():
    p = argparse.ArgumentParser(
        description="Kidney digital-twin force-replay pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--self-test", action="store_true", help="Run internal self-tests and exit")
    sub = p.add_subparsers(dest="cmd")

    pp = sub.add_parser("prep", help="Real CSV -> forces_model.csv/labels.csv/camera.json/meta")
    pp.add_argument("--real-csv", required=True)
    pp.add_argument("--mesh", required=True)
    pp.add_argument("--annotation", required=True)
    pp.add_argument("--out-dir", required=True)
    pp.add_argument("--seed", type=int, default=None, help="Contact seed (default: annotation contact[0])")
    pp.add_argument("--subsample", type=int, default=None, help="Evenly sample N frames from the sequence")
    pp.add_argument("--young", type=float, default=DEFAULT_YOUNG_MPA)
    pp.add_argument("--poisson", type=float, default=DEFAULT_POISSON)

    pr = sub.add_parser("render", help="Deformed PLYs -> PNGs with the fixed camera")
    pr.add_argument("--ply-dir", required=True)
    pr.add_argument("--camera", required=True)
    pr.add_argument("--out-png-dir", required=True)
    pr.add_argument("--size", type=int, default=None)

    ps = sub.add_parser("serialize", help="PNGs + labels.csv -> preprocessed_batch_*.pt")
    ps.add_argument("--png-dir", required=True)
    ps.add_argument("--labels", required=True)
    ps.add_argument("--out-data-dir", required=True)
    ps.add_argument("--resize", type=str, default=None,
                    help='Resize images to WxH (e.g. "224x224") or a single int '
                         'for a square (e.g. "224"); default keeps native size')

    pa = sub.add_parser("artifacts",
                        help="Replay dir -> maxu.csv + waveform/video/montage artifacts")
    pa.add_argument("--seq-dir", required=True,
                    help="Replay output dir (holds labels.csv, png/, sim/DeformedSample_*/)")
    pa.add_argument("--mesh", required=True, help="Rest mesh PLY (for max|u| vs rest)")
    pa.add_argument("--fps", type=float, default=DEFAULT_FPS)
    pa.add_argument("--seq-id", type=str, default=None,
                    help="Override the sequence id used in titles (default: meta seq_id)")

    return p


def parse_resize(spec):
    """Parse a --resize spec into a (W, H) int tuple, or None when unset.

    Accepts "WxH" (e.g. "224x224") or a single int "N" -> (N, N).
    """
    if spec is None:
        return None
    s = str(spec).strip().lower()
    if "x" in s:
        parts = s.split("x")
        if len(parts) != 2:
            raise ValueError(f"invalid --resize {spec!r}: expected WxH or an int")
        w, h = int(parts[0]), int(parts[1])
    else:
        w = h = int(s)
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid --resize {spec!r}: dimensions must be positive")
    return (w, h)


def main():
    args = _build_parser().parse_args()
    if args.self_test:
        _self_test()
        return
    if args.cmd == "prep":
        prep(args.real_csv, args.mesh, args.annotation, args.out_dir,
             seed=args.seed, subsample=args.subsample, young=args.young, poisson=args.poisson)
    elif args.cmd == "render":
        render(args.ply_dir, args.camera, args.out_png_dir, size=args.size)
    elif args.cmd == "serialize":
        serialize(args.png_dir, args.labels, args.out_data_dir,
                  resize=parse_resize(args.resize))
    elif args.cmd == "artifacts":
        artifacts(args.seq_dir, args.mesh, fps=args.fps, seq_id=args.seq_id)
    else:
        _build_parser().print_help()


if __name__ == "__main__":
    main()
