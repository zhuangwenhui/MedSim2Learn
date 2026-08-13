"""Appearance domain randomization (Track C / C1, design v2 + v3 vessels):
draws, texel texture bake, per-frame textured meshes, and provenance.

Per-sequence draws come from ``numpy.random.SeedSequence([seed, ordinal])``
spawned into four child streams (organ / background / postprocess / vessel;
the vessel stream is the v3 append and leaves the first three streams'
draws bit-identical to v2). The postprocess stream re-derives one child per
frame index (``spawn_key=(2, frame_index)``), so any single frame's
photometric jitter is reproducible in isolation: same seed + same frame ->
same parameters.

v2 organ colouring (the v1 uniform flat paint and per-vertex colours were
rejected at the 2026-08-10 visual gate): the painter bakes ONE texture per
sequence from the R25 procedural field family (dpost.texture_bake, module
extracted from commit 9c74cf0) evaluated on the canonical FIRST frame, using
an xatlas UV parametrization of the canonical topology (an R16-schema
sidecar npz, or generated at prime time). Every frame's mesh is then rebuilt
through the proven R16 ``triangle_uvs + textures`` path with the SAME UV and
texture bytes -- the identity contract that keeps the texture glued to the
surface under deformation. A vertex-count or face-topology mismatch against
the locked UV basis raises, so a topology break can never produce a
wrongly-textured frame.

Everything here touches pixels only: cameras, geometry, forces, SampleIDs
and the real<->twin pairing are never modified.
"""

import dataclasses
import hashlib
import json
import os

import numpy as np
import open3d as o3d

from . import paths

# Commit that authored the R25 module this branch extracts by file.
R25_MODULE_SOURCE_COMMIT = "9c74cf0"
# Commit that authored the R21/R23 vessel modules this branch extracts by
# file (r23 branch, byte-exact).
VESSEL_MODULE_SOURCE_COMMIT = "9d3011f"
# Spawn keys of the four child streams under the per-sequence root. The
# vessel stream is the FOURTH child (v3): appending it leaves the first
# three children's spawn keys -- and therefore every v2 draw -- bit-identical.
ORGAN_STREAM_KEY = 0
BACKGROUND_STREAM_KEY = 1
POSTPROCESS_STREAM_KEY = 2
VESSEL_STREAM_KEY = 3
# Array schema of an R16 UV sidecar npz.
UV_SIDECAR_ARRAY_NAMES = (
    "source_faces", "uv_vertex_to_source_vertex", "uv_faces", "uv_vertices")

# Cached (h, w) -> squared normalized center distance for the vignette.
_VIGNETTE_R2_CACHE = {}


@dataclasses.dataclass(frozen=True)
class AppearanceDraw:
    """One sequence's fully-drawn appearance (deterministic from the seeds).

    ``base_rgb01`` is the raw draw from the real-corpus organ box;
    ``base_rgb01_calibrated`` applies the global per-channel calibration
    multiplier (smoke colour-gate correction, config-frozen) and
    ``base_rgb255`` is its round-half-up byte triple -- the R25 colour
    formula input. The bake knobs ride along so one draw fully describes
    the sequence's texture.
    """

    seed: int
    sequence_ordinal: int
    organ_mode: str  # always "r25_field" in v2 (uniform mode deleted)
    base_rgb01: tuple
    base_rgb01_calibrated: tuple
    base_rgb255: tuple
    r25_variant: str
    r25_amplitude: float
    background_rgb: tuple
    brightness_range: tuple
    contrast_range: tuple
    gamma_range: tuple
    vignette_range: tuple
    noise_sigma_range: tuple
    calibration_multiplier: tuple
    texture_size: int
    gutter_px: int
    fine_octave: float
    # v3 vessel layer: drawn from the fourth child stream (tree seed first,
    # then the colour channels). The draw-specific fields are None when the
    # layer is config-disabled; ratio/antialias always carry the config
    # values for provenance.
    vessel_enabled: bool = False
    vessel_tree_seed: object = None
    vessel_rgb01: object = None
    vessel_rgb01_calibrated: object = None
    vessel_rgb255: object = None
    vessel_ratio: float = 0.012
    vessel_antialias_mm: float = 0.10


