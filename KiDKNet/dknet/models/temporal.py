"""Temporal modules for sequence force regression in KiDKNet.

These modules consume a per-frame feature sequence ``(B, T, F)`` produced by a
shared frame encoder (e.g. ConvNeXt) and predict a per-frame force vector,
returning a LIST of ``(B, T, out_dim)`` stage outputs. The list carries the
multi-stage refinement of MS-TCN for deep supervision; single-stage heads
(GRU/LSTM/Transformer) return a one-element list so the trainer and loss treat
every temporal module uniformly.

The SOTA shortlist for "ConvNeXt frame encoder + temporal head, seq-to-seq
per-frame force, few clips" (see SERVER_DEPLOY / experiment notes):
  - ``tcn``         : MS-TCN / TeCNO-style causal dilated 1D conv, multi-stage
                      refinement, deep supervision. Recommended default.
  - ``gru``/``lstm``: recurrent baseline (bidirectional for offline use).
  - ``transformer`` : encoder over frame tokens with sinusoidal positional
                      encoding and optional causal masking (ASFormer-style intent).

All modules fold the final per-frame projection to ``out_dim`` (default 3) into
themselves, so no separate regression head is needed for the sequence path.
"""

import math
from typing import Any, Dict, List

import torch
import torch.nn as nn
import torch.nn.functional as F


