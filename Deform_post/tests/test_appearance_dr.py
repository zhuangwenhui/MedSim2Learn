"""C1 appearance domain-randomization tests, design v2 (texel-baked texture).

v2 replaces the rejected v1 vertex-colour path: the organ is ALWAYS coloured
by a per-sequence 1024^2 texture baked from the R25 field family (plus one
appended fine octave) on the sequence's canonical first frame, colour boxes
are anchored to the real-corpus statistics (_c1_scratch/real_color_anchor.json),
and the render path assigns `triangle_uvs + textures` per frame (R16 pattern).

Open3D's visualizer is replaced with an in-process fake mirroring only the
attribute surface dpost.render touches (same approach as test_render_guards);
the painter and bake run the real modules on a tiny synthetic UV quad. The
end-to-end OFF-parity / ON-smoke gates against real seq01 data run outside
pytest (see the C1 v2 task record).
"""

import builtins
import csv
import json
import os
import sys
import types

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FAKE_CAM_SIZE = 48

# The frozen v2 engineering ranges: real-corpus anchored colour boxes
# (2026-08-10 design v2 revision, _c1_scratch/real_color_anchor.json) and
# the v2-4 narrowed photometric post-process ranges.
FROZEN_RANGES = {
    "albedo_r": (0.8180, 0.8605),
    "albedo_g": (0.6944, 0.7519),
    "albedo_b": (0.7423, 0.7866),
    "r25_amplitude": (0.13, 0.18),
    "background_r": (0.3943, 0.4581),
    "background_g": (0.2834, 0.3359),
    "background_b": (0.3300, 0.3871),
    "brightness": (0.92, 1.08),
    "contrast": (0.92, 1.08),
    "gamma": (0.90, 1.12),
    "vignette": (0.10, 0.35),
    "noise_sigma": (0.0, 0.008),
}

QUAD_VERTS = np.array(
    [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], dtype=np.float64)
QUAD_FACES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
QUAD_UV = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
QUAD_MAPPING = np.arange(4, dtype=np.uint32)


def _write_toy_sidecar(path):
    """Persist the quad's UV sidecar in the R16 npz array schema.

    Written once per tmp_path: np.savez embeds zip timestamps, so a rewrite
    would change the file hash that the provenance round-trip pins.
    """
    if not os.path.isfile(str(path)):
        np.savez(path,
                 source_faces=QUAD_FACES,
                 uv_vertex_to_source_vertex=QUAD_MAPPING,
                 uv_faces=QUAD_FACES.astype(np.uint32),
                 uv_vertices=QUAD_UV)
    return str(path)


# ---------------------------------------------------------------------------
# Fake Open3D surface (only what dpost.render / dpost.diversity touch)
# ---------------------------------------------------------------------------

class _FakeIntrinsic:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class _FakeCam:
    def __init__(self, width=FAKE_CAM_SIZE, height=FAKE_CAM_SIZE):
        self.intrinsic = _FakeIntrinsic(width, height)
        self.extrinsic = np.eye(4)


class _FakeMesh:
    """Mesh fake exposing vertices/triangles/normals as plain arrays."""

    def __init__(self, vertices, faces=None):
        self.vertices = np.asarray(vertices, dtype=np.float64)
        self.triangles = (QUAD_FACES.copy() if faces is None
                          else np.asarray(faces))
        self.vertex_normals = np.zeros((len(self.vertices), 3))

    def compute_vertex_normals(self):
        self.vertex_normals = np.tile(
            np.array([0.0, 0.0, 1.0]), (len(self.vertices), 1))

    def has_vertices(self):
        return len(self.vertices) > 0


class _FakeViewControl:
    def convert_to_pinhole_camera_parameters(self):
        return _FakeCam()

    def convert_from_pinhole_camera_parameters(self, cam, allow_arbitrary=False):
        pass


class _FakeRenderOption:
    pass


class _MeshColorOption:
    Default = "fake-mesh-color-option-Default"
    Color = "fake-mesh-color-option-Color"


def _install_fake_o3d(monkeypatch, vertices_by_stem=None):
    """Patch render's AND diversity's o3d with a fake; returns shared state.

    ``vertices_by_stem`` maps PLY stems to ``(vertices, faces_or_None)`` so
    per-frame topology is controllable; unmapped stems load the toy quad.
    """
    from dpost import diversity as diversity_mod
    from dpost import render as render_mod

    state = types.SimpleNamespace(
        vertices_by_stem=dict(vertices_by_stem or {}),
        meshes={}, options=[], geoms=[], added_log=[])

    class FakeVisualizer:
        def create_window(self, visible=True, width=0, height=0):
            self._w, self._h = width, height

        def get_render_option(self):
            opt = _FakeRenderOption()
            state.options.append(opt)
            return opt

        def get_view_control(self):
            return _FakeViewControl()

        def add_geometry(self, geom, reset_bounding_box=True):
            state.geoms.append(geom)
            state.added_log.append(geom)

        def remove_geometry(self, geom, reset_bounding_box=True):
            state.geoms.remove(geom)

        def poll_events(self):
            pass

        def update_renderer(self):
            pass

        def capture_screen_float_buffer(self, do_render=False):
            ramp = np.linspace(0.0, 1.0, self._w)
            return np.broadcast_to(
                ramp, (self._h, self._w))[..., None].repeat(3, axis=2)

        def destroy_window(self):
            pass

    def read_triangle_mesh(path):
        stem = os.path.splitext(os.path.basename(path))[0]
        spec = state.vertices_by_stem.get(stem)
        if spec is None:
            mesh = _FakeMesh(QUAD_VERTS)
        else:
            verts, faces = spec
            mesh = _FakeMesh(verts, faces)
        state.meshes[stem] = mesh
        return mesh

    fake = types.SimpleNamespace(
        io=types.SimpleNamespace(
            read_pinhole_camera_parameters=lambda path: _FakeCam(),
            read_triangle_mesh=read_triangle_mesh,
            write_image=lambda path, arr: Image.fromarray(np.asarray(arr)).save(path),
        ),
        geometry=types.SimpleNamespace(Image=lambda arr: arr),
        visualization=types.SimpleNamespace(
            Visualizer=FakeVisualizer, MeshColorOption=_MeshColorOption),
    )
    monkeypatch.setattr(render_mod, "o3d", fake)
    monkeypatch.setattr(diversity_mod, "o3d", fake)
    return state


