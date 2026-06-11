import os
import time
import argparse
import logging
import random
import math
import torch
import yaml
import numpy as np
import open3d as o3d
import multiprocessing as mp
import pandas as pd
from PIL import Image
from tqdm import tqdm
import asyncio
import concurrent.futures
import matplotlib.pyplot as plt
from typing import Optional, Dict, List, Tuple, Any


class CaptureConfig:
    """Configuration class for the Vision-Force Processor."""
    MAX_CAMERAS = 5

    def __init__(self) -> None:
        """Initialize default configuration paths and settings."""
        self.base_dir = os.path.abspath(os.path.dirname(__file__))
        # Pipeline data lives under the workspace DataFlow/ root, not next to the
        # source module. base_dir = Deform_post/, its parent = workspace root.
        self.dataflow_dir = os.path.join(
            os.path.dirname(self.base_dir), "DataFlow", "Deform_post"
        )

        self.camera_dir = os.path.join(
            self.dataflow_dir, "cameraSetupTest"
        )
        self.default_sample_ply = os.path.join(
            self.camera_dir, "plate.ply"
        )

        self.default_input = os.path.join(
            self.dataflow_dir, "Ori_deformation"
        )
        self.render_result_path = os.path.join(
            self.dataflow_dir, "Ren_png"
        )
        self.default_serialization_result_path = os.path.join(
            self.dataflow_dir, "preprocessed_data"
        )

        self.default_error_log = os.path.join(
            self.dataflow_dir, "render_errors", "error_log.csv"
        )


class CameraManager:
    """
    Manages camera views for 3D model preview and rendering.
    Handles saving, loading, and selecting camera configurations.
    """

    def __init__(self, camera_dir: str) -> None:
        self.camera_dir = camera_dir

    def _filter_files(
        self,
        directory: str,
        extension: str,
        exclude_pattern: Optional[str] = None
    ) -> List[str]:
        """
        Filter files in a directory by extension and optional exclusion pattern.

        Args:
            directory (str): Directory to search
            extension (str): File extension to filter by
            exclude_pattern (str, optional): Pattern to exclude from results

        Returns:
            list: Filtered file list
        """
        files = [f for f in os.listdir(directory) if f.endswith(extension)]
        if exclude_pattern:
            files = [f for f in files if exclude_pattern not in f]
        return sorted(files)

    def list_available_cameras(self) -> None:
        if not os.path.isdir(self.camera_dir):
            print("No camera directory found.")
            return

        files = self._filter_files(self.camera_dir, ".json")
        if not files:
            print("No saved camera views found.")
        else:
            print("Available saved camera views:")
            for f in files:
                print(f"  - {f}")

    def interactive_select_camera(self) -> Optional[str]:
        cam_list = self._filter_files(
            self.camera_dir, ".json", "(default)"
        )
        if not cam_list:
            print(
                "No saved camera views found. "
                "Please run --preview --preview-mode instance first."
            )
            return None

        while True:
            print("Available camera configs:")
            for i, cam in enumerate(cam_list):
                print(f"  {i+1}: {cam}")
            choice = input(
                "Choose a camera config (number, or 'q' to quit): "
            ).strip()

            if choice.lower() == 'q':
                return None

            try:
                cam_idx = int(choice) - 1
                if 0 <= cam_idx < len(cam_list):
                    return os.path.join(self.camera_dir, cam_list[cam_idx])
                else:
                    print("Invalid choice.")
            except ValueError:
                print("Invalid input.")

    def preview_ply_with_save(
        self, ply_path: str, mode: str = "instance"
    ) -> None:
        """
        Opens an Open3D preview window for a given mesh file. On exit, prompts the user
        to optionally save the current camera view as a JSON file.

        Camera views are saved to the `camera_dir` with filenames like:
        - camera_config_1.json
        - camera_config_1(default).json (if mode == "default")

        Args:
            ply_path (str): Path to the .ply mesh file for preview.
            mode (str): Either 'default' or 'instance', used to determine filename suffix.

        Returns:
            None
        """
        if not os.path.isfile(ply_path):
            logging.error(f"File does not exist: {ply_path}")
            return

        if not os.path.isdir(self.camera_dir):
            os.makedirs(self.camera_dir)

        mesh = o3d.io.read_triangle_mesh(ply_path)
        mesh.compute_vertex_normals()

        window_title = (
            "Default Preview" if mode == "default" else "Instance Preview"
        )
        vis = o3d.visualization.Visualizer()
        vis.create_window(window_name=window_title, width=800, height=800)
        vis.add_geometry(mesh)

        logging.info("Adjust the camera. Close the window when you're ready.")
        vis.run()

        choice = input(
            "Do you want to save the current camera view? (y/n): "
        ).strip().lower()
        if choice != 'y':
            logging.info("Camera view not saved.")
            vis.destroy_window()
            return

        if mode == "default":
            suffix = "(default).json"
            existing_files = self._filter_files(
                self.camera_dir, "(default).json"
            )
        else:
            suffix = ".json"
            existing_files = self._filter_files(
                self.camera_dir, ".json", "(default)"
            )

        existing_count = len(existing_files)

        if existing_count < CaptureConfig.MAX_CAMERAS:
            index = existing_count + 1
            filename = f"camera_config_{index}{suffix}"
        else:
            print("Maximum number of saved cameras reached.")
            print("Choose a number (1-5) to overwrite:")
            for i in range(1, CaptureConfig.MAX_CAMERAS + 1):
                print(f"{i}: camera_config_{i}{suffix}")
            overwrite_choice = input(
                "Enter number to overwrite or any other key to cancel: "
            )
            if overwrite_choice in [
                str(i) for i in range(1, CaptureConfig.MAX_CAMERAS + 1)
            ]:
                index = int(overwrite_choice)
                filename = f"camera_config_{index}{suffix}"
            else:
                logging.info("Camera view not saved.")
                vis.destroy_window()
                return

        save_path = os.path.join(self.camera_dir, filename)
        view_ctl = vis.get_view_control()
        param = view_ctl.convert_to_pinhole_camera_parameters()
        o3d.io.write_pinhole_camera_parameters(save_path, param)
        logging.info(f"Camera view saved to: {save_path}")

        vis.destroy_window()

    def preview_with_camera_params(
        self, ply_path: str, cam_json_path: str
    ) -> None:
        """
        Previews a .ply mesh using a pre-defined camera configuration (.json).

        This is used for confirmation before rendering or pipeline execution.

        Args:
            ply_path (str): Path to the .ply mesh file to preview.
            cam_json_path (str): Path to the saved camera configuration JSON file.

        Returns:
            None
        """
        mesh = o3d.io.read_triangle_mesh(ply_path)
        mesh.compute_vertex_normals()

        vis = o3d.visualization.Visualizer()
        vis.create_window(
            window_name="Preview with Camera Params", width=800, height=800
        )
        vis.add_geometry(mesh)

        if cam_json_path and os.path.exists(cam_json_path):
            param = o3d.io.read_pinhole_camera_parameters(cam_json_path)
            vis.get_view_control().convert_from_pinhole_camera_parameters(param)
        else:
            print(
                f"Camera config {cam_json_path} not found. "
                "Using default view."
            )

        vis.run()
        vis.destroy_window()

    def preview_random_ply_with_camera(
        self, dataset_dir: str, cam_json_path: str
    ) -> None:
        """
        Randomly selects one .ply file in the dataset and previews it with the given camera parameters.

        Args:
            dataset_dir (str): Path to dataset directory under Ori_deformation containing .ply files.
            cam_json_path (str): Path to saved camera_config_*.json file.

        Returns:
            None
        """
        ply_files = [f for f in os.listdir(dataset_dir) if f.lower().endswith(".ply")]
        if not ply_files:
            print("No .ply files found in dataset.")
            return

        chosen_file = random.choice(ply_files)
        full_path = os.path.join(dataset_dir, chosen_file)
        print(f"Previewing sample: {chosen_file}")

        self.preview_with_camera_params(full_path, cam_json_path)

    def interactive_render_confirmation(self) -> str:
        """Asks the user whether to proceed with batch rendering after preview."""
        while True:
            choice = input(
                "Proceed to render all .ply files with this camera? (y/n/q): "
            ).strip().lower()
            if choice in ['y', 'n', 'q']:
                return choice
            else:
                print(
                    "Invalid input. Enter 'y' to proceed, 'n' to choose "
                    "another view, or 'q' to quit."
                )


