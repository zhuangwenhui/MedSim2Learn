"""Experiment recipe: defaults, YAML loading, and validation.

A recipe collects every knob the pipeline needs (asset paths, material,
camera placement, sim threading, serialization, batching) so a run is fully
described by one YAML file plus CLI overrides. The defaults below reproduce
the proven kidney digital-twin decisions; `configs/kidney_twin.yaml` mirrors
them on disk.
"""

import dataclasses
import os

import yaml

from . import paths

# Fixed material decision for the kidney digital twin.
DEFAULT_YOUNG_MPA = 0.03
DEFAULT_POISSON = 0.49
# Real recordings are 30 fps; replay frame indices map to time through this.
DEFAULT_FPS = 30.0
# mt19937 seed the DeformSim exe expects even in replay mode (unused there,
# but kept identical to the historical runs for reproducibility).
DEFAULT_SIM_SEED = 20260530


@dataclasses.dataclass
class CameraConfig:
    """Camera source for every replay frame (one fixed camera per sequence).

    mode selects where the camera comes from:
      auto      deterministic placement from the fields below, centered on the
                sequence's contact point
      profile   a saved contact-frame view profile (interactively picked once,
                re-instantiated around each sequence's own contact); `profile`
                names it (bare name resolved in cameras_dir, or a path)
      absolute  a saved PinholeCameraParameters JSON applied verbatim to every
                sequence (the viewpoint does NOT follow the contact);
                `absolute` is its path

    The auto defaults: the eye direction grazes the contact region from the
    side (~70 deg from +z, azimuth ~240 deg) so the indentation breaks the top
    silhouette; up must stay +z because a +y up would be nearly parallel to
    the grazing view direction and the camera basis would degenerate. The
    close standoff frames the contact region, not the whole organ.
    """

    mode: str = "auto"
    profile: str = ""
    absolute: str = ""
    width: int = 800
    height: int = 800
    fov_deg: float = 60.0
    standoff_mm: float = 70.0
    eye_dir: tuple = (-0.47, -0.81, 0.34)
    up: tuple = (0.0, 0.0, 1.0)


@dataclasses.dataclass
class MaterialConfig:
    young_mpa: float = DEFAULT_YOUNG_MPA
    poisson: float = DEFAULT_POISSON


@dataclasses.dataclass
class SimConfig:
    """DeformSim invocation knobs (exe path resolved separately)."""

    num_threads: int = 1
    mkl_threads: int = 1
    seed: int = DEFAULT_SIM_SEED


@dataclasses.dataclass
class SerializeConfig:
    # 256x256 matches the real corpus and the experiment datasets (datasets/*);
    # raw 800 px was ~13 GB/seq.
    resize: tuple = (256, 256)
    # F3 opt-in coverage assertion: raise when any PNG lacks a labels.csv row
    # (matched != total) instead of the historical warn-and-drop. Default off
    # preserves current behavior; the coverage line + dropped-stem manifest
    # are emitted either way.
    require_full_coverage: bool = False


@dataclasses.dataclass
class BatchConfig:
    max_parallel: int = 1
    keep_intermediate: bool = False


