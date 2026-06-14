import os

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import ExercisePattern, InjuryProfile, Plan, UserInjury
from app.modules.coach.service import coach_service
from app.modules.planner.service import planner_service
from app.modules.profile.service import profile_service
from app.modules.substitution.service import substitution_service

pytestmark = pytest.mark.integration


def seeded_database_available(db) -> bool:
    return bool(db.scalar(select(InjuryProfile.code).limit(1))) and bool(
        db.scalar(select(ExercisePattern.exercise_id).limit(1))
    )


requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs seeded PostgreSQL")


@requires_db
def test_create_user_rejects_invalid_injury_code() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")

        with pytest.raises(ValueError, match="Invalid injury codes"):
            profile_service.create_user(
                db,
                {
                    "name": "Bad Injury",
                    "level": "beginner",
                    "goal": "hypertrophy",
                    "days_per_week": 3,
                    "minutes_per_session": 45,
                    "equipment": ["body only"],
                    "injuries": [{"injury_code": "not_real", "severity": "moderate"}],
                },
            )


@requires_db
def test_knee_pain_user_never_receives_blocked_patterns() -> None:
    blocked_patterns = {"deep_knee_flexion", "high_impact", "lunge_pattern", "squat_pattern"}
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        flagged_ids = set(
            db.scalars(
                select(ExercisePattern.exercise_id).where(ExercisePattern.pattern.in_(blocked_patterns))
            ).all()
        )
        user = profile_service.create_user(
            db,
            {
                "name": "Safety Knee",
                "age": 25,
                "sex": "m",
                "height_cm": 175,
                "weight_kg": 70,
                "level": "beginner",
                "goal": "hypertrophy",
                "days_per_week": 4,
                "minutes_per_session": 45,
                "equipment": ["body only", "dumbbell", "barbell", "machine", "cable", "pull-up bar", "other"],
                "injuries": [{"injury_code": "knee_pain", "severity": "severe"}],
            },
        )
        for week in range(1, 21):
            plan = planner_service.generate_plan(db, user.id, week_index=week)
            for day in plan.days:
                for slot in day.slots:
                    assert slot.exercise_id not in flagged_ids, (
                        f"week {week}: {slot.exercise_id} violates knee_pain contraindications"
                    )


@requires_db
def test_lower_back_user_never_receives_blocked_patterns_or_swap_alternatives() -> None:
    blocked_patterns = {"spinal_loading", "spinal_flexion", "hip_hinge"}
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        flagged_ids = set(
            db.scalars(
                select(ExercisePattern.exercise_id).where(ExercisePattern.pattern.in_(blocked_patterns))
            ).all()
        )
        user = profile_service.create_user(
            db,
            {
                "name": "Safety Back",
                "age": 32,
                "sex": "m",
                "height_cm": 178,
                "weight_kg": 78,
                "level": "beginner",
                "goal": "hypertrophy",
                "days_per_week": 3,
                "minutes_per_session": 45,
                "equipment": ["body only", "dumbbell", "barbell", "machine", "cable", "pull-up bar", "other"],
                "injuries": [{"injury_code": "lower_back_pain", "severity": "severe"}],
            },
        )
        plan = planner_service.generate_plan(db, user.id, week_index=1)
        for day in plan.days:
            for slot in day.slots:
                assert slot.exercise_id not in flagged_ids

        first_slot = plan.days[0].slots[0]
        alternatives = substitution_service.alternatives(db, first_slot.id, k=10)
        for item in alternatives:
            assert item["exercise"].id not in flagged_ids


@requires_db
def test_coach_injury_update_persists_safety_profile_and_regenerates_plan() -> None:
    with SessionLocal() as db:
        if not seeded_database_available(db):
            pytest.skip("seeded database required")
        user = profile_service.create_user(
            db,
            {
                "name": "Coach Safety",
                "age": 28,
                "sex": "m",
                "height_cm": 175,
                "weight_kg": 75,
                "level": "beginner",
                "goal": "hypertrophy",
                "days_per_week": 3,
                "minutes_per_session": 35,
                "equipment": ["body only", "dumbbell", "machine"],
                "injuries": [],
            },
        )
        old_plan = planner_service.generate_plan(db, user.id, week_index=1)

        response = coach_service.chat(db, user_id=user.id, message="I have a knee injury", history=[])

        injury = db.get(UserInjury, {"user_id": user.id, "injury_code": "knee_pain"})
        active_plan = db.scalar(select(Plan).where(Plan.user_id == user.id, Plan.status == "active"))
        db.refresh(old_plan)

        assert injury is not None
        assert injury.severity == "moderate"
        assert old_plan.status == "replaced"
        assert active_plan is not None
        assert active_plan.id != old_plan.id
        assert response["tool_results"][0]["tool"] == "update_safety_profile"
        assert "Safety profile updated" in response["message"]
