"""F1/F2/F3 robustness-guard tests (render preview gate, blank-frame assert,
per-frame error isolation, real-extract alignment sidecar, serialize coverage).

Open3D and cv2 are replaced with in-process fakes so the guards are exercised
without a GL context or video codecs; the fakes mirror only the attribute
surface the production code touches. The end-to-end byte-parity gate against
real seq01 data runs outside pytest (see the F1/F2/F3 task record).
"""

import builtins
import csv
import os
import sys
import types

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

CORRUPT_MARKER = b"CORRUPTPLY"
FAKE_CAM_SIZE = 48


# ---------------------------------------------------------------------------
# Fake Open3D surface (only what dpost.render touches)
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
    def __init__(self, empty=False):
        self._empty = empty

    def compute_vertex_normals(self):
        pass

    def has_vertices(self):
        return not self._empty


class _FakeViewControl:
    def convert_to_pinhole_camera_parameters(self):
        return _FakeCam()

    def convert_from_pinhole_camera_parameters(self, cam, allow_arbitrary=False):
        pass


class _FakeRenderOption:
    pass


def _install_fake_o3d(monkeypatch, blank_stems=(), blank_all=False):
    """Patch dpost.render's o3d with a fake; returns the shared state object.

    ``blank_stems`` / ``blank_all`` make capture_screen_float_buffer return an
    all-zero buffer for the named PLY stems (simulating the regressed-camera
    blank frame) while every other frame gets a non-blank gradient.
    """
    from dpost import render as render_mod

    state = types.SimpleNamespace(
        blank_stems=set(blank_stems), blank_all=blank_all,
        last_stem=None, geoms=[], windows=0)

    class FakeVisualizer:
        def create_window(self, visible=True, width=0, height=0):
            state.windows += 1
            self._w, self._h = width, height

        def get_render_option(self):
            return _FakeRenderOption()

        def get_view_control(self):
            return _FakeViewControl()

        def add_geometry(self, geom, reset_bounding_box=True):
            state.geoms.append(geom)

        def remove_geometry(self, geom, reset_bounding_box=True):
            state.geoms.remove(geom)

        def poll_events(self):
            pass

        def update_renderer(self):
            pass

        def capture_screen_float_buffer(self, do_render=False):
            if state.blank_all or state.last_stem in state.blank_stems:
                return np.zeros((self._h, self._w, 3), dtype=np.float64)
            ramp = np.linspace(0.0, 1.0, self._w)
            return np.broadcast_to(
                ramp, (self._h, self._w))[..., None].repeat(3, axis=2)

        def destroy_window(self):
            pass

    def read_triangle_mesh(path):
        state.last_stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, "rb") as fh:
            corrupt = fh.read().startswith(CORRUPT_MARKER)
        return _FakeMesh(empty=corrupt)

    fake = types.SimpleNamespace(
        io=types.SimpleNamespace(
            read_pinhole_camera_parameters=lambda path: _FakeCam(),
            read_triangle_mesh=read_triangle_mesh,
            write_image=lambda path, arr: Image.fromarray(np.asarray(arr)).save(path),
        ),
        geometry=types.SimpleNamespace(Image=lambda arr: arr),
        visualization=types.SimpleNamespace(Visualizer=FakeVisualizer),
    )
    monkeypatch.setattr(render_mod, "o3d", fake)
    return state


def _make_seq_dir(tmp_path, stems, corrupt=()):
    """Write fake PLY files + a dummy camera.json; returns (ply_dir, cam_path)."""
    ply_dir = tmp_path / "sim"
    ply_dir.mkdir(exist_ok=True)
    for stem in stems:
        payload = CORRUPT_MARKER if stem in corrupt else b"ply fake payload"
        (ply_dir / f"{stem}.ply").write_bytes(payload)
    cam_path = tmp_path / "camera.json"
    cam_path.write_text("{}")
    return str(ply_dir), str(cam_path)


STEMS = ["deformed_s0001_v0000", "deformed_s0001_v0001", "deformed_s0001_v0002"]


# ---------------------------------------------------------------------------
# F1 -- blank-frame assertion + preview
# ---------------------------------------------------------------------------

def test_preview_blank_frame_raises(tmp_path, monkeypatch):
    from dpost.render import render_preview_frame

    _install_fake_o3d(monkeypatch, blank_all=True)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS[:1])
    out_png = tmp_path / "render_preview.png"
    with pytest.raises(AssertionError, match=STEMS[0]):
        render_preview_frame(
            os.path.join(ply_dir, STEMS[0] + ".ply"), cam, str(out_png))
    assert not out_png.exists(), "blank preview must not be written"


