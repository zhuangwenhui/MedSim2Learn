"""Per-frame ConvNeXt feature precompute + cached-feature dataset.

The recommended (and resource-safe) path for the sequence conditions is to run
the frozen ConvNeXt frame encoder over every frame ONCE, cache the per-frame
features, and train only the temporal head on those features. This avoids
re-running ConvNeXt over ``B*T`` frames on every optimization step, which would
otherwise dominate compute and memory for clips of hundreds of frames.

:func:`precompute_features` reads a merged KiDKNet ``data_dir`` (the
``preprocessed_batch_*.pt`` + ``metadata.yaml`` + ``sequence_index.json``
produced by Deform_post ``assemble``), applies the SAME image normalization the
model would see at train time, runs the encoder, and writes a feature cache
directory with ``features.pt`` / ``forces.pt`` / ``ids.json`` plus a copied
``sequence_index.json`` and a ``metadata.yaml`` that records the original
``source_data_dir`` (so the existing by-sequence splits validate unchanged --
global frame indexing is preserved).

:class:`FeatureForceDataset` is a drop-in replacement for
:class:`~dknet.data.dataset.ForceDataset` whose ``image`` field carries the
cached feature vector ``(F,)`` instead of an image. Wrapped by
:class:`~dknet.data.sequence_dataset.SequenceDataset` it yields ``(T, F)``
windows for the feature-mode :class:`SequenceForceNet`.

Leak-safety across CV folds: a frame's cached feature is a deterministic frozen
ConvNeXt forward under FIXED ImageNet normalization -- it depends only on that
frame's image and the pretrained weights, never on any data-derived statistic.
Forces are cached raw (the merged dirs set ``normalize_forces: false`` /
``force_normalization: null``). So ONE cache per source is reused read-only across
all folds: each fold's split selects a disjoint subset of the SAME features with
no cross-fold information bleed, and the recorded ``source_data_dir`` lets the
loader validate every fold split against the cache unchanged. Run
``precompute_features`` once per source (real_merged, mixed_merged_256) on the
server before any C5-C8 fold.
"""

import json
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

import torch
import yaml

logger = logging.getLogger(__name__)

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

FEATURES_FILENAME = "features.pt"
FORCES_FILENAME = "forces.pt"
IDS_FILENAME = "ids.json"
SEQUENCE_INDEX_FILENAME = "sequence_index.json"
METADATA_FILENAME = "metadata.yaml"


def _discover_batch_files(data_dir: str) -> List[str]:
    """Return sorted ``*batch*.pt`` file names in *data_dir* (global frame order)."""
    files = sorted(
        f for f in os.listdir(data_dir)
        if f.endswith(".pt") and "batch" in f.lower()
    )
    if not files:
        raise FileNotFoundError(f"No .pt batch files found in {data_dir}")
    return files


