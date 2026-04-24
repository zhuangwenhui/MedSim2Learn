"""Splitter module.
===================
Provides utilities to build hold-out and cross-validation dataset partitions.
"""

import os
import json
import logging
import torch
import time
import hashlib
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .dataset import ForceDataset

logger = logging.getLogger(__name__)


# =========================================================================
# Pre-split helpers
# =========================================================================
def _get_split_ratios(config: Dict[str, Any]) -> Tuple[float, float, float]:
    """Return train/validation/test ratios defined in the configuration.

    Args:
        config: Full configuration dictionary.

    Returns:
        Tuple with training, validation, and test ratios in that order.

    Raises:
        ValueError: If ratios are missing, invalid, or do not add up to one.
    """
    data_config = config["data"]
    # Ensure the configuration provides the split_ratios map.
    if "split_ratios" not in data_config:
        raise ValueError(
            "Missing 'split_ratios' configuration in config file. "
            "Please add complete split_ratios configuration with "
            "'train', 'val', and 'test' keys."
        )

    split_ratios = data_config["split_ratios"]
    # Ensure ratios are provided as a mapping so required keys can be validated.
    if not isinstance(split_ratios, dict):
        raise ValueError(
            "Invalid 'split_ratios' configuration. Must be a dictionary with "
            "'train', 'val', and 'test' keys."
        )

    # Ensure every required ratio key is present.
    required_keys = ["train", "val", "test"]
    missing_keys = [key for key in required_keys if key not in split_ratios]
    if missing_keys:
        raise ValueError(
            f"Missing required keys in split_ratios: {missing_keys}. "
            f"Please provide values for all of: {required_keys}"
        )

    train_ratio = split_ratios["train"]
    val_ratio = split_ratios["val"]
    test_ratio = split_ratios["test"]

    # Validate that each ratio is numeric and within range.
    for name, ratio in [
        ("train", train_ratio), ("val", val_ratio), ("test", test_ratio)
    ]:
        if not isinstance(ratio, (int, float)) or ratio < 0 or ratio > 1:
            raise ValueError(
                f"Invalid {name} ratio: {ratio}. Must be a number between 0 and 1."
            )

    # Confirm the ratios sum to one to avoid drift.
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(
            "Split ratios must sum to 1.0, but got "
            f"{total_ratio}. Current ratios: train={train_ratio}, "
            f"val={val_ratio}, test={test_ratio}. Please correct the "
            "configuration file."
        )

    return train_ratio, val_ratio, test_ratio

# =========================================================================
# Split execution
# =========================================================================
def _load_dataset_for_split(config: Dict[str, Any]) -> "ForceDataset":
    """Load the dataset described by *config* and validate it is non-empty.

    Args:
        config: Full configuration dictionary.

    Returns:
        Loaded :class:`ForceDataset` instance.

    Raises:
        RuntimeError: If the dataset is empty.
    """
    data_dir = config["data"]["data_dir"]
    enable_selection = config["data"].get("enable_dataset_selection", True)
    logger.info("Loading dataset: %s", data_dir)
    dataset = ForceDataset(
        data_dir=data_dir,
        transform=None,
        dataset_selection=enable_selection,
    )
    dataset_size = len(dataset)
    logger.info("Dataset size: %d", dataset_size)
    if dataset_size == 0:
        raise RuntimeError(
            f"Dataset is empty (found 0 samples in {dataset.data_dir}). "
            "Please check the data directory for valid .pt batch files."
        )
    return dataset