def _make_seq_dir(tmp_path, stems):
    ply_dir = tmp_path / "sim"
    ply_dir.mkdir(exist_ok=True)
    for stem in stems:
        (ply_dir / f"{stem}.ply").write_bytes(b"ply fake payload")
    cam_path = tmp_path / "camera.json"
    cam_path.write_text("{}")
    return str(ply_dir), str(cam_path)


STEMS = ["deformed_s0001_v0000", "deformed_s0001_v0001", "deformed_s0001_v0002"]


def _enabled_cfg(uv_sidecar="", **overrides):
    from dpost.config import AppearanceConfig

    cfg = AppearanceConfig(enabled=True, seed=1, texture_size=32, gutter_px=2,
                           uv_sidecar=uv_sidecar)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _primed_painter(tmp_path, **overrides):
    """Painter over the toy quad sidecar, primed on the quad's first frame."""
    from dpost.diversity import make_painter

    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path, **overrides), 1)
    painter.prime(QUAD_VERTS, QUAD_FACES)
    return painter


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------

def test_config_appearance_defaults_off_and_frozen_ranges():
    from dpost.config import load_recipe

    recipe = load_recipe(None)
    app = recipe.diversity.appearance
    assert app.enabled is False
    assert app.seed == 0
    # v2: the uniform flat-paint mode is deleted outright.
    assert not hasattr(app, "organ_uniform_prob")
    assert app.r25_variants == ("candidate-1", "candidate-2", "candidate-3")
    for name, expected in FROZEN_RANGES.items():
        assert tuple(getattr(app, name)) == pytest.approx(expected), name
    assert app.texture_size == 1024
    assert app.gutter_px == 4
    assert app.fine_octave == pytest.approx(0.08)
    assert tuple(app.calibration_multiplier) == pytest.approx((1.0, 1.0, 1.0))
    assert app.uv_sidecar == ""


def test_config_appearance_unknown_key_rejected(tmp_path):
    from dpost.config import load_recipe

    # The removed v1 knob must now be rejected, not silently ignored.
    bad = tmp_path / "bad.yaml"
    bad.write_text("diversity:\n  appearance:\n    organ_uniform_prob: 0.3\n")
    with pytest.raises(ValueError, match="organ_uniform_prob"):
        load_recipe(str(bad))


def test_config_appearance_yaml_plumbing(tmp_path):
    from dpost.config import load_recipe

    cfg = tmp_path / "recipe.yaml"
    cfg.write_text(
        "diversity:\n"
        "  appearance:\n"
        "    enabled: true\n"
        "    seed: 7\n"
        "    albedo_r: [0.82, 0.85]\n"
        "    texture_size: 512\n"
        "    calibration_multiplier: [1.05, 1.0, 0.98]\n"
        "    uv_sidecar: 'D:/somewhere/uv.npz'\n")
    app = load_recipe(str(cfg)).diversity.appearance
    assert app.enabled is True
    assert app.seed == 7
    assert tuple(app.albedo_r) == pytest.approx((0.82, 0.85))
    assert app.texture_size == 512
    assert tuple(app.calibration_multiplier) == pytest.approx((1.05, 1.0, 0.98))
    assert app.uv_sidecar == "D:/somewhere/uv.npz"
    # Untouched knobs keep the frozen defaults.
    assert tuple(app.albedo_g) == pytest.approx(FROZEN_RANGES["albedo_g"])


@pytest.mark.parametrize("snippet, match", [
    ("    seed: -3\n", "seed"),
    ("    albedo_r: [0.9, 0.8]\n", "albedo_r"),
    ("    background_g: [-0.1, 0.2]\n", "background_g"),
    ("    gamma: [0.0, 1.1]\n", "gamma"),
    ("    vignette: [0.0, 1.5]\n", "vignette"),
    ("    noise_sigma: [-0.01, 0.01]\n", "noise_sigma"),
    ("    r25_variants: []\n", "r25_variants"),
    ("    texture_size: 0\n", "texture_size"),
    ("    gutter_px: -1\n", "gutter_px"),
    ("    fine_octave: 0.0\n", "fine_octave"),
    ("    calibration_multiplier: [1.0, 1.0]\n", "calibration_multiplier"),
    ("    calibration_multiplier: [0.0, 1.0, 1.0]\n", "calibration_multiplier"),
])
def test_config_appearance_validation_rejects_bad_values(tmp_path, snippet, match):
    from dpost.config import load_recipe

    bad = tmp_path / "bad.yaml"
    bad.write_text("diversity:\n  appearance:\n" + snippet)
    with pytest.raises(ValueError, match=match):
        load_recipe(str(bad))


# ---------------------------------------------------------------------------
# Per-sequence sampler
# ---------------------------------------------------------------------------

def test_sample_appearance_deterministic():
    from dpost.diversity import appearance_meta_payload, sample_appearance

    cfg = _enabled_cfg()
    a = sample_appearance(cfg, 1)
    b = sample_appearance(cfg, 1)
    assert a == b
    assert appearance_meta_payload(a) == appearance_meta_payload(b)


