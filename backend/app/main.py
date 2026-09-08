"""FastAPI application entrypoint.

Startup: create tables, load runtime settings, resolve the JWT secret, bootstrap the first
admin, warm the model, load the gallery, start enabled cameras. All data endpoints require a
valid session; user/settings management requires admin; media is auth-gated.
"""
import os
import secrets

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models, security, settings_store  # noqa: F401 (models registers tables)
from .database import Base, SessionLocal, engine
from .deps import get_current_user
from .ingest.camera_worker import manager
from .models import User
from .recognition import engine as rec_engine
from .recognition.gallery import gallery
from .routers import auth, cameras, events, media, people
from .routers import settings as settings_router

# Media dirs must exist before anything serves from them.
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)


def _resolve_jwt_secret() -> str:
    if config.JWT_SECRET:
        return config.JWT_SECRET
    existing = settings_store.get("jwt_secret")
    if existing:
        return existing
    generated = secrets.token_urlsafe(48)
    settings_store.set_many({"jwt_secret": generated})
    return generated


def _bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        password = config.ADMIN_PASSWORD or secrets.token_urlsafe(12)
        db.add(
            User(
                username=config.ADMIN_USERNAME,
                password_hash=security.hash_password(password),
                role="admin",
            )
        )
        db.commit()
        bar = "=" * 64
        if config.ADMIN_PASSWORD:
            print(f"[startup] created admin '{config.ADMIN_USERNAME}' from ADMIN_PASSWORD")
        else:
            print(
                f"\n{bar}\n[startup] INITIAL ADMIN ACCOUNT CREATED\n"
                f"  username: {config.ADMIN_USERNAME}\n"
                f"  password: {password}\n"
                f"  -> log in and change it (Settings > Users).\n{bar}\n"
            )
    finally:
        db.close()


async def _lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    settings_store.load()
    security.set_active_secret(_resolve_jwt_secret())
    _bootstrap_admin()
    try:
        rec_engine.get_engine()  # warm/verify the offline model
        print("[startup] recognition model ready")
    except Exception as exc:
        print(f"[startup] WARNING: model failed to load: {exc}")
    gallery.load()
    rows, people_count = gallery.size()
    print(f"[startup] gallery loaded: {rows} face(s) across {people_count} person(s)")
    manager.start_all_enabled()
    yield
    manager.stop_all()


app = FastAPI(title="Face Access Control", version="0.2.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,  # required so the browser sends the session cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth endpoints are public (login/logout); /me and /users self-guard.
app.include_router(auth.router)

# All data endpoints require a valid session.
authed = [Depends(get_current_user)]
app.include_router(people.router, dependencies=authed)
app.include_router(cameras.router, dependencies=authed)
app.include_router(events.router, dependencies=authed)
app.include_router(media.router)            # routes self-guard with get_current_user
app.include_router(settings_router.router)  # routes self-guard with require_admin


@app.get("/api/ping")
def ping():
    """Public, minimal liveness probe (no sensitive data)."""
    return {"status": "ok"}


@app.get("/api/health")
def health(_: User = Depends(get_current_user)):
    rows, people_count = gallery.size()
    return {
        "status": "ok",
        "model_ready": rec_engine.is_ready(),
        "enrolled_faces": rows,
        "people": people_count,
        "threshold": settings_store.get_float("recognition_threshold", config.RECOGNITION_THRESHOLD),
        "gpu": config.USE_GPU,
    }
