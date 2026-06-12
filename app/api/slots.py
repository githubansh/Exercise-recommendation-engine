from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import SwapRequest
from app.api.serializers import exercise_dict, slot_dict
from app.core.db import get_db
from app.modules.substitution.service import substitution_service

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/{slot_id}/alternatives")
def alternatives(slot_id: int, k: int = 5, db: Session = Depends(get_db)) -> list[dict]:
    try:
        items = substitution_service.alternatives(db, slot_id, k=k)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        {
            "exercise": exercise_dict(item["exercise"]),
            "score": item["score"],
            "similarity": item["similarity"],
            "utility": item["utility"],
            "primary_group": item["primary_group"],
        }
        for item in items
    ]


@router.post("/{slot_id}/swap")
def swap(slot_id: int, payload: SwapRequest, db: Session = Depends(get_db)) -> dict:
    try:
        slot = substitution_service.swap(db, slot_id, payload.exercise_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return slot_dict(slot)