class Renderer:
    """
    Handles rendering of 3D .ply models to 2D .png images.
    Supports both single and batch processing with multiprocessing.
    """
    
    def __init__(self) -> None:
        self.ply_dir: Optional[str] = None
        self.save_dir: Optional[str] = None
        self.cam_json_path: Optional[str] = None
        self.error_log_path: Optional[str] = None
        self.max_workers: int = 8
        self.results: Optional[Dict[str, Any]] = None
    
    def set_source(self, ply_dir):
        """Set the source directory containing .ply files."""
        self.ply_dir = ply_dir
        return self
    
    def set_output(self, save_dir):
        """Set the output directory for rendered .png images."""
        self.save_dir = save_dir
        return self
    
    def set_camera(self, cam_json_path):
        """Set the camera configuration to use for rendering."""
        self.cam_json_path = cam_json_path
        return self
    
    def set_error_log(self, error_log_path):
        """Set the path for error logging."""
        self.error_log_path = error_log_path
        return self
    
    def set_workers(self, max_workers):
        """Set the number of worker processes for parallel rendering."""
        self.max_workers = max_workers
        return self
    
    @staticmethod
    def render_single_ply(
        args: Tuple[str, str, Optional[str]]
    ) -> Tuple[str, str]:
        """
        Renders a single .ply file to a .png image using Open3D in headless mode.

        Args:
            args (tuple): A tuple of:
                - filepath (str): Path to the input .ply file.
                - save_path (str): Path to save the rendered .png.
                - cam_json_path (str or None): Path to camera config file.

        Returns:
            tuple: (filepath, status), where status is 'success' or an error message.
        """
        filepath, save_path, cam_json_path = args
        try:
            vis = o3d.visualization.Visualizer()
            vis.create_window(visible=False, width=800, height=800)
            mesh = o3d.io.read_triangle_mesh(filepath)
            mesh.compute_vertex_normals()

            vis.add_geometry(mesh)
            if cam_json_path and os.path.exists(cam_json_path):
                param = o3d.io.read_pinhole_camera_parameters(cam_json_path)
                vis.get_view_control().convert_from_pinhole_camera_parameters(param)

            vis.update_renderer()
            vis.poll_events()
            vis.capture_screen_image(save_path)
            vis.destroy_window()
            return (filepath, "success")
        except Exception as e:
            return (filepath, f"error: {str(e)}")
    
    def _get_ply_files(self, directory: str) -> List[str]:
        """Get list of .ply files in directory."""
        return [f for f in os.listdir(directory) if f.lower().endswith(".ply")]
    
    def render(self):
        """Batch render all .ply files to .png images using multiprocessing."""
        if not self.ply_dir or not self.save_dir:
            raise ValueError(
                "Source and output directories must be set before rendering"
            )
        
        if not os.path.isdir(self.save_dir):
            os.makedirs(self.save_dir)

        ply_files = self._get_ply_files(self.ply_dir)
        if not ply_files:
            logging.warning(f"No .ply files found in {self.ply_dir}")
            return self

        task_list = []
        for filename in ply_files:
            filepath = os.path.join(self.ply_dir, filename)
            outname = os.path.splitext(filename)[0] + ".png"
            save_path = os.path.join(self.save_dir, outname)
            task_list.append((filepath, save_path, self.cam_json_path))

        logging.info(
            f"Launching {len(task_list)} rendering tasks with "
            f"{self.max_workers} processes..."
        )

        error_log = []
        with mp.get_context("spawn").Pool(processes=self.max_workers) as pool:
            for filepath, status in tqdm(
                pool.imap_unordered(self.render_single_ply, task_list),
                total=len(task_list),
                desc="Rendering"
            ):
                if "error" in status:
                    error_log.append(f"{os.path.basename(filepath)},{status}")

        if self.error_log_path and error_log:
            os.makedirs(os.path.dirname(self.error_log_path), exist_ok=True)
            with open(self.error_log_path, "w") as f:
                f.write("filename,error_message\n")
                f.write("\n".join(error_log))

        # Store results for later retrieval
        self.results = {
            "total": len(task_list),
            "successful": len(task_list) - len(error_log),
            "errors": len(error_log),
            "error_details": error_log
        }

        logging.info(
            f"Rendering completed: {self.results['successful']}/"
            f"{self.results['total']} successful"
        )
        return self
    
    def get_results(self) -> Optional[Dict[str, Any]]:
        """Get the results of the rendering operation."""
        return self.results
    