def precompute_features(
    source_data_dir: str,
    out_dir: str,
    backbone_size: str = "large",
    normalize: Optional[Dict[str, List[float]]] = None,
    batch_size: int = 256,
    device: str = "cuda",
    store_dtype: str = "float16",
    pretrained: bool = True,
) -> Dict[str, Any]:
    """Encode every frame with a frozen ConvNeXt and cache the features.

    Args:
        source_data_dir: Merged KiDKNet ``data_dir`` (batches + metadata +
            ``sequence_index.json``).
        out_dir: Output feature-cache directory (created).
        backbone_size: ConvNeXt size (``tiny``/``small``/``base``/``large``).
        normalize: ``{"mean": [...], "std": [...]}`` applied before the encoder;
            defaults to ImageNet stats (matching the training configs).
        batch_size: Encoder forward batch size.
        device: ``"cuda"`` (default) or ``"cpu"`` (slow; for tests only).
        store_dtype: Feature storage dtype (``float16`` keeps the cache small).
        pretrained: Load ImageNet-pretrained ConvNeXt weights.

    Returns:
        Summary dict with sample count, feature dim, and output paths.
    """
    from ..models.backbones.convnext import ConvNeXtBackbone
    from torchvision import transforms

    start = time.time()
    if normalize is None:
        normalize = {"mean": IMAGENET_MEAN, "std": IMAGENET_STD}
    norm_tf = transforms.Normalize(mean=normalize["mean"], std=normalize["std"])

    meta_path = os.path.join(source_data_dir, METADATA_FILENAME)
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Missing {METADATA_FILENAME} in {source_data_dir}")
    with open(meta_path, "r", encoding="utf-8") as handle:
        src_meta = yaml.safe_load(handle) or {}
    total_expected = int(src_meta.get("total_samples", 0))

    seq_index_src = os.path.join(source_data_dir, SEQUENCE_INDEX_FILENAME)
    if not os.path.exists(seq_index_src):
        raise FileNotFoundError(
            f"Missing {SEQUENCE_INDEX_FILENAME} in {source_data_dir}; sequence "
            "feature caching needs the by-sequence index from Deform_post assemble."
        )

    target_dtype = getattr(torch, store_dtype)
    backbone = ConvNeXtBackbone(
        size=backbone_size, pretrained=pretrained, freeze_backbone=True
    ).to(device).eval()
    feat_dim = int(backbone.out_features)

    batch_files = _discover_batch_files(source_data_dir)
    feats_chunks: List[torch.Tensor] = []
    forces_list: List[torch.Tensor] = []
    ids: List[Any] = []

    with torch.no_grad():
        for bf in batch_files:
            data = torch.load(
                os.path.join(source_data_dir, bf),
                map_location="cpu", weights_only=False,
            )
            for lo in range(0, len(data), batch_size):
                chunk = data[lo:lo + batch_size]
                imgs = torch.stack([
                    s["image"] if isinstance(s["image"], torch.Tensor)
                    else torch.as_tensor(s["image"]) for s in chunk
                ]).float()
                imgs = norm_tf(imgs).to(device, non_blocking=True)
                out = backbone(imgs)  # (b, F)
                feats_chunks.append(out.detach().to("cpu", dtype=target_dtype))
                for s in chunk:
                    f = s["force"]
                    forces_list.append(
                        f.detach().float() if isinstance(f, torch.Tensor)
                        else torch.as_tensor(f, dtype=torch.float32)
                    )
                    ids.append(s.get("id"))
            del data

    features = torch.cat(feats_chunks, dim=0)
    forces = torch.stack(forces_list, dim=0)
    n = features.shape[0]
    if total_expected and n != total_expected:
        raise RuntimeError(
            f"Encoded {n} frames but metadata.total_samples={total_expected}; "
            "feature cache would desync from the splits."
        )

    os.makedirs(out_dir, exist_ok=True)
    torch.save(features, os.path.join(out_dir, FEATURES_FILENAME))
    torch.save(forces, os.path.join(out_dir, FORCES_FILENAME))
    with open(os.path.join(out_dir, IDS_FILENAME), "w", encoding="utf-8") as handle:
        json.dump([str(i) for i in ids], handle)
    shutil.copy2(seq_index_src, os.path.join(out_dir, SEQUENCE_INDEX_FILENAME))

    out_meta = {
        "total_samples": n,
        "batch_size": int(src_meta.get("batch_size", batch_size)),
        # Features are NOT images; downstream image-normalize must stay off.
        "normalize_images": False,
        "normalize_forces": bool(src_meta.get("normalize_forces", False)),
        "force_normalization": src_meta.get("force_normalization"),
        "feature_dim": feat_dim,
        "feature_backbone": f"convnext_{backbone_size}",
        "feature_normalize": normalize,
        "store_dtype": store_dtype,
        # The splits were authored against the source dir; record it so split
        # validation matches while features load from out_dir.
        "source_data_dir": str(os.path.abspath(source_data_dir)),
        "creation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out_dir, METADATA_FILENAME), "w", encoding="utf-8") as handle:
        yaml.safe_dump(out_meta, handle, sort_keys=True)

    elapsed = time.time() - start
    logger.info(
        "Precomputed %d features (dim=%d) from %s -> %s in %.1fs",
        n, feat_dim, source_data_dir, out_dir, elapsed,
    )
    return {
        "total_samples": n,
        "feature_dim": feat_dim,
        "out_dir": str(os.path.abspath(out_dir)),
        "source_data_dir": out_meta["source_data_dir"],
        "elapsed_sec": elapsed,
    }


class FeatureForceDataset:
    """Cached per-frame features, drop-in for :class:`ForceDataset`.

    ``__getitem__`` returns ``{"id", "image": feature (F,), "force": (3,)}`` so a
    :class:`SequenceDataset` stacks windows to ``(T, F)``. Exposes ``data_dir``,
    ``metadata``, and ``total_samples`` like ``ForceDataset`` for the loader.
    """

    def __init__(
        self,
        data_dir: str,
        transform: Optional[Any] = None,
        use_mmap: bool = False,
        cache_data: bool = True,
        max_samples: Optional[int] = None,
        dataset_selection: bool = False,
        cache_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        # transform/cache flags are accepted for signature parity with
        # ForceDataset but features are pre-encoded, so no image transform runs.
        self.transform = transform
        self.data_dir = data_dir
        if not os.path.isdir(data_dir):
            raise FileNotFoundError(f"Feature cache dir not found: {data_dir}")

        meta_path = os.path.join(data_dir, METADATA_FILENAME)
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"Missing {METADATA_FILENAME} in {data_dir}")
        with open(meta_path, "r", encoding="utf-8") as handle:
            self.metadata = yaml.safe_load(handle) or {}

        self.features = torch.load(
            os.path.join(data_dir, FEATURES_FILENAME),
            map_location="cpu", weights_only=False,
        )
        self.forces = torch.load(
            os.path.join(data_dir, FORCES_FILENAME),
            map_location="cpu", weights_only=False,
        )
        ids_path = os.path.join(data_dir, IDS_FILENAME)
        if os.path.exists(ids_path):
            with open(ids_path, "r", encoding="utf-8") as handle:
                self.ids = json.load(handle)
        else:
            self.ids = list(range(self.features.shape[0]))

        if self.features.shape[0] != self.forces.shape[0]:
            raise ValueError(
                f"features ({self.features.shape[0]}) and forces "
                f"({self.forces.shape[0]}) count mismatch in {data_dir}"
            )
        self.total_samples = int(self.features.shape[0])
        meta_total = self.metadata.get("total_samples")
        if meta_total is not None and int(meta_total) != self.total_samples:
            raise ValueError(
                f"metadata total_samples={meta_total} != features "
                f"{self.total_samples} in {data_dir}"
            )
        if max_samples is not None:
            self.total_samples = min(self.total_samples, int(max_samples))
        logger.info(
            "Loaded feature cache %s: %d frames, dim=%d",
            data_dir, self.total_samples, self.features.shape[1],
        )

    def __len__(self) -> int:
        return self.total_samples

    def __getitem__(self, index: int) -> Dict[str, Any]:
        if index < 0 or index >= self.total_samples:
            raise IndexError(
                f"Index {index} out of range for {self.total_samples} features"
            )
        return {
            "id": self.ids[index],
            "image": self.features[index].float(),
            "force": self.forces[index].float(),
        }


def _self_test() -> bool:
    """End-to-end precompute + FeatureForceDataset + SequenceDataset on CPU."""
    import tempfile

    ok = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "merged")
            os.makedirs(src)
            n = 12
            samples = [
                {"id": f"seq01_v{i:04d}",
                 "image": torch.rand(3, 32, 32),
                 "force": torch.tensor([float(i), 0.0, 0.0])}
                for i in range(n)
            ]
            torch.save(samples, os.path.join(src, "preprocessed_batch_0000.pt"))
            with open(os.path.join(src, METADATA_FILENAME), "w", encoding="utf-8") as fh:
                yaml.safe_dump(
                    {"total_samples": n, "batch_size": 2000,
                     "normalize_images": False, "normalize_forces": False},
                    fh,
                )
            with open(os.path.join(src, SEQUENCE_INDEX_FILENAME), "w", encoding="utf-8") as fh:
                json.dump(
                    {"seq_order": ["seq01"],
                     "sequences": {"seq01": {"batch_file": "preprocessed_batch_0000.pt",
                                             "start": 0, "end": n, "n": n}},
                     "total_samples": n},
                    fh,
                )

            out = os.path.join(tmp, "feat")
            summary = precompute_features(
                src, out, backbone_size="tiny", batch_size=4,
                device="cpu", pretrained=False,
            )
            assert summary["feature_dim"] == 768, summary
            assert summary["total_samples"] == n

            ds = FeatureForceDataset(out)
            assert len(ds) == n
            item = ds[3]
            assert item["image"].shape == (768,), item["image"].shape
            assert item["force"].shape == (3,)
            assert ds.metadata["source_data_dir"] == os.path.abspath(src)

            # Wrap in SequenceDataset (feature windows -> (T, F)).
            from .sequence_dataset import SequenceDataset, load_sequence_ranges
            ranges = load_sequence_ranges(out)
            seq = SequenceDataset(ds, list(range(n)), ranges,
                                 window_length=4, stride=2)
            w = seq[0]
            assert w["image"].shape == (4, 768), w["image"].shape
            assert w["force"].shape == (4, 3)
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[feature_cache self-test] FAILED: {exc}")
        import traceback
        traceback.print_exc()
    print(f"feature_cache self-test {'PASS' if ok else 'FAIL'}")
    return ok


def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Precompute frozen-ConvNeXt per-frame features for the "
                    "sequence conditions."
    )
    parser.add_argument("--source", help="Merged KiDKNet data_dir (batches + "
                                         "metadata + sequence_index.json).")
    parser.add_argument("--out", help="Output feature-cache directory.")
    parser.add_argument("--size", default="large",
                        choices=["tiny", "small", "base", "large"],
                        help="ConvNeXt size (default: large).")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--store-dtype", default="float16",
                        choices=["float16", "float32", "bfloat16"])
    parser.add_argument("--self-test", action="store_true",
                        help="Run the CPU self-test and exit.")
    return parser


def main(argv=None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    if not args.source or not args.out:
        print("[error] --source and --out are required (or use --self-test)")
        return 2
    summary = precompute_features(
        args.source, args.out, backbone_size=args.size,
        batch_size=args.batch_size, device=args.device,
        store_dtype=args.store_dtype,
    )
    print(f"[done] {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
