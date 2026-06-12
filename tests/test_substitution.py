from app.core.models import Exercise, PlanDay, PlanSlot
from app.modules.substitution.service import day_minutes


def exercise(exercise_id: str, mechanic: str) -> Exercise:
    return Exercise(
        id=exercise_id,
        name=exercise_id,
        level="beginner",
        force=None,
        mechanic=mechanic,
        equipment="body only",
        category="strength",
        primary_muscles=["chest"],
        secondary_muscles=[],
        instructions=["Move under control."],
        instructions_generated=False,
        images=[],
        muscle_groups=["chest"],
    )


def test_day_minutes_uses_override_for_swap_projection() -> None:
    day = PlanDay(id=1, plan_id=1, day_index=1, focus="upper")
    slot = PlanSlot(
        id=10,
        plan_day_id=1,
        slot_index=1,
        exercise_id="curl",
        sets=3,
        reps="8-12",
        rest_sec=90,
        rpe_target=8,
        rationale="test",
        status="planned",
    )
    slot.exercise = exercise("curl", "isolation")
    day.slots = [slot]

    assert day_minutes(day) == 17.0
    assert day_minutes(day, override={slot.id: (slot.sets, "compound")}) == 20.0