def sample_appearance(cfg, sequence_ordinal):
    """Draw one sequence's appearance from SeedSequence([cfg.seed, ordinal]).

    The root spawns four child streams (organ / background / postprocess /
    vessel). Spawn keys are assigned by child ORDER, so the fourth (vessel)
    stream leaves the first three streams' draws bit-identical to the v2
    sampler -- locked by the pilot-golden regression tests.
    """
    root = np.random.SeedSequence([int(cfg.seed), int(sequence_ordinal)])
    organ_ss, background_ss, _post_ss, vessel_ss = root.spawn(4)

    organ = np.random.default_rng(organ_ss)
    base_rgb01 = tuple(
        float(organ.uniform(lo, hi))
        for lo, hi in (cfg.albedo_r, cfg.albedo_g, cfg.albedo_b))
    variant = str(cfg.r25_variants[int(organ.integers(len(cfg.r25_variants)))])
    amplitude = float(organ.uniform(*cfg.r25_amplitude))

    background = np.random.default_rng(background_ss)
    background_rgb = tuple(
        float(background.uniform(lo, hi))
        for lo, hi in (cfg.background_r, cfg.background_g, cfg.background_b))

    multiplier = tuple(float(m) for m in cfg.calibration_multiplier)
    calibrated = tuple(
        float(np.clip(c * m, 0.0, 1.0))
        for c, m in zip(base_rgb01, multiplier))

    # v3 vessel draws: tree seed FIRST, then the three colour channels (the
    # order is part of the provenance contract). Config-disabling the layer
    # skips the stream entirely; the other streams are unaffected either way.
    vessel_tree_seed = None
    vessel_rgb01 = None
    vessel_calibrated = None
    vessel_rgb255 = None
    if cfg.vessel_enabled:
        vessel = np.random.default_rng(vessel_ss)
        vessel_tree_seed = int(vessel.integers(2 ** 32))
        vessel_rgb01 = tuple(
            float(vessel.uniform(lo, hi))
            for lo, hi in (cfg.vessel_r, cfg.vessel_g, cfg.vessel_b))
        vessel_calibrated = tuple(
            float(np.clip(c * m, 0.0, 1.0))
            for c, m in zip(vessel_rgb01, multiplier))
        vessel_rgb255 = tuple(
            int(np.floor(c * 255.0 + 0.5)) for c in vessel_calibrated)

    return AppearanceDraw(
        seed=int(cfg.seed),
        sequence_ordinal=int(sequence_ordinal),
        organ_mode="r25_field",
        base_rgb01=base_rgb01,
        base_rgb01_calibrated=calibrated,
        base_rgb255=tuple(
            int(np.floor(c * 255.0 + 0.5)) for c in calibrated),
        r25_variant=variant,
        r25_amplitude=amplitude,
        background_rgb=background_rgb,
        brightness_range=tuple(float(v) for v in cfg.brightness),
        contrast_range=tuple(float(v) for v in cfg.contrast),
        gamma_range=tuple(float(v) for v in cfg.gamma),
        vignette_range=tuple(float(v) for v in cfg.vignette),
        noise_sigma_range=tuple(float(v) for v in cfg.noise_sigma),
        calibration_multiplier=multiplier,
        texture_size=int(cfg.texture_size),
        gutter_px=int(cfg.gutter_px),
        fine_octave=float(cfg.fine_octave),
        vessel_enabled=bool(cfg.vessel_enabled),
        vessel_tree_seed=vessel_tree_seed,
        vessel_rgb01=vessel_rgb01,
        vessel_rgb01_calibrated=vessel_calibrated,
        vessel_rgb255=vessel_rgb255,
        vessel_ratio=float(cfg.vessel_ratio),
        vessel_antialias_mm=float(cfg.vessel_antialias_mm),
    )


