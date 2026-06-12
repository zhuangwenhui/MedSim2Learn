"""Vision-force pair serialization: PNG dir + labels CSV -> .pt batches.

DataPreprocessor pairs each rendered PNG with its force row by stem
(PNG stem == SampleID) and writes torch batches plus a metadata.yaml that
records every normalization decision. This is the non-interactive core of the
original sim2vfp implementation; every setting is supplied programmatically
and serialize() raises instead of prompting when something is missing. The
processing path (sorted PNG order, PIL resize, /255 scaling, batching,
metadata fields) is kept byte-compatible with the historical .pt outputs.
"""

import asyncio
import concurrent.futures
import os
import time

import numpy as np
import pandas as pd
import torch
import yaml
from PIL import Image
from tqdm import tqdm


def parse_resize(spec):
    """Parse a resize spec into a (W, H) int tuple, or None when unset.

    Accepts "WxH" (e.g. "224x224") or a single int "N" -> (N, N).
    """
    if spec is None:
        return None
    s = str(spec).strip().lower()
    if "x" in s:
        parts = s.split("x")
        if len(parts) != 2:
            raise ValueError(f"invalid resize {spec!r}: expected WxH or an int")
        w, h = int(parts[0]), int(parts[1])
    else:
        w = h = int(s)
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid resize {spec!r}: dimensions must be positive")
    return (w, h)


