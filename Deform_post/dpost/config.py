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
class AppearanceConfig:
    """C1 appearance domain randomization, design v2 (texel-baked texture).

    Disabled by default: OFF keeps the render pipeline byte-identical to the
    legacy behavior. When enabled, each sequence draws its appearance from
    numpy SeedSequence([seed, sequence_ordinal]) (see dpost.diversity), the
    organ is ALWAYS coloured by one per-sequence texture baked from the R25
    procedural field family on the canonical first frame (the v1 uniform
    flat-paint mode was deleted at the 2026-08-10 visual gate), and the
    per-frame photometric post-process chain runs after capture. Every
    two-element field is a closed uniform draw interval.

    Colour boxes are the empirical support of the real corpus (31 sequences
    x 10 frames; derivation and full-precision numbers recorded in
    _c1_scratch/real_color_anchor.json): albedo = bright-region (lum >= q60)
    per-frame mean p05-p95, background = dark-region (lum <= q35) p05-p95,
    both rounded to 4 decimals here.
    """

    enabled: bool = False
    seed: int = 0
    # Organ base albedo: real-corpus organ box (anchor JSON organ_bright_*).
    albedo_r: tuple = (0.8180, 0.8605)
    albedo_g: tuple = (0.6944, 0.7519)
    albedo_b: tuple = (0.7423, 0.7866)
    # R25 field family: equal-probability variant set + amplitude interval
    # (v2-3: narrowed so colour excursions stay near the empirical support).
    r25_variants: tuple = ("candidate-1", "candidate-2", "candidate-3")
    r25_amplitude: tuple = (0.13, 0.18)
    # Cavity background: real-corpus dark box (anchor JSON cavity_dark_*).
    background_r: tuple = (0.3943, 0.4581)
    background_g: tuple = (0.2834, 0.3359)
    background_b: tuple = (0.3300, 0.3871)
    # Per-frame numpy post-process chain (applied after capture, before PNG;
    # v2-4 narrowed ranges, vignette floor kept above zero because real
    # endoscope frames always carry one).
    brightness: tuple = (0.92, 1.08)
    contrast: tuple = (0.92, 1.08)
    gamma: tuple = (0.90, 1.12)
    vignette: tuple = (0.10, 0.35)
    noise_sigma: tuple = (0.0, 0.008)
    # Texture bake (v2-1): texel resolution, chart gutter dilation, and the
    # extra texel-scale fine octave appended to every R25 variant ladder.
    texture_size: int = 1024
    gutter_px: int = 4
    fine_octave: float = 0.08
    # Global per-channel albedo multiplier fixed by the smoke colour gate
    # (rendered organ-region mean must land in the anchor band); recorded in
    # provenance. (1, 1, 1) means no calibration.
    calibration_multiplier: tuple = (1.0, 1.0, 1.0)
    # v3 vessel layer (design v3, 2026-08-10): the R23 implicit vessel field
    # composited into the baked texture BEFORE the gutter. Only effective
    # when `enabled` is True; the OFF path stays byte-identical regardless.
    vessel_enabled: bool = True
    # Frozen at the R23-accepted "small" scale: root vessel diameter =
    # vessel_ratio x canonical surface extent (c1_r23 R23_RATIOS[0]).
    vessel_ratio: float = 0.012
    # R23 antialias half-width in millimetres around the vessel boundary
    # (c1_r23 R23_ANTIALIAS_HALF_WIDTH_MM).
    vessel_antialias_mm: float = 0.10
    # Vessel colour box: real-corpus high-redness empirical support
    # (_c1_scratch/real_vessel_anchor.json: 310 frames, per-frame mean RGB of
    # the top-3% redness in-FOV pixels, p05-p95), rounded to 4 decimals as
    # the other anchored boxes are. The tree growth parameters themselves
    # are NOT knobs: they stay at the frozen R21 module constants and only
    # the per-sequence tree seed varies the layout.
    vessel_r: tuple = (0.6615, 0.7977)
    vessel_g: tuple = (0.4189, 0.5587)
    vessel_b: tuple = (0.4690, 0.6220)
    # Path to an R16-schema UV sidecar npz for the canonical topology; empty
    # generates the parametrization from the sequence's first frame with
    # xatlas at prime time. {workspace}/{dataflow} placeholders are expanded.
    uv_sidecar: str = ""


