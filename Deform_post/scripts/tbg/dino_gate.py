"""DINOv2 feature-distance gate for texture candidates (server-side).

Pre-registered quantitative companion to the human visual gate
(T-B manifest section 6): organ-INTERIOR crops only, so the metric
scores material/texture rather than background layout. For each
candidate directory under GATE_IN, reports mean cosine distance to the
curated real-tissue crops; the real->real internal spread and the
white-model distance anchor the scale.
"""
import glob
import json
import os

import numpy as np
import torch
from PIL import Image

GATE_IN = "/workspace/project/tools/kidney_assets/gate_in"
REAL_DIR = "/workspace/project/tools/kidney_assets/lora_train_v4"
DEV = "cuda"
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


@torch.no_grad()
def features(files, model):
    feats = []
    for i in range(0, len(files), 64):
        ims = []
        for p in files[i:i + 64]:
            im = Image.open(p).convert("RGB").resize((224, 224),
                                                     Image.LANCZOS)
            t = torch.from_numpy(np.asarray(im).copy()).permute(
                2, 0, 1).float() / 255.0
            ims.append((t - IMAGENET_MEAN) / IMAGENET_STD)
        feats.append(model(torch.stack(ims).to(DEV)).cpu())
    f = torch.cat(feats)
    return torch.nn.functional.normalize(f, dim=1)


def mean_cross_distance(a, b):
    return float(1.0 - (a @ b.T).mean())


def main():
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14")
    model.eval().to(DEV)
    rng = np.random.default_rng(20260815)
    real_files = sorted(glob.glob(f"{REAL_DIR}/*.png"))
    pick = rng.choice(len(real_files), 128, replace=False)
    real = features([real_files[j] for j in pick], model)
    half = len(real) // 2
    report = {"real_internal": mean_cross_distance(real[:half],
                                                   real[half:])}
    for cand in sorted(os.listdir(GATE_IN)):
        files = sorted(glob.glob(f"{GATE_IN}/{cand}/*.png"))
        if not files:
            continue
        report[cand] = mean_cross_distance(features(files, model), real)
    print("DINO-GATE " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
