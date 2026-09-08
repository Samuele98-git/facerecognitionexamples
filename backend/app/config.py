"""Central configuration, read from environment variables with sensible defaults.

Everything that affects accuracy or performance is tunable here so you can adjust
without touching code (via docker-compose environment: or a local .env).
"""
import os


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# --- Database -------------------------------------------------------------
# Defaults to a local SQLite file so the app runs with zero setup.
# docker-compose overrides this with PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# --- Storage paths --------------------------------------------------------
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")      # enrollment photos
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "./data/snapshots")  # recognition event crops

# --- Recognition model ----------------------------------------------------
# buffalo_l = SCRFD-10G detector + ResNet100 ArcFace (glint360k). State of the art, ~326MB.
# Downloaded automatically on first run into ~/.insightface/models.
MODEL_NAME = os.getenv("MODEL_NAME", "buffalo_l")
USE_GPU = _get_bool("USE_GPU", False)
DET_SIZE = int(os.getenv("DET_SIZE", "640"))  # detector input size (higher = smaller/farther faces, slower)

# Cosine-similarity threshold for declaring a match (0..1).
# Higher = stricter (fewer false accepts, the safe direction for access control).
# Calibrate on your own data with ml/benchmark.py. 0.45 is a secure default for buffalo_l.
RECOGNITION_THRESHOLD = float(os.getenv("RECOGNITION_THRESHOLD", "0.45"))

# Ignore faces smaller than this (pixels, longest side) — too far/blurry to trust.
MIN_FACE_PIXELS = int(os.getenv("MIN_FACE_PIXELS", "50"))

# --- Camera processing ----------------------------------------------------
PROCESS_FPS = float(os.getenv("PROCESS_FPS", "6"))          # recognition passes per second per camera
EVENT_DEBOUNCE_SECONDS = float(os.getenv("EVENT_DEBOUNCE_SECONDS", "15"))  # don't re-log same person/camera
LOG_UNKNOWN = _get_bool("LOG_UNKNOWN", True)                # log unrecognized faces as alerts

# --- Liveness / anti-spoofing (see recognition/liveness.py) ---------------
LIVENESS_ENABLED = _get_bool("LIVENESS_ENABLED", False)
# Averaged "real" probability required to pass liveness (higher = stricter).
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.5"))
# Directory of the MiniFASNet anti-spoof ONNX models (baked into the image).
ANTISPOOF_DIR = os.getenv("ANTISPOOF_DIR", "/app/antispoof_models")

# --- CORS (the Vite dev server origin) ------------------------------------
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

# --- Authentication -------------------------------------------------------
# If JWT_SECRET is empty, a strong random secret is generated and persisted in the
# settings table on first startup (stable across restarts).
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALG = "HS256"
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "480"))  # session length (8h)

COOKIE_NAME = os.getenv("COOKIE_NAME", "fac_session")
# Secure=true requires HTTPS — turn it on in production (behind TLS). SameSite=strict
# blocks cross-site requests, giving CSRF protection for this same-origin SPA.
COOKIE_SECURE = _get_bool("COOKIE_SECURE", False)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "strict")

# First-run admin bootstrap. If ADMIN_PASSWORD is empty, a random one is generated
# and printed to the logs ONCE — change it immediately after first login.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Brute-force protection
MAX_FAILED_ATTEMPTS = int(os.getenv("MAX_FAILED_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
LOGIN_RATE_PER_MIN = int(os.getenv("LOGIN_RATE_PER_MIN", "10"))  # per client IP
