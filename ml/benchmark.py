"""Calibrate the recognition threshold and measure accuracy on a public benchmark.

This is the *right* use of free datasets: not to train (the model is already trained on
far more data than you could gather), but to MEASURE how well it separates same-person
from different-person pairs on your chosen model, and to pick the threshold that gives you
the security/convenience trade-off you want.

Currently supports the LFW (Labeled Faces in the Wild) protocol, which ships a standard
`pairs.txt`. CFP-FP (frontal-profile, great for your "different angles" requirement) uses
the same idea — see DATASETS.md.

Usage:
    python benchmark.py --lfw-dir ./datasets/lfw --pairs ./datasets/pairs.txt
    python benchmark.py --lfw-dir ./datasets/lfw --pairs ./datasets/pairs.txt --gpu

Run it inside the backend environment (it uses the same insightface model), e.g.:
    docker compose run --rm -v %cd%/ml:/ml backend python /ml/benchmark.py --lfw-dir /ml/datasets/lfw --pairs /ml/datasets/pairs.txt
"""
import argparse
import os

import cv2
import numpy as np


def load_engine(use_gpu: bool, model_name: str, det_size: int):
    from insightface.app import FaceAnalysis

    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
    )
    app = FaceAnalysis(name=model_name, providers=providers)
    app.prepare(ctx_id=0 if use_gpu else -1, det_size=(det_size, det_size))
    return app


def embed(app, path):
    """Return the normalized embedding of the largest face in an image, or None."""
    img = cv2.imread(path)
    if img is None:
        return None
    faces = app.get(img)
    if not faces:
        return None
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    return np.asarray(faces[0].normed_embedding, dtype=np.float32)


def lfw_image_path(lfw_dir, name, idx):
    return os.path.join(lfw_dir, name, f"{name}_{int(idx):04d}.jpg")


def parse_pairs(pairs_path, lfw_dir):
    """Parse the standard LFW pairs.txt into (pathA, pathB, same) tuples."""
    with open(pairs_path) as fh:
        lines = [ln.strip().split("\t") for ln in fh if ln.strip()]
    # First line is "<folds> <pairs_per_fold>"; skip if present.
    if len(lines[0]) == 2 and lines[0][0].isdigit():
        lines = lines[1:]
    pairs = []
    for parts in lines:
        if len(parts) == 3:  # same person: name idx1 idx2
            name, a, b = parts
            pairs.append((lfw_image_path(lfw_dir, name, a), lfw_image_path(lfw_dir, name, b), True))
        elif len(parts) == 4:  # different: name1 idx1 name2 idx2
            n1, a, n2, b = parts
            pairs.append((lfw_image_path(lfw_dir, n1, a), lfw_image_path(lfw_dir, n2, b), False))
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Calibrate face-recognition threshold on LFW.")
    ap.add_argument("--lfw-dir", required=True, help="folder of per-person subfolders")
    ap.add_argument("--pairs", required=True, help="path to pairs.txt")
    ap.add_argument("--model", default="buffalo_l")
    ap.add_argument("--det-size", type=int, default=640)
    ap.add_argument("--gpu", action="store_true")
    args = ap.parse_args()

    print(f"Loading model '{args.model}' ...")
    app = load_engine(args.gpu, args.model, args.det_size)

    pairs = parse_pairs(args.pairs, args.lfw_dir)
    print(f"Scoring {len(pairs)} pairs ...")

    sims, labels, skipped = [], [], 0
    cache = {}

    def get(path):
        if path not in cache:
            cache[path] = embed(app, path)
        return cache[path]

    for i, (pa, pb, same) in enumerate(pairs):
        ea, eb = get(pa), get(pb)
        if ea is None or eb is None:
            skipped += 1
            continue
        sims.append(float(np.dot(ea, eb)))  # cosine (embeddings are normalized)
        labels.append(1 if same else 0)
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(pairs)}")

    sims = np.array(sims)
    labels = np.array(labels)
    print(f"\nScored {len(sims)} pairs ({skipped} skipped for undetected faces).")

    # Sweep thresholds; report accuracy + the security-relevant error rates.
    best_t, best_acc = 0.0, 0.0
    print("\n threshold |  accuracy |  FRR (reject genuine) |  FAR (accept impostor)")
    print(" ----------+-----------+-----------------------+-----------------------")
    for t in np.arange(0.20, 0.75, 0.01):
        pred = sims >= t
        acc = float(np.mean(pred == labels))
        genuine = labels == 1
        impostor = labels == 0
        frr = float(np.mean(~pred[genuine])) if genuine.any() else 0.0  # false reject
        far = float(np.mean(pred[impostor])) if impostor.any() else 0.0  # false accept (dangerous)
        if abs(t - round(t, 2)) < 1e-9 and (round(t * 100) % 5 == 0):
            print(f"    {t:0.2f}   |   {acc*100:6.2f}% |        {frr*100:6.2f}%        |        {far*100:6.2f}%")
        if acc > best_acc:
            best_acc, best_t = acc, t

    print(f"\nBest accuracy {best_acc*100:.2f}% at threshold {best_t:.2f}.")
    print("For an ENTRANCE, prefer a threshold with near-zero FAR (don't let impostors in),")
    print("even if it costs a little FRR. Set RECOGNITION_THRESHOLD accordingly.\n")


if __name__ == "__main__":
    main()
