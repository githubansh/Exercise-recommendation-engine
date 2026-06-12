from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import CoachChatRequest
from app.core.db import get_db
from app.modules.coach.service import coach_service

router = APIRouter(prefix="/coach", tags=["coach"])


@router.post("/chat")
def chat(payload: CoachChatRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return coach_service.chat(db, user_id=payload.user_id, message=payload.message, history=payload.history)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
