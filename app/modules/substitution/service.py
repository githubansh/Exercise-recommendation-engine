from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Plan, PlanDay, PlanSlot, SwapEvent
from app.modules.catalog.service import catalog_service
from app.modules.catalog.utils import lexical_similarity, primary_group
from app.modules.safety.service import safety_service
from app.modules.scoring.service import scoring_service


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
        results = []
        for exercise in candidates:
            if exercise.id in plan_exercise_ids:
                continue
            if not safety_service.is_safe(db, user.id, exercise.id):
                continue
            if any(lexical_similarity(exercise, other) >= 0.95 for other in same_day_exercises):
                continue
            similarity = lexical_similarity(current, exercise) if current else 0
            utility = scoring_service.utility(db, user, exercise)
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
        valid_ids = {item["exercise"].id for item in self.alternatives(db, slot_id, k=20)}
        if new_exercise_id not in valid_ids:
            raise ValueError("New exercise must come from the safe alternatives list.")
        old_exercise_id = slot.exercise_id
        slot.exercise_id = new_exercise_id
        slot.status = "swapped"
        new_exercise = catalog_service.get_exercise(db, new_exercise_id)
        if slot.sets > 1 and new_exercise and new_exercise.mechanic == "compound":
            slot.sets -= 1
        if new_exercise:
            group = primary_group(new_exercise) or (new_exercise.muscle_groups[0] if new_exercise.muscle_groups else "general")
            slot.rationale = (
                f"{new_exercise.name}: targets {group}, {new_exercise.level} level matches you, "
                f"{new_exercise.equipment} available, swapped from {old_exercise_id}"
            )
        db.add(
            SwapEvent(
                plan_slot_id=slot.id,
                from_exercise=old_exercise_id,
                to_exercise=new_exercise_id,
                reason="user swap",
            )
        )
        day = db.get(PlanDay, slot.plan_day_id)
        plan = db.get(Plan, day.plan_id)
        user = plan_user(db, plan)
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


substitution_service = SubstitutionService()
