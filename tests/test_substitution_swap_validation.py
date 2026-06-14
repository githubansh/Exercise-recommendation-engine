import os

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Exercise, ExercisePattern, InjuryProfile
from app.modules.planner.service import planner_service
from app.modules.profile.service import profile_service
from app.modules.substitution.service import substitution_service

pytestmark = pytest.mark.integration

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs seeded PostgreSQL")


def seeded_database_available(db) -> bool:
    return bool(db.scalar(select(InjuryProfile.code).limit(1))) and bool(
        db.scalar(select(ExercisePattern.exercise_id).limit(1))
    )


def create_swap_plan(db, *, equipment: list[str], injuries: list[dict] | None = None):
    user = profile_service.create_user(
        db,
        {
            "name": "Swap Validation",
            "level": "beginner",
            "goal": "hypertrophy",
            "days_per_week": 3,
            "minutes_per_session": 45,
            "equipment": equipment,
            "injuries": injuries or [],
        },
    )
    return planner_service.generate_plan(db, user.id, week_index=1)


@requires_db
def test_swap_rejects_missing_exercise() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_swap_plan(db, equipment=["body only", "dumbbell", "machine"])
        slot = plan.days[0].slots[0]

        with pytest.raises(ValueError, match="does not exist"):
            substitution_service.swap(db, slot.id, "not_a_real_exercise")


@requires_db
def test_swap_rejects_wrong_equipment() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_swap_plan(db, equipment=["body only"])
        slot = plan.days[0].slots[0]
        plan_ids = {slot.exercise_id for day in plan.days for slot in day.slots}
        candidate = db.scalar(
            select(Exercise)
            .where(Exercise.equipment != "body only", ~Exercise.id.in_(plan_ids))
            .limit(1)
        )
        if candidate is None:
            pytest.skip("no wrong-equipment exercise available")

        with pytest.raises(ValueError, match="which you do not have"):
            substitution_service.swap(db, slot.id, candidate.id)


@requires_db
def test_swap_rejects_exercise_already_in_plan() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_swap_plan(db, equipment=["body only", "dumbbell", "machine", "cable"])
        slots = [slot for day in plan.days for slot in day.slots]
        if len(slots) < 2:
            pytest.skip("plan needs at least two slots")

        with pytest.raises(ValueError, match="already in this plan"):
            substitution_service.swap(db, slots[0].id, slots[1].exercise_id)


@requires_db
def test_swap_rejects_safety_blocked_exercise() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        plan = create_swap_plan(
            db,
            equipment=["body only", "dumbbell", "barbell", "machine", "cable", "pull-up bar", "other"],
            injuries=[{"injury_code": "knee_pain", "severity": "severe"}],
        )
        slot = plan.days[0].slots[0]
        blocked_id = db.scalar(
            select(ExercisePattern.exercise_id)
            .where(ExercisePattern.pattern.in_(["deep_knee_flexion", "high_impact", "lunge_pattern", "squat_pattern"]))
            .limit(1)
        )
        if blocked_id is None:
            pytest.skip("no knee-blocked exercise available")

        with pytest.raises(ValueError, match="blocked by your safety rules"):
            substitution_service.swap(db, slot.id, blocked_id)
