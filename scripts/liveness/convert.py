"""Convert the official MiniFASNet .pth weights to ONNX, verifying numeric fidelity.

Runs inside a throwaway python:3.12 + torch container. Self-checks:
  1. state_dict loads strictly into the ported architecture (arch matches weights).
  2. torch output vs onnxruntime output match within 1e-3 (ONNX is faithful).
"""
import os

import numpy as np
import torch
import onnxruntime as ort

from MiniFASNet import MiniFASNetV2, MiniFASNetV1SE

MODELS = {
    "2.7_80x80_MiniFASNetV2.pth": MiniFASNetV2,
    "4_0_0_80x80_MiniFASNetV1SE.pth": MiniFASNetV1SE,
}
KERNEL = (5, 5)  # (80+15)//16 == 5, per utility.get_kernel
WEIGHTS_DIR = "/work/weights"
OUT_DIR = "/out"


def load(fname, ctor):
    model = ctor(conv6_kernel=KERNEL)
    state = torch.load(os.path.join(WEIGHTS_DIR, fname), map_location="cpu")
    keys = list(state.keys())
    if keys and keys[0].startswith("module."):
        state = {k[7:]: v for k, v in state.items()}
    model.load_state_dict(state)  # strict: raises on any mismatch
    model.eval()
    return model


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, ctor in MODELS.items():
        print(f"== {fname} ==")
        model = load(fname, ctor)
        dummy = torch.randn(1, 3, 80, 80)
        with torch.no_grad():
            out_torch = model(dummy).numpy()

        onnx_path = os.path.join(OUT_DIR, fname.replace(".pth", ".onnx"))
        torch.onnx.export(
            model, dummy, onnx_path,
            input_names=["input"], output_names=["logits"],
            opset_version=11,
        )

        sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        out_onnx = sess.run(None, {"input": dummy.numpy()})[0]
        diff = float(np.abs(out_torch - out_onnx).max())
        print(f"  exported {os.path.basename(onnx_path)}  |  max|torch-onnx| = {diff:.3e}")
        assert diff < 1e-3, f"ONNX mismatch for {fname}: {diff}"
    print("ALL OK")


if __name__ == "__main__":
    main()
