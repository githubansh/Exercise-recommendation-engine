from types import SimpleNamespace

from app.modules.planner.service import Candidate, PlannerService


def test_split_selection() -> None:
    planner = PlannerService()
    assert planner.split_for_days(2) == ("full_body", ["full", "full"])
    assert planner.split_for_days(4) == ("upper_lower", ["upper", "lower", "upper", "lower"])
    assert planner.split_for_days(5) == ("ppl", ["push", "pull", "legs", "push", "pull"])


def test_bodyweight_gap_creates_feasibility_note() -> None:
    planner = PlannerService()
    targets = {"biceps": (4, 6), "back": (6, 10)}
    exercise = SimpleNamespace(
        id="pushup",
        name="Push-Up",
        level="beginner",
        mechanic="compound",
        equipment="body only",
        category="strength",
        primary_muscles=["chest"],
        secondary_muscles=["triceps"],
        muscle_groups=["chest", "triceps"],
        instructions=["Do a push-up."],
    )
    adjusted, aliases, notes = planner.apply_feasibility_ladder(targets, [Candidate(exercise=exercise, score=1.0)])
    assert adjusted["biceps"] == (0, 0)
    assert aliases["biceps"] == "back"
    assert any("No direct biceps options" in note for note in notes)


def test_slots_for_worst_case_still_allows_a_session() -> None:
    planner = PlannerService()
    assert planner.slots_for_session(minutes=30, sets=3) >= 2


def test_conditioning_blocks_for_cardio_skew_goals() -> None:
    planner = PlannerService()
    assert planner.conditioning_blocks("fat_loss", 45)[0]["type"] == "intervals"
    assert planner.conditioning_blocks("endurance", 45)[0]["type"] == "liss"