def _frame_seed_sequence(draw, frame_index):
    """Postprocess-stream child for one frame, addressable at random."""
    return np.random.SeedSequence(
        entropy=[int(draw.seed), int(draw.sequence_ordinal)],
        spawn_key=(POSTPROCESS_STREAM_KEY, int(frame_index)))


def frame_postprocess_params(draw, frame_index):
    """Deterministic per-frame photometric parameters; returns (params, rng).

    The returned rng has consumed exactly the five parameter draws and is the
    one to use for the frame's gaussian noise field, so the whole frame
    derives from the single per-frame seed.
    """
    rng = np.random.default_rng(_frame_seed_sequence(draw, frame_index))
    params = {
        "brightness": float(rng.uniform(*draw.brightness_range)),
        "contrast": float(rng.uniform(*draw.contrast_range)),
        "gamma": float(rng.uniform(*draw.gamma_range)),
        "vignette": float(rng.uniform(*draw.vignette_range)),
        "noise_sigma": float(rng.uniform(*draw.noise_sigma_range)),
    }
    return params, rng


def _vignette_radius_sq(h, w):
    """Squared distance from the image center, 1.0 at the farthest corner."""
    key = (int(h), int(w))
    cached = _VIGNETTE_R2_CACHE.get(key)
    if cached is None:
        cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
        yy = (np.arange(h, dtype=np.float64) - cy) ** 2
        xx = (np.arange(w, dtype=np.float64) - cx) ** 2
        r2 = yy[:, None] + xx[None, :]
        peak = float(r2.max())
        cached = r2 / peak if peak > 0.0 else r2
        _VIGNETTE_R2_CACHE[key] = cached
    return cached


def apply_postprocess(buf, params, rng):
    """brightness -> contrast -> gamma -> vignette -> noise, clipped to [0, 1].

    Pure numpy on the captured float buffer (H, W, 3); the caller converts to
    uint8 afterwards exactly as the legacy path does.
    """
    x = np.asarray(buf, dtype=np.float64) * params["brightness"]
    x = (x - 0.5) * params["contrast"] + 0.5
    np.clip(x, 0.0, 1.0, out=x)
    x **= params["gamma"]
    x *= (1.0 - params["vignette"]
          * _vignette_radius_sq(x.shape[0], x.shape[1]))[..., None]
    x += rng.normal(0.0, params["noise_sigma"], size=x.shape)
    np.clip(x, 0.0, 1.0, out=x)
    return x


