"""Tests for the reusable, training-independent domain-gap measurement."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from dknet.utils.domain_gap import coral_distance, domain_gap_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "measure_domain_gap.py"


def _load_measurement_script():
    spec = importlib.util.spec_from_file_location(
        "measure_domain_gap",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coral_distance_matches_hand_derived_normalization():
    source = torch.tensor([
        [0.0, 0.0],
        [2.0, 0.0],
        [0.0, 2.0],
    ])
    target = source / 2.0

    assert coral_distance(source, target) == pytest.approx(0.15625)


def test_coral_distance_is_zero_for_identical_features():
    features = torch.tensor([
        [1.0, 2.0, 3.0],
        [2.0, 1.0, 4.0],
        [4.0, 3.0, 2.0],
    ])

    assert coral_distance(features, features.clone()) == pytest.approx(0.0)


def test_domain_gap_report_exposes_mean_shift_and_is_deterministic():
    generator = torch.Generator().manual_seed(7)
    source = torch.randn(128, 8, generator=generator)
    target = source + 5.0

    first = domain_gap_report(source, target, seed=11)
    second = domain_gap_report(source, target, seed=11)

    assert first == second
    assert first["coral_distance"] == pytest.approx(0.0, abs=1e-10)
    assert first["mean_l2"] == pytest.approx(5.0 * (8**0.5))
    assert first["n_source"] == 128
    assert first["n_target"] == 128
    assert first["feature_dim"] == 8


@pytest.mark.parametrize(
    ("source", "target", "message"),
    [
        (torch.randn(8), torch.randn(8, 2), "2-D"),
        (torch.randn(8, 2), torch.randn(8, 3), "feature dimension"),
        (torch.randn(1, 2), torch.randn(8, 2), "at least two"),
    ],
)
def test_domain_gap_report_rejects_invalid_feature_matrices(
    source,
    target,
    message,
):
    with pytest.raises(ValueError, match=message):
        domain_gap_report(source, target)


def test_extract_domain_features_filters_ids_and_uses_frozen_backbone(tmp_path):
    module = _load_measurement_script()
    samples = [
        {
            "id": f"synt_seq01_v{index:04d}",
            "image": torch.full((3, 4, 4), float(index + 1)),
        }
        for index in range(2)
    ]
    samples.extend([
        {
            "id": f"real_seq01_v{index:04d}",
            "image": torch.full((3, 4, 4), float(index + 3)),
        }
        for index in range(2)
    ])
    torch.save(samples, tmp_path / "preprocessed_batch_0000.pt")

    class MeanBackbone(torch.nn.Module):
        def forward(self, images):
            return images.mean(dim=(2, 3))

    features = module.extract_domain_features(
        tmp_path,
        MeanBackbone().eval(),
        device="cpu",
        id_prefix="synt_",
        batch_size=1,
    )

    assert features.shape == (2, 3)
    assert features.device.type == "cpu"


@pytest.mark.parametrize(
    ("data_dir", "synth_dir", "real_dir"),
    [
        ("merged", "unexpected", None),
        ("merged", None, "unexpected"),
        (None, "synthetic", None),
        (None, None, "real"),
    ],
)
def test_resolve_sources_rejects_mixed_or_incomplete_modes(
    data_dir,
    synth_dir,
    real_dir,
):
    module = _load_measurement_script()
    args = SimpleNamespace(
        data_dir=data_dir,
        synth_dir=synth_dir,
        real_dir=real_dir,
        synth_prefix="synt_",
        real_prefix="real_",
    )

    with pytest.raises(ValueError):
        module._resolve_sources(args)


def test_source_label_records_single_directory_prefix():
    module = _load_measurement_script()

    assert module._source_label(("merged", "custom_synth_")) == (
        "merged[prefix=custom_synth_]"
    )
    assert module._source_label(("synthetic", None)) == "synthetic"


def test_measurement_cli_self_test_runs_without_weights_or_dataset():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--self-test"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "SELF_TEST_OK" in completed.stdout