def test_preview_good_frame_written(tmp_path, monkeypatch):
    from dpost.render import render_preview_frame

    _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS[:1])
    out_png = tmp_path / "render_preview.png"
    std = render_preview_frame(
        os.path.join(ply_dir, STEMS[0] + ".ply"), cam, str(out_png))
    assert out_png.exists()
    assert std > 1e-4


def test_sequence_blank_frames_raise_and_log(tmp_path, monkeypatch):
    from dpost.render import render_fixed_camera_sequence

    _install_fake_o3d(monkeypatch, blank_all=True)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS[:2])
    png_dir = tmp_path / "png"
    with pytest.raises(RuntimeError):
        render_fixed_camera_sequence(ply_dir, cam, str(png_dir))
    assert not list(png_dir.glob("*.png")), "no black PNG may be written"
    log = tmp_path / "render_errors" / "error_log.csv"
    assert log.exists()
    text = log.read_text()
    assert "blank render" in text
    for stem in STEMS[:2]:
        assert stem in text


# ---------------------------------------------------------------------------
# F2 -- per-frame render error isolation
# ---------------------------------------------------------------------------

def test_corrupt_frame_isolated_and_logged(tmp_path, monkeypatch):
    from dpost.render import render_fixed_camera_sequence

    state = _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS, corrupt={STEMS[1]})
    png_dir = tmp_path / "png"
    n_ok, n_failed = render_fixed_camera_sequence(ply_dir, cam, str(png_dir))
    assert (n_ok, n_failed) == (2, 1)
    written = sorted(p.name for p in png_dir.glob("*.png"))
    assert written == [STEMS[0] + ".png", STEMS[2] + ".png"]
    with open(tmp_path / "render_errors" / "error_log.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["filename"] == STEMS[1] + ".ply"
    assert rows[0]["error_message"]
    assert state.geoms == [], "failed frame must not leak geometry into the scene"


def test_wholly_failed_sequence_raises(tmp_path, monkeypatch):
    from dpost.render import render_fixed_camera_sequence

    _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS, corrupt=set(STEMS))
    with pytest.raises(RuntimeError, match="0"):
        render_fixed_camera_sequence(ply_dir, cam, str(tmp_path / "png"))
    with open(tmp_path / "render_errors" / "error_log.csv", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == len(STEMS)


def test_error_log_stale_file_replaced(tmp_path, monkeypatch):
    from dpost.render import render_fixed_camera_sequence

    _install_fake_o3d(monkeypatch)
    ply_dir, cam = _make_seq_dir(tmp_path, STEMS)
    log_dir = tmp_path / "render_errors"
    log_dir.mkdir()
    stale = log_dir / "error_log.csv"
    stale.write_text("filename,error_message\nstale.ply,old failure\n")
    n_ok, n_failed = render_fixed_camera_sequence(
        ply_dir, cam, str(tmp_path / "png"))
    assert (n_ok, n_failed) == (3, 0)
    assert not stale.exists(), "clean run must not keep a stale error log"


# ---------------------------------------------------------------------------
# F1 -- preview + confirm gate in the render CLI entry
# ---------------------------------------------------------------------------

def _cli_render_args(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    ply_dir, cam = _make_seq_dir(run_dir, STEMS)
    png_dir = run_dir / "png"
    argv = ["render", "--ply-dir", ply_dir, "--camera", cam,
            "--out-png-dir", str(png_dir)]
    return argv, run_dir, png_dir


def test_cmd_render_yes_skips_prompt(tmp_path, monkeypatch):
    import main

    _install_fake_o3d(monkeypatch)
    argv, run_dir, png_dir = _cli_render_args(tmp_path)

    def _no_prompt(*args, **kwargs):
        raise AssertionError("--yes must skip the interactive prompt")

    monkeypatch.setattr(builtins, "input", _no_prompt)
    main.main(argv + ["--yes"])
    assert (run_dir / "render_preview.png").exists()
    assert not (png_dir / "render_preview.png").exists(), \
        "preview must stay out of the paired PNG dir"
    assert len(list(png_dir.glob("*.png"))) == len(STEMS)


def test_cmd_render_prompt_abort(tmp_path, monkeypatch):
    import main

    _install_fake_o3d(monkeypatch)
    argv, run_dir, png_dir = _cli_render_args(tmp_path)
    answers = iter(["zzz", "q"])
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(answers))
    with pytest.raises(SystemExit):
        main.main(argv)
    assert (run_dir / "render_preview.png").exists()
    assert not list(png_dir.glob("*.png")), "aborted run must not batch-render"


def test_cmd_render_prompt_proceed(tmp_path, monkeypatch):
    import main

    _install_fake_o3d(monkeypatch)
    argv, _run_dir, png_dir = _cli_render_args(tmp_path)
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "y")
    main.main(argv)
    assert len(list(png_dir.glob("*.png"))) == len(STEMS)