class DataPreprocessor:
    """
    Data preprocessing class for dataset operations like selecting subdirectories
    and serializing vision-force pairs.
    """
    
    def __init__(self) -> None:
        self.base_input_dir: Optional[str] = None
        self.dataset_dir: Optional[str] = None
        self.image_dir: Optional[str] = None
        self.output_dir: Optional[str] = None
        self.batch_size: int = 2000

        # Serialization settings
        self.do_resize: Optional[bool] = None
        self.target_size: Optional[Tuple[int, int]] = None
        self.normalize_images: Optional[bool] = None
        self.mean: Optional[torch.Tensor] = None
        self.std: Optional[torch.Tensor] = None
        self.normalize_forces: Optional[bool] = None
        self.force_normalization: Optional[Dict[str, float]] = None

        # Results
        self.metadata: Optional[Dict[str, Any]] = None
        self.results: Optional[Dict[str, Any]] = None

        # Attributes for caching frequently used computations
        # Cache for tensor normalization parameters
        self._tensor_cache: Dict[str, Any] = {}

    def set_base_directory(self, base_input_dir):
        """Set the base input directory for datasets."""
        self.base_input_dir = base_input_dir
        return self
    
    def set_dataset_directory(self, dataset_dir):
        """Set the selected dataset directory."""
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
        """
        Configure image normalization options.
        
        Args:
            normalize_images (bool): Whether to normalize images
            mean (list/tensor, optional): Mean values for normalization
            std (list/tensor, optional): Standard deviation values for normalization
            
        Returns:
            self: For method chaining
        """
        self.normalize_images = normalize_images
        if normalize_images:
            if mean is None:
                # ImageNet defaults
                self.mean = torch.tensor(
                    [0.485, 0.456, 0.406], dtype=torch.float32
                )
            # Clone caller-provided tensors to avoid shared autograd
            # state and enforce dtype.
            elif isinstance(mean, torch.Tensor):
                self.mean = mean.clone().detach().to(dtype=torch.float32)
            else:
                # Accept plain Python sequences and coerce them into
                # float tensors.
                self.mean = torch.tensor(mean, dtype=torch.float32)

            if std is None:
                # ImageNet defaults
                self.std = torch.tensor(
                    [0.229, 0.224, 0.225], dtype=torch.float32
                )
            # Mirror the cloning logic for standard deviation tensors.
            elif isinstance(std, torch.Tensor):
                self.std = std.clone().detach().to(dtype=torch.float32)
            else:
                self.std = torch.tensor(std, dtype=torch.float32)
        else:
            # Provide neutral parameters so downstream code can rely on
            # tensor attributes.
            self.mean = torch.tensor([0, 0, 0], dtype=torch.float32)
            self.std = torch.tensor([1, 1, 1], dtype=torch.float32)
        return self
    
    def set_force_normalization(self, normalize_forces, scale_values=None):
        """
        Configure force normalization options.
        
        Args:
            normalize_forces (bool): Whether to normalize force values
            scale_values (dict, optional): Dictionary with 'x_scale',
                'y_scale', 'z_scale' keys
            
        Returns:
            self: For method chaining
        """
        self.normalize_forces = normalize_forces
        if normalize_forces and scale_values:
            self.force_normalization = scale_values
        return self
    
    def choose_dataset(self):
        if not self.base_input_dir:
            raise ValueError("Base input directory not specified")
            
        subdirs = [
            d for d in os.listdir(self.base_input_dir)
            if os.path.isdir(os.path.join(self.base_input_dir, d))
        ]
        if not subdirs:
            print(f"No subdirectories found in {self.base_input_dir}")
            exit(1)

        print("Available datasets:")
        for i, d in enumerate(subdirs):
            print(f"  {i+1}: {d}")

        choice = input("Choose a dataset to process: ").strip()
        try:
            index = int(choice) - 1
            if 0 <= index < len(subdirs):
                self.dataset_dir = os.path.join(
                    self.base_input_dir, subdirs[index]
                )
            else:
                print("Invalid choice.")
                exit(1)
        except ValueError:
            print("Invalid input.")
            exit(1)
            
        return self
    
    def _ask_yes_no(self, prompt: str, default: str = "n") -> bool:
        while True:
            response = input(f"{prompt} (y/n): ").strip().lower() or default
            if response in ["y", "n"]:
                return response == "y"
            print("Invalid input. Please enter 'y' or 'n'.")
    
    def interactive_config(self):
        # Ask about resizing
        self.do_resize = self._ask_yes_no(
            "Do you want to resize images before serializing?"
        )
        size_identifier = ""
        
        if self.do_resize:
            print("Choose a target image size:")
            print("  1: 512×512")
            print("  2: 256×256")
            print("  3: 224×224")
            size_choice = input("Enter your choice (1-3): ").strip()
            
            if size_choice == "1":
                self.target_size = (512, 512)
                size_identifier = "512"
            elif size_choice == "2":
                self.target_size = (256, 256)
                size_identifier = "256"
            elif size_choice == "3":
                self.target_size = (224, 224)
                size_identifier = "224"
            else:
                print("[WARNING] Invalid choice. Using default 512×512.")
                self.target_size = (512, 512)
                size_identifier = "512"
                
            print(
                f"[INFO] Images will be resized to "
                f"{self.target_size[0]}×{self.target_size[1]}."
            )
        
        # Ask about image normalization with expanded options
        print("\nChoose image normalization strategy:")
        print("  0: None (only scale to [0,1] range)")
        print(
            "  1: ImageNet (mean=[0.485, 0.456, 0.406], "
            "std=[0.229, 0.224, 0.225])"
        )
        print(
            "  2: Dataset-specific (calculate mean and std from "
            "your dataset)"
        )
        print("  3: Grayscale-optimized (treats channels uniformly)")
        
        norm_choice = input("Enter your choice (0-3): ").strip()
        norm_identifier = ""
        
        if norm_choice == "0":
            self.normalize_images = False
            norm_identifier = "NoNorm"
            print(
                "[INFO] Images will only be scaled to [0,1] range "
                "without normalization."
            )
        elif norm_choice == "1":
            self.normalize_images = True
            self.normalization_type = "imagenet"
            norm_identifier = "ImgNetNorm"
            self.set_image_normalization(True)  # Uses ImageNet defaults
            print(
                "[INFO] Images will be normalized using ImageNet mean "
                "and std."
            )
        elif norm_choice == "2":
            self.normalize_images = True
            self.normalization_type = "dataset"
            norm_identifier = "DataNorm"
            print("[INFO] Images will be normalized using dataset statistics.")
            print(
                "[INFO] This requires a preliminary pass through the "
                "dataset to calculate statistics."
            )
            if self._ask_yes_no("Proceed with dataset statistics calculation?"):
                mean, std = self._calculate_dataset_stats()
                self.set_image_normalization(True, mean, std)
                print(f"[INFO] Calculated dataset mean: {mean.tolist()}")
                print(f"[INFO] Calculated dataset std: {std.tolist()}")
            else:
                print(
                    "[WARNING] Dataset normalization canceled. "
                    "Using ImageNet defaults."
                )
                self.normalization_type = "imagenet"
                norm_identifier = "ImgNetNorm"
                self.set_image_normalization(True)
        elif norm_choice == "3":
            self.normalize_images = True
            self.normalization_type = "grayscale"
            norm_identifier = "GrayNorm"
            # For grayscale-optimized, calculate the mean/std on the
            # average across channels
            if self._ask_yes_no("Calculate grayscale statistics from dataset?"):
                mean, std = self._calculate_grayscale_stats()
                # Use the same value for all channels
                mean_val = mean.item()
                std_val = std.item()
                self.set_image_normalization(
                    True,
                    [mean_val, mean_val, mean_val],
                    [std_val, std_val, std_val]
                )
                print(
                    f"[INFO] Using grayscale normalization with "
                    f"mean={mean_val:.4f}, std={std_val:.4f}"
                )
            else:
                print(
                    "[WARNING] Grayscale calculation canceled. "
                    "Using standard grayscale values."
                )
                self.set_image_normalization(
                    True, [0.5, 0.5, 0.5], [0.5, 0.5, 0.5]
                )
        else:
            print(
                "[WARNING] Invalid choice. No normalization will be applied."
            )
            self.normalize_images = False
            norm_identifier = "NoNorm"

        # Ask about force normalization
        self.normalize_forces = self._ask_yes_no(
            "Do you want to normalize force values?"
        )
        force_identifier = "FN" if self.normalize_forces else "NFN"
        
        if self.normalize_forces:
            print("[INFO] Please specify force normalization scale values:")
            try:
                x_scale = float(input("  X scale value: ").strip())
                y_scale = float(input("  Y scale value: ").strip())
                z_scale = float(input("  Z scale value: ").strip())
                self.force_normalization = {
                    'x_scale': x_scale,
                    'y_scale': y_scale,
                    'z_scale': z_scale
                }
                print(
                    f"[INFO] Forces will be normalized with scales: "
                    f"x={x_scale}, y={y_scale}, z={z_scale}"
                )
            except ValueError:
                print(
                    "[WARNING] Invalid input for force normalization. "
                    "Forces will not be normalized."
                )
                self.normalize_forces = False
                force_identifier = "NFN"
        
        # Ask about custom suffix
        custom_suffix = ""
        add_suffix = self._ask_yes_no(
            "Do you want to add a custom suffix to the output directory name?"
        )
        
        if add_suffix:
            custom_suffix = input(
                "Enter custom suffix (e.g., 'Center'): "
            ).strip()
            if custom_suffix and not custom_suffix.startswith("_"):
                custom_suffix = "_" + custom_suffix
            print(
                f"[INFO] Custom suffix '{custom_suffix}' will be added to "
                "directory name."
            )
                
        # Create subdirectory path based on configuration parameters
        if self.do_resize and self.output_dir:
            subdirectory_name = (
                f"{size_identifier}_{norm_identifier}_"
                f"{force_identifier}{custom_suffix}"
            )
            self.output_dir = os.path.join(self.output_dir, subdirectory_name)
            print(f"[INFO] Output subdirectory: {subdirectory_name}")
            print(f"[INFO] Full output path: {self.output_dir}")
            
        return self
    
    def _calculate_dataset_stats(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Calculate mean and standard deviation across the entire dataset.

        Returns:
            tuple: (mean_tensor, std_tensor) for the dataset
        """
        print("[INFO] Calculating dataset statistics...")
        image_files = [f for f in os.listdir(self.image_dir) if f.endswith(".png")]
        
        total_images = len(image_files)
        if total_images == 0:
            raise ValueError(
                "No PNG images found for statistics calculation."
            )
        sample_count = max(1, min(total_images, math.ceil(total_images * 0.1)))
        if sample_count < total_images:
            print(
                f"[INFO] Sampling {sample_count} images (~10%) from "
                f"{total_images} total."
            )
            image_files = random.sample(image_files, sample_count)
        else:
            print(f"[INFO] Using all {total_images} images for statistics.")
        
        sum_tensor = torch.zeros(3)
        sum_squared_tensor = torch.zeros(3)
        pixel_count = 0

        for fname in tqdm(
            image_files, desc="Calculating statistics", unit="img"
        ):
            image_path = os.path.join(self.image_dir, fname)
            img = Image.open(image_path).convert("RGB")
            if self.do_resize:
                img = img.resize(self.target_size)
            
            # Convert to tensor [0, 1]
            img_tensor = (
                torch.from_numpy(np.asarray(img, dtype=np.float32)) / 255.0
            )

            # Convert to CHW format
            if img_tensor.dim() == 3 and img_tensor.shape[-1] == 3:
                img_tensor = img_tensor.permute(2, 0, 1)
            
            # Update sums
            sum_tensor += img_tensor.sum(dim=(1, 2))
            sum_squared_tensor += (img_tensor ** 2).sum(dim=(1, 2))
            pixel_count += img_tensor.shape[1] * img_tensor.shape[2]
        
        # Calculate mean and std
        mean = sum_tensor / pixel_count
        var = (sum_squared_tensor / pixel_count) - (mean ** 2)
        std = torch.sqrt(var)
        
        return mean, std

    def _calculate_grayscale_stats(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Calculate grayscale mean and standard deviation.

        Returns:
            tuple: (mean_scalar, std_scalar) for grayscale representation
        """
        print("[INFO] Calculating grayscale statistics...")
        image_files = [f for f in os.listdir(self.image_dir) if f.endswith(".png")]
        
        total_images = len(image_files)
        if total_images == 0:
            raise ValueError(
                "No PNG images found for statistics calculation."
            )
        sample_count = max(1, min(total_images, math.ceil(total_images * 0.1)))
        if sample_count < total_images:
            print(
                f"[INFO] Sampling {sample_count} images (~10%) from "
                f"{total_images} total."
            )
            image_files = random.sample(image_files, sample_count)
        else:
            print(f"[INFO] Using all {total_images} images for statistics.")
        
        sum_val = 0
        sum_squared_val = 0
        pixel_count = 0

        for fname in tqdm(
            image_files, desc="Calculating statistics", unit="img"
        ):
            image_path = os.path.join(self.image_dir, fname)
            img = Image.open(image_path).convert("L")  # Convert to grayscale
            if self.do_resize:
                img = img.resize(self.target_size)
            
            # Convert to tensor [0, 1]
            img_tensor = (
                torch.from_numpy(np.asarray(img, dtype=np.float32)) / 255.0
            )

            # Update sums
            sum_val += img_tensor.sum()
            sum_squared_val += (img_tensor ** 2).sum()
            pixel_count += img_tensor.numel()
        
        # Calculate mean and std
        mean = sum_val / pixel_count
        var = (sum_squared_val / pixel_count) - (mean ** 2)
        std = torch.sqrt(var)
        
        return mean, std

    def _load_force_data(self) -> Dict[str, Tuple[float, float, float]]:
        """Load and parse force data from CSV file with optimized performance"""
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
            df = pd.read_csv(csv_path, engine='pyarrow')
        except:
            df = pd.read_csv(csv_path)

        sample_ids = df["SampleID"].values
        forces = df[["force_x", "force_y", "force_z"]].values.astype(np.float32)

        return {sid: tuple(f) for sid, f in zip(sample_ids, forces)}
    
    def _process_image(
        self, image_path: str, target_size: Tuple[int, int]
    ) -> torch.Tensor:
        """Process a single image and return the processed tensor"""
        # Use caching for tensor operations
        cache_key = f"{target_size}_{self.normalize_images}"

        # Image loading with context manager
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

        # Apply normalization if requested with cached parameters
        if self.normalize_images:
            # Cache normalization parameters for reuse
            if cache_key not in self._tensor_cache:
                self._tensor_cache[cache_key] = {
                    'mean_view': self.mean.view(3, 1, 1),
                    'std_view': self.std.view(3, 1, 1)
                }

            cached_params = self._tensor_cache[cache_key]
            img_tensor = (img_tensor - cached_params['mean_view']) / cached_params['std_view']

        return img_tensor
    
    def _normalize_force(
        self, force_values: Tuple[float, float, float]
    ) -> torch.Tensor:
        """Normalize force data values"""
        force_tensor = torch.tensor(force_values, dtype=torch.float32)

        # Cache force scaling factors
        if self.normalize_forces and self.force_normalization:
            if not hasattr(self, '_force_scales'):
                self._force_scales = torch.tensor([
                    self.force_normalization['x_scale'],
                    self.force_normalization['y_scale'],
                    self.force_normalization['z_scale']
                ], dtype=torch.float32)
            force_tensor = force_tensor / self._force_scales

        return force_tensor
    
    async def _save_batch_async(
        self, batch: List[Dict[str, Any]], batch_count: int
    ) -> str:
        """
        Asynchronously save a batch of processed data.

        Uses a thread pool executor to perform I/O operations without
        blocking the async event loop. This allows other tasks to continue
        processing while data is being saved to disk.

        Args:
            batch (list): List of processed samples to save
            batch_count (int): Sequential batch number for filename generation

        Returns:
            str: Path to the saved batch file
        """
        batch_path = os.path.join(
            self.output_dir, f"preprocessed_batch_{batch_count:04d}.pt"
        )

        # Use thread pool executor for I/O intensive operations to
        # avoid blocking event loop
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            await loop.run_in_executor(
                executor, torch.save, batch, batch_path
            )

        print(f"[INFO] Saved batch to {batch_path} ({len(batch)} samples)")
        return batch_path
        
    def serialize(self):
        """Serialize vision-force pairs from rendered images and force CSV
        with async processing."""
        if not self.dataset_dir or not self.image_dir or not self.output_dir:
            raise ValueError(
                "Dataset, image, and output directories must be set "
                "before serializing"
            )

        # If settings not configured, prompt for them
        if (self.do_resize is None or self.normalize_images is None or
                self.normalize_forces is None):
            self.interactive_config()

        # Create output directory if it doesn't exist (check again after
        # interactive_config may have changed it)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        # Run async serialization
        return asyncio.run(self._serialize_async())

    async def _serialize_async(self):
        """
        Asynchronous serialization implementation.

        This method processes images in parallel using asyncio and thread pools.
        Key optimizations include:
        - Concurrent image processing with semaphore-controlled parallelism
        - Chunked processing to manage memory usage
        - Asynchronous I/O operations for batch saving
        - Thread pool executors for CPU-intensive operations

        Returns:
            self: For method chaining
        """
        start_time = time.time()

        # Load force data
        force_dict = self._load_force_data()

        # Get image files
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

        # Semaphore to control concurrency level and prevent overwhelming
        # the system. Limits the number of concurrent image processing
        # tasks to avoid memory issues
        semaphore = asyncio.Semaphore(64)

        async def process_image_async(fname):
            """
            Asynchronously process a single image file with force data pairing.

            Uses semaphore for concurrency control and thread pool executors
            for CPU-intensive image processing operations. This prevents
            blocking the async event loop while maintaining high throughput.

            Args:
                fname (str): Image filename to process

            Returns:
                tuple: (processed_sample_dict, error_message) where one is None
            """
            async with semaphore:
                sample_id = os.path.splitext(fname)[0]
                if sample_id not in force_dict:
                    return None, f"No force label for image: {sample_id}"

                image_path = os.path.join(self.image_dir, fname)
                try:
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                        # Process image and force data in thread pool
                        img_tensor = await loop.run_in_executor(
                            executor,
                            self._process_image,
                            image_path,
                            target_size
                        )
                        force_tensor = await loop.run_in_executor(
                            executor,
                            self._normalize_force,
                            force_dict[sample_id]
                        )

                    return {
                        "id": sample_id,
                        "image": img_tensor,
                        "force": force_tensor
                    }, None
                except Exception as e:
                    return None, f"Failed to process {fname}: {e}"

        # Process images in chunks for better memory management and
        # controlled resource usage. Smaller chunks reduce peak memory
        # usage while maintaining good parallelism
        chunk_size = 200

        # Create progress bar
        progress_bar = tqdm(
            total=len(image_files), desc="Serializing", unit="img"
        )

        # Process images in chunks
        for i in range(0, len(image_files), chunk_size):
            chunk = image_files[i:i + chunk_size]

            # Create tasks for the chunk
            tasks = [process_image_async(fname) for fname in chunk]
            results = await asyncio.gather(*tasks)

            # Process results
            for result, error in results:
                if error:
                    progress_bar.write(f"[Warning] {error}")
                    continue
                if result:
                    batch.append(result)
                    matched_total += 1

                    # Save batch when it reaches the specified size
                    if len(batch) >= self.batch_size:
                        await self._save_batch_async(batch, batch_count)
                        batch_count += 1
                        batch = []

            # Update progress bar
            chunk_processed = min(len(chunk), len(image_files) - i)
            progress_bar.update(chunk_processed)

        progress_bar.close()

        # Save remaining samples
        if batch:
            await self._save_batch_async(batch, batch_count)
            batch_count += 1

        # Save metadata
        process_time = time.time() - start_time
        self.metadata = {
            'total_samples': matched_total,
            'batch_size': self.batch_size,
            'num_batches': batch_count,
            'original_image_size': (
                list(original_image_size) if original_image_size else None
            ),
            'image_size': list(target_size),
            'normalize_images': self.normalize_images,
            'normalize_forces': self.normalize_forces,
            'force_normalization': self.force_normalization,
            'image_mean': (
                self.mean.tolist() if self.normalize_images else None
            ),
            'image_std': (
                self.std.tolist() if self.normalize_images else None
            ),
            'dataset_name': os.path.basename(self.dataset_dir),
            'image_dir': os.path.basename(self.image_dir),
            'processing_time': process_time,
            'preprocess_date': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        metadata_path = os.path.join(self.output_dir, "metadata.yaml")
        with open(metadata_path, 'w') as f:
            yaml.dump(self.metadata, f)

        # Store results
        samples_per_sec = (
            matched_total / process_time if process_time > 0 else 0
        )
        self.results = {
            "total_samples": matched_total,
            "batches": batch_count,
            "processing_time": process_time,
            "samples_per_sec": samples_per_sec,
            "metadata_path": metadata_path
        }

        print(f"[SUCCESS] Total matched samples serialized: {matched_total}")
        print(
            f"[INFO] Processing time: {process_time:.2f} seconds, "
            f"Rate: {samples_per_sec:.2f} samples/sec"
        )
        print(f"[INFO] Metadata saved to: {metadata_path}")

        return self
    
    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """Get the metadata from the serialization process."""
        return self.metadata

    def get_results(self) -> Optional[Dict[str, Any]]:
        """Get the results from the serialization process."""
        return self.results


class Sim2VFP:
    """
    Main Simulation to Vision-Force Processor class.
    Orchestrates the complete pipeline of dataset selection, rendering, and serialization.
    Supports both interactive and programmatic modes with fluent interface.
    """
    
    def __init__(self) -> None:
        self.config = CaptureConfig()
        self.camera_manager = CameraManager(self.config.camera_dir)
        self.renderer = Renderer()
        self.data_preprocessor = DataPreprocessor()
        
        # Pipeline state
        self.dataset_dir: Optional[str] = None
        self.cam_json_path: Optional[str] = None
        self.output_png_dir: Optional[str] = None
        self.output_data_dir: Optional[str] = None

        # Setup logging
        logging.basicConfig(
            level=logging.INFO, format="[%(levelname)s] %(message)s"
        )
    
    # === Dataset Methods ===
    
    def select_dataset(self, base_dir=None):
        if base_dir is None:
            base_dir = self.config.default_input
            
        self.data_preprocessor.set_base_directory(base_dir).choose_dataset()
        self.dataset_dir = self.data_preprocessor.dataset_dir
        
        # Validate that .ply files exist in the selected directory
        self._validate_dataset_has_ply_files(self.dataset_dir)
        return self
    
    def _validate_dataset_has_ply_files(self, dataset_dir: str) -> List[str]:
        """
        Validate that the dataset directory contains .ply files.

        Args:
            dataset_dir (str): Path to dataset directory

        Returns:
            list: List of .ply files found

        Raises:
            SystemExit: If no .ply files are found
        """
        ply_files = [f for f in os.listdir(dataset_dir) if f.lower().endswith(".ply")]
        if not ply_files:
            print(
                f"[ERROR] No .ply files found in selected dataset: "
                f"{os.path.basename(dataset_dir)}"
            )
            print("Please choose a dataset with valid .ply files.")
            exit(1)

        logging.info(
            f"Found {len(ply_files)} .ply files in "
            f"{os.path.basename(dataset_dir)}"
        )
        return ply_files
    
    def use_dataset(self, dataset_path):
        if not os.path.isdir(dataset_path):
            raise ValueError(
                f"Dataset directory does not exist: {dataset_path}"
            )
            
        ply_files = self._validate_dataset_has_ply_files(dataset_path)
            
        self.dataset_dir = dataset_path
        self.data_preprocessor.set_dataset_directory(dataset_path)

        logging.info(
            f"Using dataset: {os.path.basename(dataset_path)} "
            f"({len(ply_files)} ply files)"
        )
        return self
    
    # === Camera Methods ===
    
    def select_camera(self):
        if not self.dataset_dir:
            raise ValueError("Dataset must be selected before camera")
            
        cam_json = self.camera_manager.interactive_select_camera()
        if cam_json is None:
            print("User aborted camera selection. Exiting.")
            exit(0)
            
        self.cam_json_path = cam_json
        return self
    
    def use_camera(self, camera_path):
        if not os.path.isfile(camera_path):
            raise ValueError(
                f"Camera configuration file does not exist: {camera_path}"
            )

        self.cam_json_path = camera_path
        logging.info(
            f"Using camera configuration: {os.path.basename(camera_path)}"
        )
        return self
    
    def preview(self) -> str:
        if not self.dataset_dir:
            raise ValueError("Dataset must be selected before preview")

        if not self.cam_json_path:
            raise ValueError("Camera must be selected before preview")

        self.camera_manager.preview_random_ply_with_camera(
            self.dataset_dir, self.cam_json_path
        )

        # Get confirmation to proceed
        decision = self.camera_manager.interactive_render_confirmation()
        if decision == 'y':
            return 'proceed'
        elif decision == 'n':
            return 'reselect'
        else:
            return 'quit'
    
    def _camera_selection_loop(self) -> bool:
        """
        Interactive camera selection loop until user is satisfied or quits.

        Returns:
            bool: True if user is satisfied, False if user quits
        """
        while True:
            self.select_camera()
            preview_result = self.preview()
            
            if preview_result == 'proceed':
                return True
            elif preview_result == 'reselect':
                continue
            else:  # 'quit'
                return False
    
    # === Rendering Methods ===
    
    def set_output_png_dir(self, output_dir=None):
        if output_dir is None:
            output_dir = self.config.render_result_path
            
        self.output_png_dir = output_dir
        return self
    
    def render(
        self,
        max_workers: Optional[int] = None,
        error_log_path: Optional[str] = None
    ):
        if not self.dataset_dir:
            raise ValueError("Dataset must be selected before rendering")

        if not self.cam_json_path:
            raise ValueError("Camera must be selected before rendering")

        if not self.output_png_dir:
            self.set_output_png_dir()

        if max_workers is None:
            total_cores = mp.cpu_count()
            max_workers = max(1, int(total_cores * 0.75))

        if error_log_path is None:
            error_log_path = self.config.default_error_log

        # Configure and run the renderer
        self.renderer.set_source(self.dataset_dir) \
                     .set_output(self.output_png_dir) \
                     .set_camera(self.cam_json_path) \
                     .set_error_log(error_log_path) \
                     .set_workers(max_workers) \
                     .render()

        results = self.renderer.get_results()
        if results:
            logging.info(
                f"Rendering complete: {results['successful']}/"
                f"{results['total']} images"
            )

        return self
    
    # === Serialization Methods ===
    
    def set_output_data_dir(self, output_dir=None):
        if output_dir is None:
            output_dir = self.config.default_serialization_result_path

        self.output_data_dir = output_dir
        return self
    
    def configure_serialization(
        self,
        do_resize: Optional[bool] = None,
        target_size: Optional[Tuple[int, int]] = None,
        normalize_images: Optional[bool] = None,
        normalize_forces: Optional[bool] = None,
        force_normalization: Optional[Dict[str, float]] = None,
        batch_size: Optional[int] = None
    ):
        """
        Configure serialization settings programmatically.

        Args:
            do_resize (bool, optional): Whether to resize images
            target_size (tuple, optional): Target size for resizing (width, height)
            normalize_images (bool, optional): Whether to normalize images
            normalize_forces (bool, optional): Whether to normalize forces
            force_normalization (dict, optional): Force normalization scales
            batch_size (int, optional): Batch size for serialization

        Returns:
            self: For method chaining
        """
        if do_resize is not None:
            self.data_preprocessor.set_resize(do_resize, target_size)
            
        if normalize_images is not None:
            self.data_preprocessor.set_image_normalization(normalize_images)

        if normalize_forces is not None:
            self.data_preprocessor.set_force_normalization(
                normalize_forces, force_normalization
            )
            
        if batch_size is not None:
            self.data_preprocessor.set_batch_size(batch_size)
            
        return self
    
    def serialize(self):
        """Serialize rendered images and force data to PT files."""
        if not self.dataset_dir:
            raise ValueError("Dataset must be selected before serialization")
            
        if not self.output_png_dir:
            raise ValueError("Rendered images directory must be specified")
            
        if not self.output_data_dir:
            self.set_output_data_dir()
            
        # Configure and run serialization
        self.data_preprocessor.set_dataset_directory(self.dataset_dir) \
                             .set_image_directory(self.output_png_dir) \
                             .set_output_directory(self.output_data_dir) \
                             .serialize()
                          
        results = self.data_preprocessor.get_results()
        if results:
            logging.info(
                f"Serialization complete: {results['total_samples']} "
                f"samples in {results['batches']} batches"
            )
            
        return self
    
    # === Pipeline Methods ===
    
    def run_pipeline(self):
        """
        Run the complete pipeline: dataset selection, camera selection,
        preview, render, and serialize.
        """
        return self.handle_pipeline()
    
    # === Command Line Interface Methods ===
    
    def _create_argument_parser(self) -> argparse.ArgumentParser:
        """
        Create and configure command line argument parser.

        Returns:
            argparse.ArgumentParser: Configured argument parser
        """
        parser = argparse.ArgumentParser(
            description=(
                "Simulation to Vision-Force Processor - Convert 3D PLY "
                "models to 2D images and serialize with force data"
            ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )

        parser.add_argument(
            "--input", "-i",
            type=str,
            default=self.config.default_input,
            help="Input directory containing PLY datasets"
        )
        parser.add_argument(
            "--output", "-o",
            type=str,
            default=self.config.render_result_path,
            help="Output directory for rendered PNG images"
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Open 3D preview window to setup camera angles"
        )
        parser.add_argument(
            "--preview-mode",
            type=str,
            choices=["default", "instance"],
            default="default",
            help=(
                "Preview mode: 'default' uses plate.ply, 'instance' uses "
                "random dataset sample"
            )
        )
        parser.add_argument(
            "--sample",
            type=str,
            default=self.config.default_sample_ply,
            help="Sample PLY file for default preview mode"
        )
        parser.add_argument(
            "--list-cameras",
            action="store_true",
            help="List all saved camera configurations"
        )
        parser.add_argument(
            "--errorlog",
            type=str,
            default=self.config.default_error_log,
            help="Path to error log CSV file"
        )
        parser.add_argument(
            "--parallel",
            action="store_true",
            help="Enable parallel rendering with multiprocessing"
        )
        parser.add_argument(
            "--load",
            type=int,
            choices=range(1, 101),
            default=50,
            metavar="1-100",
            help="CPU utilization percentage for parallel rendering"
        )
        parser.add_argument(
            "--serialize",
            action="store_true",
            help="Serialize images and forces to PyTorch tensors"
        )
        parser.add_argument(
            "--pipeline",
            action="store_true",
            help=(
                "Run complete pipeline: select dataset, setup camera, "
                "render, serialize"
            )
        )
        parser.add_argument(
            "--visualize",
            action="store_true",
            help="Visualize serialized data to verify content"
        )

        return parser
    
    def parse_args(self) -> argparse.Namespace:
        """
        Parse command line arguments.

        Returns:
            argparse.Namespace: Parsed arguments
        """
        return self._create_argument_parser().parse_args()
    
    def handle_preview_mode(self, args: argparse.Namespace) -> None:
        """Handle preview mode command from CLI."""
        if args.preview_mode == "default":
            self.camera_manager.preview_ply_with_save(
                args.sample, mode="default"
            )
        else:
            dataset_input_dir = (
                self.data_preprocessor
                .set_base_directory(self.config.default_input)
                .choose_dataset()
                .dataset_dir
            )
            sample_list = self.camera_manager._filter_files(
                dataset_input_dir, ".ply"
            )
            if not sample_list:
                print(f"No .ply files found in {dataset_input_dir}")
                exit(1)
            instance_sample_path = os.path.join(
                dataset_input_dir, random.choice(sample_list)
            )
            print(
                f"Randomly selected file for preview: "
                f"{os.path.basename(instance_sample_path)}"
            )
            self.camera_manager.preview_ply_with_save(
                instance_sample_path, mode="instance"
            )
    
    def handle_list_cameras(self) -> None:
        """List all saved camera views."""
        self.camera_manager.list_available_cameras()

    def handle_render_only(self, args: argparse.Namespace) -> None:
        """Handle render-only command from CLI with proper camera
        selection loop."""
        self.select_dataset(args.input)
        
        if not self._camera_selection_loop():
            print("User exited rendering process.")
            exit(0)
            
        # User confirmed, execute rendering
        total_cores = mp.cpu_count()
        max_workers = max(1, int(total_cores * (args.load/100)))
        print(f"Rendering with {max_workers} workers...")
        
        self.set_output_png_dir(args.output)
        self.render(max_workers=max_workers, error_log_path=args.errorlog)
    
    def handle_serialize_only(self) -> None:
        """Handle serialize-only command from CLI."""
        ori_deformation_dir = self.config.default_input
        ren_dir = self.config.render_result_path

        self.select_dataset(ori_deformation_dir)

        output_dir = self.config.default_serialization_result_path

        # Ask user if they want to use a different base output directory
        custom_dir = input(
            f"Base output directory [default: {output_dir}]: "
        ).strip()
        if custom_dir:
            output_dir = custom_dir

        # Perform serialization
        self.set_output_png_dir(ren_dir)
        self.set_output_data_dir(output_dir)
        self.serialize()
    
    def handle_pipeline(self) -> None:
        """Handle full pipeline command from CLI."""
        # Select dataset
        self.select_dataset()
        
        # Camera selection loop
        if not self._camera_selection_loop():
            print("User exited pipeline.")
            exit(0)
        
        # Execute rendering and serialization
        self.set_output_png_dir()
        self.render()
        self.set_output_data_dir()
        self.serialize()
    
    def run_cli(self) -> None:
        """Process command line arguments and execute the appropriate
        actions."""
        args = self.parse_args()

        if args.preview:
            self.handle_preview_mode(args)
        elif args.list_cameras:
            self.handle_list_cameras()
        elif args.parallel:
            self.handle_render_only(args)
        elif args.serialize:
            self.handle_serialize_only()
        elif args.pipeline:
            self.handle_pipeline()
        elif args.visualize:
            # Create data visualizer and run interactive visualization
            visualizer = DataVisualizer()
            visualizer.interactive_batch_visualization()
        else:
            self._create_argument_parser().print_help()


class DataVisualizer:
    """
    Visualizes serialized data from .pt files to verify content.
    Displays images and outputs corresponding force data.
    """
    
    def __init__(self) -> None:
        pass

    def _get_normalization_params(
        self, data_dir: str
    ) -> Tuple[Optional[List[float]], Optional[List[float]]]:
        """
        Get normalization parameters from metadata.yaml in the data directory.

        Args:
            data_dir (str): Path to the data directory containing metadata.yaml

        Returns:
            tuple: (mean, std) as lists or None if not found
        """
        metadata_path = os.path.join(data_dir, "metadata.yaml")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = yaml.safe_load(f)
                    if metadata.get('normalize_images', False):
                        return (
                            metadata.get('image_mean'),
                            metadata.get('image_std')
                        )
                    print(
                        "[INFO] Images were not normalized during "
                        "preprocessing according to metadata."
                    )
            except Exception as e:
                print(
                    f"[WARNING] Failed to read normalization parameters "
                    f"from metadata: {e}"
                )
        else:
            print(f"[WARNING] No metadata.yaml found in {data_dir}")
        return None, None
        
    def visualize_batch(
        self, batch_path: str, sample_indices: Optional[List[int]] = None
    ) -> None:
        """
        Visualize samples from a serialized batch file.

        Args:
            batch_path (str): Path to the serialized .pt file
            sample_indices (list, optional): List of indices to visualize.
                If None, shows first sample.

        Returns:
            None
        """
        if not os.path.exists(batch_path):
            print(f"[ERROR] Batch file not found: {batch_path}")
            return
            
        # Load the batch data
        try:
            batch_data = torch.load(batch_path)
            print(f"[INFO] Loaded batch containing {len(batch_data)} samples")
            
            if not batch_data:
                print("[ERROR] Batch file is empty")
                return
                
            # Determine which samples to show
            if sample_indices is None:
                sample_indices = [0]  # Default to first sample
            elif isinstance(sample_indices, int):
                sample_indices = [sample_indices]
                
            # Validate indices
            valid_indices = [i for i in sample_indices if 0 <= i < len(batch_data)]
            if not valid_indices:
                print("[ERROR] No valid sample indices provided")
                return
                
            # Get normalization parameters from metadata
            data_dir = os.path.dirname(batch_path)
            custom_mean, custom_std = self._get_normalization_params(data_dir)
            
            if custom_mean and custom_std:
                print(f"[INFO] Using normalization parameters from metadata:")
                print(f"  - Mean: {custom_mean}")
                print(f"  - Std: {custom_std}")
                use_custom_norm = True
            else:
                print(
                    "[INFO] Using default ImageNet normalization parameters "
                    "for visualization"
                )
                use_custom_norm = False
                
            # Create figure and subplots
            num_samples = len(valid_indices)
            _, axes = plt.subplots(1, num_samples, figsize=(5*num_samples, 5))
            
            # Handle case with only one sample
            if num_samples == 1:
                axes = [axes]
                
            # Visualize each selected sample
            for i, sample_idx in enumerate(valid_indices):
                sample = batch_data[sample_idx]
                
                # Extract sample id, image, and force data
                sample_id = sample["id"]
                img_tensor = sample["image"]
                force_tensor = sample["force"]
                
                # Print force information to console
                print(f"\nSample ID: {sample_id}")
                print(f"Force data (x, y, z): {force_tensor.tolist()}")
                print(f"Image shape: {img_tensor.shape}")
                
                # Convert tensor to displayable image
                # De-normalize if necessary
                img_display = img_tensor.clone()
                
                # If image is normalized (likely in range [-1, 1] or similar)
                # we need to convert back to [0, 1] for display
                if img_display.min() < 0:
                    if use_custom_norm:
                        # Use parameters from metadata
                        mean = torch.tensor(custom_mean).view(3, 1, 1)
                        std = torch.tensor(custom_std).view(3, 1, 1)
                    else:
                        # Fall back to ImageNet defaults
                        mean = torch.tensor(
                            [0.485, 0.456, 0.406]
                        ).view(3, 1, 1)
                        std = torch.tensor(
                            [0.229, 0.224, 0.225]
                        ).view(3, 1, 1)
                    
                    img_display = img_display * std + mean
                
                # Ensure image is in [0, 1] range
                img_display = torch.clamp(img_display, 0, 1)
                
                # Convert from CHW to HWC format for matplotlib
                img_display = img_display.permute(1, 2, 0)
                
                # Convert to numpy for matplotlib
                img_display = img_display.numpy()
                
                # Display the image
                axes[i].imshow(img_display)
                axes[i].set_title(f"Sample: {sample_id}")
                axes[i].axis('off')
                
            plt.tight_layout()
            plt.show()
            
        except Exception as e:
            print(f"[ERROR] Failed to visualize batch: {e}")
    
    def interactive_batch_visualization(
        self, data_dir: Optional[str] = None
    ) -> None:
        """
        Interactive visualization of serialized data.
        Lets user select batch file and samples to visualize.

        Args:
            data_dir (str, optional): Directory containing serialized .pt files

        Returns:
            None
        """
        # Find data directory if not specified
        if data_dir is None:
            # Look for directories matching pattern
            potential_dirs = [
                d for d in os.listdir()
                if os.path.isdir(d) and d.startswith("preprocessed_data")
            ]
            
            if not potential_dirs:
                print("[ERROR] No preprocessed data directories found")
                return
                
            print("Available data directories:")
            for i, d in enumerate(potential_dirs):
                print(f"  {i+1}: {d}")
                
            choice = input("Select data directory (number): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(potential_dirs):
                    data_dir = potential_dirs[idx]
                else:
                    print("[ERROR] Invalid selection")
                    return
            except ValueError:
                print("[ERROR] Invalid input")
                return
        
        # Check if directory exists
        if not os.path.isdir(data_dir):
            print(f"[ERROR] Directory not found: {data_dir}")
            return
        
        current_dir = data_dir
        while True:
            pt_files = sorted([
                f for f in os.listdir(current_dir)
                if f.endswith(".pt") and "batch" in f
            ])
            if pt_files:
                data_dir = current_dir
                break

            subdirs = sorted([
                d for d in os.listdir(current_dir)
                if os.path.isdir(os.path.join(current_dir, d))
            ])
            if not subdirs:
                print(f"[ERROR] No batch files found in {current_dir}")
                return

            print(f"[INFO] No batch files found in {current_dir}.")
            print("Available subdirectories:")
            for i, sub in enumerate(subdirs):
                print(f"  {i+1}: {sub}")
            selection = input(
                "Select subdirectory (number, or 'q' to quit): "
            ).strip()
            if selection.lower() == 'q':
                return
            try:
                idx = int(selection) - 1
                if 0 <= idx < len(subdirs):
                    current_dir = os.path.join(current_dir, subdirs[idx])
                else:
                    print("[ERROR] Invalid selection")
            except ValueError:
                print("[ERROR] Invalid input")

        # Check for metadata.yaml and show information if available
        metadata_path = os.path.join(data_dir, "metadata.yaml")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = yaml.safe_load(f)
                    print("\n[INFO] Dataset metadata summary:")
                    print(
                        f"  - Total samples: "
                        f"{metadata.get('total_samples', 'Unknown')}"
                    )
                    print(
                        f"  - Image size: "
                        f"{metadata.get('image_size', 'Unknown')}"
                    )
                    print(
                        f"  - Normalized images: "
                        f"{metadata.get('normalize_images', False)}"
                    )
                    print(
                        f"  - Normalized forces: "
                        f"{metadata.get('normalize_forces', False)}"
                    )
                    if (metadata.get('normalize_forces', False) and
                            metadata.get('force_normalization')):
                        print(
                            f"  - Force normalization: "
                            f"{metadata.get('force_normalization')}"
                        )
                    print(
                        f"  - Processing date: "
                        f"{metadata.get('preprocess_date', 'Unknown')}"
                    )
                    print()
            except Exception as e:
                print(f"[WARNING] Failed to read metadata: {e}")
            
        # Let user select batch file
        print(f"Found {len(pt_files)} batch files:")
        for i, f in enumerate(pt_files):
            print(f"  {i+1}: {f}")
            
        batch_choice = input("Select batch file (number): ").strip()
        try:
            batch_idx = int(batch_choice) - 1
            if 0 <= batch_idx < len(pt_files):
                batch_file = pt_files[batch_idx]
            else:
                print("[ERROR] Invalid selection")
                return
        except ValueError:
            print("[ERROR] Invalid input")
            return
            
        # Load the batch to check how many samples it contains
        try:
            batch_path = os.path.join(data_dir, batch_file)
            batch_data = torch.load(batch_path)
            num_samples = len(batch_data)
            print(f"Batch contains {num_samples} samples")
            
            # Loop for continuous visualization
            while True:
                # Let user select samples to visualize
                sample_input = input(
                    f"Enter sample indices to visualize (0-{num_samples-1}, "
                    "comma-separated, 'r' for random, 'q' to quit): "
                ).strip()
                
                if sample_input.lower() == 'q':
                    # Exit the loop
                    break
                
                if sample_input.lower() == 'r':
                    # Random samples (show 3 random samples)
                    sample_indices = random.sample(
                        range(num_samples), min(3, num_samples)
                    )
                else:
                    # Parse user input
                    try:
                        sample_indices = [
                            int(s.strip()) for s in sample_input.split(',')
                        ]
                        # Validate indices
                        sample_indices = [
                            i for i in sample_indices
                            if 0 <= i < num_samples
                        ]
                        if not sample_indices:
                            sample_indices = [0]  # Default to first sample
                    except ValueError:
                        print("[WARNING] Invalid input, showing first sample")
                        sample_indices = [0]
                        
                # Visualize the selected samples
                self.visualize_batch(batch_path, sample_indices)
            
        except Exception as e:
            print(f"[ERROR] Failed to process batch file: {e}")


def main():
    """Entry point of sim2vfp.py. Creates a Sim2VFP instance and processes command line arguments."""
    processor = Sim2VFP()
    processor.run_cli()


if __name__ == "__main__":
    main()