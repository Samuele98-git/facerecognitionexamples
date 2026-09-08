"""Runtime settings (admin only): recognition threshold, door-relay webhook, unknown logging."""
from fastapi import APIRouter, Depends, HTTPException

from .. import settings_store
from ..deps import require_admin
from ..models import User
from ..schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings(_: User = Depends(require_admin)):
    return SettingsOut(
        recognition_threshold=settings_store.get_float("recognition_threshold", 0.45),
        access_webhook_url=settings_store.get("access_webhook_url", "") or "",
        log_unknown=settings_store.get_bool("log_unknown", True),
        liveness_enabled=settings_store.get_bool("liveness_enabled", False),
        liveness_threshold=settings_store.get_float("liveness_threshold", 0.5),
    )


@router.patch("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, _: User = Depends(require_admin)):
    updates = {}
    if payload.recognition_threshold is not None:
        if not (0.05 <= payload.recognition_threshold <= 0.95):
            raise HTTPException(422, "recognition_threshold must be between 0.05 and 0.95")
        updates["recognition_threshold"] = payload.recognition_threshold
    if payload.access_webhook_url is not None:
        url = payload.access_webhook_url.strip()
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(422, "webhook URL must start with http:// or https://")
        updates["access_webhook_url"] = url
    if payload.log_unknown is not None:
        updates["log_unknown"] = "true" if payload.log_unknown else "false"
    if payload.liveness_enabled is not None:
        updates["liveness_enabled"] = "true" if payload.liveness_enabled else "false"
    if payload.liveness_threshold is not None:
        if not (0.05 <= payload.liveness_threshold <= 0.99):
            raise HTTPException(422, "liveness_threshold must be between 0.05 and 0.99")
        updates["liveness_threshold"] = payload.liveness_threshold

    if updates:
        settings_store.set_many(updates)

    return get_settings(_)