# ---------------------------------------------------------------------------
# F2 -- real-extract alignment sidecar + strict flag
# ---------------------------------------------------------------------------

class _FakeCapture:
    frames = []

    def __init__(self, path):
        self._i = 0

    def isOpened(self):
        return True

    def get(self, prop):
        return float(len(self.frames))

    def read(self):
        if self._i < len(self.frames):
            frame = self.frames[self._i]
            self._i += 1
            return True, frame
        return False, None

    def release(self):
        pass


def _write_force_csv(path, n_rows):
    with open(path, "w", newline="") as fh:
        for i in range(n_rows):
            fh.write(f"{0.1 * i},{0.2 * i},{0.3 * i}\n")


def _install_fake_capture(monkeypatch, n_frames):
    from dpost import realvideo as rv

    class Cap(_FakeCapture):
        frames = [np.full((32, 32, 3), 60 + 10 * i, np.uint8)
                  for i in range(n_frames)]

    monkeypatch.setattr(rv.cv2, "VideoCapture", Cap)
    return rv


def test_realvideo_sidecar_records_drop(tmp_path, monkeypatch):
    import json

    rv = _install_fake_capture(monkeypatch, n_frames=5)
    csv_path = tmp_path / "01.csv"
    _write_force_csv(csv_path, 2)
    out_dir = tmp_path / "seq01"
    written, _png_dir, _labels = rv.extract_sequence(
        "01", "dummy.mp4", str(csv_path), str(out_dir), size=32)
    assert written == 2
    with open(out_dir / "alignment.json") as fh:
        align = json.load(fh)
    assert align == {"n_frames": 5, "n_forces": 2, "paired": 2, "dropped": 3}


def test_realvideo_strict_raises_on_short_csv(tmp_path, monkeypatch):
    import json

    rv = _install_fake_capture(monkeypatch, n_frames=5)
    csv_path = tmp_path / "01.csv"
    _write_force_csv(csv_path, 2)
    out_dir = tmp_path / "seq01"
    with pytest.raises(ValueError, match="strict"):
        rv.extract_sequence(
            "01", "dummy.mp4", str(csv_path), str(out_dir), size=32,
            strict=True)
    with open(out_dir / "alignment.json") as fh:
        align = json.load(fh)
    assert align["n_frames"] == 5 and align["n_forces"] == 2
    assert align["paired"] == 0
    png_dir = out_dir / "png"
    assert not png_dir.is_dir() or not list(png_dir.glob("*.png")), \
        "strict abort must not extract frames"


