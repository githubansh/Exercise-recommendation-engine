from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import SessionLogRequest
from app.core.db import get_db
from app.modules.feedback.service import feedback_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/log")
def log_session(payload: SessionLogRequest, db: Session = Depends(get_db)) -> dict:
    try:
        log = feedback_service.log_session(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": log.id,
        "plan_day_id": log.plan_day_id,
        "rpe": log.rpe,
        "duration_min": log.duration_min,
        "notes": log.notes,
    }
