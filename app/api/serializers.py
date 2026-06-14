from __future__ import annotations

from app.core.models import Exercise, Plan, PlanDay, PlanSlot, User
from app.core.config import settings


def image_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{settings.imagekit_base_url.rstrip('/')}/{path.lstrip('/')}"


def exercise_dict(exercise: Exercise) -> dict:
    return {
        "id": exercise.id,
        "name": exercise.name,
        "level": exercise.level,
        "force": exercise.force,
        "mechanic": exercise.mechanic,
        "equipment": exercise.equipment,
        "category": exercise.category,
        "primary_muscles": exercise.primary_muscles,
        "secondary_muscles": exercise.secondary_muscles,
        "muscle_groups": exercise.muscle_groups,
        "instructions": exercise.instructions,
        "images": exercise.images,
        "image_urls": [image_url(path) for path in exercise.images],
    }


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "age": user.age,
        "sex": user.sex,
        "height_cm": user.height_cm,
        "weight_kg": user.weight_kg,
        "level": user.level,
        "goal": user.goal,
        "days_per_week": user.days_per_week,
        "minutes_per_session": user.minutes_per_session,
        "equipment": user.equipment,
    }


def slot_dict(slot: PlanSlot) -> dict:
    return {
        "id": slot.id,
        "slot_index": slot.slot_index,
        "exercise_id": slot.exercise_id,
        "exercise": exercise_dict(slot.exercise) if slot.exercise else None,
        "sets": slot.sets,
        "reps": slot.reps,
        "rest_sec": slot.rest_sec,
        "rpe_target": slot.rpe_target,
        "rationale": slot.rationale,
        "status": slot.status,
    }


def day_dict(day: PlanDay) -> dict:
    return {
        "id": day.id,
        "day_index": day.day_index,
        "focus": day.focus,
        "slots": [slot_dict(slot) for slot in day.slots],
    }


def plan_dict(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "week_index": plan.week_index,
        "version": plan.version,
        "split": plan.split,
        "status": plan.status,
        "params": plan.params,
        "days": [day_dict(day) for day in plan.days],
    }