def test_sample_appearance_varies_by_sequence_and_seed():
    from dpost.diversity import sample_appearance

    cfg = _enabled_cfg()
    base = sample_appearance(cfg, 1)
    other_seq = sample_appearance(cfg, 2)
    other_seed = sample_appearance(_enabled_cfg(seed=2), 1)
    assert base.base_rgb01 != other_seq.base_rgb01
    assert base.base_rgb01 != other_seed.base_rgb01
    assert base.background_rgb != other_seq.background_rgb


def test_sample_appearance_ranges_anchored():
    from dpost.diversity import sample_appearance

    for ordinal in range(1, 33):
        draw = sample_appearance(_enabled_cfg(), ordinal)
        assert draw.organ_mode == "r25_field"
        for value, key in zip(draw.base_rgb01,
                              ("albedo_r", "albedo_g", "albedo_b")):
            lo, hi = FROZEN_RANGES[key]
            assert lo <= value <= hi
        for value, key in zip(draw.background_rgb,
                              ("background_r", "background_g", "background_b")):
            lo, hi = FROZEN_RANGES[key]
            assert lo <= value <= hi
        assert draw.r25_variant in ("candidate-1", "candidate-2", "candidate-3")
        lo, hi = FROZEN_RANGES["r25_amplitude"]
        assert lo <= draw.r25_amplitude <= hi


def test_sample_appearance_calibration_multiplier_applied():
    from dpost.diversity import sample_appearance

    plain = sample_appearance(_enabled_cfg(), 1)
    mult = (1.05, 1.0, 0.90)
    scaled = sample_appearance(
        _enabled_cfg(calibration_multiplier=mult), 1)
    # Same underlying draw; only the calibrated albedo moves.
    assert scaled.base_rgb01 == plain.base_rgb01
    expected = tuple(
        float(np.clip(c * m, 0.0, 1.0))
        for c, m in zip(plain.base_rgb01, mult))
    assert scaled.base_rgb01_calibrated == pytest.approx(expected)
    assert scaled.base_rgb255 == tuple(
        int(np.floor(c * 255.0 + 0.5)) for c in expected)
    assert scaled.calibration_multiplier == pytest.approx(mult)


def test_frame_postprocess_params_deterministic_and_in_range():
    from dpost.diversity import frame_postprocess_params, sample_appearance

    draw = sample_appearance(_enabled_cfg(), 1)
    params_a, _rng_a = frame_postprocess_params(draw, 5)
    params_b, _rng_b = frame_postprocess_params(draw, 5)
    assert params_a == params_b
    params_c, _rng_c = frame_postprocess_params(draw, 6)
    assert params_a != params_c
    for frame in (0, 1, 5, 6, 1715):
        params, _rng = frame_postprocess_params(draw, frame)
        for key in ("brightness", "contrast", "gamma", "vignette", "noise_sigma"):
            lo, hi = FROZEN_RANGES[key]
            assert lo <= params[key] <= hi, (frame, key)


# ---------------------------------------------------------------------------
# Painter: UV sidecar + texture bake + per-frame textured mesh
# ---------------------------------------------------------------------------

def test_painter_prime_and_textured_mesh_contract(tmp_path):
    painter = _primed_painter(tmp_path)
    assert painter.primed
    assert painter.texture.dtype == np.uint8
    assert painter.texture.shape == (32, 32, 3)
    assert len(painter.texture_sha256) == 64

    mesh = _FakeMesh(QUAD_VERTS)
    mesh.compute_vertex_normals()
    out = painter.textured_mesh(mesh)
    assert len(out.triangle_uvs) == 3 * len(QUAD_FACES)
    assert out.has_textures() and len(out.textures) == 1
    np.testing.assert_array_equal(
        np.asarray(out.textures[0]), painter.texture)
    np.testing.assert_array_equal(
        np.asarray(out.vertices), QUAD_VERTS[QUAD_MAPPING])
    np.testing.assert_array_equal(
        np.asarray(out.triangles), QUAD_FACES)
    # Smooth normals transfer from the source mesh through the UV mapping.
    np.testing.assert_allclose(
        np.asarray(out.vertex_normals),
        mesh.vertex_normals[QUAD_MAPPING])


def test_painter_texture_matches_direct_bake(tmp_path):
    # v3: vessel_enabled=False keeps this the plain v2 bake-delegation lock;
    # the vessel-layer delegation twin lives in the v3 section below.
    from dpost.texture_bake import bake_field_texture

    painter = _primed_painter(tmp_path, vessel_enabled=False)
    draw = painter.draw
    expected = bake_field_texture(
        QUAD_VERTS, QUAD_UV, QUAD_FACES.astype(np.uint32), QUAD_MAPPING,
        draw.r25_variant, draw.base_rgb01_calibrated, draw.r25_amplitude,
        size=draw.texture_size, gutter_px=draw.gutter_px,
        fine_wavelength=draw.fine_octave)
    np.testing.assert_array_equal(painter.texture, expected)


def test_painter_texture_reused_across_deformed_frames(tmp_path):
    painter = _primed_painter(tmp_path)
    mesh_a = _FakeMesh(QUAD_VERTS)
    mesh_a.compute_vertex_normals()
    mesh_b = _FakeMesh(QUAD_VERTS + 0.25)  # deformed, same topology
    mesh_b.compute_vertex_normals()
    out_a = painter.textured_mesh(mesh_a)
    out_b = painter.textured_mesh(mesh_b)
    np.testing.assert_array_equal(
        np.asarray(out_a.textures[0]), np.asarray(out_b.textures[0]))
    np.testing.assert_allclose(
        np.asarray(out_b.vertices), (QUAD_VERTS + 0.25)[QUAD_MAPPING])