def _compute_split_sizes(
    dataset_size: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> Tuple[int, int, int]:
    """Compute rounded split sizes and correct rounding drift.

    Args:
        dataset_size: Total number of samples available.
        train_ratio: Desired fraction assigned to the training split.
        val_ratio: Desired fraction assigned to the validation split.
        test_ratio: Desired fraction assigned to the test split.

    Returns:
        Tuple with the sample counts for training, validation, and test splits.
    """
    train_size = round(dataset_size * train_ratio)
    val_size = round(dataset_size * val_ratio)
    test_size = dataset_size - train_size - val_size
    if test_size < 0:
        # Shift deficit to training so counts remain non-negative.
        train_size += test_size
        test_size = 0
    elif test_size > round(dataset_size * test_ratio) + 1:
        # Return surplus so the test split stays near its target ratio.
        adjustment = test_size - round(dataset_size * test_ratio)
        train_size += adjustment
        test_size -= adjustment

    return train_size, val_size, test_size

def holdout_split_dataset(config: Dict[str, Any]) -> None:
    """Create a random hold-out split for training, validation, and testing.

    Args:
        config: Full configuration dictionary.

    Raises:
        ValueError: If the dataset directory is empty or config is invalid.
    """
    train_ratio, val_ratio, test_ratio = _get_split_ratios(config)
    logger.info(
        "Dataset split ratios: training=%.2f, validation=%.2f, test=%.2f",
        train_ratio,
        val_ratio,
        test_ratio,
    )

    dataset = _load_dataset_for_split(config)
    dataset_size = len(dataset)

    train_size, val_size, test_size = _compute_split_sizes(
        dataset_size, train_ratio, val_ratio, test_ratio
    )
    logger.info(
        "Split size: training=%d, validation=%d, test=%d",
        train_size,
        val_size,
        test_size,
    )

    logger.info("Using random splitting (Hold-out validation)")
    indices = torch.randperm(dataset_size).tolist()
    train_indices = indices[:train_size]
    val_indices = indices[train_size : train_size + val_size]
    test_indices = indices[train_size + val_size :]
    logger.info(
        "Splitting completed: training=%d, validation=%d, test=%d",
        len(train_indices),
        len(val_indices),
        len(test_indices),
    )

    # Read destination path from the data configuration.
    split_file_setting = config["data"]["split_file"]
    if not split_file_setting:
        raise ValueError(
            "Configuration is missing 'data.split_file'. "
            "Please provide an explicit path for saving dataset splits."
        )

    # Wrap the configured value as a Path for later checks.
    split_path = Path(split_file_setting)
    if not split_path.is_absolute():
        # Resolve relative paths against KiDKNet/configs.
        configs_dir = Path(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        ) / "configs"
        split_path = configs_dir / split_file_setting

    if not split_path.parent.exists():
        raise FileNotFoundError(
            f"Split file directory does not exist: {split_path.parent}. "
            "Please create it or update 'data.split_file' accordingly."
        )

    # Collect split metadata so future runs can reuse this partition.
    split_data = {
        "train_indices": train_indices,
        "val_indices": val_indices,
        "test_indices": test_indices,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
        "dataset_size": dataset_size,
        "data_dir": dataset.data_dir,
        "creation_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "config_hash": hashlib.md5(
            str(config.get("data", {})).encode()
        ).hexdigest(),
        "dataset_stats": {
            "train_samples": len(train_indices),
            "val_samples": len(val_indices),
            "test_samples": len(test_indices),
        },
    }

    # Persist the split metadata as JSON and log the destination file.
    logger.info("Saving split results to: %s", split_path)
    with open(split_path, "w", encoding="utf-8") as f:
        json.dump(split_data, f, indent=2)


def cross_validation_splits(
    config: Dict[str, Any], n_folds: int = 5, save_to_file: bool = True
) -> List[Tuple[List[int], List[int]]]:
    """Create cross-validation folds using random assignment.

    Args:
        config: Full configuration dictionary.
        n_folds: Number of folds to produce.
        save_to_file: Whether to persist each fold to disk.

    Returns:
        List of ``(train_indices, val_indices)`` tuples for every fold.
    """
    dataset = _load_dataset_for_split(config)
    dataset_size = len(dataset)

    logger.info("Using random splitting for cross-validation")
    indices = torch.randperm(dataset_size).tolist()
    fold_size = dataset_size // n_folds
    remainder = dataset_size % n_folds
    folds: List[Tuple[List[int], List[int]]] = []

    for fold in range(n_folds):
        start_idx = fold * fold_size + min(fold, remainder)
        end_idx = (fold + 1) * fold_size + min(fold + 1, remainder)
        val_indices = indices[start_idx:end_idx]
        val_set = set(val_indices)
        train_indices = [idx for idx in indices if idx not in val_set]
        folds.append((train_indices, val_indices))

    for fold, (train_indices, val_indices) in enumerate(folds):
        logger.info(
            "Fold %d: training=%d, validation=%d",
            fold + 1,
            len(train_indices),
            len(val_indices),
        )

    if save_to_file:
        configs_dir = (
            Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            / "configs"
            / "cv_splits"
        )
        configs_dir.mkdir(parents=True, exist_ok=True)

        for fold, (train_indices, val_indices) in enumerate(folds):
            split_file = configs_dir / f"cv_fold_{fold + 1}_of_{n_folds}.json"
            split_data = {
                "fold": fold + 1,
                "n_folds": n_folds,
                "train_indices": train_indices,
                "val_indices": val_indices,
                "dataset_size": dataset_size,
                "data_dir": dataset.data_dir,
                "creation_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "config_hash": hashlib.md5(
                    str(config.get("data", {})).encode()
                ).hexdigest(),
            }
            with open(split_file, "w", encoding="utf-8") as f:
                json.dump(split_data, f, indent=2)
            logger.info(
                "Saved fold %d split results to: %s", fold + 1, split_file
            )

    return folds

