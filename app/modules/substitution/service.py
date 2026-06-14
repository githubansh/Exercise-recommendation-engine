from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Plan, PlanDay, PlanSlot, SwapEvent
from app.modules.catalog.service import catalog_service, cosine_vectors
from app.modules.catalog.utils import lexical_similarity, primary_group
from app.modules.safety.service import safety_service
from app.modules.scoring.service import scoring_service

WARMUP_MINUTES = 8.0
COMPOUND_MINUTES_PER_SET = 4.0
ISOLATION_MINUTES_PER_SET = 3.0


class SubstitutionService:
    def alternatives(self, db: Session, slot_id: int, *, k: int = 5) -> list[dict]:
        slot = db.get(PlanSlot, slot_id)
        if slot is None:
            raise ValueError(f"Slot {slot_id} does not exist")
        day = db.get(PlanDay, slot.plan_day_id)
        plan = db.get(Plan, day.plan_id)
        user = plan_user(db, plan)
        current = catalog_service.get_exercise(db, slot.exercise_id)
        equipment = set(user.equipment or []) | {"body only"}
        filters = {"equipment": equipment, "max_level": user.level}
        candidates = catalog_service.similar_exercises(db, slot.exercise_id, k=30, filters=filters)
        plan_exercise_ids = set(
            db.scalars(
                select(PlanSlot.exercise_id)
                .join(PlanDay, PlanDay.id == PlanSlot.plan_day_id)
                .where(PlanDay.plan_id == plan.id)
            ).all()
        )
        same_day_exercises = [
            other.exercise
            for other in day.slots
            if other.id != slot.id and other.exercise is not None
        ]
        vector_ids = {slot.exercise_id, *[exercise.id for exercise in candidates], *[exercise.id for exercise in same_day_exercises]}
        vectors = catalog_service.embedding_vectors(db, vector_ids)
        prefs, total_pulls = scoring_service.preference_snapshot(db, user.id)
        results = []
        for exercise in candidates:
            if exercise.id in plan_exercise_ids:
                continue
            if not safety_service.is_safe(db, user.id, exercise.id):
                continue
            if any(exercise_similarity(exercise, other, vectors) >= 0.92 for other in same_day_exercises):
                continue
            similarity = exercise_similarity(current, exercise, vectors) if current else 0
            utility = scoring_service.utility_from_snapshot(user, exercise, prefs, total_pulls)
            results.append(
                {
                    "exercise": exercise,
                    "score": round(0.6 * similarity + 0.4 * utility, 6),
                    "similarity": round(similarity, 6),
                    "utility": utility,
                    "primary_group": primary_group(exercise),
                }
            )
        return sorted(results, key=lambda item: (-item["score"], item["exercise"].id))[:k]

    def swap(self, db: Session, slot_id: int, new_exercise_id: str) -> PlanSlot:
        slot = db.get(PlanSlot, slot_id)
        if slot is None:
            raise ValueError(f"Slot {slot_id} does not exist")
        day = db.get(PlanDay, slot.plan_day_id)
        plan = db.get(Plan, day.plan_id)
        user = plan_user(db, plan)

        new_exercise = catalog_service.get_exercise(db, new_exercise_id)
        if new_exercise is None:
            raise ValueError(f"Exercise {new_exercise_id} does not exist.")
        if not safety_service.is_safe(db, user.id, new_exercise_id):
            raise ValueError(f"Exercise {new_exercise_id} is blocked by your safety rules.")
        allowed_equipment = set(user.equipment or []) | {"body only"}
        if new_exercise.equipment not in allowed_equipment:
            raise ValueError(f"Exercise {new_exercise_id} requires {new_exercise.equipment} which you do not have.")
        in_plan = db.scalar(
            select(PlanSlot.id)
            .join(PlanDay, PlanDay.id == PlanSlot.plan_day_id)
            .where(
                PlanDay.plan_id == plan.id,
                PlanSlot.exercise_id == new_exercise_id,
                PlanSlot.id != slot.id,
            )
        )
        if in_plan:
            raise ValueError(f"Exercise {new_exercise_id} is already in this plan.")

        old_exercise_id = slot.exercise_id
        slot.exercise_id = new_exercise_id
        slot.status = "swapped"
        budget_note = ""
        projected_minutes = day_minutes(
            day,
            override={slot.id: (slot.sets, new_exercise.mechanic)},
        )
        if projected_minutes > user.minutes_per_session and slot.sets > 1:
            slot.sets -= 1
            budget_note = f", reduced to {slot.sets} sets to fit your {user.minutes_per_session}-minute session"
        group = primary_group(new_exercise) or (new_exercise.muscle_groups[0] if new_exercise.muscle_groups else "general")
        slot.rationale = (
            f"{new_exercise.name}: targets {group}, {new_exercise.level} level matches you, "
            f"{new_exercise.equipment} available, swapped from {old_exercise_id}{budget_note}"
        )
        db.add(
            SwapEvent(
                plan_slot_id=slot.id,
                from_exercise=old_exercise_id,
                to_exercise=new_exercise_id,
                reason="user swap",
            )
        )
        scoring_service.update_preference(db, user.id, old_exercise_id, 0.2)
        db.commit()
        db.refresh(slot)
        return slot


def plan_user(db: Session, plan: Plan):
    from app.core.models import User

    user = db.get(User, plan.user_id)
    if user is None:
        raise ValueError(f"Plan {plan.id} has no user")
    return user


def exercise_similarity(current, candidate, vectors: dict[str, list[float]]) -> float:
    if current is None or candidate is None:
        return 0.0
    semantic = cosine_vectors(vectors.get(current.id), vectors.get(candidate.id))
    if semantic is not None:
        return semantic
    return lexical_similarity(current, candidate)


def slot_minutes(sets: int, mechanic: str | None) -> float:
    return sets * (COMPOUND_MINUTES_PER_SET if mechanic == "compound" else ISOLATION_MINUTES_PER_SET)


def day_minutes(day: PlanDay, override: dict[int, tuple[int, str | None]] | None = None) -> float:
    override = override or {}
    total = WARMUP_MINUTES
    for slot in day.slots:
        sets, mechanic = override.get(slot.id, (slot.sets, slot.exercise.mechanic if slot.exercise else None))
        total += slot_minutes(sets, mechanic)
    return total


substitution_service = SubstitutionService()