def _file_sha256(path):
    """Streamed sha256 of one file's exact bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_uv_sidecar_npz(npz_path):
    """Load an R16-schema UV sidecar npz; returns (sidecar, uv_source_info).

    A sibling ``receipt.json`` (the R16 sidecar receipt) is honoured when
    present: its ``npz_sha256`` must match the file and its generator fields
    are carried into the provenance record. Lazy import keeps the OFF path
    free of the extracted route-line closure.
    """
    from . import c1_r16_uv_render as r16

    npz_sha256 = _file_sha256(npz_path)
    with np.load(npz_path, allow_pickle=False) as archive:
        if set(archive.files) != set(UV_SIDECAR_ARRAY_NAMES):
            raise ValueError(
                f"UV sidecar {npz_path} keys {sorted(archive.files)} differ "
                f"from the R16 schema {sorted(UV_SIDECAR_ARRAY_NAMES)}")
        arrays = {name: archive[name] for name in UV_SIDECAR_ARRAY_NAMES}

    generator, generator_version = "external", ""
    receipt_path = os.path.join(os.path.dirname(npz_path), "receipt.json")
    if os.path.isfile(receipt_path):
        with open(receipt_path, "r", encoding="utf-8") as fh:
            receipt = json.load(fh)
        recorded = receipt.get("npz_sha256")
        if recorded is not None and recorded != npz_sha256:
            raise ValueError(
                f"UV sidecar npz hash {npz_sha256} differs from its receipt "
                f"{receipt_path}")
        generator = str(receipt.get("generator", generator))
        generator_version = str(receipt.get("generator_version", ""))

    sidecar = r16.UvSidecar(
        source_faces=arrays["source_faces"],
        uv_vertex_to_source_vertex=arrays["uv_vertex_to_source_vertex"],
        uv_faces=arrays["uv_faces"],
        uv_vertices=arrays["uv_vertices"],
        generator=generator,
        generator_version=generator_version or "unrecorded",
    )
    info = {
        "kind": "external_npz",
        "path": os.path.abspath(npz_path),
        "npz_sha256": npz_sha256,
        "generator": generator,
        "generator_version": generator_version,
    }
    return sidecar, info


class AppearancePainter:
    """One sequence's appearance: baked texture, per-frame mesh, postprocess.

    ``prime`` locks the UV basis and bakes the texture ONCE from the
    sequence's canonical first frame; ``textured_mesh`` rebuilds every
    frame's mesh onto that UV with the same texture bytes. Priming is
    explicit-or-first-frame: the sequence renderer primes from the sorted
    listing's first PLY, and the preview refuses to run unprimed so it can
    never bake from a mid-sequence deformation. A vertex-count or topology
    mismatch raises ValueError (the F2 per-frame isolation turns that into a
    logged frame failure instead of a wrongly-textured PNG).
    """

    def __init__(self, draw, uv_sidecar_path=""):
        self.draw = draw
        self.uv_sidecar_path = uv_sidecar_path
        self._sidecar = None
        self._uv_info = None
        self._texture = None
        self._texture_sha256 = None
        self._coverage = None
        self._vessel_stats = None
        self._locked_vertex_count = None

    @property
    def background_rgb(self):
        return self.draw.background_rgb

    @property
    def primed(self):
        return self._texture is not None

    @property
    def texture(self):
        self.require_primed()
        return self._texture

    @property
    def texture_sha256(self):
        self.require_primed()
        return self._texture_sha256

    def require_primed(self):
        if not self.primed:
            raise ValueError(
                "appearance painter is not primed: prime it from the "
                "sequence's canonical FIRST frame before rendering")

    def _check_topology(self, sidecar, faces):
        """Frame faces must match the UV source faces row-for-row.

        DeformSim frame PLYs store each face cyclically rotated relative to
        the canonical mesh (verified 2026-08-10), so the comparison is the
        R16 oriented-cycle check: same row order and winding, any rotation.
        """
        from . import c1_r16_uv_render as r16

        try:
            r16.validate_oriented_face_rows(
                sidecar.source_faces,
                np.asarray(faces).astype(sidecar.source_faces.dtype,
                                         copy=False))
        except ValueError as exc:
            raise ValueError(
                f"appearance topology mismatch vs the UV sidecar: {exc}"
            ) from exc

    def prime(self, vertices, faces):
        """Lock the UV basis and bake the texture from the first frame."""
        if self.primed:
            return
        from . import c1_r16_uv_render as r16
        from . import texture_bake

        vertices = np.asarray(vertices, dtype=np.float64)
        faces = np.asarray(faces)
        if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
            raise ValueError("prime needs a nonempty (F, 3) face array")

        if self.uv_sidecar_path:
            sidecar, uv_info = _load_uv_sidecar_npz(self.uv_sidecar_path)
        else:
            sidecar = r16.generate_xatlas_sidecar(
                vertices, np.ascontiguousarray(faces, dtype=np.int32))
            uv_info = {
                "kind": "xatlas_generated",
                "source": "sequence_first_frame",
                "generator": sidecar.generator,
                "generator_version": sidecar.generator_version,
                "arrays_sha256": {
                    name: hashlib.sha256(np.ascontiguousarray(
                        getattr(sidecar, name)).tobytes()).hexdigest()
                    for name in UV_SIDECAR_ARRAY_NAMES},
            }
        r16.validate_uv_sidecar(sidecar, vertices, sidecar.source_faces)
        self._check_topology(sidecar, faces)

        draw = self.draw
        vessel_stats = None
        if draw.vessel_enabled:
            # v3: composite the seeded vessel layer into the bake. The tree
            # grows on the sidecar's canonical faces (already validated
            # against the frame topology above).
            texture, vessel_stats = texture_bake.bake_field_texture(
                vertices, sidecar.uv_vertices, sidecar.uv_faces,
                sidecar.uv_vertex_to_source_vertex, draw.r25_variant,
                draw.base_rgb01_calibrated, draw.r25_amplitude,
                size=draw.texture_size, gutter_px=draw.gutter_px,
                fine_wavelength=draw.fine_octave,
                vessel={"tree_seed": draw.vessel_tree_seed,
                        "ratio": draw.vessel_ratio,
                        "antialias_mm": draw.vessel_antialias_mm,
                        "rgb255": draw.vessel_rgb255},
                source_faces=sidecar.source_faces)
        else:
            texture = texture_bake.bake_field_texture(
                vertices, sidecar.uv_vertices, sidecar.uv_faces,
                sidecar.uv_vertex_to_source_vertex, draw.r25_variant,
                draw.base_rgb01_calibrated, draw.r25_amplitude,
                size=draw.texture_size, gutter_px=draw.gutter_px,
                fine_wavelength=draw.fine_octave)
        face_index, _bary = texture_bake.rasterize_uv_charts(
            sidecar.uv_vertices, sidecar.uv_faces, draw.texture_size)
        self._coverage = texture_bake.chart_coverage(
            face_index, len(sidecar.uv_faces))
        self._texture = texture
        self._texture_sha256 = hashlib.sha256(texture.tobytes()).hexdigest()
        self._vessel_stats = vessel_stats
        self._sidecar = sidecar
        self._uv_info = uv_info
        self._locked_vertex_count = len(vertices)

    def prime_from_ply(self, ply_path):
        """Prime from a PLY on disk (the sequence's first frame)."""
        mesh = o3d.io.read_triangle_mesh(ply_path)
        if not mesh.has_vertices():
            raise ValueError(f"cannot prime appearance from empty mesh: {ply_path}")
        self.prime(np.asarray(mesh.vertices, dtype=np.float64),
                   np.asarray(mesh.triangles))

    def textured_mesh(self, mesh):
        """Rebuild one frame's mesh onto the locked UV with the baked texture.

        Returns a NEW legacy Open3D mesh (R16 ``triangle_uvs + textures``
        contract) whose smooth vertex normals transfer from the source mesh
        through the UV mapping, so seam-duplicated vertices keep the shading
        of their source vertex.
        """
        self.require_primed()
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.triangles)
        if len(vertices) != self._locked_vertex_count:
            raise ValueError(
                f"appearance vertex count mismatch: frame has {len(vertices)} "
                f"vertices but the sequence UV basis has "
                f"{self._locked_vertex_count}; refusing to retexture a "
                "different topology")
        self._check_topology(self._sidecar, faces)

        from . import c1_r16_uv_render as r16

        rebuilt = r16.build_textured_mesh(vertices, self._sidecar, self._texture)
        # The rebuilt mesh is always a REAL Open3D object (build_textured_mesh
        # binds open3d itself), so fetch the real binding here even when the
        # module-level o3d has been replaced by the test fake for mesh I/O.
        import open3d

        normals = np.asarray(mesh.vertex_normals)
        if len(normals) == len(vertices):
            mapping = self._sidecar.uv_vertex_to_source_vertex
            rebuilt.vertex_normals = open3d.utility.Vector3dVector(
                np.asarray(normals, dtype=np.float64)[mapping])
        else:
            rebuilt.compute_vertex_normals()
        return rebuilt

    def postprocess(self, buf, frame_index):
        """Per-frame photometric chain on the captured float buffer."""
        params, rng = frame_postprocess_params(self.draw, frame_index)
        return apply_postprocess(buf, params, rng)

    def provenance_payload(self):
        """Draw + UV + texture provenance; requires a primed painter."""
        self.require_primed()
        payload = appearance_meta_payload(self.draw)
        payload["uv_source"] = dict(self._uv_info)
        payload["texture_sha256"] = self._texture_sha256
        payload["texture_coverage"] = dict(self._coverage)
        if self._vessel_stats is not None:
            payload["vessel"]["tree_stats"] = dict(self._vessel_stats)
        return payload