def test_painter_vertex_count_mismatch_raises(tmp_path):
    painter = _primed_painter(tmp_path)
    five = np.vstack([QUAD_VERTS, [[5.0, 5.0, 1.0]]])
    mesh = _FakeMesh(five)
    mesh.compute_vertex_normals()
    with pytest.raises(ValueError, match="vertex count"):
        painter.textured_mesh(mesh)


def test_painter_accepts_cyclically_rotated_faces(tmp_path):
    # DeformSim frame PLYs store each face cyclically rotated (probe
    # 2026-08-10): rotation-tolerant matching must accept them.
    painter = _primed_painter(tmp_path)
    rotated = np.array([[1, 2, 0], [2, 3, 0]], dtype=np.int32)
    mesh = _FakeMesh(QUAD_VERTS, rotated)
    mesh.compute_vertex_normals()
    out = painter.textured_mesh(mesh)
    assert out.has_textures()


def test_painter_rejects_broken_topology(tmp_path):
    painter = _primed_painter(tmp_path)
    reversed_winding = np.array([[0, 2, 1], [0, 2, 3]], dtype=np.int32)
    mesh = _FakeMesh(QUAD_VERTS, reversed_winding)
    mesh.compute_vertex_normals()
    with pytest.raises(ValueError, match="topology|face row"):
        painter.textured_mesh(mesh)


def test_painter_unprimed_textured_mesh_raises(tmp_path):
    from dpost.diversity import make_painter

    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    mesh = _FakeMesh(QUAD_VERTS)
    mesh.compute_vertex_normals()
    with pytest.raises(ValueError, match="primed"):
        painter.textured_mesh(mesh)


def test_painter_amplitude_zero_bakes_flat_texture(tmp_path):
    # v3: vessel_enabled=False isolates the amplitude-0 tissue short-circuit
    # (with vessels on, an amplitude-0 bake still carries the vessel layer).
    painter = _primed_painter(tmp_path, r25_amplitude=(0.0, 0.0),
                              vessel_enabled=False)
    expected = np.array(painter.draw.base_rgb255, dtype=np.uint8)
    assert np.array_equal(
        painter.texture, np.broadcast_to(expected, painter.texture.shape))


# ---------------------------------------------------------------------------
# Post-process chain numerics
# ---------------------------------------------------------------------------

def _flat_buffer(value=0.5, size=32):
    return np.full((size, size, 3), value, dtype=np.float64)


def test_postprocess_identity_params_is_noop():
    from dpost.diversity import apply_postprocess

    params = {"brightness": 1.0, "contrast": 1.0, "gamma": 1.0,
              "vignette": 0.0, "noise_sigma": 0.0}
    buf = np.linspace(0.0, 1.0, 32 * 32 * 3).reshape(32, 32, 3)
    out = apply_postprocess(buf, params, np.random.default_rng(0))
    np.testing.assert_allclose(out, buf, atol=1e-12)


