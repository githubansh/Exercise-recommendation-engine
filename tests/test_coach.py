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


def test_coach_routes_today_time_request_to_default_day() -> None:
    call = CoachService().deterministic_tool_call("I only have 20 minutes today", default_day_id=99)
    assert call == {"name": "replan_session", "arguments": {"plan_day_id": 99, "available_minutes": 20}}


def test_coach_head_injury_is_medical_red_flag() -> None:
    warning = CoachService().medical_red_flag("I have a head injury")
    assert warning is not None
    assert "consult a doctor" in warning


def test_coach_rpe_question_is_direct_answer() -> None:
    assert CoachService().is_rpe_question("what is rpe 7?")


def test_coach_rejects_generic_current_plan_tool_for_chitchat() -> None:
    assert CoachService().tool_matches_message("get_current_plan", "hello there") is False
    assert CoachService().tool_matches_message("get_current_plan", "show my plan") is True


def test_coach_fallback_chat_varies_by_intent() -> None:
    service = CoachService()

    hello = service.fallback_chat_response("hii")
    help_me = service.fallback_chat_response("i want help")

    assert hello != help_me
    assert "workout plan" in hello
    assert "time, pain, equipment" in help_me
