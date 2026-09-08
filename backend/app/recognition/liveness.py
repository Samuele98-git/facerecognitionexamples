"""Passive face anti-spoofing (liveness) — Silent-Face MiniFASNet, ONNX / onnxruntime.

Two small models (scale 2.7 and 4.0, 80x80 crops) vote via summed softmax; class index 1
means "real". A face that matches an enrolled person but fails liveness is denied and flagged
as a possible spoof (printed photo / phone screen). Runs fully offline on baked-in ONNX
weights, converted 1:1 from the official PyTorch weights.

Preprocessing is ported exactly from the reference (generate_patches.CropImage +
torchvision ToTensor: HWC->CHW, /255, BGR kept, no normalization).
"""
import os
import threading

import cv2
import numpy as np

from .. import config, settings_store

_lock = threading.Lock()
_sessions = None  # list of dicts: {scale, w, h, sess, input_name}


# --- reference filename parsing (utility.parse_model_name, adapted for .onnx) ----
def _parse(model_name: str):
    info = model_name.split("_")[0:-1]          # drop the "MiniFASNet*.onnx" token
    h_input, w_input = info[-1].split("x")
    scale = None if info[0] == "org" else float(info[0])
    return int(h_input), int(w_input), scale


# --- reference CropImage (generate_patches.py), numpy/cv2 -------------------------
def _get_new_box(src_w, src_h, bbox, scale):
    x, y, box_w, box_h = bbox
    scale = min((src_h - 1) / box_h, min((src_w - 1) / box_w, scale))
    new_w, new_h = box_w * scale, box_h * scale
    cx, cy = box_w / 2 + x, box_h / 2 + y
    ltx, lty = cx - new_w / 2, cy - new_h / 2
    rbx, rby = cx + new_w / 2, cy + new_h / 2
    if ltx < 0:
        rbx -= ltx; ltx = 0
    if lty < 0:
        rby -= lty; lty = 0
    if rbx > src_w - 1:
        ltx -= (rbx - src_w + 1); rbx = src_w - 1
    if rby > src_h - 1:
        lty -= (rby - src_h + 1); rby = src_h - 1
    return int(ltx), int(lty), int(rbx), int(rby)


def _crop(org_img, bbox, scale, out_w, out_h):
    if scale is None:
        return cv2.resize(org_img, (out_w, out_h))
    src_h, src_w = org_img.shape[:2]
    ltx, lty, rbx, rby = _get_new_box(src_w, src_h, bbox, scale)
    patch = org_img[lty:rby + 1, ltx:rbx + 1]
    return cv2.resize(patch, (out_w, out_h))


def _softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


def _get_sessions():
    global _sessions
    if _sessions is None:
        with _lock:
            if _sessions is None:
                import onnxruntime as ort

                directory = config.ANTISPOOF_DIR
                sess_list = []
                for fname in sorted(os.listdir(directory)):
                    if not fname.endswith(".onnx"):
                        continue
                    h, w, scale = _parse(fname)
                    sess = ort.InferenceSession(
                        os.path.join(directory, fname), providers=["CPUExecutionProvider"]
                    )
                    sess_list.append(
                        {"scale": scale, "w": w, "h": h, "sess": sess, "input": sess.get_inputs()[0].name}
                    )
                if not sess_list:
                    raise RuntimeError(f"No anti-spoof ONNX models found in {directory}")
                _sessions = sess_list
    return _sessions


def predict(image_bgr, bbox_xywh):
    """Return the averaged 3-class probability [spoof2d, real, spoof3d-ish]."""
    total = np.zeros(3, dtype=np.float64)
    sessions = _get_sessions()
    for m in sessions:
        patch = _crop(image_bgr, bbox_xywh, m["scale"], m["w"], m["h"])
        inp = patch.astype(np.float32).transpose(2, 0, 1)[None] / 255.0  # 1x3xHxW, BGR, /255
        logits = m["sess"].run(None, {m["input"]: inp})[0][0]
        total += _softmax(logits)
    return total / len(sessions)


def is_live(image_bgr, face) -> bool:
    """True if the face looks like a real, present person.

    No-op (returns True) unless liveness is enabled. When enabled, a face is "live" only if
    the real class wins AND its averaged probability clears the threshold. On an unexpected
    error we fail OPEN (recognition still gates access) but log loudly.
    """
    if not settings_store.get_bool("liveness_enabled", config.LIVENESS_ENABLED):
        return True
    x1, y1, x2, y2 = face.bbox
    bbox = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
    try:
        prob = predict(image_bgr, bbox)
    except Exception as exc:
        print(f"[liveness] error, allowing through: {exc}")
        return True
    label = int(np.argmax(prob))
    threshold = settings_store.get_float("liveness_threshold", config.LIVENESS_THRESHOLD)
    return label == 1 and float(prob[1]) >= threshold
