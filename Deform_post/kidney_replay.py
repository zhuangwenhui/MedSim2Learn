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
    else:
        _build_parser().print_help()


if __name__ == "__main__":
    main()
