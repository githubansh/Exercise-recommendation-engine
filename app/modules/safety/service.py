from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Contraindication, ExercisePattern, UserExclusion, UserInjury
from app.modules.catalog.constants import SEVERITY_ORDER


def severity_blocks(user_severity: str, min_severity: str) -> bool:
    return SEVERITY_ORDER[user_severity] >= SEVERITY_ORDER[min_severity]


class SafetyService:
    def blocked_patterns(self, db: Session, user_id: int) -> set[str]:
        injuries = list(db.scalars(select(UserInjury).where(UserInjury.user_id == user_id)).all())
        if not injuries:
            return set()
        injury_by_code = {injury.injury_code: injury.severity for injury in injuries}
        contraindications = list(
            db.scalars(select(Contraindication).where(Contraindication.injury_code.in_(injury_by_code))).all()
        )
        return {
            item.pattern
            for item in contraindications
            if severity_blocks(injury_by_code[item.injury_code], item.min_severity)
        }

    def blocked_exercise_ids(self, db: Session, user_id: int) -> set[str]:
        blocked_patterns = self.blocked_patterns(db, user_id)
        ids: set[str] = set()
        if blocked_patterns:
            ids.update(
                db.scalars(select(ExercisePattern.exercise_id).where(ExercisePattern.pattern.in_(blocked_patterns))).all()
            )
        ids.update(db.scalars(select(UserExclusion.exercise_id).where(UserExclusion.user_id == user_id)).all())
        return ids

    def is_safe(self, db: Session, user_id: int, exercise_id: str) -> bool:
        return exercise_id not in self.blocked_exercise_ids(db, user_id)

    def block_reason(self, db: Session, user_id: int, exercise_id: str) -> str | None:
        exclusion = db.get(UserExclusion, {"user_id": user_id, "exercise_id": exercise_id})
        if exclusion:
            return exclusion.reason or "excluded by user"
        blocked_patterns = self.blocked_patterns(db, user_id)
        patterns = set(
            db.scalars(select(ExercisePattern.pattern).where(ExercisePattern.exercise_id == exercise_id)).all()
        )
        overlap = sorted(patterns & blocked_patterns)
        if overlap:
            return f"blocked movement pattern: {', '.join(overlap)}"
        return None


safety_service = SafetyService()
