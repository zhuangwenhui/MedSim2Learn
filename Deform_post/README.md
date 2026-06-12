# Deform_post

Turns DeformSim FEM output into vision-force training data that mirrors the
real recordings. One CLI front door (`main.py`), one functional package
(`dpost/`), one on-disk recipe (`configs/kidney_twin.yaml`).

The pipeline per sequence:

```
real force CSV ---forcegen/prep--> forces_model.csv (rotated, model frame)
                                   labels.csv       (raw sensor N, supervision)
mesh + annotation ----camera-----> camera.json      (one fixed view/sequence)
forces_model.csv --simulate------> deformed PLYs    (DeformSim exact replay)
PLYs + camera.json --render------> one PNG per frame (stationary laparoscope)
PNGs + labels.csv --serialize----> preprocessed_batch_*.pt (+ metadata.yaml)
per-seq datasets ---assemble-----> merged KiDKNet data_dir + by-sequence splits
completed seq dir --artifacts----> maxu.csv, waveform, twin_sync.mp4, montages
```

Real force and video recordings are 30 fps time series; the simulation is
**quasi-static** linear FEM (each frame solved independently, no inertia), so
the time axis lives in the bookkeeping: forces are continuous per-frame
trajectories, frame index maps to time via `fps`, and every dataset keeps
whole sequences contiguous (splits are by sequence, never by frame).

## Layout

- `main.py` -- the only entry point; `python main.py --help`
- `configs/kidney_twin.yaml` -- the production recipe (paths via
  `{workspace}`/`{dataflow}` placeholders, material, camera, sim threading,
  serialization, batching); CLI flags override individual values
- `dpost/replay.py` -- prep (sensor->model rotation, labels, camera, meta)
  and the per-sequence end-to-end orchestration
- `dpost/forces/` -- real recording IO + the real-referenced trajectory
  generator (`forcegen`)
- `dpost/camera/` -- camera math, auto placement, contact-frame view
  profiles, interactive picker
- `dpost/render.py` -- offscreen fixed-camera sequence renderer
- `dpost/simrun/` -- DeformSim subprocess wrapper + batch driver
- `dpost/dataset/` -- .pt serialization and multi-sequence assembly/splits
- `dpost/annotate.py` -- freeze band + accessible-zone Poisson-disk contacts
- `dpost/artifacts.py` -- per-sequence QA outputs
- `tests/` -- pytest wrappers around the per-module self-tests

## Common commands

```powershell
$py = 'C:/Users/space/anaconda3/envs/MedLearning/python.exe'

# one real sequence end to end (prep -> sim -> render -> serialize -> artifacts)
& $py main.py run --seq 01

# all 32 real sequences, two at a time
& $py main.py batch --seqs 01..32 --max-parallel 2

# synthesize 5 force-trajectory variants anchored to real sequence 07
& $py main.py forcegen --source 07 --out-dir DataFlow-path\synth --count 5

# pick a camera angle once, reuse it for every sequence
& $py main.py camera pick --name myview      # opens a window, close to save
# then in the recipe: camera: { mode: profile, profile: myview }

# merge per-sequence datasets for KiDKNet
& $py main.py assemble -- --twin-root <twin_full> --out-dir <merged> ...

# everything self-checkable without assets
& $py main.py selftest
```

## Cameras

Each sequence renders with ONE fixed camera (a stationary laparoscope); the
deformation appears as the surface moving, never the view. Three sources,
selected by `camera.mode` in the recipe:

- `auto` (default): deterministic placement around the sequence's contact
  point from the recipe constants (side-grazing close-up, 70 mm standoff)
- `profile`: a viewpoint you picked once in the interactive window
  (`camera pick`), stored relative to the contact's local frame so the same
  angle follows every sequence's own contact site
- `absolute`: a saved Open3D `PinholeCameraParameters` JSON applied verbatim
  (the view does NOT follow the contact)

The picker starts from the auto camera, so picking is fine-tuning, not
hunting. Saved cameras live under `DataFlow/Deform_post/cameras/`.

## Force sources

- Exact replay: `prep` rotates a real recording into the model frame per
  contact (the rotation is derived from the mesh + contact seed and preserves
  magnitude); `labels.csv` always keeps the RAW sensor Newtons.
- Real-referenced synthesis: `forcegen` builds new trajectories as
  scale/time-warp/small-rotation transforms of a real recording, each variant
  auto-validated (inverse-reconstruction RMS, peak and step envelopes) with
  provenance in a `.gen.json`. Synthetic CSVs flow through the identical
  pipeline; combined with the ~30 annotated contact sites this scales the
  training set combinatorially while staying inside the real force envelope.
- The legacy uniform-box sampler still exists inside DeformSim (sampling
  mode) for ablations, but is no longer the data recipe.

## Conventions

- Units: mm / MPa / N (inherited from DeformSim); kidney decision E=0.03 MPa,
  v=0.49; recordings at 30 fps.
- `SampleID = deformed_s<contactSeed>_v<frameIndex>` is the universal stem:
  PLY name == PNG name == labels row == .pt sample id.
- `.pt` sample: `{"id": str, "image": float32 (3,H,W) in [0,1], "force":
  float32 (3,) raw sensor N}`; `metadata.yaml` records every normalization
  decision. Consumers must pair data with its metadata.
- Sub-batch parallelism is per sequence (separate processes); rendering
  within a sequence is intentionally sequential (one Open3D offscreen window).

## Verification

`python main.py selftest` runs every module's self-test without needing
assets. The 2026-06 migration from the legacy scripts (sim2vfp.py,
kidney_replay.py, run_replay*.ps1, ...) was gated on a byte-level parity run
against the existing `twin_full/seq01` products: prep CSVs/camera identical,
new sim wrapper identical to the old PowerShell path under the same exe,
1716/1716 rendered PNGs identical, serialized tensors equal element-wise.
