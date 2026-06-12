"""Per-sequence replay pipeline: prep and end-to-end orchestration.

prep turns one real sensor CSV into the exact DeformSim replay inputs
(forces_model.csv, the rotated per-frame model forces) plus the supervision
labels (labels.csv keeps the RAW sensor Newtons), a fixed laparoscope camera
and a provenance record. run_sequence chains prep -> DeformSim replay ->
render -> serialize (-> artifacts -> cleanup) for one sequence, writing a
run_status.json the batch driver can inspect.
"""

import csv
import json
import os
import shutil

import numpy as np
import open3d as o3d

from .camera import build_camera_params
from .config import DEFAULT_FPS, DEFAULT_POISSON, DEFAULT_YOUNG_MPA, CameraConfig
from .forces import (
    load_real_forces,
    map_forces,
    sample_id,
    sensor_to_model_rotation,
    subsample_indices,
)
from .meshio import contact_normal, load_mesh


def prep(real_csv, mesh_path, annotation_path, out_dir, seed=None,
         subsample=None, young=DEFAULT_YOUNG_MPA, poisson=DEFAULT_POISSON,
         cam_cfg=None, fps=DEFAULT_FPS):
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
    cfg = cam_cfg if cam_cfg is not None else CameraConfig()
    cam, eye = build_camera_params(p_world, cfg)
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
        "fps": fps,
        "camera": {
            "width": cfg.width, "height": cfg.height, "fov_deg": cfg.fov_deg,
            "standoff_mm": cfg.standoff_mm,
            "eye": [float(x) for x in eye],
            "center": [float(x) for x in p_world],
            "up": [float(x) for x in cfg.up],
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


def _write_status(out_dir, stage, status, error=""):
    """Record run progress so the batch driver can attribute failures to a stage."""
    payload = {"stage": stage, "status": status, "error": error}
    with open(os.path.join(out_dir, "run_status.json"), "w") as fh:
        json.dump(payload, fh, indent=2)


def run_sequence(recipe, seq, out_dir, subsample=None, with_artifacts=True,
                 keep_intermediate=None):
    """One sequence end to end: prep -> sim -> render -> serialize (-> artifacts).

    Mirrors the proven per-sequence stage order; every stage writes its outputs
    under `out_dir` (sim/, png/, dataset/, plus the prep CSVs and camera).
    Unless intermediates are kept, the bulky sim PLYs and render PNGs are
    deleted after the artifacts stage. Returns a summary dict.
    """
    from .dataset.serialize import serialize_labels_dataset
    from .render import render_fixed_camera_sequence
    from .simrun import run_deformsim_replay
    from . import artifacts as artifacts_mod

    real_csv = os.path.join(recipe.resolved("real_data_root"), f"{seq}.csv")
    mesh_path = recipe.resolved("mesh")
    annotation_path = recipe.resolved("annotation")
    keep = (recipe.batch.keep_intermediate
            if keep_intermediate is None else keep_intermediate)

    for path, label in ((real_csv, "real CSV"), (mesh_path, "mesh"),
                        (annotation_path, "annotation")):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{label} not found: {path}")

    os.makedirs(out_dir, exist_ok=True)
    sim_dir = os.path.join(out_dir, "sim")
    png_dir = os.path.join(out_dir, "png")
    data_dir = os.path.join(out_dir, "dataset")
    for d in (sim_dir, png_dir, data_dir):
        os.makedirs(d, exist_ok=True)

    stage = "prep"
    try:
        _write_status(out_dir, stage, "running")
        print("=== Stage 1: prep ===")
        meta = prep(real_csv, mesh_path, annotation_path, out_dir,
                    subsample=subsample, young=recipe.material.young_mpa,
                    poisson=recipe.material.poisson, cam_cfg=recipe.camera,
                    fps=recipe.fps)

        stage = "simulate"
        _write_status(out_dir, stage, "running")
        print("=== Stage 2: DeformSim exact replay ===")
        ply_dir = run_deformsim_replay(
            exe=recipe.resolved("exe"),
            mesh_path=mesh_path,
            annotation_path=annotation_path,
            sim_dir=sim_dir,
            force_list_csv=os.path.join(out_dir, "forces_model.csv"),
            young=recipe.material.young_mpa,
            poisson=recipe.material.poisson,
            num_threads=recipe.sim.num_threads,
            mkl_threads=recipe.sim.mkl_threads,
            seed=recipe.sim.seed,
            mkl_bin=recipe.mkl_bin,
            compiler_bin=recipe.compiler_bin,
        )
        print(f"Deformed PLYs: {ply_dir}")

        stage = "render"
        _write_status(out_dir, stage, "running")
        print("=== Stage 3: render ===")
        camera_path = os.path.join(out_dir, "camera.json")
        n_png = render_fixed_camera_sequence(ply_dir, camera_path, png_dir)
        print(f"render: {n_png} PNGs -> {png_dir}")

        stage = "serialize"
        _write_status(out_dir, stage, "running")
        print("=== Stage 4: serialize ===")
        # DataPreprocessor wants exactly one CSV next to labels.csv, so the
        # labels get an isolated directory (forces_model.csv stays in out_dir).
        labels_dir = os.path.join(out_dir, "labels_only")
        os.makedirs(labels_dir, exist_ok=True)
        labels_iso = os.path.join(labels_dir, "labels.csv")
        shutil.copyfile(os.path.join(out_dir, "labels.csv"), labels_iso)
        serialize_labels_dataset(png_dir, labels_iso, data_dir,
                                 resize=recipe.serialize.resize)

        if with_artifacts:
            stage = "artifacts"
            _write_status(out_dir, stage, "running")
            print("=== Stage 5: artifacts ===")
            artifacts_mod.artifacts(out_dir, mesh_path, fps=recipe.fps,
                                    seq_id=meta["seq_id"])

        if not keep:
            stage = "cleanup"
            _write_status(out_dir, stage, "running")
            print("=== Stage 6: cleanup intermediates ===")
            n_ply = _delete_files(sim_dir, ".ply", recurse=True)
            n_png_del = _delete_files(png_dir, ".png", recurse=False)
            print(f"cleanup: removed {n_ply} PLYs, {n_png_del} PNGs")
    except Exception as exc:
        _write_status(out_dir, stage, "FAIL", error=str(exc))
        raise

    _write_status(out_dir, "done", "OK")
    return {"seq": seq, "out_dir": out_dir, "frames": meta["frame_count"]}


def _delete_files(root, suffix, recurse):
    """Delete files with `suffix` under root; returns the count removed."""
    n = 0
    if not os.path.isdir(root):
        return n
    if recurse:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if fname.lower().endswith(suffix):
                    os.remove(os.path.join(dirpath, fname))
                    n += 1
    else:
        for fname in os.listdir(root):
            if fname.lower().endswith(suffix):
                os.remove(os.path.join(root, fname))
                n += 1
    return n


def _self_test():
    """prep round-trip on a synthetic mesh; raises AssertionError on failure."""
    import tempfile

    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as td:
        real = os.path.join(td, "synthetic.csv")
        Fr = rng.normal(size=(12, 3))
        with open(real, "w", newline="") as fh:
            for r in Fr:
                fh.write(f"{r[0]},{r[1]},{r[2]}\n")
        # Minimal synthetic mesh + annotation so prep runs without real assets.
        sph = o3d.geometry.TriangleMesh.create_sphere(radius=10.0, resolution=10)
        sph.compute_vertex_normals()
        mp = os.path.join(td, "m.ply")
        o3d.io.write_triangle_mesh(mp, sph)
        ap = os.path.join(td, "a.json")
        with open(ap, "w") as fh:
            json.dump({"freeze": {"vertices": []},
                       "contacts": [{"seed": 0, "k_ring": 2}]}, fh)
        meta = prep(real, mp, ap, td, seed=0)
        assert meta["frame_count"] == 12, "frame_count != rows"

        fm = load_real_forces(os.path.join(td, "forces_model.csv"))
        assert len(fm) == 12, "forces_model rowcount"
        # forces_model should equal R @ real (rotated), NOT the raw sensor force.
        Rseed = np.array(meta["R"])
        assert np.allclose(fm, map_forces(Fr, Rseed), atol=1e-5), "forces_model != R@real"
        assert not np.allclose(fm, Fr, atol=1e-3), "forces_model not rotated"

        # labels.csv holds the REAL sensor force, keyed by SampleID.
        lab = {}
        with open(os.path.join(td, "labels.csv")) as fh:
            rd = csv.DictReader(fh)
            for row in rd:
                lab[row["SampleID"]] = np.array(
                    [float(row["force_x"]), float(row["force_y"]), float(row["force_z"])])
        assert len(lab) == 12, "labels rowcount"
        sid = sample_id(0, 5)
        assert sid in lab, "labels SampleID present"
        assert np.allclose(lab[sid], Fr[5], atol=1e-5), "labels == real sensor force"
        assert not np.allclose(lab[sid], fm[5], atol=1e-3), "labels != rotated force"

        # camera.json must be a readable Open3D pinhole camera.
        cam = o3d.io.read_pinhole_camera_parameters(os.path.join(td, "camera.json"))
        assert cam.intrinsic.width == 800 and cam.intrinsic.height == 800
    print("replay self-test PASS")
