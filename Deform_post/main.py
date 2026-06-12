"""Deform_post command-line entry point.

Single front door for the kidney digital-twin data pipeline; each subcommand
maps onto one dpost module:

  annotate   mesh -> freeze/contact annotation JSON + verification renders
  prep       real sensor CSV -> forces_model.csv / labels.csv / camera.json / meta
  simulate   forces_model.csv -> deformed PLYs (DeformSim exact replay)
  render     deformed PLYs -> one PNG per frame with the fixed camera
  serialize  PNGs + labels.csv -> preprocessed_batch_*.pt
  artifacts  completed replay dir -> maxu/waveform/twin-sync/montage QA outputs
  run        one sequence end to end (prep -> simulate -> render -> serialize
             -> artifacts -> cleanup), config-driven
  batch      many sequences via `run` subprocesses, throttled, with batch_log.csv
  assemble   per-sequence .pt outputs -> merged KiDKNet data_dir + splits
  selftest   run every module's self-test

Defaults come from configs/kidney_twin.yaml (override with --config); explicit
CLI flags win over the config file.
"""

import argparse
import os
import sys

# Make the dpost package importable no matter where main.py is invoked from.
_HERE = os.path.abspath(os.path.dirname(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dpost.config import load_recipe  # noqa: E402
from dpost.dataset.serialize import parse_resize  # noqa: E402

DEFAULT_CONFIG = os.path.join(_HERE, "configs", "kidney_twin.yaml")


def _recipe_from(args):
    """Load the recipe named by --config (or the default when it exists)."""
    config_path = getattr(args, "config", None)
    if config_path is None and os.path.isfile(DEFAULT_CONFIG):
        config_path = DEFAULT_CONFIG
    return load_recipe(config_path)


def _build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Kidney digital-twin data pipeline (Deform_post)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    def add_config(sp):
        sp.add_argument("--config", type=str, default=None,
                        help="Recipe YAML (default: configs/kidney_twin.yaml)")

    # --- annotate -------------------------------------------------------
    pa = sub.add_parser("annotate",
                        help="Mesh -> freeze/contact annotation JSON + renders")
    pa.add_argument("--ply", type=str, required=True, help="Input canonical (posed) PLY")
    pa.add_argument("--out", type=str, default="annotation.json")
    pa.add_argument("--render-dir", type=str, default="pose_snapshots")
    pa.add_argument("--freeze-ratio", type=float, default=0.15)
    pa.add_argument("--num-centers", type=int, default=30)
    pa.add_argument("--k-ring", type=int, default=2)
    pa.add_argument("--zone-normal-deg", type=float, default=45.0)
    pa.add_argument("--zone-shoulder-deg", type=float, default=30.0)
    pa.add_argument("--zone-sharp-max", type=float, default=0.15)
    pa.add_argument("--zone-concave-max", type=float, default=0.05)
    pa.add_argument("--zone-edge-margin-rings", type=int, default=None)
    pa.add_argument("--center-min-dist", type=float, default=None)
    pa.add_argument("--support-min-ratio", type=float, default=0.4)
    pa.add_argument("--seed", type=int, default=42)
    pa.add_argument("--gate", type=float, default=None)

    # --- prep -----------------------------------------------------------
    pp = sub.add_parser("prep",
                        help="Real CSV -> forces_model.csv/labels.csv/camera.json/meta")
    add_config(pp)
    pp.add_argument("--real-csv", required=True)
    pp.add_argument("--mesh", required=True)
    pp.add_argument("--annotation", required=True)
    pp.add_argument("--out-dir", required=True)
    pp.add_argument("--seed", type=int, default=None,
                    help="Contact seed (default: annotation contact[0])")
    pp.add_argument("--subsample", type=int, default=None,
                    help="Evenly sample N frames from the sequence")
    pp.add_argument("--young", type=float, default=None)
    pp.add_argument("--poisson", type=float, default=None)

    # --- simulate -------------------------------------------------------
    pm = sub.add_parser("simulate",
                        help="forces_model.csv -> deformed PLYs (DeformSim replay)")
    add_config(pm)
    pm.add_argument("--mesh", required=True)
    pm.add_argument("--annotation", required=True)
    pm.add_argument("--forces", required=True, help="forces_model.csv path")
    pm.add_argument("--sim-dir", required=True)

    # --- render ---------------------------------------------------------
    pr = sub.add_parser("render", help="Deformed PLYs -> PNGs with the fixed camera")
    pr.add_argument("--ply-dir", required=True)
    pr.add_argument("--camera", required=True)
    pr.add_argument("--out-png-dir", required=True)
    pr.add_argument("--size", type=int, default=None)

    # --- serialize ------------------------------------------------------
    ps = sub.add_parser("serialize",
                        help="PNGs + labels.csv -> preprocessed_batch_*.pt")
    ps.add_argument("--png-dir", required=True)
    ps.add_argument("--labels", required=True)
    ps.add_argument("--out-data-dir", required=True)
    ps.add_argument("--resize", type=str, default=None,
                    help='Resize images to WxH (e.g. "224x224") or a single int '
                         'for a square (e.g. "224"); default keeps native size')

    # --- artifacts ------------------------------------------------------
    pf = sub.add_parser("artifacts",
                        help="Replay dir -> maxu.csv + waveform/video/montage artifacts")
    pf.add_argument("--seq-dir", required=True,
                    help="Replay output dir (holds labels.csv, png/, sim/DeformedSample_*/)")
    pf.add_argument("--mesh", required=True, help="Rest mesh PLY (for max|u| vs rest)")
    pf.add_argument("--fps", type=float, default=30.0)
    pf.add_argument("--seq-id", type=str, default=None,
                    help="Override the sequence id used in titles (default: meta seq_id)")

    # --- run ------------------------------------------------------------
    pu = sub.add_parser("run", help="One sequence end to end (config-driven)")
    add_config(pu)
    pu.add_argument("--seq", required=True, help="Sequence id, e.g. 01")
    pu.add_argument("--out-dir", type=str, default=None,
                    help="Default: <out_root>/seq<seq>")
    pu.add_argument("--subsample", type=int, default=None)
    pu.add_argument("--no-artifacts", action="store_true")
    pu.add_argument("--keep-intermediate", action="store_true")

    # --- batch ----------------------------------------------------------
    pb = sub.add_parser("batch", help="Run many sequences via `run` subprocesses")
    add_config(pb)
    pb.add_argument("--seqs", required=True,
                    help="Comma list and/or ranges, e.g. '02,05..07,12'")
    pb.add_argument("--out-root", type=str, default=None,
                    help="Default: recipe out_root")
    pb.add_argument("--max-parallel", type=int, default=None)
    pb.add_argument("--keep-intermediate", action="store_true")
    pb.add_argument("--subsample", type=int, default=None)

    # --- assemble -------------------------------------------------------
    pg = sub.add_parser("assemble",
                        help="Per-sequence .pt outputs -> merged data_dir + splits "
                             "(see `assemble --help` via the module for full flags)")
    pg.add_argument("rest", nargs=argparse.REMAINDER,
                    help="Arguments forwarded to dpost.dataset.assemble")

    # --- selftest -------------------------------------------------------
    sub.add_parser("selftest", help="Run every module's self-test")

    return p


def _cmd_annotate(args):
    import json

    import numpy as np

    from dpost import annotate as ann_mod

    if not (0.0 <= args.freeze_ratio < 1.0):
        raise SystemExit("--freeze-ratio must be in [0, 1)")
    if args.num_centers < 1:
        raise SystemExit("--num-centers must be >= 1")
    if args.k_ring < 1:
        raise SystemExit("--k-ring must be >= 1")
    if not (0.0 < args.zone_normal_deg < 90.0):
        raise SystemExit("--zone-normal-deg must be in (0, 90)")
    if not (0.0 < args.zone_shoulder_deg < 90.0):
        raise SystemExit("--zone-shoulder-deg must be in (0, 90)")
    if args.zone_sharp_max < 0.0:
        raise SystemExit("--zone-sharp-max must be >= 0")
    if not (-1.0 <= args.zone_concave_max <= 1.0):
        raise SystemExit("--zone-concave-max must be in [-1, 1]")
    if not (0.0 <= args.support_min_ratio < 1.0):
        raise SystemExit("--support-min-ratio must be in [0, 1)")
    if args.zone_edge_margin_rings is not None and args.zone_edge_margin_rings < 0:
        raise SystemExit("--zone-edge-margin-rings must be >= 0")
    if args.center_min_dist is not None and args.center_min_dist <= 0.0:
        raise SystemExit("--center-min-dist must be > 0")

    mesh = ann_mod.load_mesh(args.ply)
    top, bottom = ann_mod.flatness_metric(mesh)
    print(f"flatness: top(+z)={top:.3f} bottom(-z)={bottom:.3f}")
    ann_mod.render_views(mesh, args.render_dir)
    if args.gate is not None and (top < args.gate or bottom < args.gate):
        raise SystemExit(f"pose gate failed: top={top:.3f} bottom={bottom:.3f} < {args.gate}")

    freeze = ann_mod.compute_freeze(np.asarray(mesh.vertices), args.freeze_ratio)
    zone, centers = ann_mod.select_contacts(
        mesh, set(freeze), args.num_centers, k_ring=args.k_ring,
        normal_deg=args.zone_normal_deg, shoulder_deg=args.zone_shoulder_deg,
        sharp_max=args.zone_sharp_max, concave_max=args.zone_concave_max,
        support_min_ratio=args.support_min_ratio,
        edge_margin_rings=args.zone_edge_margin_rings,
        center_min_dist=args.center_min_dist, rng_seed=args.seed)
    ann = ann_mod._assemble_annotation(freeze, centers, args.k_ring)
    if not ann["contacts"] or not ann["freeze"]["vertices"]:
        raise SystemExit("annotation has empty contacts or freeze; relax the zone/freeze params")
    ann_mod.render_zone(mesh, freeze, zone, centers, args.k_ring, args.render_dir)
    with open(args.out, "w") as fh:
        json.dump(ann, fh, indent=4)
    print(f"wrote {args.out}: {len(ann['freeze']['vertices'])} freeze, "
          f"{len(ann['contacts'])} contacts; zone={len(zone)} vertices")


def _cmd_prep(args):
    from dpost.replay import prep

    recipe = _recipe_from(args)
    young = args.young if args.young is not None else recipe.material.young_mpa
    poisson = args.poisson if args.poisson is not None else recipe.material.poisson
    prep(args.real_csv, args.mesh, args.annotation, args.out_dir,
         seed=args.seed, subsample=args.subsample, young=young, poisson=poisson,
         cam_cfg=recipe.camera, fps=recipe.fps)


def _cmd_simulate(args):
    from dpost.simrun import run_deformsim_replay

    recipe = _recipe_from(args)
    ply_dir = run_deformsim_replay(
        exe=recipe.resolved("exe"),
        mesh_path=args.mesh,
        annotation_path=args.annotation,
        sim_dir=args.sim_dir,
        force_list_csv=args.forces,
        young=recipe.material.young_mpa,
        poisson=recipe.material.poisson,
        num_threads=recipe.sim.num_threads,
        mkl_threads=recipe.sim.mkl_threads,
        seed=recipe.sim.seed,
        mkl_bin=recipe.mkl_bin,
        compiler_bin=recipe.compiler_bin,
    )
    print(f"Deformed PLYs: {ply_dir}")


def _cmd_render(args):
    from dpost.render import render_fixed_camera_sequence

    n_ok = render_fixed_camera_sequence(
        args.ply_dir, args.camera, args.out_png_dir, size=args.size)
    print(f"render: {n_ok} PNGs -> {args.out_png_dir}")


def _cmd_serialize(args):
    from dpost.dataset.serialize import serialize_labels_dataset

    serialize_labels_dataset(args.png_dir, args.labels, args.out_data_dir,
                             resize=parse_resize(args.resize))


def _cmd_artifacts(args):
    from dpost.artifacts import artifacts

    artifacts(args.seq_dir, args.mesh, fps=args.fps, seq_id=args.seq_id)


def _cmd_run(args):
    from dpost.replay import run_sequence

    recipe = _recipe_from(args)
    out_dir = args.out_dir or os.path.join(recipe.resolved("out_root"),
                                           f"seq{args.seq}")
    run_sequence(recipe, args.seq, out_dir, subsample=args.subsample,
                 with_artifacts=not args.no_artifacts,
                 keep_intermediate=True if args.keep_intermediate else None)


def _cmd_batch(args):
    from dpost.simrun import run_batch

    recipe = _recipe_from(args)
    out_root = args.out_root or recipe.resolved("out_root")
    max_parallel = (args.max_parallel if args.max_parallel is not None
                    else recipe.batch.max_parallel)
    config_path = args.config
    if config_path is None and os.path.isfile(DEFAULT_CONFIG):
        config_path = DEFAULT_CONFIG
    _n_ok, n_fail, _log = run_batch(
        os.path.abspath(__file__), args.seqs, out_root,
        config_path=config_path, max_parallel=max_parallel,
        keep_intermediate=args.keep_intermediate, subsample=args.subsample)
    if n_fail:
        raise SystemExit(1)


def _cmd_assemble(args):
    from dpost.dataset import assemble as asm

    rest = list(args.rest)
    if rest and rest[0] == "--":
        rest = rest[1:]
    raise SystemExit(asm.main(rest))


def _cmd_selftest(_args):
    from dpost import annotate as ann_mod
    from dpost import artifacts as artifacts_mod
    from dpost import replay as replay_mod
    from dpost.dataset import assemble as assemble_mod
    from dpost.dataset import serialize as serialize_mod
    from dpost.forces import real as forces_mod
    from dpost.simrun import batch as batch_mod

    forces_mod._self_test()
    serialize_mod._self_test()
    batch_mod._self_test()
    replay_mod._self_test()
    artifacts_mod._self_test()
    ann_mod._self_test()
    ann_mod._self_test_descriptors()
    ann_mod._self_test_zone()
    ann_mod._self_test_poisson()
    ann_mod._self_test_cli()
    ann_mod._self_test_annotation()
    if not assemble_mod.run_self_test():
        raise SystemExit("assemble self-test FAILED")
    print("\nAll self-tests PASSED")


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "annotate": _cmd_annotate,
        "prep": _cmd_prep,
        "simulate": _cmd_simulate,
        "render": _cmd_render,
        "serialize": _cmd_serialize,
        "artifacts": _cmd_artifacts,
        "run": _cmd_run,
        "batch": _cmd_batch,
        "assemble": _cmd_assemble,
        "selftest": _cmd_selftest,
    }
    handler = handlers.get(args.cmd)
    if handler is None:
        parser.print_help()
        return
    handler(args)


if __name__ == "__main__":
    main()
