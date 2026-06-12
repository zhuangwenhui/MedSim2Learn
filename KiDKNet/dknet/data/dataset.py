"""Dataset module.
===================
Provides utilities to load image-force pairs produced by the Deform_post pipeline (main.py serialize).
"""

import os
import time
import yaml
import logging
import torch
from torch.utils.data import Dataset
from typing import Dict, Any, List, Optional, Callable, Tuple

logger = logging.getLogger(__name__)


class ForceDataset(Dataset):
    """Dataset for paired images and forces exported by Deform_post."""
    def __init__(
        self,
        data_dir: str,
        transform: Optional[Callable] = None,
        use_mmap: bool = False,
        cache_data: bool = True,
        max_samples: Optional[int] = None,
        dataset_selection: bool = False,
        cache_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set up the loading policy for preprocessed batches.

        Args:
            data_dir: Path that holds preprocessed .pt files or dataset folders.
            transform: Optional transform applied to each image.
            use_mmap: True to enable memory mapped loading.
            cache_data: True to read all samples into RAM.
            max_samples: Optional cap on the number of samples to read.
            dataset_selection: True to choose a dataset interactively.
            cache_config: Optional cache options like pin_memory or dtype.
        """
        # Optional per-sample transform applied when reading a sample.
        self.transform = transform

        # Normalise cache configuration so downstream logic always reads from
        # self.cache_config.
        self.cache_config = cache_config.copy() if cache_config else {}
        # Control host-memory flags and cloning behaviour for cached tensors.
        self.cache_pin_memory = bool(
            self.cache_config.get("pin_memory", False)
        )
        self.clone_image_on_get = bool(
            self.cache_config.get("clone_image_on_get", False)
        )
        self.cache_clone_force = bool(
            self.cache_config.get("clone_force", False)
        )

        # Honour target dtype if the caller wishes to cache in BF16/FP16 etc.
        cache_dtype_name = self.cache_config.get("dtype")
        if cache_dtype_name:
            if not hasattr(torch, cache_dtype_name):
                raise ValueError(
                    f"Unsupported cache dtype '{cache_dtype_name}'"
                )
            self.cache_target_dtype = getattr(torch, cache_dtype_name)
        else:
            self.cache_target_dtype = None

        # Allow sharing the cached tensors across worker processes.
        self.cache_share_memory = bool(
            self.cache_config.get("share_memory", False)
        )

        # Determine loading strategy. Cache takes precedence when enabled.
        self.use_mmap = use_mmap
        self.cache_data = cache_data and not self.use_mmap

        if dataset_selection:
            self.data_dir = self._select_dataset(data_dir)
        else:
            self.data_dir = data_dir

        if not os.path.exists(self.data_dir):
            raise FileNotFoundError(
                f"Data directory does not exist: {self.data_dir}"
            )

        self._load_metadata()
        self.batch_files = sorted([
            f for f in os.listdir(self.data_dir)
            if f.endswith(".pt") and "batch" in f.lower()
        ])

        if not self.batch_files:
            raise FileNotFoundError(
                f"No .pt batch files found in {self.data_dir}"
            )
        logger.info(
            "Found %d batch files in %s", len(self.batch_files), self.data_dir
        )

        # Allocate placeholders that will be filled in by the chosen strategy.
        self.cache_images: Optional[torch.Tensor] = None
        self.cache_forces: Optional[torch.Tensor] = None
        self.cache_ids: Optional[List[Any]] = None
        self.sample_map: List[Tuple[str, int]] = []
        self.total_samples: int = 0
        if self.cache_data:
            self._load_all_data(max_samples=max_samples)
        else:
            self._build_sample_map(max_samples=max_samples)

    # =========================================================================
    # Common Methods (Strategy-Independent)
    # =========================================================================
    def _select_dataset(self, base_dir: str) -> str:
        """Resolve the dataset directory to use.

        Args:
            base_dir: Directory that may hold one or more datasets.

        Returns:
            str: Absolute path to the chosen dataset.

        Raises:
            FileNotFoundError: If the base directory or dataset is missing.
        """
        if not os.path.exists(base_dir):
            raise FileNotFoundError(f"Base directory missing: {base_dir}")

        candidates = [
            item for item in sorted(os.listdir(base_dir))
            if os.path.isdir(os.path.join(base_dir, item))
            and any(
                f.endswith(".pt")
                for f in os.listdir(os.path.join(base_dir, item))
            )
        ]

        if not candidates:
            raise FileNotFoundError(f"No .pt datasets under {base_dir}")
        # Auto-select if only one candidate
        if len(candidates) == 1:
            logger.info("Auto-selected dataset: %s", candidates[0])
            return os.path.join(base_dir, candidates[0])

        print("Available datasets:")
        for idx, name in enumerate(candidates, start=1):
            print(f"  {idx}: {name}")

        while True:
            try:
                choice = int(input("Select dataset (number): ").strip()) - 1
            except ValueError:
                print("Please enter a valid number.")
                continue
            # Return the selected dataset path
            if 0 <= choice < len(candidates):
                return os.path.join(base_dir, candidates[choice])

            print("Invalid selection. Please try again.")

    def _load_metadata(self) -> None:
        """Read metadata.yaml and validate required fields."""
        metadata_path = os.path.join(self.data_dir, "metadata.yaml")
        if not os.path.exists(metadata_path):
            raise FileNotFoundError(
                f"Required metadata file not found: {metadata_path}. "
                "Please ensure the Deform_post pipeline (main.py serialize) produced metadata.yaml."
            )
        # Load metadata
        try:
            with open(metadata_path, "r") as f:
                self.metadata = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Invalid YAML in metadata file {metadata_path}: {exc}"
            )
        # Validate essential metadata fields
        required_fields = ["total_samples", "batch_size", "normalize_images"]
        missing = [
            field for field in required_fields if field not in self.metadata
        ]
        if missing:
            raise ValueError(
                f"Metadata file is incomplete, missing fields: {missing}. "
                "Please regenerate the dataset using the Deform_post pipeline (main.py serialize)."
            )

    # =========================================================================
    # Full Cache Strategy Method
    # =========================================================================
    def _load_all_data(self, max_samples: Optional[int]) -> None:
        """Materialise the dataset in memory when cache mode is active.

        Args:
            max_samples: Optional cap on the number of samples to load.

        Raises:
            RuntimeError: If no samples were loaded into the cache.
        """
        start_time = time.time()

        total_limit = max_samples
        images: List[torch.Tensor] = []
        forces: List[torch.Tensor] = []
        ids: List[Any] = []
        # Prepare target dtypes so image/force tensors stay consistent.
        image_dtype = self.cache_target_dtype
        force_dtype = torch.float32

        for batch_file in self.batch_files:
            batch_path = os.path.join(self.data_dir, batch_file)
            batch_data = torch.load(
                batch_path,
                map_location="cpu",
                weights_only=False,
            )

            for sample in batch_data:
                # Stop once the desired number of samples has been cached.
                if total_limit is not None and len(ids) >= total_limit:
                    break

                image = sample["image"]
                if not isinstance(image, torch.Tensor):
                    image = torch.as_tensor(image)
                else:
                    image = image.detach()

                # Adopt the dtype of the first sample when none was preset.
                if image_dtype is None:
                    image_dtype = image.dtype
                image = image.to(dtype=image_dtype or torch.float32).contiguous()

                force = sample["force"]
                if not isinstance(force, torch.Tensor):
                    force = torch.as_tensor(force, dtype=force_dtype)
                else:
                    force = force.detach().to(dtype=force_dtype)

                images.append(image)
                forces.append(force)
                ids.append(sample.get("id"))

            if total_limit is not None and len(ids) >= total_limit:
                break

        if not images:
            raise RuntimeError(
                "No samples were loaded into cache; check dataset integrity."
            )

        # Consolidate per-sample lists into contiguous batch-major tensors.
        cache_images = torch.stack(images, dim=0)
        cache_forces = torch.stack(forces, dim=0)

        # Share backing storage across workers to avoid per-process duplication.
        if self.cache_share_memory:
            cache_images = cache_images.share_memory_()
            cache_forces = cache_forces.share_memory_()

        # Keep tensors in pinned host memory to speed up H2D transfers.
        if self.cache_pin_memory:
            cache_images = cache_images.pin_memory()
            cache_forces = cache_forces.pin_memory()

        self.cache_images = cache_images
        self.cache_forces = cache_forces
        self.cache_ids = ids
        self.total_samples = len(ids)

        elapsed = time.time() - start_time
        logger.info(
            "Cached %d samples into memory (dtype=%s, pin_memory=%s, "
            "share_memory=%s) in %.2fs",
            self.total_samples,
            str(cache_images.dtype),
            self.cache_pin_memory,
            self.cache_share_memory,
            elapsed,
        )

    # =========================================================================
    # On-Demand (mmap) Strategy Method
    # =========================================================================
    def _build_sample_map(self, max_samples: Optional[int]) -> None:
        """Create the index map used by on-demand loading.

        Args:
            max_samples: Optional cap on the number of samples to index.

        Raises:
            RuntimeError: If no samples were found across the batches.
        """
        for batch_file in self.batch_files:
            batch_path = os.path.join(self.data_dir, batch_file)
            batch_data = torch.load(
                batch_path,
                map_location="cpu",
                weights_only=False,
            )

            batch_size = len(batch_data)
            for local_idx in range(batch_size):
                if max_samples is not None and self.total_samples >= max_samples:
                    break
                self.sample_map.append((batch_file, local_idx))
                self.total_samples += 1

            del batch_data

            if max_samples is not None and self.total_samples >= max_samples:
                break

        if self.total_samples == 0:
            raise RuntimeError(
                "No samples discovered in dataset; check .pt files."
            )

    # =========================================================================
    # Common Methods
    # =========================================================================
    def __len__(self) -> int:
        """Return the number of available samples."""
        return self.total_samples

    def __getitem__(self, index: int) -> Dict[str, Any]:
        """Return a single sample, respecting the active loading strategy."""
        if index < 0 or index >= self.total_samples:
            raise IndexError(
                f"Index {index} out of range for dataset size "
                f"{self.total_samples}"
            )
        # Full Cache Strategy Method
        if self.cache_data:
            if (
                self.cache_images is None
                or self.cache_forces is None
                or self.cache_ids is None
            ):
                raise RuntimeError(
                    "Cache arrays were not initialised despite cache_data=True."
                )

            cache_images = self.cache_images
            cache_forces = self.cache_forces
            cache_ids = self.cache_ids

            image = cache_images[index]
            force = cache_forces[index]
            sample_id = cache_ids[index]

            if self.transform is not None:
                image = self.transform(image.clone())
            elif self.clone_image_on_get:
                image = image.clone()

            if self.cache_clone_force:
                force = force.clone()

            # Early return keeps the cache path isolated from the mmap branch.
            return {
                "id": sample_id,
                "image": image,
                "force": force,
            }
        # On-Demand (mmap) Strategy Method if self.cache_data is False
        batch_file, local_idx = self.sample_map[index]
        batch_path = os.path.join(self.data_dir, batch_file)
        batch_data = torch.load(
            batch_path,
            map_location="cpu",
            mmap=self.use_mmap,
            weights_only=False,
        )

        sample = batch_data[local_idx]

        image = sample["image"]
        if not isinstance(image, torch.Tensor):
            image = torch.as_tensor(image)
        else:
            image = image.clone()

        force = sample["force"]
        if not isinstance(force, torch.Tensor):
            force = torch.as_tensor(force, dtype=torch.float32)
        else:
            force = force.clone().to(dtype=torch.float32)

        processed = {
            "id": sample.get("id"),
            "image": image,
            "force": force,
        }

        if self.transform is not None:
            processed["image"] = self.transform(processed["image"])

        return processed


class SubsetDataset(Dataset):
    # Used by train/val/test splits to read samples from the base dataset.
    """Lightweight view of a ForceDataset filtered by index list."""
    def __init__(
        self,
        dataset: ForceDataset,
        indices: List[int],
        transform: Optional[Callable] = None,
    ) -> None:
        """Store the base dataset, index list, and optional extra transform.

        Args:
            dataset: Source ForceDataset instance.
            indices: Sample indices exposed by this subset.
            transform: Optional transform applied after the base dataset.
        """
        self.dataset = dataset
        self.indices = indices
        self.transform = transform

    def __len__(self) -> int:
        """Return the subset length."""
        return len(self.indices)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """Return a sample with the optional extra transform."""
        if idx < 0 or idx >= len(self.indices):
            raise IndexError(
                f"Index {idx} out of range for subset size {len(self.indices)}"
            )

        sample = self.dataset[self.indices[idx]]
        if self.transform and "image" in sample:
            sample = sample.copy()
            sample["image"] = self.transform(sample["image"].clone())

        return sample
