"""FastAPI auth dependencies. Read the session cookie, validate the JWT, load the user."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config, security
from .database import get_db
from .models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = security.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user
