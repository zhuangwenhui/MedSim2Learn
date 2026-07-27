#!/usr/bin/env python3
"""Measure a synthetic-to-real gap on frozen ConvNeXt features."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dknet.data.feature_cache import (  # noqa: E402
    IMAGENET_MEAN,
    IMAGENET_STD,
    _discover_batch_files,
)
from dknet.utils.domain_gap import domain_gap_report  # noqa: E402


def _normalize_images(images: torch.Tensor) -> torch.Tensor:
    mean = torch.tensor(
        IMAGENET_MEAN,
        dtype=images.dtype,
        device=images.device,
    ).view(1, -1, 1, 1)
    standard_deviation = torch.tensor(
        IMAGENET_STD,
        dtype=images.dtype,
        device=images.device,
    ).view(1, -1, 1, 1)
    return (images - mean) / standard_deviation


@torch.no_grad()
def extract_domain_features(
    data_dir: str | Path,
    backbone: torch.nn.Module,
    device: str,
    id_prefix: str | None = None,
    batch_size: int = 256,
    max_per_domain: int | None = None,
    seed: int = 0,
) -> torch.Tensor:
    """Stream one data domain through a frozen backbone and return CPU features."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_per_domain is not None and max_per_domain < 2:
        raise ValueError("max_per_domain must be at least two")

    root = Path(data_dir).resolve()
    features = []
    for batch_name in _discover_batch_files(str(root)):
        samples = torch.load(
            root / batch_name,
            map_location="cpu",
            weights_only=False,
        )
        selected = [
            sample
            for sample in samples
            if id_prefix is None
            or str(sample.get("id", "")).startswith(id_prefix)
        ]
        for start in range(0, len(selected), batch_size):
            chunk = selected[start : start + batch_size]
            images = torch.stack([
                torch.as_tensor(sample["image"])
                for sample in chunk
            ]).float()
            images = _normalize_images(images).to(
                device,
                non_blocking=True,
            )
            encoded = backbone(images)
            features.append(encoded.detach().float().cpu())

    if not features:
        raise RuntimeError(
            f"no frames matched prefix={id_prefix!r} in {root}"
        )

    combined = torch.cat(features, dim=0)
    if max_per_domain is not None and combined.size(0) > max_per_domain:
        generator = torch.Generator().manual_seed(seed)
        selection = torch.randperm(
            combined.size(0),
            generator=generator,
        )[:max_per_domain]
        combined = combined[selection]
    return combined


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--synth-prefix", default="synt_")
    parser.add_argument("--real-prefix", default="real_")
    parser.add_argument("--synth-dir")
    parser.add_argument("--real-dir")
    parser.add_argument(
        "--backbone",
        default="large",
        choices=("tiny", "small", "base", "large"),
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-per-domain", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser


def _self_test() -> int:
    generator = torch.Generator().manual_seed(17)
    source = torch.randn(512, 16, generator=generator)
    target = torch.randn(512, 16, generator=generator) * 1.5 + 0.25
    report = domain_gap_report(source, target, seed=19)
    if report["coral_distance"] <= 0 or report["mean_l2"] <= 0:
        return 1
    print("SELF_TEST_OK")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _resolve_sources(args) -> tuple[tuple[str, str | None], ...]:
    has_data_directory = args.data_dir is not None
    has_synth_directory = args.synth_dir is not None
    has_real_directory = args.real_dir is not None
    if has_data_directory and (has_synth_directory or has_real_directory):
        raise ValueError(
            "--data-dir cannot be combined with --synth-dir or --real-dir"
        )
    if has_synth_directory != has_real_directory:
        raise ValueError(
            "--synth-dir and --real-dir must be provided together"
        )
    if not has_data_directory and not has_synth_directory:
        raise ValueError(
            "provide either --data-dir or both --synth-dir and --real-dir"
        )
    if has_data_directory:
        return (
            (args.data_dir, args.synth_prefix),
            (args.data_dir, args.real_prefix),
        )
    return ((args.synth_dir, None), (args.real_dir, None))


def _source_label(source_spec: tuple[str, str | None]) -> str:
    data_directory, id_prefix = source_spec
    if id_prefix is None:
        return str(data_directory)
    return f"{data_directory}[prefix={id_prefix}]"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        return _self_test()

    try:
        source_spec, target_spec = _resolve_sources(args)
    except ValueError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 2

    from dknet.models.backbones.convnext import ConvNeXtBackbone

    started = time.time()
    backbone = ConvNeXtBackbone(
        size=args.backbone,
        pretrained=True,
        freeze_backbone=True,
    ).to(args.device).eval()
    source = extract_domain_features(
        source_spec[0],
        backbone,
        args.device,
        id_prefix=source_spec[1],
        batch_size=args.batch_size,
        max_per_domain=args.max_per_domain,
        seed=args.seed,
    )
    target = extract_domain_features(
        target_spec[0],
        backbone,
        args.device,
        id_prefix=target_spec[1],
        batch_size=args.batch_size,
        max_per_domain=args.max_per_domain,
        seed=args.seed + 1,
    )
    report = domain_gap_report(source, target, seed=args.seed)
    report.update({
        "backbone": f"convnext_{args.backbone}",
        "source": _source_label(source_spec),
        "target": _source_label(target_spec),
        "elapsed_seconds": round(time.time() - started, 3),
    })
    serialized = json.dumps(report, indent=2, sort_keys=True)
    print(serialized)
    if args.out is not None:
        args.out.write_text(serialized + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