@dataclasses.dataclass
class RecipeConfig:
    """One fully-resolved experiment recipe."""

    # External read-only corpus; canonical path lives in
    # data_sources.yaml[real_visual_force_dataset].path -- keep the two in sync.
    real_data_root: str = "D:/Image2Force Data/Real Visual-force Paired Data"
    # Purified real corpus (Data Processpor pipeline): visual_data/NN.mp4 +
    # force_data/NN.csv, frame i <-> force row i (alignment pre-validated).
    # Canonical path: data_sources.yaml[real_origin_data].path -- keep in sync.
    real_origin_root: str = "D:/Data Processpor/Origin_data"
    mesh: str = "{dataflow}/ShapeReconstruction/meshes/kidney_anat.ply"
    annotation: str = "{dataflow}/Deform_post/inputs/annotations/kidney_anat_contact_k1.json"
    out_root: str = "{dataflow}/Deform_post/primary/twin_full"
    exe: str = "{workspace}/build/DeformSim/vs2022-x64/Release/LVBasicFramework.exe"
    cameras_dir: str = "{dataflow}/Deform_post/inputs/cameras"
    mkl_bin: str = "C:/Program Files (x86)/Intel/oneAPI/mkl/latest/bin"
    compiler_bin: str = "C:/Program Files (x86)/Intel/oneAPI/compiler/latest/bin"
    fps: float = DEFAULT_FPS
    camera: CameraConfig = dataclasses.field(default_factory=CameraConfig)
    material: MaterialConfig = dataclasses.field(default_factory=MaterialConfig)
    sim: SimConfig = dataclasses.field(default_factory=SimConfig)
    serialize: SerializeConfig = dataclasses.field(default_factory=SerializeConfig)
    batch: BatchConfig = dataclasses.field(default_factory=BatchConfig)

    def resolved(self, name) -> str:
        """Return a path field with {workspace}/{dataflow} expanded."""
        value = paths.expand(getattr(self, name))
        if value is None:
            raise ValueError(f"recipe path field {name!r} is unset")
        return value


def _apply_section(obj, data, label):
    """Overlay a YAML mapping onto a dataclass instance, rejecting unknown keys."""
    fields = {f.name for f in dataclasses.fields(obj)}
    for key, value in data.items():
        if key not in fields:
            raise ValueError(f"unknown key '{key}' in config section '{label}'")
        current = getattr(obj, key)
        if dataclasses.is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f"config section '{label}.{key}' must be a mapping")
            _apply_section(current, value, f"{label}.{key}")
        elif isinstance(current, tuple):
            setattr(obj, key, tuple(value))
        else:
            setattr(obj, key, value)


def load_recipe(config_path=None):
    """Load a recipe YAML over the defaults; None returns pure defaults."""
    recipe = RecipeConfig()
    if config_path:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"config root must be a mapping: {config_path}")
        _apply_section(recipe, data, os.path.basename(config_path))
    _validate(recipe)
    return recipe


def _validate(recipe):
    if not (-1.0 < recipe.material.poisson < 0.5):
        raise ValueError(f"poisson {recipe.material.poisson} outside (-1, 0.5)")
    if recipe.material.young_mpa <= 0.0:
        raise ValueError(f"young_mpa {recipe.material.young_mpa} must be > 0")
    if recipe.fps <= 0.0:
        raise ValueError(f"fps {recipe.fps} must be > 0")
    cam = recipe.camera
    if cam.mode not in ("auto", "profile", "absolute"):
        raise ValueError(f"camera mode '{cam.mode}' not in auto/profile/absolute")
    if cam.mode == "profile" and not cam.profile:
        raise ValueError("camera mode 'profile' needs camera.profile (name or path)")
    if cam.mode == "absolute" and not cam.absolute:
        raise ValueError("camera mode 'absolute' needs camera.absolute (path)")
    if cam.width <= 0 or cam.height <= 0:
        raise ValueError("camera width/height must be positive")
    if not (0.0 < cam.fov_deg < 180.0):
        raise ValueError(f"camera fov_deg {cam.fov_deg} outside (0, 180)")
    if cam.standoff_mm <= 0.0:
        raise ValueError(f"camera standoff_mm {cam.standoff_mm} must be > 0")
    if len(cam.eye_dir) != 3 or len(cam.up) != 3:
        raise ValueError("camera eye_dir/up must be 3-vectors")
    if recipe.sim.num_threads < 1 or recipe.sim.mkl_threads < 0:
        raise ValueError("sim.num_threads must be >= 1 and sim.mkl_threads >= 0")
    if recipe.batch.max_parallel < 1:
        raise ValueError("batch.max_parallel must be >= 1")