# =========================================================================
# Post-split validation and loading
# =========================================================================
def _validate_split_compatibility(
    split_data: Dict[str, Any], data_dir: str
) -> bool:
    """Confirm that saved split metadata matches the active dataset.

    Args:
        split_data: Split metadata loaded from JSON.
        data_dir: Directory containing the dataset currently in use.

    Returns:
        True if metadata matches the dataset directory and contents.

    Raises:
        ValueError: If the saved split was generated for a different dataset.
    """
    # Verify the split file was produced for the same dataset directory.
    split_data_dir = split_data.get("data_dir")
    if not split_data_dir:
        raise ValueError(
            "Split metadata is missing 'data_dir'; please regenerate the "
            "split file."
        )

    split_data_path = Path(split_data_dir).resolve()
    current_data_path = Path(data_dir).resolve()
    if split_data_path != current_data_path:
        raise ValueError(
            f"Split data was created for directory '{split_data_dir}' "
            f"but current directory is '{data_dir}'. The saved split is "
            "incompatible with this dataset. Regenerate the split before "
            "continuing."
        )
        
    # Ensure the stored dataset size matches the active dataset.
    expected_size = split_data.get("dataset_size", 0)
    metadata_path = current_data_path / "metadata.yaml"
    if not metadata_path.exists():
        raise ValueError(
            f"Metadata file not found at {metadata_path}. "
            "Please ensure the dataset has been preprocessed correctly."
        )

    with open(metadata_path, "r", encoding="utf-8") as meta_file:
        metadata = yaml.safe_load(meta_file)

    actual_size = metadata.get("total_samples")
    if actual_size is None:
        raise ValueError(
            f"Metadata file {metadata_path} is missing 'total_samples'. "
            "Please regenerate preprocessing output."
        )

    if expected_size and expected_size != actual_size:
        raise ValueError(
            f"Split file expects dataset size {expected_size}, "
            f"but metadata reports {actual_size}. The split is incompatible."
        )

    # Confirm that batch files exist in the dataset directory.
    pt_files = [
        f
        for f in os.listdir(data_dir)
        if f.endswith(".pt") and "batch" in f
    ]
    
    if not pt_files:
        raise ValueError(
            f"No batch files found in current directory: {data_dir}. "
            "Please verify the directory contains valid preprocessed data."
        )
    
    logger.info(
        "Split validation passed. Using split created at %s",
        split_data.get("creation_time", "unknown time"),
    )

    return True

def load_split(
    split_file: str, data_dir: Optional[str] = None, validate: bool = True
) -> Tuple[List[int], List[int], List[int]]:
    """Load saved split indices from disk.

    Args:
        split_file: Path to the JSON split file.
        data_dir: Dataset directory to validate against, if provided.
        validate: Whether to verify compatibility with the active dataset.

    Returns:
        Tuple containing training, validation, and test index lists.

    Raises:
        FileNotFoundError: If the split file does not exist.
        ValueError: If the split metadata is incompatible with the dataset.
    """
    if not os.path.exists(split_file):
        raise FileNotFoundError(
            f"Dataset split file does not exist: {split_file}. "
            "Please run data splitting first with "
            "'python main.py --mode split' to generate the split file."
        )
    
    logger.info("Loading split results from file: %s", split_file)
    with open(split_file, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    train_indices = split_data.get("train_indices", [])
    val_indices = split_data.get("val_indices", [])
    test_indices = split_data.get("test_indices", [])

    # Validate compatibility when requested
    if validate and data_dir:
        _validate_split_compatibility(split_data, data_dir)

    logger.info(
        "Loaded indices: training=%d, validation=%d, test=%d",
        len(train_indices),
        len(val_indices),
        len(test_indices),
    )

    return train_indices, val_indices, test_indices
