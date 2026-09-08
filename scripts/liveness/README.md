# Liveness / anti-spoofing models — provenance & rebuild

The app uses **Silent-Face-Anti-Spoofing (MiniFASNet)** to detect presentation attacks
(printed photos, phone/tablet screens) from a single frame. The two small models are
converted from the official PyTorch weights to **ONNX** so they run on the `onnxruntime`
we already ship — no PyTorch in the runtime image, fully offline.

The converted models live in `backend/models/antispoof/` and are baked into the image:
- `2.7_80x80_MiniFASNetV2.onnx` (+ `.onnx.data`)
- `4_0_0_80x80_MiniFASNetV1SE.onnx` (+ `.onnx.data`)

## Source & license
- Upstream: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing — **Apache-2.0**.
- `MiniFASNet.py` here is the upstream architecture (unmodified), kept for reproducible conversion.
- The `.pth` weights are downloaded from the upstream repo during the rebuild below.

## How the ONNX was produced (reproducible)
1. Download the architecture + weights (on a machine with internet):
   ```
   base=https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master
   mkdir -p weights
   curl -sL $base/src/model_lib/MiniFASNet.py -o MiniFASNet.py
   curl -sL $base/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth     -o weights/2.7_80x80_MiniFASNetV2.pth
   curl -sL $base/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth -o weights/4_0_0_80x80_MiniFASNetV1SE.pth
   ```
2. Convert in a throwaway container (installs CPU torch just to export, then discards it):
   ```
   docker run --rm -v "$PWD:/work" -v "<repo>/backend/models/antispoof:/out" python:3.12-slim bash -c \
     "pip install -q onnx onnxruntime onnxscript && \
      pip install -q torch --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple && \
      cd /work && python convert.py"
   ```

`convert.py` self-verifies: the weights must load strictly into the architecture, and the
ONNX output must match PyTorch within 1e-3 (observed ~1e-6). Runtime inference + the exact
CropImage/ToTensor preprocessing live in `backend/app/recognition/liveness.py`.
