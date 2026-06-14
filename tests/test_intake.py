from app.modules.profile import service as profile_module
from app.modules.profile.service import ProfileService


def test_deterministic_intake_extracts_knee_and_lunges() -> None:
    parsed = ProfileService().deterministic_parse("my knee hurts when I squat deep and I hate lunges")
    assert [injury.code for injury in parsed.injuries] == ["knee_pain"]
    assert parsed.injuries[0].severity == "moderate"
    assert "lunges" in parsed.exclusions_by_name


def test_deterministic_intake_detects_severe_lower_back() -> None:
    parsed = ProfileService().deterministic_parse("sharp lower back pain after deadlifts")
    assert parsed.injuries[0].code == "lower_back_pain"
    assert parsed.injuries[0].severity == "severe"


def test_preferences_do_not_match_dislike() -> None:
    parsed = ProfileService().deterministic_parse("I dislike mountain climbers but prefer dumbbells")
    assert parsed.preferences_text == "dumbbells"


def test_supported_injury_uses_deterministic_fallback_when_llm_fails(monkeypatch) -> None:
    class FailingLLM:
        def structured_json(self, *_args, **_kwargs):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(profile_module, "get_llm_client", lambda: FailingLLM())
    monkeypatch.setattr(profile_module.settings, "gemini_api_key", "configured")

    parsed, source = ProfileService().parse_with_llm_or_fallback("I have a knee injury", {"knee_pain"})

    assert source == "deterministic_fallback"
    assert [injury.code for injury in parsed.injuries] == ["knee_pain"]


def test_head_injury_returns_medical_red_flag_response() -> None:
    service = ProfileService()
    warning = service.medical_red_flag_warning("I have a head injury")

    response = service.medical_red_flag_response(warning)

    assert response["source"] == "medical_red_flag"
    assert response["requires_structured_form"] is True
    assert "consult a doctor" in response["medical_warning"]
