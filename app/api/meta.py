from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import InjuryProfile
from app.modules.catalog.constants import EQUIPMENT_VALUES, GOALS, LEVEL_ORDER

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/options")
def options(db: Session = Depends(get_db)) -> dict:
    injuries = db.scalars(select(InjuryProfile).order_by(InjuryProfile.display_name)).all()
    return {
        "goals": GOALS,
        "levels": list(LEVEL_ORDER.keys()),
        "equipment": sorted(EQUIPMENT_VALUES),
        "injuries": [
            {
                "code": injury.code,
                "display_name": injury.display_name,
                "description": injury.description,
            }
            for injury in injuries
        ],
    }
