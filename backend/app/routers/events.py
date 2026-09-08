"""Recognition event feed — the audit log and the dashboard's live activity stream."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RecognitionEvent
from ..schemas import EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, le=500),
    camera_id: Optional[int] = None,
    person_id: Optional[int] = None,
    decision: Optional[str] = None,
):
    q = db.query(RecognitionEvent)
    if camera_id is not None:
        q = q.filter(RecognitionEvent.camera_id == camera_id)
    if person_id is not None:
        q = q.filter(RecognitionEvent.person_id == person_id)
    if decision:
        q = q.filter(RecognitionEvent.decision == decision)
    return q.order_by(RecognitionEvent.created_at.desc()).limit(limit).all()
