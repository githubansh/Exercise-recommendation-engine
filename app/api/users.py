from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import IntakeTextRequest, UserCreate
from app.api.serializers import user_dict
from app.core.db import get_db
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


@router.post("/{user_id}/intake-text")
def parse_intake_text(user_id: int, payload: IntakeTextRequest, db: Session = Depends(get_db)) -> dict:
    user = profile_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        return profile_service.parse_intake_text(db, user_id, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
