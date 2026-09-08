"""Password hashing + JWT session tokens.

Passwords: bcrypt over a base64(sha256(pw)) pre-hash. The pre-hash sidesteps bcrypt's
72-byte input limit and its null-byte truncation, so arbitrarily long passwords are
handled safely.

Tokens: HS256 JWT signed with a per-install secret (resolved once at startup and set via
set_active_secret). Delivered to the browser in an httpOnly cookie so JavaScript (and thus
XSS) can never read it.
"""
import base64
import datetime
import hashlib

import bcrypt
import jwt

from . import config

_active_secret: str | None = None


def set_active_secret(secret: str) -> None:
    global _active_secret
    _active_secret = secret


def _prep(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(password), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(username: str, role: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=config.TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, _active_secret, algorithm=config.JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _active_secret, algorithms=[config.JWT_ALG])
