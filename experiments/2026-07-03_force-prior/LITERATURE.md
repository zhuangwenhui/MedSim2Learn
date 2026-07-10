# Force-prior literature & dataset survey (existence-only, 2026-07-03)

**Scope:** what a *physically reasonable* surgical grasper/forceps-on-soft-tissue force sequence
looks like (magnitudes, N; 3D vs scalar; contact on/off; retraction/traction dynamics), for
validating a synthetic FEM force generator (Track A: force-prior). Porcine kidney /
laparoscopic forceps is our target setup.

**Discipline note:** every row below was fetched and read unless explicitly marked
"UNVERIFIED". Numbers I could not confirm from the source text (e.g. paywalled full text) are
flagged. This survey is existence-only; nothing is padded to look thorough.

---

## 1. Verified surgical tool-tissue force magnitudes/dynamics

Distinguish two families: **(A) instrument-tip interaction forces during actual manipulation**
(closest to what we want to model) and **(B) tissue-damage/safety thresholds** (upper bounds,
useful for an acceptance gate ceiling). Both are given below.

| Source | Organ / setup | Force range & units | Temporal notes |
|---|---|---|---|
| **Otsuka et al., *Scientific Reports* 2024** — "Vision-based estimation of manipulation forces … porcine excised kidney" ([nature](https://www.nature.com/articles/s41598-024-60574-w), [PMC11055910](https://pmc.ncbi.nlm.nih.gov/articles/PMC11055910/)) | **Ex-vivo porcine kidney**, custom sensorized forceps (tip 3-axis sensor **USLG10-5N, Tec Gihan**, ±5 N rated, 100 Hz). Our exact tissue+tool class. | **3D (Fx,Fy,Fz)**, sensor range **±5 N**. "Over-force" (dangerous) **threshold set at 0.5 N** by surgeon consensus. Two regimes tested: Level 1 "normal laparoscopic" force vs Level 2 "strong/dangerous" force. Paper does **not** publish min/max/typical magnitudes per frame. | 100 Hz force stream synced to endoscopic video. 3 videos, 7,148 frames, 8 sequences/organ across 3 pigs. Dataset **on request only** (not public). |
| **da Vinci force-feedback evaluation, *J. Endourol.-adjacent* 2024** ([PMC11458697](https://pmc.ncbi.nlm.nih.gov/articles/PMC11458697/)) | **Ex-vivo porcine** abdominal wall / small bowel + plant-based dissection model; **da Vinci** with tip force sensors (X,Y,Z), 28 surgeons. Direct per-task envelope. | **Retraction:** mean **3.25 ± 1.77 N**, peak **10.57 ± 5.96 N** (feedback OFF). **Dissection:** mean **1.68 ± 0.75 N**, peak **6.60 ± 3.21 N**. **Suturing:** mean **1.53 ± 0.55 N**, peak **9.16 ± 3.90 N**. Force feedback cut peaks 36–55 %. | **Forces < 0.5 N excluded** as "typical endoscopic minimum" — i.e. a de-facto contact-on floor. Per-task mean-vs-peak spread is the most directly reusable dynamic range we found. |
| **Shah, Alderson et al., *Surg. Innov.* 2018** — "In Vivo Measurement of Surface Pressures … Abdominal Organs" ([PubMed 29241404](https://pubmed.ncbi.nlm.nih.gov/29241404/), [Sage](https://journals.sagepub.com/doi/10.1177/1553350617745952), [SHURA PDF](https://shura.shu.ac.uk/17729/)) | **In vivo human**, open + hand-assisted lap; thin-film pressure sensor; **9 kidney retractions** among 12 patients. | Surface **pressure** (not tip force): max **1–41 kPa** across organs; **avg max 14 ± 3 kPa**. Kidney included but combined into the aggregate. Pressure, not N — needs contact-area assumption to convert. | Measured during active retraction movements. (Full-text PDF returned as binary; numbers taken from the PubMed/Sage abstract, which I read directly.) |
| **Establishing intraoperative force boundaries, 2021/22** ([PMC8749288](https://pmc.ncbi.nlm.nih.gov/articles/PMC8749288/), [medRxiv](https://www.medrxiv.org/content/10.1101/2021.02.19.21252109.full.pdf)) | **Ex-vivo human** small bowel + colon, simulated grasper compression (contact area 19.6 mm²). Damage-threshold study. | Applied 0–**11.8 N** (0–600 kPa). Serosal damage threshold **~329–330 kPa** (≈ 6.4 N over 19.6 mm²); trauma progressive >300 kPa, total at 600 kPa; no trauma at 100 kPa. | Each grasp **10 s** hold. Damage correlated with a **force-time product** (grasp force × duration) — supports treating our sequences as time-integrated, not just peak. |
| **In vivo colorectal grasping thresholds** ([PMC6132882](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6132882/)) | **In vivo porcine colon**, grasper. Damage-threshold study. | Applied **10, 20, 40, 50, 70 N**; significant muscle-layer damage at **≥50 N** (all durations). Below tip-manipulation range — this is the destructive ceiling. | Durations **5, 30, 60 s**; damage rises with force×time, echoing the force-time-product finding above. |
| **"Science of Surgical Force in Urology" systematic review, *J. Endourol.* 2026** ([Sage/Liebert doi](https://doi.org/10.1177/08927790251394738), [RG](https://www.researchgate.net/publication/398061654)) | Systematic review 1974–2024: 36 urology force studies, 741 patients + 46 ex-vivo specimens. Per-organ force data incl. **kidney (n=5)**. | **Ureter safety threshold 6–8 N** (UAS insertion >8 N risks high-grade injury). Prostate needle insertion **2–9 N**. **Kidney (n=5 studies): specific N values are in the paywalled full text — UNVERIFIED, could not confirm the kidney magnitudes from the abstract.** | Review-level; best single pointer to *kidney-specific* primary studies once full text is obtained. |

**General consensus (multiple sources above + search snippets):** atraumatic grasping/manipulation
of abdominal soft tissue is typically a **few Newtons (< ~5 N)**; **retraction peaks reach ~10 N**;
**tissue damage** for bowel begins in the **tens of kPa→N** range and scales with force×time.

---

## 2. Public recorded-force datasets

The critical question: *is there recorded surgical force-sequence data we can use as a reference
distribution?* Findings below. **Bottom line: no public, downloadable, real-intraoperative
tool-tissue force dataset was found.** The force-labeled datasets that exist are **lab/phantom**
setups, and none has a **confirmed public download link** — all are "self-collected", "code only",
or "available on request".

| Name | Exists? Downloadable? | Modality / units | Paired video? | URL |
|---|---|---|---|---|
| **DaFoEs** (Reyzabal, Chen, Huang, Ourselin, Liu; *IEEE RA-L* 9(3):2527-2534, 2024) | Exists (verified). **Dataset download NOT confirmed** — only training **code** is public on GitHub; no Zenodo/figshare/DOI for the raw data found; paper gives no data-availability statement beyond the code. | **3D forces (Fx,Fy,Fz), N**, ground truth from **Sunrise Instruments M3815A1 6-axis F/T sensor**. Silicone phantoms (Ecoflex 00-30, DragonSkin20), laparoscopic forceps on robot arm. | **Yes** — RGB @30 Hz (Intel RealSense D405) + robot state. 90 clips × ~30 s ≈ 70,000 frames. | [arXiv 2401.09239](https://arxiv.org/abs/2401.09239) · [IEEE 10410871](https://ieeexplore.ieee.org/document/10410871/) · code [github.com/mikelitu/DaFoEs](https://github.com/mikelitu/DaFoEs) |
| **Marban et al. 2019 / 2018 preprint** — RCNN sensorless force estimation | Exists (verified). **Public download NOT confirmed** (self-collected; no repo/DOI found). | Interaction force via **6-DOF ATI Gamma SI-32-2.5** F/T sensor; **artificial tissue**, da Vinci. | **Yes** — **44 video sequences, 4.31 h** of synced video+tool+force. | [arXiv 1805.08545](https://arxiv.org/abs/1805.08545) · Biomed. Signal Process. Control 50:134-150 |
| **Chua, Jarc, Okamura 2021** — force est. w/ vision+robot state | Exists (verified). **Public download NOT confirmed** ("self-collected"; DaFoEs reused it *by author sharing*, implying it is not openly hosted). | Ground truth from **6-axis Nano17** under silicone tissue; **dVRK** PSM; **46 demonstrations** retraction/palpation. | **Yes** — stereo 960×540 @30 Hz. | [arXiv 2011.02112](https://arxiv.org/abs/2011.02112) · [IEEE 9560945](https://ieeexplore.ieee.org/document/9560945/) |
| **SurgSync 2026** — time-synced multimodal dVRK dataset | Exists; **data + code public** (surgsync.github.io, CC BY-NC-SA 4.0). | **Contact = BINARY on/off only** (capacitive sensor), **NOT continuous force / not Newtons**. Ex-vivo chicken/beef/pork + phantoms, dVRK-Si. | Yes (video + kinematics + binary contact). | [arXiv 2603.06919](https://arxiv.org/html/2603.06919) |
| **JIGSAWS, ROSMA, UCL dVRK** (kinematic/video benchmarks) | Exist; public. | **NO force channel.** JIGSAWS = 76-D kinematics + video + gestures only; ROSMA = 154 kinematic vars + video; UCL = video on animal tissue. | Yes (but no force). | [JIGSAWS PMC5559351](https://pmc.ncbi.nlm.nih.gov/articles/PMC5559351/) |

**Explicit statement:** For **real intraoperative human/porcine tool-tissue force sequences,
publicly downloadable**, with or without paired video — **NONE FOUND.** The nearest available
recorded force+video data is all **phantom/silicone-on-bench** (DaFoEs, Chua, Marban), and even
those have **no confirmed open download** (code-only or on-request). The one openly published
"contact" dataset (SurgSync) records **binary contact, not force magnitude**.

---

## 3. Force-trajectory generation / plausibility-validation methods

Honest assessment: **no method was found that explicitly *generates synthetic surgical force
trajectories* and validates their *plausibility against a real force distribution*** — which is
exactly our Track-A gap. What exists is adjacent:

- **FEM / precomputed-FEM soft-tissue simulators** produce force–deformation responses from
  continuum mechanics, but are validated on **deformation accuracy (sub-mm)**, not on force-
  trajectory realism. Surveys: [Deformable Models for Surgical Simulation (arXiv 1909.03363)](https://arxiv.org/pdf/1909.03363);
  [Systematic review of real-time soft-tissue simulation (PMC7053477)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7053477/).
- **GNN / equivariant-GNN force+deformation prediction** (Kojanazarova et al., *Healthcare Tech.
  Lett.* 2025) trains on **FEM-synthetic + real silicone/bone phantom** data and reports sub-mm
  deformation + force error — again validated on accuracy vs held-out measurements, not on
  distributional plausibility. [arXiv 2509.10125](https://arxiv.org/html/2509.10125v1) · [Wiley](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/htl2.70042).
- **SurgeMOD 2024** — infers forces from image-space tissue motion (a *validation-by-motion*
  idea) but is estimation, not trajectory generation. [arXiv 2406.17707](https://arxiv.org/html/2406.17707v1).

**Takeaway for us:** the standard "plausibility check" in this literature is *held-out
measurement error against a real F/T sensor*, not *does this trajectory look like a real force
distribution*. Our force-envelope acceptance gate (magnitude range + contact on/off + rate-of-
change bounds) appears to be a **novel-enough contribution** — but that also means there is **no
off-the-shelf validated generator to borrow.**

---

## 4. Vision->force baselines (brief refresh — confirmed)

- **DaFoEs, RA-L 2024** — confirmed (RA-L 9(3), *not* an ICRA paper). Best models report
  estimation error **< 0.2 N**. Phantom, 3D force. (§2 for details.)
- **Marban et al. 2019**, *Biomed. Signal Process. Control* 50:134-150 — RCNN (CNN+LSTM) sensorless
  force from tissue-deformation video; confirmed exists. [arXiv 1805.08545](https://arxiv.org/abs/1805.08545).
- **Otsuka et al., *Sci. Reports* 2024 (porcine excised kidney, VGG-16)** — confirmed; our closest
  analogue. 3-axis ±5 N tip sensor, 0.5 N over-force threshold, VGG-16 magnitude estimation.
  [nature s41598-024-60574-w](https://www.nature.com/articles/s41598-024-60574-w).
- **Chua, Jarc, Okamura, ICRA 2021** — vision+robot-state force estimation, dVRK, Nano17 ground
  truth. [arXiv 2011.02112](https://arxiv.org/abs/2011.02112).

(All four re-confirmed against source; no correction needed to the project's existing knowledge
except the DaFoEs venue = RA-L 2024, presented at ICRA 2024.)

---

## 5. Gaps / NOT FOUND (stated plainly)

1. **No public downloadable real intraoperative (human or in-vivo porcine) tool-tissue force
   sequence dataset** — with or without video. Does not appear to exist.
2. **No confirmed open download for even the phantom force+video datasets** (DaFoEs, Marban, Chua).
   Code only, or "on request". Treat as *not obtainable without contacting authors*.
3. **No published per-frame force-magnitude distribution for kidney manipulation.** The porcine-
   kidney paper closest to us (Otsuka 2024) reports a sensor range (±5 N) and a 0.5 N over-force
   flag but not the empirical magnitude/temporal distribution; its data is on-request only.
4. **Kidney-specific N thresholds** in the 2026 urology systematic review are in paywalled full
   text — UNVERIFIED. Only ureter (6–8 N) and prostate (2–9 N) numbers were confirmable.
5. **No FEM/data-driven method that generates synthetic surgical force trajectories and validates
   their statistical plausibility against real force data.** The field validates estimation error,
   not trajectory realism.
6. **Rate-of-change / contact-transition dynamics** are essentially unquantified in the public
   literature: sources give means and peaks, and one 0.5 N contact floor, but no published dF/dt
   bounds or contact on/off timing statistics.

---

## 6. Implications for our force-envelope acceptance gate

We **can** borrow a defensible numeric envelope from verified ex-vivo/in-vivo measurements even
though no reference *sequence* dataset exists. Concretely: treat a **contact-on floor of ~0.5 N**
(the endoscopic minimum used independently by both the porcine-kidney study and the da Vinci
force-feedback study), an **atraumatic manipulation band of ~1–4 N mean** with **transient peaks
up to ~10 N for retraction** (da Vinci porcine per-task numbers; consistent with the "few N"
consensus), and a **hard upper ceiling** anchored to tissue-damage onset (bowel serosal damage
≈ 330 kPa ≈ single-digit N over a grasper footprint; muscle damage in vivo ≥ 50 N — well above
any plausible grasp). Because damage scales with a **force-time product**, the gate should bound
*sustained* force, not just instantaneous peaks. What we **cannot** borrow is a real per-frame
distribution or dF/dt / contact-timing prior for kidney — those must be set from our own FEM
model plus the Otsuka porcine-kidney sensor characteristics (±5 N, 0.5 N flag), and clearly
labeled as engineering assumptions, not literature-validated priors.
