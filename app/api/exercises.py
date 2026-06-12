from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.serializers import exercise_dict
from app.core.db import get_db
from app.modules.catalog.service import catalog_service

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("/search")
def search_exercises(
    q: str = "",
    muscle: str | None = None,
    equipment: list[str] | None = Query(default=None),
    level: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    filters = {
        "muscle_group": muscle,
        "equipment": set(equipment) if equipment else None,
        "max_level": level,
    }
    return [exercise_dict(item) for item in catalog_service.semantic_search(db, q, k=20, filters=filters)]


@router.get("/{exercise_id}")
def get_exercise(exercise_id: str, db: Session = Depends(get_db)) -> dict:
    exercise = catalog_service.get_exercise(db, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise_dict(exercise)
