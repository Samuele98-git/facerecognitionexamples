"""Pydantic request/response schemas (API contract)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- People ---------------------------------------------------------------
class PersonBase(BaseModel):
    name: str
    employee_id: Optional[str] = None
    role: Optional[str] = None
    active: bool = True


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None


class PhotoOut(BaseModel):
    id: int
    filename: str
    quality: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PersonOut(PersonBase):
    id: int
    created_at: datetime
    photos: list[PhotoOut] = []

    class Config:
        from_attributes = True


# --- Cameras --------------------------------------------------------------
class CameraBase(BaseModel):
    name: str
    rtsp_url: str
    location: Optional[str] = None
    enabled: bool = True


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    enabled: Optional[bool] = None


class CameraOut(CameraBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Auth / users ---------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


# --- Settings -------------------------------------------------------------
class SettingsOut(BaseModel):
    recognition_threshold: float
    access_webhook_url: str
    log_unknown: bool
    liveness_enabled: bool
    liveness_threshold: float


class SettingsUpdate(BaseModel):
    recognition_threshold: Optional[float] = None
    access_webhook_url: Optional[str] = None
    log_unknown: Optional[bool] = None
    liveness_enabled: Optional[bool] = None
    liveness_threshold: Optional[float] = None


# --- Events ---------------------------------------------------------------
class EventOut(BaseModel):
    id: int
    camera_id: Optional[int] = None
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    similarity: Optional[float] = None
    decision: str
    snapshot: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