def test_postprocess_chain_effects_and_clip_bounds():
    from dpost.diversity import apply_postprocess

    rng = np.random.default_rng(0)
    base = {"brightness": 1.0, "contrast": 1.0, "gamma": 1.0,
            "vignette": 0.0, "noise_sigma": 0.0}
    buf = _flat_buffer(0.5)

    brighter = apply_postprocess(buf, dict(base, brightness=1.08), rng)
    assert float(brighter.mean()) > 0.5
    dimmer = apply_postprocess(buf, dict(base, brightness=0.92), rng)
    assert float(dimmer.mean()) < 0.5

    contrasty = apply_postprocess(
        np.clip(buf + 0.2, 0, 1), dict(base, contrast=1.08), rng)
    assert float(contrasty.mean()) > 0.7  # values above midpoint move up

    dark_gamma = apply_postprocess(buf, dict(base, gamma=1.12), rng)
    assert float(dark_gamma.mean()) < 0.5  # gamma > 1 darkens midtones

    # Odd size so an exact center pixel exists (even grids center between
    # pixels and the center pixel would sit half a pixel into the falloff).
    odd = np.full((33, 33, 3), 0.5, dtype=np.float64)
    vignetted = apply_postprocess(odd, dict(base, vignette=0.35), rng)
    h, w = vignetted.shape[:2]
    center = float(vignetted[h // 2, w // 2].mean())
    corner = float(vignetted[0, 0].mean())
    assert corner < center
    assert center == pytest.approx(0.5, abs=1e-6)  # center stays untouched

    # Clip bounds: extreme inputs stay inside [0, 1].
    hot = apply_postprocess(
        _flat_buffer(0.99), dict(base, brightness=1.08, noise_sigma=0.008),
        np.random.default_rng(1))
    assert float(hot.max()) <= 1.0
    cold = apply_postprocess(
        _flat_buffer(0.01), dict(base, brightness=0.92, noise_sigma=0.008),
        np.random.default_rng(2))
    assert float(cold.min()) >= 0.0


def test_postprocess_per_frame_noise_deterministic(tmp_path):
    painter = _primed_painter(tmp_path)
    buf = np.linspace(0.0, 1.0, 24 * 24 * 3).reshape(24, 24, 3)
    out_a = painter.postprocess(buf, 3)
    out_b = painter.postprocess(buf, 3)
    np.testing.assert_array_equal(out_a, out_b)
    out_c = painter.postprocess(buf, 4)
    assert not np.array_equal(out_a, out_c)


# ---------------------------------------------------------------------------
# Render integration (fake Open3D, real painter + bake)
# ---------------------------------------------------------------------------

def _expected_off_png_bytes(tmp_path):
    """The byte-exact PNG the fake ramp buffer produces without appearance."""
    ramp = np.linspace(0.0, 1.0, FAKE_CAM_SIZE)
    buf = np.broadcast_to(
        ramp, (FAKE_CAM_SIZE, FAKE_CAM_SIZE))[..., None].repeat(3, axis=2)
    arr = (np.clip(buf, 0, 1) * 255).astype(np.uint8)
    ref = tmp_path / "expected_off.png"
    Image.fromarray(arr).save(ref)
    return ref.read_bytes()


def test_render_off_path_unchanged(tmp_path, monkeypatch):
    from dpost.render import render_fixed_camera_sequence

    state = _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS)
    png_dir = tmp_path / "png"
    n_ok, n_failed = render_fixed_camera_sequence(
        ply_dir, cam, str(png_dir), appearance=None)
    assert (n_ok, n_failed) == (3, 0)
    expected = _expected_off_png_bytes(tmp_path)
    for stem in STEMS:
        assert (png_dir / f"{stem}.png").read_bytes() == expected
    for opt in state.options:
        assert not hasattr(opt, "mesh_color_option"), \
            "OFF path must not touch the mesh colour option"
    # OFF adds the loaded source meshes untouched (no textured rebuild).
    assert state.added_log == list(state.meshes.values())


def test_render_on_textures_background_and_postprocess(tmp_path, monkeypatch):
    from dpost.diversity import make_painter
    from dpost.render import render_fixed_camera_sequence

    rotated = np.array([[1, 2, 0], [2, 3, 0]], dtype=np.int32)
    state = _install_fake_o3d(monkeypatch, vertices_by_stem={
        STEMS[1]: (QUAD_VERTS + 0.5, None),
        STEMS[2]: (QUAD_VERTS + 1.0, rotated),
    })
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS)
    png_dir = tmp_path / "png"
    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    n_ok, n_failed = render_fixed_camera_sequence(
        ply_dir, cam, str(png_dir), appearance=painter)
    assert (n_ok, n_failed) == (3, 0)

    draw = painter.draw
    opt = state.options[0]
    assert tuple(opt.background_color) == pytest.approx(draw.background_rgb)
    assert opt.mesh_color_option == _MeshColorOption.Color
    # Every added geometry is a textured UV mesh carrying the baked bytes.
    assert len(state.added_log) == 3
    for geom in state.added_log:
        assert geom.has_textures() and len(geom.textures) == 1
        assert len(geom.triangle_uvs) == 3 * len(QUAD_FACES)
        np.testing.assert_array_equal(
            np.asarray(geom.textures[0]), painter.texture)

    expected_off = _expected_off_png_bytes(tmp_path)
    for stem in STEMS:
        assert (png_dir / f"{stem}.png").read_bytes() != expected_off, \
            "post-process must change the written bytes"


def test_render_on_disabled_config_returns_none_painter():
    from dpost.config import load_recipe
    from dpost.diversity import make_painter

    recipe = load_recipe(None)
    assert make_painter(recipe.diversity.appearance, 1) is None


def test_render_on_isolates_topology_mismatch(tmp_path, monkeypatch):
    from dpost.diversity import make_painter
    from dpost.render import render_fixed_camera_sequence

    five = np.vstack([QUAD_VERTS, [[5.0, 5.0, 1.0]]])
    state = _install_fake_o3d(monkeypatch, vertices_by_stem={
        STEMS[1]: (QUAD_VERTS + 0.5, None),
        STEMS[2]: (five, None),  # topology break
    })
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS)
    png_dir = tmp_path / "png"
    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    n_ok, n_failed = render_fixed_camera_sequence(
        ply_dir, cam, str(png_dir), appearance=painter)
    assert (n_ok, n_failed) == (2, 1)
    with open(tmp_path / "render_errors" / "error_log.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["filename"] == STEMS[2] + ".ply"
    assert "vertex count" in rows[0]["error_message"]
    assert state.geoms == [], "failed frame must not leak geometry"


def test_preview_frame_applies_appearance(tmp_path, monkeypatch):
    from dpost.diversity import make_painter
    from dpost.render import render_preview_frame

    _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS[:1])
    ply_path = os.path.join(ply_dir, STEMS[0] + ".ply")

    plain_png = tmp_path / "preview_plain.png"
    render_preview_frame(ply_path, cam, str(plain_png))

    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    painter.prime_from_ply(ply_path)
    on_png = tmp_path / "preview_on.png"
    render_preview_frame(ply_path, cam, str(on_png), appearance=painter,
                         appearance_frame_index=5)
    assert on_png.read_bytes() != plain_png.read_bytes()

    # The preview must match the batch's per-frame post-process exactly.
    ref_painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    ramp = np.linspace(0.0, 1.0, FAKE_CAM_SIZE)
    buf = np.broadcast_to(
        ramp, (FAKE_CAM_SIZE, FAKE_CAM_SIZE))[..., None].repeat(3, axis=2)
    expected = (np.clip(ref_painter.postprocess(buf, 5), 0, 1) * 255).astype(np.uint8)
    got = np.asarray(Image.open(on_png).convert("RGB"))
    np.testing.assert_array_equal(got, expected)


