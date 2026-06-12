from app.modules.feedback.service import adaptation_policy, slot_reward


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
