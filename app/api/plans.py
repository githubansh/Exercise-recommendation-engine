from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import PlanGenerateRequest
from app.api.serializers import plan_dict
from app.core.db import get_db
from app.core.models import Plan
from app.modules.feedback.service import feedback_service
from app.modules.planner.service import planner_service

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/generate")
def generate_plan(payload: PlanGenerateRequest, db: Session = Depends(get_db)) -> dict:
    try:
        plan = planner_service.generate_plan(db, payload.user_id, week_index=payload.week_index)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan_dict(plan)


@router.get("/user/{user_id}")
def list_user_plans(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    plans = db.scalars(
        select(Plan)
        .where(Plan.user_id == user_id)
        .order_by(Plan.week_index.desc(), Plan.version.desc(), Plan.id.desc())
    ).all()
    return [plan_dict(plan) for plan in plans]


@router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan_dict(plan)


@router.post("/{plan_id}/regenerate")
def regenerate_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status != "active":
        raise HTTPException(status_code=400, detail="Only the active plan can be regenerated.")
    try:
        next_plan = planner_service.generate_plan(
            db,
            plan.user_id,
            week_index=plan.week_index,
            mode_note="regenerated current week after profile or rule changes",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan_dict(next_plan)


@router.post("/{plan_id}/adapt")
def adapt_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        plan = feedback_service.adapt_week(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan_dict(plan)


@router.post("/{plan_id}/activate")
def activate_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status != "active":
        db.query(Plan).filter(Plan.user_id == plan.user_id, Plan.status == "active").update({"status": "replaced"})
        plan.status = "active"
        db.commit()
        db.refresh(plan)
    return plan_dict(plan)
