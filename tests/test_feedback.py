from app.core.models import PlanSlot
from app.modules.feedback.service import FeedbackService, adaptation_policy, slot_reward


def test_completed_reward_prefers_target_rpe() -> None:
    assert slot_reward(8, 8, completed=True) == 1.0
    assert slot_reward(10, 8, completed=True) == 0.88


def test_skipped_reward_is_zero() -> None:
    assert slot_reward(8, 8, completed=False) == 0.0


def test_adaptation_policy_scales_low_adherence() -> None:
    policy = adaptation_policy(adherence=0.5, mean_rpe=7, days_per_week=4)
    assert policy["days_override"] == 3
    assert "scaled" in policy["mode_note"]


def test_adaptation_policy_progresses_easy_high_adherence() -> None:
    policy = adaptation_policy(adherence=0.95, mean_rpe=5, days_per_week=4)
    assert policy["allow_progression"] is True


def test_adaptation_policy_deloads_high_rpe() -> None:
    policy = adaptation_policy(adherence=0.8, mean_rpe=9, days_per_week=4)
    assert policy["deload"] is True


def test_adherence_uses_completed_over_countable_non_deferred_slots() -> None:
    slots = [
        PlanSlot(id=1, plan_day_id=1, slot_index=1, exercise_id="a", status="completed", sets=3, reps="8-12", rest_sec=90, rpe_target=8, rationale=""),
        PlanSlot(id=2, plan_day_id=1, slot_index=2, exercise_id="b", status="planned", sets=3, reps="8-12", rest_sec=90, rpe_target=8, rationale=""),
        PlanSlot(id=3, plan_day_id=1, slot_index=3, exercise_id="c", status="skipped", sets=3, reps="8-12", rest_sec=90, rpe_target=8, rationale=""),
        PlanSlot(id=4, plan_day_id=1, slot_index=4, exercise_id="d", status="deferred", sets=3, reps="8-12", rest_sec=90, rpe_target=8, rationale=""),
    ]

    adherence, completed_count, countable_count = FeedbackService().adherence(slots)

    assert adherence == 1 / 3
    assert completed_count == 1
    assert countable_count == 3