def test_realvideo_strict_tolerates_matched_counts(tmp_path, monkeypatch):
    import json

    rv = _install_fake_capture(monkeypatch, n_frames=3)
    csv_path = tmp_path / "02.csv"
    _write_force_csv(csv_path, 3)
    out_dir = tmp_path / "seq02"
    written, png_dir, labels = rv.extract_sequence(
        "02", "dummy.mp4", str(csv_path), str(out_dir), size=32, strict=True)
    assert written == 3
    with open(out_dir / "alignment.json") as fh:
        align = json.load(fh)
    assert align == {"n_frames": 3, "n_forces": 3, "paired": 3, "dropped": 0}
    assert len(os.listdir(png_dir)) == 3
    with open(labels, newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 3


# ---------------------------------------------------------------------------
# F3 -- serialize coverage line, dropped manifest, opt-in assertion
# ---------------------------------------------------------------------------

def _make_png_labels(tmp_path, n_pngs, n_labeled):
    png_dir = tmp_path / "png"
    png_dir.mkdir()
    stems = [f"deformed_s0001_v{i:04d}" for i in range(n_pngs)]
    for i, stem in enumerate(stems):
        arr = np.full((8, 8, 3), 20 * (i + 1), np.uint8)
        Image.fromarray(arr).save(png_dir / f"{stem}.png")
    labels = tmp_path / "labels.csv"
    with open(labels, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["SampleID", "force_x", "force_y", "force_z"])
        for stem in stems[:n_labeled]:
            writer.writerow([stem, "0.1", "0.2", "0.3"])
    return str(png_dir), str(labels), stems


def test_serialize_coverage_line_and_manifest(tmp_path, capsys):
    from dpost.dataset.serialize import serialize_labels_dataset

    png_dir, labels, stems = _make_png_labels(tmp_path, n_pngs=3, n_labeled=2)
    out_dir = tmp_path / "dataset"
    res = serialize_labels_dataset(png_dir, labels, str(out_dir))
    assert res["total_samples"] == 2, "default warn-and-drop behavior preserved"
    out = capsys.readouterr().out
    assert "matched 2 / 3 PNGs, dropped 1" in out
    manifest = out_dir / "dropped_stems.csv"
    assert manifest.exists()
    with open(manifest, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["stem"] for r in rows] == [stems[2]]
    assert rows[0]["reason"]
    assert (out_dir / "metadata.yaml").exists()


def test_serialize_full_coverage_no_manifest(tmp_path, capsys):
    from dpost.dataset.serialize import serialize_labels_dataset

    png_dir, labels, _stems = _make_png_labels(tmp_path, n_pngs=2, n_labeled=2)
    out_dir = tmp_path / "dataset"
    res = serialize_labels_dataset(
        png_dir, labels, str(out_dir), require_full_coverage=True)
    assert res["total_samples"] == 2
    assert "matched 2 / 2 PNGs, dropped 0" in capsys.readouterr().out
    assert not (out_dir / "dropped_stems.csv").exists()


def test_serialize_require_full_coverage_raises(tmp_path):
    from dpost.dataset.serialize import serialize_labels_dataset

    png_dir, labels, _stems = _make_png_labels(tmp_path, n_pngs=3, n_labeled=2)
    out_dir = tmp_path / "dataset"
    with pytest.raises(RuntimeError, match="coverage"):
        serialize_labels_dataset(
            png_dir, labels, str(out_dir), require_full_coverage=True)
    assert not (out_dir / "metadata.yaml").exists(), \
        "failed coverage must not leave a consumable dataset"


# ---------------------------------------------------------------------------
# F3 -- hard count reconciliation for the synthetic path
# ---------------------------------------------------------------------------

def _make_counts_dirs(tmp_path, n_ply, n_png, n_rows):
    ply_dir = tmp_path / "sim"
    png_dir = tmp_path / "png"
    ply_dir.mkdir()
    png_dir.mkdir()
    for i in range(n_ply):
        (ply_dir / f"deformed_s0001_v{i:04d}.ply").write_bytes(b"x")
    for i in range(n_png):
        (png_dir / f"deformed_s0001_v{i:04d}.png").write_bytes(b"x")
    labels = tmp_path / "labels.csv"
    with open(labels, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["SampleID", "force_x", "force_y", "force_z"])
        for i in range(n_rows):
            writer.writerow([f"deformed_s0001_v{i:04d}", "0", "0", "0"])
    return str(ply_dir), str(png_dir), str(labels)


def test_reconcile_counts_pass(tmp_path):
    from dpost.replay import reconcile_sequence_counts

    ply_dir, png_dir, labels = _make_counts_dirs(tmp_path, 3, 3, 3)
    assert reconcile_sequence_counts(ply_dir, png_dir, labels) == (3, 3, 3)


def test_reconcile_counts_raises_on_dropped_label(tmp_path):
    from dpost.replay import reconcile_sequence_counts

    ply_dir, png_dir, labels = _make_counts_dirs(tmp_path, 3, 3, 2)
    with pytest.raises(ValueError, match=r"3 PLY.*3 PNG.*2 label"):
        reconcile_sequence_counts(ply_dir, png_dir, labels)


def test_reconcile_counts_raises_on_missing_png(tmp_path):
    from dpost.replay import reconcile_sequence_counts

    ply_dir, png_dir, labels = _make_counts_dirs(tmp_path, 3, 2, 3)
    with pytest.raises(ValueError):
        reconcile_sequence_counts(ply_dir, png_dir, labels)


# ---------------------------------------------------------------------------
# Config plumbing for the F3 opt-in flag
# ---------------------------------------------------------------------------

def test_config_require_full_coverage_plumbing(tmp_path):
    from dpost.config import load_recipe

    cfg = tmp_path / "recipe.yaml"
    cfg.write_text("serialize:\n  require_full_coverage: true\n")
    recipe = load_recipe(str(cfg))
    assert recipe.serialize.require_full_coverage is True
    assert load_recipe(None).serialize.require_full_coverage is False

    bad = tmp_path / "bad.yaml"
    bad.write_text("serialize:\n  no_such_knob: 1\n")
    with pytest.raises(ValueError, match="no_such_knob"):
        load_recipe(str(bad))
