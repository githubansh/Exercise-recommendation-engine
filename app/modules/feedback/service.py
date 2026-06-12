from __future__ import annotations

from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Plan, PlanDay, PlanSlot, SessionLog, SlotFeedback
from app.modules.planner.service import planner_service
from app.modules.scoring.service import scoring_service
from app.modules.substitution.service import plan_user


def slot_reward(rpe: int, rpe_target: int, *, completed: bool) -> float:
    if not completed:
        return 0.0
    return max(0.4, 1.0 - 0.06 * abs(rpe - rpe_target))


def adaptation_policy(adherence: float, mean_rpe: float, days_per_week: int) -> dict:
    if adherence < 0.6:
        return {
            "days_override": max(2, days_per_week - 1),
            "mode_note": "scaled to fit your week due to low adherence",
            "allow_progression": False,
            "deload": False,
        }
    if mean_rpe <= 5 and adherence >= 0.9:
        return {
            "days_override": None,
            "mode_note": "progressed because adherence was high and RPE was low",
            "allow_progression": True,
            "deload": False,
        }
    if mean_rpe >= 9:
        return {
            "days_override": None,
            "mode_note": "deloaded because average RPE was very high",
            "allow_progression": False,
            "deload": True,
        }
    return {"days_override": None, "mode_note": None, "allow_progression": False, "deload": False}


class FeedbackService:
    def log_session(
        self,
        db: Session,
        *,
        plan_day_id: int,
        rpe: int,
        completed_slot_ids: list[int],
        skipped_slot_ids: list[int],
        duration_min: int | None = None,
        notes: str | None = None,
    ) -> SessionLog:
        day = db.get(PlanDay, plan_day_id)
        if day is None:
            raise ValueError(f"Plan day {plan_day_id} does not exist")
        existing = db.scalar(select(SessionLog).where(SessionLog.plan_day_id == plan_day_id))
        if existing:
            raise ValueError(f"Day {plan_day_id} already has a logged session (id={existing.id}).")
        plan = db.get(Plan, day.plan_id)
        user = plan_user(db, plan)
        planned_ids = {slot.id for slot in day.slots}
        submitted_ids = set(completed_slot_ids) | set(skipped_slot_ids)
        unknown_ids = sorted(submitted_ids - planned_ids)
        if unknown_ids:
            raise ValueError(f"Slots {unknown_ids} do not belong to day {plan_day_id}")
        log = SessionLog(plan_day_id=plan_day_id, rpe=rpe, duration_min=duration_min, notes=notes)
        db.add(log)
        db.flush()
        for slot_id in completed_slot_ids:
            slot = db.get(PlanSlot, slot_id)
            reward = slot_reward(rpe, slot.rpe_target, completed=True)
            self.record_slot_feedback(db, log.id, user.id, slot, "completed", reward)
        for slot_id in skipped_slot_ids:
            slot = db.get(PlanSlot, slot_id)
            self.record_slot_feedback(db, log.id, user.id, slot, "skipped", 0.0)
        db.commit()
        db.refresh(log)
        return log

    def record_slot_feedback(
        self,
        db: Session,
        session_log_id: int,
        user_id: int,
        slot: PlanSlot,
        status: str,
        reward: float,
    ) -> None:
        slot.status = status
        db.add(SlotFeedback(session_log_id=session_log_id, plan_slot_id=slot.id, status=status, reward=reward))
        scoring_service.update_preference(db, user_id, slot.exercise_id, reward)

    def adapt_week(self, db: Session, plan_id: int) -> Plan:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} does not exist")
        if plan.status != "active":
            raise ValueError(f"Plan {plan_id} is {plan.status}; only the active plan can be adapted.")
        user = plan_user(db, plan)
        planned_slots = list(
            db.scalars(
                select(PlanSlot)
                .join(PlanDay, PlanDay.id == PlanSlot.plan_day_id)
                .where(PlanDay.plan_id == plan.id)
            ).all()
        )
        countable = [slot for slot in planned_slots if slot.status != "deferred"]
        completed = [slot for slot in countable if slot.status == "completed"]
        adherence = len(completed) / max(len(countable), 1)
        rpes = list(db.scalars(select(SessionLog.rpe).join(PlanDay, PlanDay.id == SessionLog.plan_day_id).where(PlanDay.plan_id == plan.id)).all())
        mean_rpe = mean([rpe for rpe in rpes if rpe is not None]) if rpes else 7
        policy = adaptation_policy(adherence, mean_rpe, user.days_per_week)
        return planner_service.generate_plan(
            db,
            user.id,
            week_index=plan.week_index + 1,
            days_override=policy["days_override"],
            mode_note=policy["mode_note"],
            allow_progression=policy["allow_progression"],
            deload=policy["deload"],
        )


feedback_service = FeedbackService()
