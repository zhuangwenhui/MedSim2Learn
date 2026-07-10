"""GPU-free unit tests for the Track B UDA primitives (dknet/utils/uda.py).

These verify the math BEFORE any of it is wired into the training loop. They guard the
specific mistakes an unverified draft made: the /(4d) vs /(4d^2) CORAL normalisation, the
gradient-reversal autograd contract, and the covariance estimator.
"""

import importlib.util
import unittest
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load uda.py standalone (it depends only on torch), bypassing dknet.utils.__init__,
# which eagerly imports matplotlib-backed visualization and would otherwise couple this
# lightweight primitives test to an optional plotting dependency.
_UDA_PATH = PROJECT_ROOT / "dknet" / "utils" / "uda.py"
_spec = importlib.util.spec_from_file_location("dknet_uda_standalone", _UDA_PATH)
_uda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_uda)
coral_loss = _uda.coral_loss
coral_distance = _uda.coral_distance
domain_gap_report = _uda.domain_gap_report
grad_reverse = _uda.grad_reverse
GradientReversalFunction = _uda.GradientReversalFunction
DomainClassifier = _uda.DomainClassifier


class CoralLossTests(unittest.TestCase):
    def test_scalar_and_nonnegative(self):
        src, tgt = torch.randn(16, 32), torch.randn(12, 32)
        loss = coral_loss(src, tgt)
        self.assertEqual(loss.shape, torch.Size([]))
        self.assertGreaterEqual(loss.item(), 0.0)

    def test_zero_for_identical_distributions(self):
        feats = torch.randn(48, 32)
        self.assertLess(coral_loss(feats, feats.clone()).item(), 1e-6)

    def test_matches_correct_normalization_and_rejects_the_4d_bug(self):
        torch.manual_seed(0)
        src, tgt = torch.randn(64, 8), torch.randn(48, 8) + 0.3
        d = 8
        sc = src - src.mean(0, keepdim=True)
        tc = tgt - tgt.mean(0, keepdim=True)
        cov_s = sc.t() @ sc / (src.size(0) - 1)
        cov_t = tc.t() @ tc / (tgt.size(0) - 1)
        fro2 = (cov_s - cov_t).pow(2).sum()

        expected = fro2 / (4 * d * d)
        self.assertTrue(torch.allclose(coral_loss(src, tgt), expected, atol=1e-6))
        # regression guard: must NOT be the /(4d) normalisation the draft used
        wrong = fro2 / (4 * d)
        self.assertFalse(torch.allclose(coral_loss(src, tgt), wrong, atol=1e-6))

    def test_covariance_matches_torch_cov(self):
        torch.manual_seed(1)
        x = torch.randn(100, 5)
        xc = x - x.mean(0, keepdim=True)
        cov = xc.t() @ xc / (x.size(0) - 1)
        self.assertTrue(torch.allclose(cov, torch.cov(x.t()), atol=1e-5))

    def test_feature_dim_mismatch_raises(self):
        with self.assertRaises(ValueError):
            coral_loss(torch.randn(8, 16), torch.randn(8, 32))

    def test_gradients_flow_to_both_inputs(self):
        src = torch.randn(20, 6, requires_grad=True)
        tgt = torch.randn(20, 6, requires_grad=True)
        coral_loss(src, tgt).backward()
        self.assertIsNotNone(src.grad)
        self.assertIsNotNone(tgt.grad)


class CoralDistanceMetricTests(unittest.TestCase):
    """The fossilised gap-metric role: coral_distance + domain_gap_report."""

    def test_distance_equals_loss_value(self):
        torch.manual_seed(3)
        src, tgt = torch.randn(64, 16), torch.randn(48, 16) + 0.2
        self.assertAlmostEqual(coral_distance(src, tgt), coral_loss(src, tgt).item(), places=5)

    def test_distance_zero_for_identical(self):
        feats = torch.randn(40, 16)
        self.assertLess(coral_distance(feats, feats.clone()), 1e-6)

    def test_covariance_shift_raises_gap_ratio_above_floor(self):
        torch.manual_seed(4)
        # same distribution -> ratio ~ 1; scaled covariance -> ratio >> 1.
        s = torch.randn(4000, 32)
        t_same = torch.randn(4000, 32)
        t_cov = torch.randn(4000, 32) * 3.0
        rep_same = domain_gap_report(s, t_same, seed=0)
        rep_cov = domain_gap_report(s, t_cov, seed=0)
        self.assertGreater(rep_cov["coral_distance"], rep_same["coral_distance"])
        self.assertGreater(rep_cov["gap_ratio"], rep_same["gap_ratio"])
        self.assertGreater(rep_cov["gap_ratio"], 3.0)   # genuinely far apart
        self.assertLess(rep_same["gap_ratio"], 3.0)     # within sampling noise

    def test_coral_is_blind_to_pure_mean_shift(self):
        # Documents the second-order-only nature: a pure mean shift moves mean_l2 but
        # NOT the CORAL distance (same covariance). This is why domain_gap_report ships
        # mean_l2 alongside coral_distance.
        torch.manual_seed(5)
        s = torch.randn(4000, 32)
        t_mean = torch.randn(4000, 32) + 5.0     # shifted mean, same covariance
        rep_same = domain_gap_report(s, torch.randn(4000, 32), seed=0)
        rep_mean = domain_gap_report(s, t_mean, seed=0)
        self.assertGreater(rep_mean["mean_l2"], rep_same["mean_l2"])
        # CORAL distance barely moves (covariance unchanged) -> ratio stays near floor.
        self.assertLess(rep_mean["gap_ratio"], 3.0)

    def test_report_rejects_non_2d(self):
        with self.assertRaises(ValueError):
            domain_gap_report(torch.randn(8), torch.randn(8, 4))


class GradientReversalTests(unittest.TestCase):
    def test_forward_is_identity(self):
        x = torch.randn(8, 16, requires_grad=True)
        y = grad_reverse(x, 1.0)
        self.assertTrue(torch.allclose(x.detach(), y.detach()))

    def test_backward_reverses_and_scales_by_lambda(self):
        x = torch.randn(4, 3, requires_grad=True)
        lam = 2.0
        (grad,) = torch.autograd.grad(grad_reverse(x, lam).sum(), x)
        self.assertTrue(torch.allclose(grad, -lam * torch.ones_like(grad), atol=1e-6))

    def test_backward_returns_pair_with_none_for_lambda(self):
        class _Ctx:
            lambda_ = 1.0

        out = GradientReversalFunction.backward(_Ctx, torch.ones(2, 2))
        self.assertEqual(len(out), 2)
        self.assertIsNone(out[1])


class DomainClassifierTests(unittest.TestCase):
    def test_output_shape_is_per_sample_logit(self):
        clf = DomainClassifier(feature_dim=1536)
        out = clf(torch.randn(10, 1536))
        self.assertEqual(out.shape, torch.Size([10]))

    def test_has_trainable_parameters(self):
        clf = DomainClassifier(feature_dim=64)
        self.assertGreater(sum(p.numel() for p in clf.parameters()), 0)


if __name__ == "__main__":
    unittest.main()