def test_preview_frame_requires_primed_painter(tmp_path, monkeypatch):
    from dpost.diversity import make_painter
    from dpost.render import render_preview_frame

    _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS[:1])
    ply_path = os.path.join(ply_dir, STEMS[0] + ".ply")
    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    with pytest.raises(ValueError, match="primed"):
        render_preview_frame(ply_path, cam, str(tmp_path / "p.png"),
                             appearance=painter)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_provenance_extends_replay_meta_and_roundtrip(tmp_path):
    from dpost.diversity import write_appearance_provenance

    meta_path = tmp_path / "replay_meta.json"
    meta_path.write_text(json.dumps({"seq_id": "01", "seed": 521}))
    painter = _primed_painter(tmp_path)
    out = write_appearance_provenance(str(tmp_path), painter)
    assert os.path.abspath(out) == os.path.abspath(str(meta_path))
    with open(meta_path) as fh:
        meta = json.load(fh)
    assert meta["seq_id"] == "01" and meta["seed"] == 521, "original keys kept"
    block = meta["appearance"]
    draw = painter.draw
    # v3 code generation stamps every meta (vessel on or off) with the v3
    # design version; the vessel toggle is recorded inside block["vessel"].
    assert block["design_version"] == "v3-vessel-composite"
    assert block["organ_mode"] == "r25_field"
    assert block["seed"] == 1 and block["sequence_ordinal"] == 1
    assert block["r25_module_source_commit"] == "9c74cf0"
    assert block["r25_variant"] == draw.r25_variant
    assert block["r25_amplitude"] == pytest.approx(draw.r25_amplitude)
    assert block["base_rgb01"] == pytest.approx(list(draw.base_rgb01))
    assert block["base_rgb01_calibrated"] == pytest.approx(
        list(draw.base_rgb01_calibrated))
    assert block["calibration_multiplier"] == pytest.approx(
        list(draw.calibration_multiplier))
    assert block["background_rgb"] == pytest.approx(list(draw.background_rgb))
    assert block["texture_size"] == 32 and block["gutter_px"] == 2
    assert block["fine_octave"]["wavelength"] == pytest.approx(0.08)
    assert block["texture_sha256"] == painter.texture_sha256
    assert block["uv_source"]["kind"] == "external_npz"
    assert len(block["uv_source"]["npz_sha256"]) == 64
    # Round-trip: a fresh painter from the recorded seeds and the same UV
    # sidecar reproduces the payload (texture hash included).
    replay = _primed_painter(tmp_path, seed=block["seed"])
    assert replay.provenance_payload() == block


def test_provenance_standalone_meta_file(tmp_path):
    from dpost.diversity import AppearancePainter, sample_appearance
    from dpost.diversity import write_appearance_provenance

    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = AppearancePainter(
        sample_appearance(_enabled_cfg(), 2), uv_sidecar_path=uv_path)
    painter.prime(QUAD_VERTS, QUAD_FACES)
    out = write_appearance_provenance(str(tmp_path), painter)
    assert os.path.basename(out) == "appearance_meta.json"
    with open(out) as fh:
        payload = json.load(fh)
    assert payload["appearance"]["sequence_ordinal"] == 2
    assert payload["appearance"]["enabled"] is True


def test_provenance_requires_primed_painter(tmp_path):
    from dpost.diversity import make_painter, write_appearance_provenance

    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    painter = make_painter(_enabled_cfg(uv_sidecar=uv_path), 1)
    with pytest.raises(ValueError, match="primed"):
        write_appearance_provenance(str(tmp_path), painter)


# ---------------------------------------------------------------------------
# CLI plumbing (main.py render)
# ---------------------------------------------------------------------------

def _write_enabled_config(tmp_path, uv_path, **appearance_overrides):
    lines = ["diversity:", "  appearance:", "    enabled: true", "    seed: 1",
             "    texture_size: 32",
             f"    uv_sidecar: '{uv_path.replace(os.sep, '/')}'"]
    for key, value in appearance_overrides.items():
        lines.append(f"    {key}: {value}")
    cfg = tmp_path / "appearance.yaml"
    cfg.write_text("\n".join(lines) + "\n")
    return str(cfg)


def test_cmd_render_appearance_requires_ordinal(tmp_path, monkeypatch):
    import main

    _install_fake_o3d(monkeypatch)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ply_dir, cam = _make_seq_dir(run_dir, STEMS)
    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    cfg = _write_enabled_config(tmp_path, uv_path)
    with pytest.raises(SystemExit, match="seq-ordinal"):
        main.main(["render", "--config", cfg, "--ply-dir", ply_dir,
                   "--camera", cam, "--out-png-dir", str(run_dir / "png"),
                   "--yes"])


def test_cmd_render_appearance_writes_meta_and_pngs(tmp_path, monkeypatch):
    import main
    from dpost.diversity import sample_appearance

    _install_fake_o3d(monkeypatch)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ply_dir, cam = _make_seq_dir(run_dir, STEMS)
    png_dir = run_dir / "png"
    uv_path = _write_toy_sidecar(tmp_path / "toy_uv.npz")
    cfg = _write_enabled_config(tmp_path, uv_path)

    def _no_prompt(*args, **kwargs):
        raise AssertionError("--yes must skip the interactive prompt")

    monkeypatch.setattr(builtins, "input", _no_prompt)
    main.main(["render", "--config", cfg, "--ply-dir", ply_dir,
               "--camera", cam, "--out-png-dir", str(png_dir),
               "--seq-ordinal", "3", "--appearance-seed", "9", "--yes"])
    assert len(list(png_dir.glob("*.png"))) == len(STEMS)
    assert (run_dir / "render_preview.png").exists()
    meta_file = run_dir / "appearance_meta.json"
    assert meta_file.exists()
    with open(meta_file) as fh:
        block = json.load(fh)["appearance"]
    assert block["seed"] == 9, "--appearance-seed must override the recipe"
    assert block["sequence_ordinal"] == 3
    assert len(block["texture_sha256"]) == 64
    expected = sample_appearance(_enabled_cfg(seed=9), 3)
    assert block["base_rgb01"] == pytest.approx(list(expected.base_rgb01))


