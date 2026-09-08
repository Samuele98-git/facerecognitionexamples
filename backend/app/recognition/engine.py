"""InsightFace wrapper: turn an image into detected faces + 512-d embeddings.

The model (buffalo_l) is loaded lazily and once, guarded by a lock so concurrent
camera threads don't each try to initialise it. First call downloads ~326MB into
~/.insightface/models (persisted via a Docker volume).

Why no training: `buffalo_l` is already trained on Glint360K (17M images / 360K
identities). We only ever *use* it to produce embeddings; enrolling a person means
storing their embedding, not fine-tuning the model.
"""
import threading

import cv2
import numpy as np

from .. import config

_lock = threading.Lock()
_engine = None


def get_engine():
    """Return a ready FaceAnalysis app, initialising it once on first use."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                # Imported here so the module can be imported (and syntax-checked)
                # even in environments where insightface isn't installed yet.
                from insightface.app import FaceAnalysis

                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if config.USE_GPU
                    else ["CPUExecutionProvider"]
                )
                app = FaceAnalysis(name=config.MODEL_NAME, providers=providers)
                ctx_id = 0 if config.USE_GPU else -1
                app.prepare(ctx_id=ctx_id, det_size=(config.DET_SIZE, config.DET_SIZE))
                _engine = app
    return _engine


def is_ready() -> bool:
    """True once the model is loaded in memory (used by the health endpoint)."""
    return _engine is not None


def decode_image(data: bytes):
    """Decode uploaded image bytes into a BGR ndarray, or None if unreadable."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def detect_faces(image_bgr):
    """Detect faces and compute embeddings. Returns InsightFace Face objects.

    Each face exposes: .bbox, .det_score, .kps (5 landmarks), .normed_embedding
    (L2-normalized, so cosine similarity == dot product), plus .pose/.age/.gender.
    """
    if image_bgr is None:
        return []
    return get_engine().get(image_bgr)


def face_size(face) -> int:
    """Longest bbox side in pixels — a proxy for how usable/close the face is."""
    x1, y1, x2, y2 = face.bbox
    return int(max(x2 - x1, y2 - y1))


def embedding_bytes(face) -> bytes:
    """Serialize a face's normalized embedding for DB storage."""
    return np.asarray(face.normed_embedding, dtype=np.float32).tobytes()


def bytes_to_embedding(blob: bytes) -> np.ndarray:
    """Inverse of embedding_bytes()."""
    return np.frombuffer(blob, dtype=np.float32)