class DataPreprocessor:
    """Serialize vision-force pairs from rendered images and a force CSV."""

    def __init__(self):
        self.dataset_dir = None
        self.image_dir = None
        self.output_dir = None
        self.batch_size = 2000

        # Serialization settings
        self.do_resize = None
        self.target_size = None
        self.normalize_images = None
        self.mean = None
        self.std = None
        self.normalize_forces = None
        self.force_normalization = None

        # Results
        self.metadata = None
        self.results = None

        # Cache for tensor normalization parameters
        self._tensor_cache = {}

    def set_dataset_directory(self, dataset_dir):
        """Set the directory holding the (single) force label CSV."""
        self.dataset_dir = dataset_dir
        return self

    def set_image_directory(self, image_dir):
        """Set the directory containing rendered .png images."""
        self.image_dir = image_dir
        return self

    def set_output_directory(self, output_dir):
        """Set the output directory for serialized data."""
        self.output_dir = output_dir
        return self

    def set_batch_size(self, batch_size):
        """Set the batch size for serialization."""
        self.batch_size = batch_size
        return self

    def set_resize(self, do_resize, target_size=None):
        """Configure image resizing options."""
        self.do_resize = do_resize
        self.target_size = target_size
        return self

    def set_image_normalization(self, normalize_images, mean=None, std=None):
        """Configure image normalization (mean/std default to ImageNet)."""
        self.normalize_images = normalize_images
        if normalize_images:
            if mean is None:
                self.mean = torch.tensor(
                    [0.485, 0.456, 0.406], dtype=torch.float32
                )
            # Clone caller-provided tensors to avoid shared autograd
            # state and enforce dtype.
            elif isinstance(mean, torch.Tensor):
                self.mean = mean.clone().detach().to(dtype=torch.float32)
            else:
                self.mean = torch.tensor(mean, dtype=torch.float32)

            if std is None:
                self.std = torch.tensor(
                    [0.229, 0.224, 0.225], dtype=torch.float32
                )
            elif isinstance(std, torch.Tensor):
                self.std = std.clone().detach().to(dtype=torch.float32)
            else:
                self.std = torch.tensor(std, dtype=torch.float32)
        else:
            # Neutral parameters so downstream code can rely on the tensors.
            self.mean = torch.tensor([0, 0, 0], dtype=torch.float32)
            self.std = torch.tensor([1, 1, 1], dtype=torch.float32)
        return self

    def set_force_normalization(self, normalize_forces, scale_values=None):
        """Configure per-axis force scaling ({'x_scale','y_scale','z_scale'})."""
        self.normalize_forces = normalize_forces
        if normalize_forces and scale_values:
            self.force_normalization = scale_values
        return self

    def _load_force_data(self):
        """Load the single force CSV -> {SampleID: (fx, fy, fz)}."""
        csv_files = [f for f in os.listdir(self.dataset_dir) if f.endswith(".csv")]
        if not csv_files:
            raise FileNotFoundError(
                "No CSV file found in the dataset directory."
            )
        elif len(csv_files) > 1:
            raise ValueError(
                "Multiple CSV files found. Ensure only one CSV file exists."
            )

        csv_path = os.path.join(self.dataset_dir, csv_files[0])

        try:
            df = pd.read_csv(csv_path, engine="pyarrow")
        except Exception:
            df = pd.read_csv(csv_path)

        sample_ids = df["SampleID"].values
        forces = df[["force_x", "force_y", "force_z"]].values.astype(np.float32)

        return {sid: tuple(f) for sid, f in zip(sample_ids, forces)}

    def _process_image(self, image_path, target_size):
        """Process a single image and return the processed tensor."""
        cache_key = f"{target_size}_{self.normalize_images}"

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            if self.do_resize:
                img = img.resize(target_size)

            img_array = np.asarray(img, dtype=np.float32)

        img_tensor = torch.from_numpy(img_array)

        # Convert from HWC to CHW format (if needed)
        if img_tensor.dim() == 3 and img_tensor.shape[-1] == 3:
            img_tensor = img_tensor.permute(2, 0, 1)

        # In-place division for better memory efficiency
        if img_tensor.max() > 1.0:
            img_tensor.div_(255.0)

        if self.normalize_images:
            if cache_key not in self._tensor_cache:
                self._tensor_cache[cache_key] = {
                    "mean_view": self.mean.view(3, 1, 1),
                    "std_view": self.std.view(3, 1, 1),
                }

            cached_params = self._tensor_cache[cache_key]
            img_tensor = (img_tensor - cached_params["mean_view"]) / cached_params["std_view"]

        return img_tensor

    def _normalize_force(self, force_values):
        """Force tuple -> tensor, scaled per axis when normalization is on."""
        force_tensor = torch.tensor(force_values, dtype=torch.float32)

        if self.normalize_forces and self.force_normalization:
            if not hasattr(self, "_force_scales"):
                self._force_scales = torch.tensor([
                    self.force_normalization["x_scale"],
                    self.force_normalization["y_scale"],
                    self.force_normalization["z_scale"],
                ], dtype=torch.float32)
            force_tensor = force_tensor / self._force_scales

        return force_tensor

    async def _save_batch_async(self, batch, batch_count):
        """Save one batch via a thread pool so the event loop keeps processing."""
        batch_path = os.path.join(
            self.output_dir, f"preprocessed_batch_{batch_count:04d}.pt"
        )

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            await loop.run_in_executor(
                executor, torch.save, batch, batch_path
            )

        print(f"[INFO] Saved batch to {batch_path} ({len(batch)} samples)")
        return batch_path

    def serialize(self):
        """Serialize vision-force pairs; all settings must be set beforehand."""
        if not self.dataset_dir or not self.image_dir or not self.output_dir:
            raise ValueError(
                "Dataset, image, and output directories must be set "
                "before serializing"
            )
        if (self.do_resize is None or self.normalize_images is None or
                self.normalize_forces is None):
            raise ValueError(
                "Call set_resize, set_image_normalization and "
                "set_force_normalization before serialize()"
            )

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        return asyncio.run(self._serialize_async())

    async def _serialize_async(self):
        """Concurrent serialization: semaphore-gated chunks, async batch saves."""
        start_time = time.time()

        force_dict = self._load_force_data()

        image_files = [f for f in os.listdir(self.image_dir) if f.endswith(".png")]
        image_files.sort()

        batch = []
        batch_count = 0
        matched_total = 0

        # Auto-detect image channels from first image
        first_image_path = (
            os.path.join(self.image_dir, image_files[0])
            if image_files else None
        )
        original_image_size = None
        if first_image_path:
            first_image = Image.open(first_image_path)
            original_image_size = first_image.size
            channels = len(first_image.getbands())
            print(
                f"[INFO] Detected {channels} channels in images. "
                f"Original size: {original_image_size}"
            )

        target_size = (
            self.target_size if self.do_resize else
            (original_image_size if original_image_size else (None, None))
        )

        # Semaphore bounds concurrent image tasks so memory stays in check.
        semaphore = asyncio.Semaphore(64)

        async def process_image_async(fname):
            """Pair one PNG with its force row; returns (sample, error)."""
            async with semaphore:
                sample_id = os.path.splitext(fname)[0]
                if sample_id not in force_dict:
                    return None, f"No force label for image: {sample_id}"

                image_path = os.path.join(self.image_dir, fname)
                try:
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                        img_tensor = await loop.run_in_executor(
                            executor,
                            self._process_image,
                            image_path,
                            target_size,
                        )
                        force_tensor = await loop.run_in_executor(
                            executor,
                            self._normalize_force,
                            force_dict[sample_id],
                        )

                    return {
                        "id": sample_id,
                        "image": img_tensor,
                        "force": force_tensor,
                    }, None
                except Exception as e:
                    return None, f"Failed to process {fname}: {e}"

        # Chunked processing keeps peak memory bounded while staying parallel.
        chunk_size = 200

        progress_bar = tqdm(
            total=len(image_files), desc="Serializing", unit="img"
        )

        for i in range(0, len(image_files), chunk_size):
            chunk = image_files[i:i + chunk_size]

            tasks = [process_image_async(fname) for fname in chunk]
            results = await asyncio.gather(*tasks)

            for result, error in results:
                if error:
                    progress_bar.write(f"[Warning] {error}")
                    continue
                if result:
                    batch.append(result)
                    matched_total += 1

                    if len(batch) >= self.batch_size:
                        await self._save_batch_async(batch, batch_count)
                        batch_count += 1
                        batch = []

            chunk_processed = min(len(chunk), len(image_files) - i)
            progress_bar.update(chunk_processed)

        progress_bar.close()

        if batch:
            await self._save_batch_async(batch, batch_count)
            batch_count += 1

        process_time = time.time() - start_time
        self.metadata = {
            "total_samples": matched_total,
            "batch_size": self.batch_size,
            "num_batches": batch_count,
            "original_image_size": (
                list(original_image_size) if original_image_size else None
            ),
            "image_size": list(target_size),
            "normalize_images": self.normalize_images,
            "normalize_forces": self.normalize_forces,
            "force_normalization": self.force_normalization,
            "image_mean": (
                self.mean.tolist() if self.normalize_images else None
            ),
            "image_std": (
                self.std.tolist() if self.normalize_images else None
            ),
            "dataset_name": os.path.basename(self.dataset_dir),
            "image_dir": os.path.basename(self.image_dir),
            "processing_time": process_time,
            "preprocess_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        metadata_path = os.path.join(self.output_dir, "metadata.yaml")
        with open(metadata_path, "w") as f:
            yaml.dump(self.metadata, f)

        samples_per_sec = (
            matched_total / process_time if process_time > 0 else 0
        )
        self.results = {
            "total_samples": matched_total,
            "batches": batch_count,
            "processing_time": process_time,
            "samples_per_sec": samples_per_sec,
            "metadata_path": metadata_path,
        }

        print(f"[SUCCESS] Total matched samples serialized: {matched_total}")
        print(
            f"[INFO] Processing time: {process_time:.2f} seconds, "
            f"Rate: {samples_per_sec:.2f} samples/sec"
        )
        print(f"[INFO] Metadata saved to: {metadata_path}")

        return self

    def get_metadata(self):
        """Get the metadata from the serialization process."""
        return self.metadata

    def get_results(self):
        """Get the results from the serialization process."""
        return self.results


def serialize_labels_dataset(png_dir, labels_csv, out_data_dir, resize=None):
    """Serialize PNG dir + labels.csv to preprocessed_batch_*.pt.

    DataPreprocessor expects exactly ONE CSV in its dataset dir with columns
    SampleID,force_x,force_y,force_z; the directory holding labels.csv must
    contain no other CSV (forces_model.csv belongs elsewhere). Images stay raw
    /255 floats (no normalization), matching the historical replay datasets.
    """
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
    dp.set_resize(bool(resize), tuple(resize) if resize else None)
    dp.set_image_normalization(False)
    dp.set_force_normalization(False)
    dp.serialize()
    res = dp.get_results()
    print(f"serialize: {res['total_samples']} samples, {res['batches']} batch(es) -> {out_data_dir}")
    return res


def _self_test():
    """parse_resize contract; raises AssertionError on failure."""
    assert parse_resize(None) is None
    assert parse_resize("224") == (224, 224)
    assert parse_resize("320x240") == (320, 240)
    assert parse_resize(" 224X224 ") == (224, 224)
    for bad in ("0", "1x2x3"):
        try:
            parse_resize(bad)
            raise AssertionError(f"parse_resize accepted invalid spec {bad!r}")
        except ValueError:
            pass
    print("dataset.serialize self-test PASS")
