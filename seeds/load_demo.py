from __future__ import annotations

from app.core.db import SessionLocal
from app.modules.planner.service import planner_service
from app.modules.profile.service import profile_service


DEMO_USERS = [
    {
        "name": "Demo Bodyweight Beginner",
        "level": "beginner",
        "goal": "hypertrophy",
        "days_per_week": 3,
        "minutes_per_session": 30,
        "equipment": ["body only"],
        "injuries": [{"injury_code": "knee_pain", "severity": "moderate"}],
        "exclusions": [],
    },
    {
        "name": "Demo Dumbbell Fat Loss",
        "level": "beginner",
        "goal": "fat_loss",
        "days_per_week": 4,
        "minutes_per_session": 45,
        "equipment": ["body only", "dumbbell", "bands"],
        "injuries": [],
        "exclusions": [],
    },
    {
        "name": "Demo Gym Strength",
        "level": "intermediate",
        "goal": "strength",
        "days_per_week": 5,
        "minutes_per_session": 60,
        "equipment": ["body only", "barbell", "dumbbell", "machine", "cable", "pull-up bar"],
        "injuries": [{"injury_code": "lower_back_pain", "severity": "moderate"}],
        "exclusions": [],
    },
]


def main() -> None:
    with SessionLocal() as db:
        for payload in DEMO_USERS:
            user = profile_service.create_user(db, dict(payload))
            plan = planner_service.generate_plan(db, user.id, week_index=1)
            print(f"created user={user.id} plan={plan.id} {user.name}")


if __name__ == "__main__":
    main()
