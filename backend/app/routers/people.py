"""Enrollment API: create/update/delete people and add/remove their face photos.

Adding a photo runs the detector, rejects images that don't contain exactly one clear
face, stores the embedding, and rebuilds the in-memory gallery — so a newly hired
employee is recognized within a second, and a fired one disappears the moment their
record (or `active` flag) changes.
"""
import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Person, PersonPhoto
from ..recognition import engine
from ..recognition.gallery import gallery
from ..schemas import PersonCreate, PersonOut, PersonUpdate, PhotoOut

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=list[PersonOut])
def list_people(db: Session = Depends(get_db)):
    return db.query(Person).order_by(Person.name).all()


@router.post("", response_model=PersonOut)
def create_person(payload: PersonCreate, db: Session = Depends(get_db)):
    person = Person(**payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    gallery.load()
    return person


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(person_id: int, payload: PersonUpdate, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    gallery.load()  # picks up active/inactive change immediately
    return person


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    for photo in person.photos:
        _remove_file(config.UPLOAD_DIR, photo.filename)
    db.delete(person)
    db.commit()
    gallery.load()
    return {"ok": True}


@router.post("/{person_id}/photos", response_model=PhotoOut)
async def add_photo(
    person_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")

    image = engine.decode_image(await file.read())
    if image is None:
        raise HTTPException(400, "Could not decode image file")

    faces = engine.detect_faces(image)
    if len(faces) == 0:
        raise HTTPException(422, "No face detected — use a clear, well-lit photo")
    if len(faces) > 1:
        raise HTTPException(
            422, f"{len(faces)} faces detected — an enrollment photo must contain exactly one face"
        )

    face = faces[0]
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    filename = f"person{person_id}_{int(time.time() * 1000)}{ext}"
    # Re-encode to a clean JPEG so we control format/size regardless of upload type.
    import cv2

    cv2.imwrite(os.path.join(config.UPLOAD_DIR, filename), image)

    photo = PersonPhoto(
        person_id=person_id,
        filename=filename,
        embedding=engine.embedding_bytes(face),
        quality=float(face.det_score),
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    gallery.load()
    return photo


@router.delete("/{person_id}/photos/{photo_id}")
def delete_photo(person_id: int, photo_id: int, db: Session = Depends(get_db)):
    photo = db.get(PersonPhoto, photo_id)
    if not photo or photo.person_id != person_id:
        raise HTTPException(404, "Photo not found")
    _remove_file(config.UPLOAD_DIR, photo.filename)
    db.delete(photo)
    db.commit()
    gallery.load()
    return {"ok": True}


def _remove_file(directory, filename):
    try:
        os.remove(os.path.join(directory, filename))
    except OSError:
        pass
