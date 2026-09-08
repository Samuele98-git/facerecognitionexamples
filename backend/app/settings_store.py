"""In-memory cache of runtime settings (editable by admins without a restart).

Backed by the `settings` table. Read on the hot path (every recognition match reads the
threshold), so it's cached in memory and refreshed on change.
"""
import threading

from . import config
from .database import SessionLocal
from .models import Setting

_lock = threading.RLock()
_cache: dict[str, str] = {}

# Keys exposed through the settings API (jwt_secret is intentionally NOT here).
PUBLIC_KEYS = (
    "recognition_threshold",
    "access_webhook_url",
    "log_unknown",
    "liveness_enabled",
    "liveness_threshold",
)


def _defaults() -> dict[str, str]:
    return {
        "recognition_threshold": str(config.RECOGNITION_THRESHOLD),
        "access_webhook_url": "",
        "log_unknown": "true" if config.LOG_UNKNOWN else "false",
        "liveness_enabled": "true" if config.LIVENESS_ENABLED else "false",
        "liveness_threshold": str(config.LIVENESS_THRESHOLD),
    }


def load() -> None:
    db = SessionLocal()
    try:
        rows = {s.key: s.value for s in db.query(Setting).all()}
    finally:
        db.close()
    with _lock:
        _cache.clear()
        _cache.update(_defaults())
        _cache.update(rows)


def get(key: str, default=None):
    with _lock:
        return _cache.get(key, default)


def get_float(key: str, default: float) -> float:
    try:
        return float(get(key, default))
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    v = get(key)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


def set_many(updates: dict) -> None:
    """Persist a batch of key->value (values coerced to str) and refresh the cache."""
    db = SessionLocal()
    try:
        for key, value in updates.items():
            sval = "" if value is None else str(value)
            row = db.get(Setting, key)
            if row:
                row.value = sval
            else:
                db.add(Setting(key=key, value=sval))
        db.commit()
    finally:
        db.close()
    load()
