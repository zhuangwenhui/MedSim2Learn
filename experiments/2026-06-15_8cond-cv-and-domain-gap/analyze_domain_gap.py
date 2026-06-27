#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quantify the synt<->real VISUAL domain gap from cached ConvNeXt features.

Uses the mixed feature cache (real_ and synt_ prefixed ids in one file). Reports:
  - centroid L2 distance between the real and synt feature clouds;
  - separation ratio = centroid distance / mean within-domain spread (>1 => clouds
    are far apart relative to their own size);
  - a LINEAR domain classifier (logistic regression) accuracy with a
    SEQUENCE-held-out test split -- ~1.0 means real vs synt frames are trivially
    separable in frozen-ConvNeXt feature space, i.e. a large visual covariate
    shift (the mechanism behind the ~6x zero-shot synt->real regression failure).

Read-only; CPU; reuses existing caches. No GPU, no training.
"""
import json
import os
import sys

import numpy as np
import torch

CACHE = (sys.argv[1] if len(sys.argv) > 1 else
         "/workspace/project/MedSim2Learn/DataFlow/Deform_post/feature_cache/mixed_feat_convnextL")

feats = torch.load(os.path.join(CACHE, "features.pt"), map_location="cpu").float().numpy()
ids = json.load(open(os.path.join(CACHE, "ids.json")))
assert len(ids) == len(feats), "ids/features length mismatch"

dom = np.array(["real" if str(i).startswith("real_") else "synt" for i in ids])  # synt renders are prefixed "deformed_"
seq = np.array(["_".join(str(i).split("_")[:2]) for i in ids])  # "real_seqXX"
r, s = dom == "real", dom == "synt"
print("frames: real=%d synt=%d  dim=%d" % (r.sum(), s.sum(), feats.shape[1]))
assert r.sum() and s.sum(), "need both real and synt frames in this cache"

mu_r, mu_s = feats[r].mean(0), feats[s].mean(0)
cdist = float(np.linalg.norm(mu_r - mu_s))
rms_r = float(np.sqrt(((feats[r] - mu_r) ** 2).sum(1).mean()))
rms_s = float(np.sqrt(((feats[s] - mu_s) ** 2).sum(1).mean()))
print("centroid L2 distance real<->synt : %.3f" % cdist)
print("within-domain RMS spread         : real %.3f | synt %.3f" % (rms_r, rms_s))
print("SEPARATION RATIO (cdist / spread): %.3f   (>1 => clouds far vs their own size)"
      % (cdist / (0.5 * (rms_r + rms_s))))

# --- linear domain separability: random 80/20 frame split (characterizes the
#     shift; real/synt are 50/50 so chance = majority = 0.5) ---
rng = np.random.RandomState(0)
te_mask = rng.rand(len(ids)) < 0.2
tr_mask = ~te_mask
y = (dom == "synt").astype(np.float32)
mu = feats[tr_mask].mean(0)
sd = feats[tr_mask].std(0) + 1e-6
Xt = torch.tensor((feats - mu) / sd, dtype=torch.float32)
yt = torch.tensor(y, dtype=torch.float32)
tr = torch.tensor(tr_mask)
te = torch.tensor(te_mask)
w = torch.zeros(feats.shape[1], requires_grad=True)
b = torch.zeros(1, requires_grad=True)
opt = torch.optim.Adam([w, b], lr=0.05)
for _ in range(300):
    opt.zero_grad()
    loss = torch.nn.functional.binary_cross_entropy_with_logits(Xt[tr] @ w + b, yt[tr])
    loss.backward()
    opt.step()
with torch.no_grad():
    acc = ((Xt[te] @ w + b > 0).float() == yt[te]).float().mean().item()
base = max(y[te_mask].mean(), 1 - y[te_mask].mean())
print("linear domain-classifier test acc: %.4f  (majority baseline %.3f; chance 0.5)" % (acc, base))
print("=> ~1.0 means real vs synt are trivially separable in ConvNeXt feature space")
print("   i.e. a LARGE visual domain gap -- the mechanism behind zero-shot synt->real failure.")

# --- visualization: PCA-2D scatter + within-domain diversity bar ---
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

rng2 = np.random.RandomState(1)


def _sub(mask, n=4000):
    idx = np.where(mask)[0]
    return rng2.choice(idx, min(n, len(idx)), replace=False)


ri, si = _sub(r), _sub(s)
nr = len(ri)
Xsub = feats[np.concatenate([ri, si])]
Xc = Xsub - Xsub.mean(0)                       # mean-center raw features (keep spread)
_, _, Vt = np.linalg.svd(Xc, full_matrices=False)
pc = Xc @ Vt[:2].T
sep_ratio = cdist / (0.5 * (rms_r + rms_s))

fig, ax = plt.subplots(1, 2, figsize=(12, 5))
ax[0].scatter(pc[:nr, 0], pc[:nr, 1], s=5, alpha=0.35, c="#378ADD", edgecolors="none", label="real (n=%d)" % nr)
ax[0].scatter(pc[nr:, 0], pc[nr:, 1], s=5, alpha=0.35, c="#C44E52", edgecolors="none", label="synth (n=%d)" % len(si))
ax[0].set_xlabel("PC1"); ax[0].set_ylabel("PC2")
ax[0].set_title("Frozen ConvNeXt features (PCA-2D)"); ax[0].legend(markerscale=3, fontsize=9)
ax[1].bar(["real", "synth"], [rms_r, rms_s], color=["#378ADD", "#C44E52"], edgecolor="black", linewidth=0.5)
ax[1].set_ylabel("within-domain feature spread (RMS)")
ax[1].set_title("synth ~%.1fx less diverse than real" % (rms_r / rms_s))
fig.suptitle("synt<->real domain gap | linear-probe separability %.0f%% (chance 50%%) | separation ratio %.1f"
             % (acc * 100, sep_ratio), fontsize=12)
figdir = os.path.dirname(CACHE.rstrip("/"))
figpath = os.path.join(figdir, "domain_gap.png")
fig.savefig(figpath, dpi=130, bbox_inches="tight")
print("[fig] wrote %s" % figpath)

with open(os.path.join(figdir, "domain_gap_points.json"), "w") as fh:
    json.dump({"real": pc[:nr][:1500].round(3).tolist(),
               "synth": pc[nr:][:1500].round(3).tolist(),
               "metrics": {"sep_acc": round(acc, 4), "sep_ratio": round(sep_ratio, 2),
                           "rms_real": round(rms_r, 2), "rms_synth": round(rms_s, 2),
                           "cdist": round(cdist, 2)}}, fh)
print("[fig] wrote %s/domain_gap_points.json" % figdir)
