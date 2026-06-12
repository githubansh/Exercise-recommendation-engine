import pytest
from pydantic import ValidationError

from app.api.schemas import UserCreate


def valid_user_payload() -> dict:
    return {
        "name": "Tester",
        "level": "beginner",
        "goal": "hypertrophy",
        "days_per_week": 3,
        "minutes_per_session": 45,
        "equipment": ["body only", "dumbbell"],
    }


def test_user_create_rejects_unknown_equipment() -> None:
    payload = valid_user_payload()
    payload["equipment"] = ["body only", "dumbbells"]

    with pytest.raises(ValidationError, match="Unknown equipment"):
        UserCreate.model_validate(payload)


def test_user_create_accepts_pullup_bar_and_other() -> None:
    payload = valid_user_payload()
    payload["equipment"] = ["body only", "pull-up bar", "other"]

    user = UserCreate.model_validate(payload)

    assert user.equipment == ["body only", "pull-up bar", "other"]