# =========================================================================
# TCN (MS-TCN / TeCNO-style)
# =========================================================================
class _DilatedResidualLayer(nn.Module):
    """One dilated residual layer (MS-TCN). Causal or symmetric padding.

    Causal padding pads only the left by ``(k-1)*dilation`` so the output at
    frame ``t`` never sees ``t+1`` (online/real-time capable). Symmetric padding
    pads both sides by ``dilation`` (offline/bidirectional context).
    """

    def __init__(self, channels: int, dilation: int, kernel_size: int = 3,
                 dropout: float = 0.0, causal: bool = True) -> None:
        super().__init__()
        self.causal = causal
        self.dilation = dilation
        self.kernel_size = kernel_size
        # Symmetric padding handled by Conv1d directly; causal padding is applied
        # manually in forward (left-only) so we keep padding=0 here when causal.
        pad = 0 if causal else dilation * (kernel_size - 1) // 2
        self.conv_dilated = nn.Conv1d(
            channels, channels, kernel_size, padding=pad, dilation=dilation
        )
        self.conv_1x1 = nn.Conv1d(channels, channels, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """``x``: ``(B, C, T)`` -> ``(B, C, T)``."""
        if self.causal:
            left = self.dilation * (self.kernel_size - 1)
            out = self.conv_dilated(F.pad(x, (left, 0)))
        else:
            out = self.conv_dilated(x)
        out = F.relu(out)
        out = self.conv_1x1(out)
        out = self.dropout(out)
        return x + out


class _SingleStageTCN(nn.Module):
    """One MS-TCN stage: 1x1 in-projection + N dilated residual layers + out."""

    def __init__(self, in_dim: int, num_layers: int, num_f_maps: int,
                 out_dim: int, dropout: float = 0.0, causal: bool = True) -> None:
        super().__init__()
        self.conv_in = nn.Conv1d(in_dim, num_f_maps, 1)
        self.layers = nn.ModuleList([
            _DilatedResidualLayer(
                num_f_maps, dilation=2 ** i, dropout=dropout, causal=causal
            )
            for i in range(num_layers)
        ])
        self.conv_out = nn.Conv1d(num_f_maps, out_dim, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """``x``: ``(B, in_dim, T)`` -> ``(B, out_dim, T)``."""
        out = self.conv_in(x)
        for layer in self.layers:
            out = layer(out)
        return self.conv_out(out)


class TCNHead(nn.Module):
    """Multi-stage temporal convolutional regressor (MS-TCN for regression).

    Stage 1 maps the frame features to per-frame force; each later stage refines
    the previous stage's prediction. ``forward`` returns the list of every
    stage's ``(B, T, out_dim)`` output for deep supervision.
    """

    def __init__(self, in_features: int, out_dim: int = 3, num_stages: int = 3,
                 num_layers: int = 10, num_f_maps: int = 64,
                 dropout: float = 0.1, causal: bool = True) -> None:
        super().__init__()
        self.causal = causal
        self.stage1 = _SingleStageTCN(
            in_features, num_layers, num_f_maps, out_dim, dropout, causal
        )
        self.stages = nn.ModuleList([
            _SingleStageTCN(out_dim, num_layers, num_f_maps, out_dim, dropout, causal)
            for _ in range(num_stages - 1)
        ])

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        """``x``: ``(B, T, F)`` -> list of ``(B, T, out_dim)`` per stage."""
        feat = x.transpose(1, 2)  # (B, F, T)
        out = self.stage1(feat)   # (B, out_dim, T)
        outputs = [out]
        for stage in self.stages:
            out = stage(out)
            outputs.append(out)
        return [o.transpose(1, 2).contiguous() for o in outputs]  # each (B, T, out_dim)


# =========================================================================
# Recurrent (GRU / LSTM)
# =========================================================================
class RecurrentHead(nn.Module):
    """BiLSTM/BiGRU per-frame regressor. Single-stage (returns a 1-elem list)."""

    def __init__(self, in_features: int, out_dim: int = 3, rnn_type: str = "gru",
                 hidden_size: int = 256, num_layers: int = 2,
                 bidirectional: bool = True, dropout: float = 0.1) -> None:
        super().__init__()
        rnn_type = rnn_type.lower()
        rnn_cls = {"gru": nn.GRU, "lstm": nn.LSTM}.get(rnn_type)
        if rnn_cls is None:
            raise ValueError(f"rnn_type must be 'gru' or 'lstm', got {rnn_type!r}")
        self.bidirectional = bidirectional
        self.rnn = rnn_cls(
            input_size=in_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=bidirectional,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        out_hidden = hidden_size * (2 if bidirectional else 1)
        self.proj = nn.Linear(out_hidden, out_dim)

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        """``x``: ``(B, T, F)`` -> ``[(B, T, out_dim)]``."""
        seq, _ = self.rnn(x)
        return [self.proj(seq)]


# =========================================================================
# Transformer encoder
# =========================================================================
class _SinusoidalPositionalEncoding(nn.Module):
    """Standard sinusoidal positional encoding added to ``(B, T, d_model)``."""

    def __init__(self, d_model: int, max_len: int = 8192) -> None:
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float32)
            * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


class TransformerHead(nn.Module):
    """Transformer-encoder per-frame regressor with optional causal masking."""

    def __init__(self, in_features: int, out_dim: int = 3, d_model: int = 256,
                 nhead: int = 8, num_layers: int = 4, dim_feedforward: int = 512,
                 dropout: float = 0.1, causal: bool = False) -> None:
        super().__init__()
        self.causal = causal
        self.input_proj = nn.Linear(in_features, d_model)
        self.pos_enc = _SinusoidalPositionalEncoding(d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.proj = nn.Linear(d_model, out_dim)

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        """``x``: ``(B, T, F)`` -> ``[(B, T, out_dim)]``."""
        h = self.pos_enc(self.input_proj(x))
        mask = None
        if self.causal:
            t = x.size(1)
            mask = torch.triu(
                torch.full((t, t), float("-inf"), device=x.device), diagonal=1
            )
        h = self.encoder(h, mask=mask)
        return [self.proj(h)]


# =========================================================================
# Factory
# =========================================================================
TEMPORAL_REGISTRY = {
    "tcn": TCNHead,
    "gru": RecurrentHead,
    "lstm": RecurrentHead,
    "transformer": TransformerHead,
}


def build_temporal(module_type: str, in_features: int,
                   config: Dict[str, Any]) -> nn.Module:
    """Build a temporal module by name.

    Args:
        module_type: One of ``tcn``, ``gru``, ``lstm``, ``transformer``.
        in_features: Per-frame feature dimensionality from the frame encoder.
        config: Module-specific keyword arguments (see each class).

    Returns:
        nn.Module whose ``forward((B, T, F))`` returns a list of
        ``(B, T, out_dim)`` stage outputs.
    """
    key = str(module_type).lower()
    cfg = dict(config or {})
    out_dim = cfg.pop("out_dim", 3)
    if key == "tcn":
        return TCNHead(in_features, out_dim=out_dim, **cfg)
    if key in ("gru", "lstm"):
        cfg.setdefault("rnn_type", key)
        return RecurrentHead(in_features, out_dim=out_dim, **cfg)
    if key == "transformer":
        return TransformerHead(in_features, out_dim=out_dim, **cfg)
    raise ValueError(
        f"Unknown temporal module '{module_type}'. "
        f"Available: {sorted(TEMPORAL_REGISTRY)}"
    )


def _self_test() -> bool:
    """Shape contract for every temporal module on random features (CPU)."""
    ok = True
    b, t, f = 2, 16, 1536
    x = torch.randn(b, t, f)
    cases = [
        ("tcn", {"num_stages": 3, "num_layers": 6, "num_f_maps": 32, "causal": True}),
        ("tcn", {"num_stages": 2, "num_layers": 5, "num_f_maps": 32, "causal": False}),
        ("gru", {"hidden_size": 64, "num_layers": 2, "bidirectional": True}),
        ("lstm", {"hidden_size": 64, "num_layers": 1, "bidirectional": False}),
        ("transformer", {"d_model": 64, "nhead": 4, "num_layers": 2, "causal": True}),
        ("transformer", {"d_model": 64, "nhead": 4, "num_layers": 2, "causal": False}),
    ]
    for name, cfg in cases:
        try:
            m = build_temporal(name, f, cfg)
            out = m(x)
            assert isinstance(out, list) and len(out) >= 1, f"{name}: list"
            for o in out:
                assert o.shape == (b, t, 3), f"{name}: stage shape {tuple(o.shape)}"
            n_stages = cfg.get("num_stages", 1)
            if name == "tcn":
                assert len(out) == n_stages, f"tcn stages {len(out)} != {n_stages}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"[temporal self-test] {name} {cfg} FAILED: {exc}")
    print(f"temporal self-test {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _self_test() else 1)
