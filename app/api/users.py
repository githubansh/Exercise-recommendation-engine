from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import IntakeTextRequest, UserCreate, UserUpdate
from app.api.serializers import user_dict
from app.core.db import get_db
from app.modules.feedback.service import feedback_service
from app.modules.profile.service import profile_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("")
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> dict:
    try:
        user = profile_service.create_user(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user_dict(user)


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = profile_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_dict(user)


@router.patch("/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> dict:
    try:
        user = profile_service.update_user(db, user_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user_dict(user)


@router.get("/{user_id}/progress")
def get_progress(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = profile_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return feedback_service.progress_summary(db, user_id)


@router.post("/{user_id}/intake-text")
def parse_intake_text(user_id: int, payload: IntakeTextRequest, db: Session = Depends(get_db)) -> dict:
    user = profile_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        return profile_service.parse_intake_text(db, user_id, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
