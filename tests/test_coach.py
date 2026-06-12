from app.modules.coach.service import CoachService


def test_coach_routes_explain_slot() -> None:
    call = CoachService().deterministic_tool_call("please explain slot 42")
    assert call == {"name": "explain_slot", "arguments": {"slot_id": 42}}


def test_explain_beats_generic_plan_view() -> None:
    call = CoachService().deterministic_tool_call("explain slot 3 of my plan")
    assert call == {"name": "explain_slot", "arguments": {"slot_id": 3}}


def test_coach_routes_swap_with_valid_id_shape() -> None:
    call = CoachService().deterministic_tool_call("swap slot 20 to Push-Ups_With_Feet_Elevated")
    assert call == {
        "name": "swap_exercise",
        "arguments": {"slot_id": 20, "exercise_id": "Push-Ups_With_Feet_Elevated"},
    }


def test_swap_message_with_word_plan_routes_to_swap_path() -> None:
    call = CoachService().deterministic_tool_call("swap slot 5 in my plan")
    assert call["name"] == "get_alternatives"
    assert call["arguments"] == {"slot_id": 5}


def test_coach_routes_feedback() -> None:
    call = CoachService().deterministic_tool_call("log day 13 rpe 7 completed 19,20 skipped 21")
    assert call["name"] == "log_feedback"
    assert call["arguments"]["plan_day_id"] == 13
    assert call["arguments"]["rpe"] == 7
    assert call["arguments"]["completed"] == [19, 20]
    assert call["arguments"]["skipped"] == [21]
