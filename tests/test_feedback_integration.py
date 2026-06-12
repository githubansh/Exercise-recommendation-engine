import os

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import ExercisePattern, InjuryProfile
from app.modules.feedback.service import feedback_service
from app.modules.planner.service import planner_service
from app.modules.profile.service import profile_service

pytestmark = pytest.mark.integration

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs seeded PostgreSQL")


def seeded_database_available(db) -> bool:
    return bool(db.scalar(select(InjuryProfile.code).limit(1))) and bool(
        db.scalar(select(ExercisePattern.exercise_id).limit(1))
    )


def create_demo_plan(db):
    user = profile_service.create_user(
        db,
        {
            "name": "Feedback Demo",
            "level": "beginner",
            "goal": "hypertrophy",
            "days_per_week": 3,
            "minutes_per_session": 45,
            "equipment": ["body only", "dumbbell", "machine", "cable"],
            "injuries": [],
        },
    )
    return planner_service.generate_plan(db, user.id, week_index=1)


@requires_db
def test_log_session_is_idempotent_per_day() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_demo_plan(db)
        day = plan.days[0]
        feedback_service.log_session(
            db,
            plan_day_id=day.id,
            rpe=8,
            completed_slot_ids=[day.slots[0].id],
            skipped_slot_ids=[],
        )

        with pytest.raises(ValueError, match="already has a logged session"):
            feedback_service.log_session(
                db,
                plan_day_id=day.id,
                rpe=8,
                completed_slot_ids=[day.slots[0].id],
                skipped_slot_ids=[],
            )


@requires_db
def test_deferred_slots_do_not_lower_adherence() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_demo_plan(db)
        first_slot = plan.days[0].slots[0]
        for day in plan.days:
            for slot in day.slots:
                slot.status = "deferred"
        first_slot.status = "completed"
        db.commit()

        next_plan = feedback_service.adapt_week(db, plan.id)

        assert next_plan.params["days_override"] is None


@requires_db
def test_replaced_plan_cannot_be_adapted_twice() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_demo_plan(db)
        feedback_service.adapt_week(db, plan.id)

        with pytest.raises(ValueError, match="only the active plan can be adapted"):
            feedback_service.adapt_week(db, plan.id)
