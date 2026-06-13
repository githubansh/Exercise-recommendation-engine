from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import IntakePreviewRequest
from app.core.db import get_db
from app.modules.profile.service import profile_service

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/preview")
def preview_intake(payload: IntakePreviewRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return profile_service.preview_intake_text(db, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