@dataclasses.dataclass
class DiversityConfig:
    """Track C diversity factors, each config-gated and default OFF."""

    appearance: AppearanceConfig = dataclasses.field(
        default_factory=AppearanceConfig)


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
    # Purified real corpus (Data Processor pipeline): visual_data/NN.mp4 +
    # force_data/NN.csv, frame i <-> force row i (alignment pre-validated).
    # Canonical path: data_sources.yaml[real_origin_data].path -- keep in sync.
    real_origin_root: str = "D:/Data Processor/Origin_data"
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
    diversity: DiversityConfig = dataclasses.field(default_factory=DiversityConfig)

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
    _validate_appearance(recipe.diversity.appearance)


def _check_interval(name, value, lo_min=None, hi_max=None, lo_gt=None):
    """Require a two-element (lo, hi) interval with lo <= hi inside bounds."""
    if len(value) != 2:
        raise ValueError(f"appearance.{name} must be a (lo, hi) pair")
    lo, hi = float(value[0]), float(value[1])
    if lo > hi:
        raise ValueError(f"appearance.{name} needs lo <= hi, got {value}")
    if lo_min is not None and lo < lo_min:
        raise ValueError(f"appearance.{name} low bound {lo} below {lo_min}")
    if hi_max is not None and hi > hi_max:
        raise ValueError(f"appearance.{name} high bound {hi} above {hi_max}")
    if lo_gt is not None and lo <= lo_gt:
        raise ValueError(f"appearance.{name} low bound {lo} must be > {lo_gt}")


def _validate_appearance(app):
    if app.seed < 0:
        raise ValueError(f"appearance.seed {app.seed} must be >= 0")
    if not app.r25_variants or not all(
            isinstance(v, str) and v for v in app.r25_variants):
        raise ValueError(
            "appearance.r25_variants must be a nonempty list of variant names")
    for name in ("albedo_r", "albedo_g", "albedo_b",
                 "background_r", "background_g", "background_b"):
        _check_interval(name, getattr(app, name), lo_min=0.0, hi_max=1.0)
    _check_interval("r25_amplitude", app.r25_amplitude, lo_min=0.0)
    _check_interval("brightness", app.brightness, lo_gt=0.0)
    _check_interval("contrast", app.contrast, lo_gt=0.0)
    _check_interval("gamma", app.gamma, lo_gt=0.0)
    _check_interval("vignette", app.vignette, lo_min=0.0, hi_max=1.0)
    _check_interval("noise_sigma", app.noise_sigma, lo_min=0.0)
    if app.texture_size < 16:
        raise ValueError(
            f"appearance.texture_size {app.texture_size} must be >= 16")
    if app.gutter_px < 0:
        raise ValueError(
            f"appearance.gutter_px {app.gutter_px} must be >= 0")
    if not app.fine_octave > 0.0:
        raise ValueError(
            f"appearance.fine_octave {app.fine_octave} must be > 0")
    if len(app.calibration_multiplier) != 3 or any(
            not float(m) > 0.0 for m in app.calibration_multiplier):
        raise ValueError(
            "appearance.calibration_multiplier must be three positive "
            f"per-channel factors, got {app.calibration_multiplier!r}")
    if not isinstance(app.uv_sidecar, str):
        raise ValueError("appearance.uv_sidecar must be a path string")
    if not isinstance(app.vessel_enabled, bool):
        raise ValueError(
            f"appearance.vessel_enabled must be a bool, got "
            f"{app.vessel_enabled!r}")
    if not 0.0 < app.vessel_ratio < 1.0:
        raise ValueError(
            f"appearance.vessel_ratio {app.vessel_ratio} outside (0, 1)")
    if not app.vessel_antialias_mm > 0.0:
        raise ValueError(
            f"appearance.vessel_antialias_mm {app.vessel_antialias_mm} "
            "must be > 0")
    for name in ("vessel_r", "vessel_g", "vessel_b"):
        _check_interval(name, getattr(app, name), lo_min=0.0, hi_max=1.0)
