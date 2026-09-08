"""Authenticated media serving.

Enrollment photos and event snapshots are faces — sensitive data — so they are served
through auth-gated routes instead of a public static mount. Filenames are reduced to their
basename to prevent path traversal.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..deps import get_current_user
from ..models import User

router = APIRouter(prefix="/api/media", tags=["media"])


def _safe(directory: str, filename: str) -> str:
    name = os.path.basename(filename)  # strip any path components
    if not name or name != filename:
        raise HTTPException(400, "Invalid filename")
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        raise HTTPException(404, "Not found")
    return path


@router.get("/uploads/{filename}")
def upload(filename: str, _: User = Depends(get_current_user)):
    return FileResponse(_safe(config.UPLOAD_DIR, filename))


@router.get("/snapshots/{filename}")
def snapshot(filename: str, _: User = Depends(get_current_user)):
    return FileResponse(_safe(config.SNAPSHOT_DIR, filename))