def make_painter(cfg, sequence_ordinal):
    """None when appearance DR is disabled, else a painter over a fresh draw."""
    if cfg is None or not cfg.enabled:
        return None
    uv_path = paths.expand(cfg.uv_sidecar) if cfg.uv_sidecar else ""
    return AppearancePainter(sample_appearance(cfg, sequence_ordinal),
                             uv_sidecar_path=uv_path)


def appearance_meta_payload(draw):
    """JSON-ready draw provenance block; byte-reproducible from the seeds."""
    from .texture_bake import FINE_OCTAVE_SEED_SALT, FINE_OCTAVE_WEIGHT

    if draw.vessel_enabled:
        vessel_block = {
            "enabled": True,
            "module_source_commit": VESSEL_MODULE_SOURCE_COMMIT,
            "stream_draw_order": ["tree_seed", "rgb01"],
            "tree_seed": int(draw.vessel_tree_seed),
            "rgb01": list(draw.vessel_rgb01),
            "rgb01_calibrated": list(draw.vessel_rgb01_calibrated),
            "rgb255": list(draw.vessel_rgb255),
            "ratio": float(draw.vessel_ratio),
            "antialias_mm": float(draw.vessel_antialias_mm),
        }
    else:
        vessel_block = {"enabled": False}
    return {
        "enabled": True,
        "design_version": "v3-vessel-composite",
        "seed": int(draw.seed),
        "sequence_ordinal": int(draw.sequence_ordinal),
        "seed_entropy": [int(draw.seed), int(draw.sequence_ordinal)],
        "child_spawn_keys": {
            "organ": [ORGAN_STREAM_KEY],
            "background": [BACKGROUND_STREAM_KEY],
            "postprocess": [POSTPROCESS_STREAM_KEY],
            "vessel": [VESSEL_STREAM_KEY],
        },
        "per_frame_postprocess_seeding": (
            "SeedSequence(entropy=seed_entropy, "
            "spawn_key=(postprocess, frame_index)); frame_index is the "
            "frame's position in the sorted PLY listing"),
        "organ_mode": draw.organ_mode,
        "base_rgb01": list(draw.base_rgb01),
        "calibration_multiplier": list(draw.calibration_multiplier),
        "base_rgb01_calibrated": list(draw.base_rgb01_calibrated),
        "base_rgb255": list(draw.base_rgb255),
        "r25_variant": draw.r25_variant,
        "r25_amplitude": draw.r25_amplitude,
        "r25_module_source_commit": R25_MODULE_SOURCE_COMMIT,
        "fine_octave": {
            "wavelength": draw.fine_octave,
            "weight": FINE_OCTAVE_WEIGHT,
            "seed_salt": FINE_OCTAVE_SEED_SALT,
        },
        "texture_size": int(draw.texture_size),
        "gutter_px": int(draw.gutter_px),
        "vessel": vessel_block,
        "background_rgb": list(draw.background_rgb),
        "postprocess_ranges": {
            "brightness": list(draw.brightness_range),
            "contrast": list(draw.contrast_range),
            "gamma": list(draw.gamma_range),
            "vignette": list(draw.vignette_range),
            "noise_sigma": list(draw.noise_sigma_range),
        },
        "numpy_version": np.__version__,
    }


def write_appearance_provenance(run_dir, painter):
    """Record the primed painter's provenance; returns the path written.

    Extends ``replay_meta.json`` in place when the run has one (the replay
    pipeline), otherwise writes a standalone ``appearance_meta.json`` (the
    bare ``main.py render`` entry). The painter must be primed so the
    payload can bind the UV source and the exact texture bytes.
    """
    payload = painter.provenance_payload()
    meta_path = os.path.join(run_dir, "replay_meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["appearance"] = payload
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        return meta_path
    out_path = os.path.join(run_dir, "appearance_meta.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"appearance": payload}, fh, indent=2)
    return out_path
