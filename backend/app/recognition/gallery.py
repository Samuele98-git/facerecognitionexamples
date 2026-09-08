"""In-memory gallery of enrolled face embeddings + fast cosine matching.

For up to a few thousand people this plain NumPy dot-product is effectively instant
(a matrix-vector multiply). At larger scale, swap `_matrix @ emb` for a FAISS/Qdrant
index — the interface stays the same.

Every person can have several photos (different angles). We keep one row per photo and
match against all of them, taking the best score, so an off-angle face still matches the
person's off-angle enrollment shot.
"""
import threading

import numpy as np

from .. import config, settings_store
from ..database import SessionLocal
from ..models import Person, PersonPhoto
from . import engine

EMBED_DIM = 512


class Gallery:
    def __init__(self):
        self._lock = threading.RLock()
        self._matrix = np.zeros((0, EMBED_DIM), dtype=np.float32)  # rows = photo embeddings
        self._person_ids: list[int] = []                          # parallel to matrix rows
        self._meta: dict[int, dict] = {}                          # person_id -> {name, active}

    def load(self):
        """(Re)build the in-memory gallery from the database. Called on startup and
        after any enrollment change."""
        db = SessionLocal()
        try:
            embs, pids = [], []
            for row in db.query(PersonPhoto).all():
                embs.append(engine.bytes_to_embedding(row.embedding))
                pids.append(row.person_id)
            meta = {p.id: {"name": p.name, "active": p.active} for p in db.query(Person).all()}
        finally:
            db.close()

        matrix = (
            np.vstack(embs).astype(np.float32)
            if embs
            else np.zeros((0, EMBED_DIM), dtype=np.float32)
        )
        with self._lock:
            self._matrix = matrix
            self._person_ids = pids
            self._meta = meta

    def size(self):
        with self._lock:
            return self._matrix.shape[0], len(self._meta)

    def match(self, embedding: np.ndarray):
        """Return best match dict {person_id, name, active, similarity} or None.

        Embeddings are L2-normalized, so cosine similarity is just the dot product.
        Returns None when the best score is below RECOGNITION_THRESHOLD (an unknown face).
        """
        with self._lock:
            if self._matrix.shape[0] == 0:
                return None
            sims = self._matrix @ embedding.astype(np.float32)
            idx = int(np.argmax(sims))
            sim = float(sims[idx])
            threshold = settings_store.get_float(
                "recognition_threshold", config.RECOGNITION_THRESHOLD
            )
            if sim < threshold:
                return None
            pid = self._person_ids[idx]
            meta = self._meta.get(pid, {})
            return {
                "person_id": pid,
                "name": meta.get("name"),
                "active": meta.get("active", False),
                "similarity": sim,
            }


# Singleton used by the API routers and camera workers.
gallery = Gallery()
