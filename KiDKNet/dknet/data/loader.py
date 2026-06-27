"""Data loader module.
======================
Provides unified data loader interfaces for .pt batches produced by
the Deform_post pipeline (main.py serialize).
"""

import os
import torch
import logging
from pathlib import Path
from torch.utils.data import DataLoader
from typing import Tuple, Optional, Dict, Any

from .dataset import ForceDataset, SubsetDataset
from .feature_cache import FeatureForceDataset
from .transforms import get_transforms
from .splitter import load_split

logger = logging.getLogger(__name__)


def _get_num_workers(config: Dict[str, Any]) -> int:
    """Return the number of DataLoader worker processes.

    These workers run on the CPU side to fetch mini-batches from
    ``ForceDataset`` and operate independently from the trainer routine that
    moves data to the GPU.

    Args:
        config: Configuration dictionary.

    Returns:
        int: Number of worker processes to use.
    """
    # Use the configured value when available; otherwise fall back to 4.
    if "general" in config and "num_workers" in config["general"]:
        num_workers = config["general"]["num_workers"]
    else:
        num_workers = 4

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA device not detected; training pipeline requires GPU "
            "availability."
        )

    cuda_device_count = torch.cuda.device_count()
    if cuda_device_count > 1:
        # Spread workers across GPUs so CPU usage stays reasonable.
        cpu_count = os.cpu_count() or 1
        per_device_workers = max(1, cpu_count // cuda_device_count)
        num_workers = min(num_workers, per_device_workers)
    logger.info(
        "CUDA devices detected: %s, setting worker threads to %s",
        cuda_device_count,
        num_workers,
    )

    return num_workers

def get_dataloaders(
    config: Dict[str, Any],
    split_file: Optional[str] = None,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """Build data loaders for training, validation, and testing.

    Args:
        config: Configuration dictionary. Only ``config["data"]`` and
            ``config["training"]`` keys are required.
        split_file: Optional path or filename of the JSON split file. Relative
            paths are resolved against the project root and ``configs/``.

    Returns:
        Tuple[DataLoader, DataLoader, DataLoader]: Training, validation, and
        testing data loaders.

    Raises:
        FileNotFoundError: Raised when the split file cannot be resolved.
        ValueError: Raised when the split is incompatible with the dataset.
    """
    # Configure multiprocessing sharing strategy.  'file_system' routes tensors
    # through /dev/shm, avoiding the Windows handle limit and keeping prefetch
    # behaviour stable.  Callers on systems where 'file_descriptor' works can
    # override this via config["general"]["mp_sharing_strategy"].
    sharing_strategy = config.get("general", {}).get(
        "mp_sharing_strategy", "file_system"
    )
    torch.multiprocessing.set_sharing_strategy(sharing_strategy)

    # Resolve the dataset directory; fall back to the default location.
    base_data_dir = config["data"].get(
        "data_dir", "../Deform_post/preprocessed_data"
    )

    # Bail out early when the dataset directory is missing.
    if not os.path.exists(base_data_dir):
        raise FileNotFoundError(
            f"Data directory does not exist: {base_data_dir}"
        )

    # Read loader-related options from the configuration.
    batch_size = config["training"]["batch_size"]
    num_workers = _get_num_workers(config)
    pin_memory = config["general"].get("pin_memory", True)
    loader_opts = config["data"]["loader"]
    prefetch_factor = loader_opts.get("prefetch_factor", 2)
    persistent_workers = loader_opts.get("persistent_workers", True)

    # Allow interactive dataset selection when users enable it.
    enable_dataset_selection = config["data"].get("enable_dataset_selection", True)

    # Apply the same transform across all splits because data are preprocessed.
    transform = get_transforms(config)

    # Read caching strategy options; defaults prefer full caching.
    loading_strategy = config["data"]["loading_strategy"]
    use_mmap = loading_strategy.get("use_mmap", False)  # Default to disabled mmap.
    cache_data = loading_strategy.get("cache_data", True)  # Default to cached loading.
    cache_config = loading_strategy.get("cache_settings", {}) or {}

    logger.info(
        "Data loading strategy: use_mmap=%s, cache_data=%s", use_mmap, cache_data
    )
    logger.info("Cache settings=%s", cache_config)
    logger.info("Loading dataset from %s", base_data_dir)

    # Feature mode (sequence conditions) loads precomputed ConvNeXt features
    # instead of images; the frame source is a FeatureForceDataset whose
    # metadata records the original source_data_dir for split validation.
    seq_cfg = config["data"].get("sequence") or {}
    feature_mode = bool(seq_cfg.get("enabled")) and \
        str(seq_cfg.get("mode", "image")).lower() == "feature"
    dataset_cls = FeatureForceDataset if feature_mode else ForceDataset

    try:  # Create the base dataset; subsets will point to it.
        dataset = dataset_cls(
            data_dir=base_data_dir,
            transform=None,
            use_mmap=use_mmap,
            cache_data=cache_data,
            dataset_selection=enable_dataset_selection,
            cache_config=cache_config,
        )
    except FileNotFoundError as e:
        if "metadata" in str(e).lower():
            logger.error("Dataset error: %s", e)
            logger.error(
                "Please ensure the dataset has been preprocessed by Deform_post."
            )
        raise
    except ValueError as e:
        logger.error("Dataset configuration error: %s", e)
        raise
    
    # Synchronize normalization settings so they match preprocessing.
    metadata = getattr(dataset, "metadata", None)
    if isinstance(metadata, dict) and metadata:
        normalize_flag = metadata.get("normalize_forces")
        # The metadata states whether force vectors were normalized; 
        # overwrite the config to match.
        if normalize_flag is not None:
            config.setdefault("data", {})
            config["data"]["normalize_forces"] = normalize_flag
            logger.info(
                "Sync normalize_forces from metadata: %s", normalize_flag
            )
        # Only when normalization occurred and scale factors are present do we
        # propagate the scale settings; otherwise this branch is skipped.
        if normalize_flag and metadata.get("force_normalization"):
            config["data"]["force_normalization"] = metadata["force_normalization"]
            logger.info(
                "Sync force_normalization scales from metadata: %s",
                metadata["force_normalization"],
            )
    
    # Resolve the split file path, accepting filenames or explicit paths.
    if split_file is None:
        # Fall back to the configured filename when omitted.
        split_candidate = config["data"].get(
            "split_file", "dataset_split.json"
        )
    else:  # Use the path provided by the caller.
        split_candidate = split_file

    project_root = Path(__file__).resolve().parents[2]
    # Convert to Path for consistent checks.
    candidate_path = Path(split_candidate)

    if candidate_path.is_absolute():  # Absolute paths can be used directly.
        resolved_split_path = candidate_path
    else:
        if candidate_path.exists():
            # Respect files in the current working directory.
            resolved_split_path = candidate_path.resolve()
        else:
            candidate_under_root = project_root / candidate_path
            if candidate_under_root.exists():
                # Look under the project root for matching files.
                resolved_split_path = candidate_under_root
            elif candidate_path.parent != Path("."):
                # Preserve sub-directory structure 
                # when the file is not directly under the root.
                resolved_split_path = candidate_under_root
            else:
                # Default to the configs directory 
                # when only a filename is provided.
                resolved_split_path = project_root / "configs" / candidate_path.name

    split_file_path = resolved_split_path
    logger.info("Using dataset split file: %s", split_file_path)

    if not split_file_path.exists():
        error_msg = (
            f"Dataset split file not found: {split_file_path}. "
            "Data splitting must be performed first. Please run: "
            "python main.py --mode split"
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    logger.info("Loading dataset split from: %s", split_file_path)

    try:
        # In feature mode the split was authored against the original merged
        # dir; validate against the recorded source so the same by-sequence
        # splits apply unchanged (global frame indexing is preserved).
        split_validate_dir = (
            getattr(dataset, "metadata", {}).get("source_data_dir")
            or dataset.data_dir
        )
        train_indices, val_indices, test_indices = load_split(
            str(split_file_path),
            data_dir=split_validate_dir,
            validate=True,
        )
    except ValueError as e:
        logger.error("Split compatibility error: %s", e)
        logger.error(
            "Please regenerate the split file for the current dataset."
        )
        raise

    if not train_indices or not val_indices or not test_indices:
        error_msg = (
            f"Invalid split file: {split_file_path}. Missing or empty "
            "train/validation/test indices. Please regenerate the split file "
            "with: python main.py --mode split"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(
        "Dataset split - Train: %s, Val: %s, Test: %s",
        len(train_indices),
        len(val_indices),
        len(test_indices),
    )

    # Sequence (clip) mode: window CONSECUTIVE frames within each sequence using
    # the by-sequence index, so the same by-sequence splits drive both the
    # single-image and the sequence conditions with no temporal leakage. The
    # default collate stacks per-window (T, ...) tensors to (B, T, ...).
    # (seq_cfg / feature_mode were resolved above, before dataset construction.)
    if seq_cfg.get("enabled", False):
        from .sequence_dataset import SequenceDataset, load_sequence_ranges

        seq_ranges = load_sequence_ranges(dataset.data_dir)
        window_length = int(seq_cfg["window_length"])
        stride = int(seq_cfg.get("stride", window_length))
        include_tail = bool(seq_cfg.get("include_tail", True))
        # Features are pre-encoded (and pre-normalized at precompute time), so no
        # image transform is applied in feature mode.
        seq_transform = None if feature_mode else transform
        logger.info(
            "Sequence mode (%s): window_length=%d stride=%d include_tail=%s",
            "feature" if feature_mode else "image",
            window_length, stride, include_tail,
        )

        def _build_sequence(indices):
            return SequenceDataset(
                frame_source=dataset,
                subset_indices=indices,
                seq_ranges=seq_ranges,
                window_length=window_length,
                stride=stride,
                transform=seq_transform,
                include_tail=include_tail,
            )

        train_dataset = _build_sequence(train_indices)
        val_dataset = _build_sequence(val_indices)
        test_dataset = _build_sequence(test_indices)
        logger.info(
            "Sequence windows - Train: %d, Val: %d, Test: %d",
            len(train_dataset), len(val_dataset), len(test_dataset),
        )
    else:
        train_dataset = SubsetDataset(dataset, train_indices, transform=transform)
        val_dataset = SubsetDataset(dataset, val_indices, transform=transform)
        test_dataset = SubsetDataset(dataset, test_indices, transform=transform)

    prefetch_arg = prefetch_factor if num_workers > 0 else None
    persistent_arg = persistent_workers if num_workers > 0 else False

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_arg,
        persistent_workers=persistent_arg,
        drop_last=True,  # Drop incomplete batches to keep gradient steps consistent.
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_arg,
        persistent_workers=persistent_arg,
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_arg,
        persistent_workers=persistent_arg,
    )

    logger.info(
        "Created data loaders: train=%s batches, val=%s batches, test=%s batches",
        len(train_loader),
        len(val_loader),
        len(test_loader),
    )
    logger.info("Batch size: %s", batch_size)

    return train_loader, val_loader, test_loader
