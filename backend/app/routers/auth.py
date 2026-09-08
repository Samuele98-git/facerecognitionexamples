"""Authentication + user management.

/login and /logout are public; /me and everything under /users require a valid session
(and /users requires admin). Login is protected by per-IP rate limiting and per-account
lockout after repeated failures, and returns a single generic error to avoid revealing
whether a username exists.
"""
import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import config, security
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas import LoginRequest, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Precomputed hash so a login attempt for a non-existent user still spends ~the same time
# verifying (mitigates user-enumeration via timing).
_DUMMY_HASH = security.hash_password("this-is-not-a-real-password")

# --- simple in-memory per-IP login rate limiter ---------------------------
_rl_lock = threading.Lock()
_rl_hits: dict[str, list] = {}


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        hits = [t for t in _rl_hits.get(ip, []) if now - t < 60]
        if len(hits) >= config.LOGIN_RATE_PER_MIN:
            _rl_hits[ip] = hits
            return False
        hits.append(now)
        _rl_hits[ip] = hits
        return True


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=config.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        max_age=config.TOKEN_TTL_MINUTES * 60,
        path="/",
    )


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")

    invalid = HTTPException(status_code=401, detail="Invalid username or password")
    now = datetime.utcnow()  # naive UTC (consistent with what SQLite/PG return)

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        security.verify_password(payload.password, _DUMMY_HASH)  # equalize timing
        raise invalid

    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=423, detail="Account temporarily locked. Try again later.")

    if not user.active or not security.verify_password(payload.password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= config.MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=config.LOCKOUT_MINUTES)
            user.failed_attempts = 0
        db.commit()
        raise invalid

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now
    db.commit()

    _set_session_cookie(response, security.create_token(user.username, user.role))
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# --- admin user management ------------------------------------------------
@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in ("admin", "operator"):
        raise HTTPException(422, "role must be 'admin' or 'operator'")
    if len(payload.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(409, "Username already exists")
    user = User(
        username=payload.username,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    if payload.role is not None:
        if payload.role not in ("admin", "operator"):
            raise HTTPException(422, "role must be 'admin' or 'operator'")
        # Don't allow removing the last admin.
        if user.role == "admin" and payload.role != "admin" and _admin_count(db) <= 1:
            raise HTTPException(409, "Cannot demote the last administrator")
        user.role = payload.role

    if payload.active is not None:
        if not payload.active and user.id == current.id:
            raise HTTPException(409, "You cannot deactivate your own account")
        if not payload.active and user.role == "admin" and _active_admin_count(db) <= 1:
            raise HTTPException(409, "Cannot deactivate the last administrator")
        user.active = payload.active

    if payload.password is not None:
        if len(payload.password) < 8:
            raise HTTPException(422, "Password must be at least 8 characters")
        user.password_hash = security.hash_password(payload.password)
        user.failed_attempts = 0
        user.locked_until = None

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == current.id:
        raise HTTPException(409, "You cannot delete your own account")
    if user.role == "admin" and _active_admin_count(db) <= 1:
        raise HTTPException(409, "Cannot delete the last administrator")
    db.delete(user)
    db.commit()
    return {"ok": True}


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin").count()


def _active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.active.is_(True)).count()