# ---------------------------------------------------------------------------
# v3 vessel layer: config, sampler stream, provenance, painter delegation
# ---------------------------------------------------------------------------

# Real-corpus vessel colour box (_c1_scratch/real_vessel_anchor.json p05-p95,
# 310 frames, top-3% redness in-FOV pixels), rounded to 4 decimals as the
# other anchored boxes are.
FROZEN_VESSEL_RANGES = {
    "vessel_r": (0.6615, 0.7977),
    "vessel_g": (0.4189, 0.5587),
    "vessel_b": (0.4690, 0.6220),
}

# Stream-stability goldens: the v2 pilot draws (ordinal 1, calibration
# [1.0656, 1.0068, 1.0404]) recorded in
# _c1_scratch/pilot_v2/seed*/appearance_meta.json and re-derived live from
# the pre-v3 sampler on 2026-08-10. The v3 sampler spawns a FOURTH child
# stream for the vessel layer; the first three streams' draws must stay
# BIT-identical, so these are asserted with exact float equality.
V2_GOLDEN_DRAWS = {
    1: ((0.8238916340462052, 0.7322704581094405, 0.7582390063250251),
        "candidate-3", 0.13850183111002082,
        (0.4412552926916305, 0.2993065646367678, 0.3531537001959621)),
    2: ((0.8186498931845185, 0.7107656911480348, 0.7504905412177896),
        "candidate-3", 0.1399078581485658,
        (0.4315833260204869, 0.2956883748050634, 0.3759145130633986)),
    3: ((0.826258438492826, 0.745782792375493, 0.7592470568688432),
        "candidate-1", 0.136802028437146,
        (0.4184074773718412, 0.3081298338471434, 0.35170901475788474)),
    4: ((0.8507129742584523, 0.7111874993493416, 0.7494552384814078),
        "candidate-1", 0.1441105468333308,
        (0.43995534301783157, 0.29125890674228744, 0.3654570275611078)),
    10: ((0.8587215623779383, 0.7429122491366471, 0.7480926192165178),
         "candidate-2", 0.16027175150212658,
         (0.395181252503142, 0.29681351746541706, 0.3404060062684352)),
}

# Postprocess-stream goldens: seed 1, ordinal 1, frames 0/5/9, captured from
# the pre-v3 sampler on 2026-08-10 (the per-frame chain derives from an
# explicit spawn_key and must be untouched by the fourth stream).
V2_GOLDEN_POSTPROCESS = {
    0: {"brightness": 1.0775648784043184, "contrast": 1.0222843730818534,
        "gamma": 1.1179222912672477, "vignette": 0.28722291518726284,
        "noise_sigma": 0.0025597447924201582},
    5: {"brightness": 0.9658521932446081, "contrast": 1.0760554051294233,
        "gamma": 1.0227563592018032, "vignette": 0.2156271332581473,
        "noise_sigma": 0.004424969509275962},
    9: {"brightness": 1.075454709434812, "contrast": 0.9755685956297304,
        "gamma": 1.0754813689127982, "vignette": 0.3147002653284175,
        "noise_sigma": 0.0043517192705634635},
}

V2_PILOT_CALIBRATION = (1.0656, 1.0068, 1.0404)


def test_config_vessel_defaults_frozen():
    from dpost.config import load_recipe

    app = load_recipe(None).diversity.appearance
    assert app.vessel_enabled is True
    assert app.vessel_ratio == pytest.approx(0.012)  # R23 "small", frozen
    assert app.vessel_antialias_mm == pytest.approx(0.10)
    for name, expected in FROZEN_VESSEL_RANGES.items():
        assert tuple(getattr(app, name)) == pytest.approx(expected), name


def test_config_vessel_yaml_plumbing(tmp_path):
    from dpost.config import load_recipe

    cfg = tmp_path / "recipe.yaml"
    cfg.write_text(
        "diversity:\n"
        "  appearance:\n"
        "    enabled: true\n"
        "    vessel_enabled: false\n")
    app = load_recipe(str(cfg)).diversity.appearance
    assert app.vessel_enabled is False
    assert app.vessel_ratio == pytest.approx(0.012)


@pytest.mark.parametrize("snippet, match", [
    ("    vessel_ratio: 0.0\n", "vessel_ratio"),
    ("    vessel_ratio: 1.5\n", "vessel_ratio"),
    ("    vessel_antialias_mm: 0.0\n", "vessel_antialias_mm"),
    ("    vessel_r: [0.9, 0.8]\n", "vessel_r"),
    ("    vessel_g: [-0.1, 0.5]\n", "vessel_g"),
    ("    vessel_b: [0.4, 1.2]\n", "vessel_b"),
    ("    vessel_enabled: 3\n", "vessel_enabled"),
])
def test_config_vessel_validation_rejects_bad_values(tmp_path, snippet, match):
    from dpost.config import load_recipe

    bad = tmp_path / "bad.yaml"
    bad.write_text("diversity:\n  appearance:\n" + snippet)
    with pytest.raises(ValueError, match=match):
        load_recipe(str(bad))


def test_sampler_first_three_streams_bit_identical_to_v2_pilot():
    from dpost.diversity import sample_appearance

    for seed, (base, variant, amplitude, background) in V2_GOLDEN_DRAWS.items():
        draw = sample_appearance(
            _enabled_cfg(seed=seed,
                         calibration_multiplier=V2_PILOT_CALIBRATION), 1)
        assert draw.base_rgb01 == base, seed
        assert draw.r25_variant == variant, seed
        assert draw.r25_amplitude == amplitude, seed
        assert draw.background_rgb == background, seed


