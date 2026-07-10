#!/usr/bin/env python3
"""Measure the synthetic->real domain gap with the CORAL distance (fossilised tool).

The Track B experiment (2026-07-03) found CORAL as a *training loss* does not reliably
close the synth->real gap at the current measurement fidelity (null result). This script
retains CORAL in its more defensible role: a *metric*. It runs the frozen ConvNeXt encoder
over a synthetic and a real image set, then reports the CORAL distance (covariance
discrepancy, ||C_s - C_t||_F^2 / (4 d^2)) between their features, together with the
within-domain sampling-noise floor so the number is interpretable. Re-run it after
data-side appearance work to check the gap actually shrank.

Two input modes:
  1. One merged data_dir whose ids are domain-prefixed (e.g. datasets/mixed, real_/synt_):
         --data-dir DIR [--synth-prefix synt_ --real-prefix real_]
  2. Two separate data_dirs:
         --synth-dir DIR_A --real-dir DIR_B

Features use the SAME frozen ConvNeXt + ImageNet normalisation the model sees at train
time, so distances are comparable across runs. Report is printed and (optionally) written
to JSON via --out.

Examples:
  python scripts/eval_domain_gap.py \
      --data-dir DataFlow/Deform_post/preprocessed/datasets/mixed \
      --backbone large --device cuda --out gap_mixed.json
  python scripts/eval_domain_gap.py --self-test   # CPU end-to-end smoke, no GPU/weights
"""

import argparse
import json
import os
import sys
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dknet.data.feature_cache import (  # noqa: E402
    IMAGENET_MEAN,
    IMAGENET_STD,
    _discover_batch_files,
)
from dknet.utils.uda import domain_gap_report  # noqa: E402


@torch.no_grad()
def extract_domain_features(
    data_dir,
    backbone,
    norm_tf,
    device,
    id_prefix=None,
    batch_size=256,
    max_per_domain=None,
    seed=0,
):
    """Frozen-ConvNeXt features for the frames of one domain, streamed to CPU.

    Streams the ``*batch*.pt`` files (never holding all images in RAM), keeps only frames
    whose ``id`` starts with *id_prefix* (all frames when it is None), applies the SAME
    ImageNet normalisation as training, and returns an ``(n, d)`` CPU float32 feature
    matrix. If *max_per_domain* is set and fewer would be kept, the features are randomly
    subsampled with a fixed seed (deterministic).
    """
    feats = []
    n_seen = 0
    for bf in _discover_batch_files(data_dir):
        data = torch.load(
            os.path.join(data_dir, bf), map_location="cpu", weights_only=False
        )
        sel = [
            s for s in data
            if id_prefix is None or str(s.get("id", "")).startswith(id_prefix)
        ]
        for lo in range(0, len(sel), batch_size):
            chunk = sel[lo:lo + batch_size]
            imgs = torch.stack([
                s["image"] if isinstance(s["image"], torch.Tensor)
                else torch.as_tensor(s["image"]) for s in chunk
            ]).float()
            imgs = norm_tf(imgs).to(device, non_blocking=True)
            out = backbone(imgs)  # (b, F)
            feats.append(out.detach().float().cpu())
            n_seen += len(chunk)
        del data
    if not feats:
        raise RuntimeError(
            f"No frames matched prefix={id_prefix!r} in {data_dir}; check the id scheme."
        )
    features = torch.cat(feats, dim=0)
    if max_per_domain is not None and features.size(0) > max_per_domain:
        g = torch.Generator().manual_seed(seed)
        idx = torch.randperm(features.size(0), generator=g)[:max_per_domain]
        features = features[idx]
    return features


def _print_report(report, synth_src, real_src):
    """Human-readable summary of a domain_gap_report dict."""
    print("\n=== synthetic -> real domain gap (CORAL) ===")
    print(f"  synth source : {synth_src}  (n={report['n_source']})")
    print(f"  real  source : {real_src}  (n={report['n_target']})")
    print(f"  feature dim  : {report['feature_dim']}  backbone={report.get('backbone')}")
    print("  ----------------------------------------------------------")
    print(f"  CORAL distance (cross-domain)     : {report['coral_distance']:.6g}")
    print(f"  within-domain floor  synth/real   : {report['within_source']:.6g} / {report['within_target']:.6g}")
    print(f"  within-domain floor  mean         : {report['within_mean']:.6g}")
    print(f"  GAP RATIO (cross / floor)         : {report['gap_ratio']:.3g}   <- headline")
    print("  ----------------------------------------------------------")
    print(f"  mean L2 (first-order gap, CORAL-blind): {report['mean_l2']:.4g}")
    print(f"  feature RMS synth/real            : {report['rms_source']:.4g} / {report['rms_target']:.4g}")
    print(f"  RMS ratio (synth/real diversity)  : {report['rms_ratio']:.3g}")
    print("  ==========================================================")
    if report["gap_ratio"] == report["gap_ratio"] and report["gap_ratio"] > 3:
        print("  reading: gap_ratio >> 1 -> domains are genuinely far apart (real gap).")
    else:
        print("  reading: gap_ratio ~ 1 -> gap is within sampling noise at this fidelity.")


