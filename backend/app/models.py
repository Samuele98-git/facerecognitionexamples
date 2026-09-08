"""Database models.

A Person has many PersonPhotos. Each photo stores the raw 512-float face embedding
(the "fingerprint") so we never need to re-run the model to rebuild the gallery, and
adding/removing an employee is just an INSERT/DELETE — no retraining.
"""
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    employee_id = Column(String(100), unique=True, nullable=True)
    role = Column(String(200), nullable=True)
    # active=False means fired/suspended -> recognized but access DENIED and flagged.
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    photos = relationship(
        "PersonPhoto", back_populates="person", cascade="all, delete-orphan"
    )


class PersonPhoto(Base):
    __tablename__ = "person_photos"

    id = Column(Integer, primary_key=True)
    person_id = Column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    filename = Column(String(300), nullable=False)
    embedding = Column(LargeBinary, nullable=False)  # float32 x 512, L2-normalized
    quality = Column(Float, nullable=True)           # detector confidence at enroll time
    created_at = Column(DateTime, default=utcnow)

    person = relationship("Person", back_populates="photos")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    rtsp_url = Column(Text, nullable=False)
    location = Column(String(200), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="operator")  # admin | operator
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_login = Column(DateTime, nullable=True)
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)  # naive UTC (see routers/auth.py)


class Setting(Base):
    """Key/value runtime settings (threshold, webhook, jwt secret, ...)."""
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class RecognitionEvent(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True)
    # Denormalized name so the audit log stays readable even after a person is deleted.
    person_name = Column(String(200), nullable=True)
    similarity = Column(Float, nullable=True)
    decision = Column(String(20), nullable=False, default="denied")  # granted | denied
    snapshot = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
