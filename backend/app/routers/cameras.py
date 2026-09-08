"""Camera management API + live MJPEG stream.

Creating/enabling a camera starts a worker thread; disabling/deleting stops it. The
`/stream` endpoint serves the annotated video as multipart MJPEG, which any browser can
render in a plain <img> tag — no media server needed for the pilot. (For production/low
latency, put go2rtc in front and switch the dashboard to WebRTC — see README.)
"""
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingest.camera_worker import manager
from ..models import Camera
from ..schemas import CameraCreate, CameraOut, CameraUpdate

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).order_by(Camera.name).all()


@router.post("", response_model=CameraOut)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    cam = Camera(**payload.model_dump())
    db.add(cam)
    db.commit()
    db.refresh(cam)
    if cam.enabled:
        manager.start_camera(cam)
    return cam


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: int, payload: CameraUpdate, db: Session = Depends(get_db)):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cam, field, value)
    db.commit()
    db.refresh(cam)
    if cam.enabled:
        manager.restart_camera(cam)  # picks up url/name changes too
    else:
        manager.stop_camera(cam.id)
    return cam


@router.delete("/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    manager.stop_camera(cam.id)
    db.delete(cam)
    db.commit()
    return {"ok": True}


def _mjpeg(worker):
    """Yield the worker's latest annotated frame as an MJPEG multipart stream."""
    while True:
        jpeg = worker.get_jpeg()
        if jpeg is not None:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
        time.sleep(0.05)  # ~20 fps cap on the preview


@router.get("/{camera_id}/stream")
def stream(camera_id: int):
    worker = manager.get_worker(camera_id)
    if worker is None:
        raise HTTPException(404, "Camera not running (is it enabled?)")
    return StreamingResponse(
        _mjpeg(worker), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/{camera_id}/snapshot")
def snapshot(camera_id: int):
    worker = manager.get_worker(camera_id)
    if worker is None:
        raise HTTPException(404, "Camera not running")
    jpeg = worker.get_jpeg()
    if jpeg is None:
        raise HTTPException(503, "No frame available yet")
    return Response(content=jpeg, media_type="image/jpeg")