def test_sampler_postprocess_stream_bit_identical_to_v2():
    from dpost.diversity import frame_postprocess_params, sample_appearance

    draw = sample_appearance(
        _enabled_cfg(seed=1, calibration_multiplier=V2_PILOT_CALIBRATION), 1)
    for frame, expected in V2_GOLDEN_POSTPROCESS.items():
        params, _rng = frame_postprocess_params(draw, frame)
        assert params == expected, frame


def test_sampler_vessel_draws_deterministic_and_in_box():
    from dpost.diversity import sample_appearance

    for ordinal in range(1, 12):
        draw = sample_appearance(_enabled_cfg(), ordinal)
        replay = sample_appearance(_enabled_cfg(), ordinal)
        assert draw.vessel_enabled is True
        assert draw == replay
        assert isinstance(draw.vessel_tree_seed, int)
        assert draw.vessel_tree_seed >= 0
        for value, key in zip(draw.vessel_rgb01,
                              ("vessel_r", "vessel_g", "vessel_b")):
            lo, hi = FROZEN_VESSEL_RANGES[key]
            assert lo <= value <= hi
        assert draw.vessel_ratio == pytest.approx(0.012)
        assert draw.vessel_antialias_mm == pytest.approx(0.10)


def test_sampler_vessel_calibration_applied():
    from dpost.diversity import sample_appearance

    plain = sample_appearance(_enabled_cfg(), 1)
    mult = (1.05, 1.0, 0.90)
    scaled = sample_appearance(_enabled_cfg(calibration_multiplier=mult), 1)
    assert scaled.vessel_rgb01 == plain.vessel_rgb01
    expected = tuple(
        float(np.clip(c * m, 0.0, 1.0))
        for c, m in zip(plain.vessel_rgb01, mult))
    assert scaled.vessel_rgb01_calibrated == pytest.approx(expected)
    assert scaled.vessel_rgb255 == tuple(
        int(np.floor(c * 255.0 + 0.5)) for c in expected)


def test_sampler_vessel_disabled_leaves_other_streams_unchanged():
    from dpost.diversity import sample_appearance

    on = sample_appearance(_enabled_cfg(), 1)
    off = sample_appearance(_enabled_cfg(vessel_enabled=False), 1)
    assert off.vessel_enabled is False
    assert off.vessel_tree_seed is None
    assert off.vessel_rgb01 is None
    assert off.vessel_rgb01_calibrated is None
    assert off.vessel_rgb255 is None
    # Organ / background / postprocess draws are stream-independent of the
    # vessel toggle.
    assert off.base_rgb01 == on.base_rgb01
    assert off.r25_variant == on.r25_variant
    assert off.r25_amplitude == on.r25_amplitude
    assert off.background_rgb == on.background_rgb


def test_sampler_vessel_varies_by_seed_and_ordinal():
    from dpost.diversity import sample_appearance

    base = sample_appearance(_enabled_cfg(), 1)
    other_seq = sample_appearance(_enabled_cfg(), 2)
    other_seed = sample_appearance(_enabled_cfg(seed=2), 1)
    assert base.vessel_tree_seed != other_seq.vessel_tree_seed
    assert base.vessel_tree_seed != other_seed.vessel_tree_seed
    assert base.vessel_rgb01 != other_seq.vessel_rgb01


def test_painter_vessel_texture_matches_direct_bake(tmp_path):
    from dpost.texture_bake import bake_field_texture

    painter = _primed_painter(tmp_path, vessel_ratio=0.2)
    draw = painter.draw
    assert draw.vessel_enabled is True
    expected, stats = bake_field_texture(
        QUAD_VERTS, QUAD_UV, QUAD_FACES.astype(np.uint32), QUAD_MAPPING,
        draw.r25_variant, draw.base_rgb01_calibrated, draw.r25_amplitude,
        size=draw.texture_size, gutter_px=draw.gutter_px,
        fine_wavelength=draw.fine_octave,
        vessel={"tree_seed": draw.vessel_tree_seed,
                "ratio": draw.vessel_ratio,
                "antialias_mm": draw.vessel_antialias_mm,
                "rgb255": draw.vessel_rgb255},
        source_faces=QUAD_FACES)
    np.testing.assert_array_equal(painter.texture, expected)
    assert stats["vessel_texels"] > 0


def test_provenance_vessel_block(tmp_path):
    painter = _primed_painter(tmp_path, vessel_ratio=0.2)
    block = painter.provenance_payload()
    assert block["design_version"] == "v3-vessel-composite"
    vessel = block["vessel"]
    draw = painter.draw
    assert vessel["enabled"] is True
    assert vessel["module_source_commit"] == "9d3011f"
    assert vessel["tree_seed"] == draw.vessel_tree_seed
    assert vessel["rgb01"] == pytest.approx(list(draw.vessel_rgb01))
    assert vessel["rgb01_calibrated"] == pytest.approx(
        list(draw.vessel_rgb01_calibrated))
    assert vessel["rgb255"] == list(draw.vessel_rgb255)
    assert vessel["ratio"] == pytest.approx(0.2)
    assert vessel["antialias_mm"] == pytest.approx(0.10)
    stats = vessel["tree_stats"]
    assert stats["segment_count"] >= 1
    assert stats["total_length_mm"] > 0.0
    assert 0.0 <= stats["vessel_texel_fraction"] <= 1.0
    # Round-trip: a fresh painter over the same seeds reproduces the block.
    replay = _primed_painter(tmp_path, vessel_ratio=0.2)
    assert replay.provenance_payload() == block


def test_provenance_vessel_disabled_block(tmp_path):
    painter = _primed_painter(tmp_path, vessel_enabled=False)
    block = painter.provenance_payload()
    assert block["design_version"] == "v3-vessel-composite"
    assert block["vessel"] == {"enabled": False}
