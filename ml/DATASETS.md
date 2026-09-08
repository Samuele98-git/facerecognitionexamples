# Datasets — what they're for (and what they're NOT for)

**Key point:** you do **not** train a face model for this project. The recognition model
(`buffalo_l` = ResNet100 ArcFace) is already trained on **Glint360K** — ~17M images of
~360K identities. No GPU you rent + free datasets you download will beat that; the public
training sets are *smaller* than what the model already learned from. So these datasets are
for two things only:

1. **Evaluation / threshold calibration** — measure real accuracy and pick your threshold.
2. **(Optional, later) fine-tuning on YOUR OWN camera footage** — domain adaptation. That
   needs *your* labeled data, not the generic sets below.

For **enrollment** you use your employees' own photos (via the dashboard), not any of these.

---

## 1. Evaluation / benchmark datasets (use these now)

Run them through `benchmark.py` to get accuracy + FAR/FRR and calibrate `RECOGNITION_THRESHOLD`.

| Dataset | What it stresses | Notes |
|---|---|---|
| **LFW** (Labeled Faces in the Wild) | General verification | The classic. `benchmark.py` supports its `pairs.txt` directly. ~13K images. Free. |
| **CFP-FP** (Celebrities Frontal-Profile) | **Extreme pose / different angles** | Most relevant to your "works at different angles" requirement. |
| **AgeDB-30** | Age variation | Same person across ages. |
| **CALFW / CPLFW** | Cross-age / cross-pose LFW | Harder LFW variants. |
| **IJB-B / IJB-C** | Surveillance-like, unconstrained | Closest to real CCTV conditions; request access from NIST. |

Download pointers:
- LFW: https://vis-www.cs.umass.edu/lfw/  (images: `lfw.tgz`, pairs: `pairs.txt`)
- CFP: http://cfpw.io/
- AgeDB / CALFW / CPLFW / verification packs are mirrored by the InsightFace project:
  https://github.com/deepinsight/insightface/tree/master/recognition/_datasets_

Put them under `ml/datasets/` (git-ignored), e.g. `ml/datasets/lfw/<Person_Name>/<Person_Name>_0001.jpg`.

## 2. Large training sets (context only — you won't retrain)

Listed so you understand what the model already knows and why retraining is unnecessary:
- **Glint360K** (~17M/360K) — what `buffalo_l` was trained on.
- **WebFace42M** — even larger academic set.
- **VGGFace2** (~3.3M/9K), **CASIA-WebFace** (~0.5M/10K) — older/smaller.
- **MS-Celeb-1M** — withdrawn by Microsoft; avoid.

## 3. If you later fine-tune (optional, needs a GPU like Vast.ai)

Only worth it once the pilot runs and you've collected labeled frames **from your own
cameras** (same lighting, angles, distances). That's a partial-fine-tune / margin-based
retrain of the recognition head on your domain — an optimization, not a prerequisite. When
you get there, that's when we set up the SSH key + remote GPU. Until then, skip it.