def _self_test():
    """CPU end-to-end smoke: tiny prefixed data_dir -> extract -> report."""
    import tempfile
    import yaml
    from torchvision import transforms
    from dknet.models.backbones.convnext import ConvNeXtBackbone

    ok = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            n = 16
            samples = []
            for i in range(n):
                dom = "real_" if i % 2 == 0 else "synt_"
                # give the two domains a clearly different image statistic
                img = torch.rand(3, 32, 32) * (1.0 if dom == "real_" else 0.3)
                samples.append({"id": f"{dom}seq01_v{i:04d}", "image": img,
                                "force": torch.zeros(3)})
            torch.save(samples, os.path.join(tmp, "preprocessed_batch_0000.pt"))
            with open(os.path.join(tmp, "metadata.yaml"), "w", encoding="utf-8") as fh:
                yaml.safe_dump({"total_samples": n}, fh)

            backbone = ConvNeXtBackbone(size="tiny", pretrained=False,
                                        freeze_backbone=True).to("cpu").eval()
            norm_tf = transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
            synth = extract_domain_features(tmp, backbone, norm_tf, "cpu",
                                            id_prefix="synt_", batch_size=4)
            real = extract_domain_features(tmp, backbone, norm_tf, "cpu",
                                           id_prefix="real_", batch_size=4)
            assert synth.shape[0] == n // 2 and real.shape[0] == n // 2, (synth.shape, real.shape)
            assert synth.shape[1] == 768, synth.shape
            rep = domain_gap_report(synth, real)
            for k in ("coral_distance", "within_mean", "gap_ratio", "mean_l2", "rms_ratio"):
                assert k in rep and rep[k] == rep[k], (k, rep)  # present + not NaN
            print(f"[self-test] report keys ok; coral={rep['coral_distance']:.4g} "
                  f"gap_ratio={rep['gap_ratio']:.3g}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        import traceback
        traceback.print_exc()
        print(f"[self-test] FAILED: {exc}")
    print(f"eval_domain_gap self-test {'PASS' if ok else 'FAIL'}")
    return ok


def _build_arg_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", help="Single merged dir with domain-prefixed ids.")
    p.add_argument("--synth-prefix", default="synt_",
                   help="Synthetic id prefix in --data-dir mode (default: synt_).")
    p.add_argument("--real-prefix", default="real_",
                   help="Real id prefix in --data-dir mode (default: real_).")
    p.add_argument("--synth-dir", help="Synthetic data_dir (two-dir mode).")
    p.add_argument("--real-dir", help="Real data_dir (two-dir mode).")
    p.add_argument("--backbone", default="large",
                   choices=["tiny", "small", "base", "large"])
    p.add_argument("--device", default="cuda")
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--max-per-domain", type=int, default=None,
                   help="Subsample each domain to at most N frames (default: all).")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", help="Optional JSON output path for the report.")
    p.add_argument("--self-test", action="store_true",
                   help="Run the CPU self-test and exit.")
    return p


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1

    single = bool(args.data_dir)
    two = bool(args.synth_dir and args.real_dir)
    if single == two:
        print("[error] provide EITHER --data-dir OR (--synth-dir AND --real-dir).")
        return 2

    from torchvision import transforms
    from dknet.models.backbones.convnext import ConvNeXtBackbone

    start = time.time()
    backbone = ConvNeXtBackbone(size=args.backbone, pretrained=True,
                                freeze_backbone=True).to(args.device).eval()
    norm_tf = transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)

    if single:
        synth_src = f"{args.data_dir}[{args.synth_prefix}]"
        real_src = f"{args.data_dir}[{args.real_prefix}]"
        synth = extract_domain_features(args.data_dir, backbone, norm_tf, args.device,
                                        id_prefix=args.synth_prefix, batch_size=args.batch_size,
                                        max_per_domain=args.max_per_domain, seed=args.seed)
        real = extract_domain_features(args.data_dir, backbone, norm_tf, args.device,
                                       id_prefix=args.real_prefix, batch_size=args.batch_size,
                                       max_per_domain=args.max_per_domain, seed=args.seed)
    else:
        synth_src, real_src = args.synth_dir, args.real_dir
        synth = extract_domain_features(args.synth_dir, backbone, norm_tf, args.device,
                                        id_prefix=None, batch_size=args.batch_size,
                                        max_per_domain=args.max_per_domain, seed=args.seed)
        real = extract_domain_features(args.real_dir, backbone, norm_tf, args.device,
                                       id_prefix=None, batch_size=args.batch_size,
                                       max_per_domain=args.max_per_domain, seed=args.seed)

    report = domain_gap_report(synth, real, seed=args.seed)
    report["backbone"] = f"convnext_{args.backbone}"
    report["synth_source"] = synth_src
    report["real_source"] = real_src
    report["elapsed_sec"] = round(time.time() - start, 1)
    _print_report(report, synth_src, real_src)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"[done] report -> {args.out}  ({report['elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
