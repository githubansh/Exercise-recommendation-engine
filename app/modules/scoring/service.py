from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import Exercise, PreferenceScore, User
from app.modules.catalog.constants import LEVEL_ORDER


class ScoringService:
    def utility(self, db: Session, user: User, exercise: Exercise, *, allow_one_above: bool = False) -> float:
        goal = self.goal_fit(user.goal, exercise)
        level = self.level_fit(user.level, exercise.level, allow_one_above=allow_one_above)
        equipment = self.equipment_pref(user, exercise)
        preference = self.preference(db, user.id, exercise.id)
        exploration = self.exploration_bonus(db, user.id, exercise.id)
        return round(
            0.30 * goal
            + 0.15 * level
            + 0.10 * equipment
            + 0.35 * preference
            + 0.10 * exploration,
            6,
        )

    def goal_fit(self, goal: str, exercise: Exercise) -> float:
        category = exercise.category
        mechanic = exercise.mechanic
        equipment = exercise.equipment
        force = exercise.force
        heavy_barbell = equipment == "barbell" and mechanic == "compound"
        bodyweight_compound = equipment == "body only" and mechanic == "compound"

        if goal == "strength":
            if mechanic == "compound" and category in {"powerlifting", "strength", "olympic weightlifting"}:
                return 1.0
            if category == "strength":
                return 0.6
            return 0.2
        if goal == "hypertrophy":
            if category == "strength":
                return 1.0 if mechanic == "compound" else 0.9
            if category == "plyometrics":
                return 0.6
            return 0.2
        if goal == "fat_loss":
            if category in {"plyometrics", "cardio"}:
                return 1.0
            if category == "strength" and mechanic == "compound":
                return 1.0
            if category == "strength":
                return 0.6
            return 0.2
        if goal == "endurance":
            if category in {"cardio", "plyometrics"} or bodyweight_compound:
                return 1.0
            if category == "strength" and not heavy_barbell:
                return 0.6
            return 0.2
        if goal == "mobility":
            if category == "stretching":
                return 1.0
            if equipment == "body only" and category == "strength":
                return 0.6
            if heavy_barbell or force in {"push", "pull"}:
                return 0.2
        return 0.5

    def level_fit(self, user_level: str, exercise_level: str, *, allow_one_above: bool = False) -> float:
        delta = LEVEL_ORDER[exercise_level] - LEVEL_ORDER[user_level]
        if delta == 0:
            return 1.0
        if delta == -1:
            return 0.7
        if delta == 1 and allow_one_above and LEVEL_ORDER[user_level] >= LEVEL_ORDER["intermediate"]:
            return 0.3
        return 0.0

    def equipment_pref(self, user: User, exercise: Exercise) -> float:
        available = set(user.equipment or []) | {"body only"}
        return 1.0 if exercise.equipment in available else 0.0

    def preference(self, db: Session, user_id: int, exercise_id: str) -> float:
        score = db.get(PreferenceScore, {"user_id": user_id, "exercise_id": exercise_id})
        return float(score.score) if score else 0.5

    def exploration_bonus(self, db: Session, user_id: int, exercise_id: str) -> float:
        total_pulls = db.scalar(
            select(func.coalesce(func.sum(PreferenceScore.pulls), 0)).where(PreferenceScore.user_id == user_id)
        )
        score = db.get(PreferenceScore, {"user_id": user_id, "exercise_id": exercise_id})
        pulls = score.pulls if score else 0
        if total_pulls is None or total_pulls <= 0:
            return 1.0
        return min(1.0, math.sqrt(math.log(total_pulls + 1) / (pulls + 1)))

    def update_preference(self, db: Session, user_id: int, exercise_id: str, reward: float, *, alpha: float = 0.3) -> PreferenceScore:
        reward = max(0.0, min(1.0, reward))
        score = db.get(PreferenceScore, {"user_id": user_id, "exercise_id": exercise_id})
        if score is None:
            score = PreferenceScore(user_id=user_id, exercise_id=exercise_id, score=0.5, pulls=0)
            db.add(score)
            db.flush()
        score.score = score.score + alpha * (reward - score.score)
        score.pulls += 1
        return score


scoring_service = ScoringService()
