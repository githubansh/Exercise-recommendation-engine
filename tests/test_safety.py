from pathlib import Path

from app.modules.safety.service import severity_blocks
from seeds.curation import tag_movement_patterns


def test_severity_thresholds_are_monotonic() -> None:
    assert severity_blocks("severe", "mild")
    assert severity_blocks("severe", "moderate")
    assert severity_blocks("moderate", "mild")
    assert not severity_blocks("mild", "moderate")
    assert not severity_blocks("moderate", "severe")


def test_lower_back_profile_blocks_required_patterns() -> None:
    text = Path("seeds/injury_profiles.yaml").read_text(encoding="utf-8")
    lower_back_section = text.split("lower_back_pain:", 1)[1].split("\nshoulder_impingement:", 1)[0]
    assert "pattern: spinal_loading" in lower_back_section
    assert "min_severity: mild" in lower_back_section
    assert "pattern: spinal_flexion" in lower_back_section
    assert "min_severity: moderate" in lower_back_section
    assert "pattern: hip_hinge" in lower_back_section
    assert "min_severity: severe" in lower_back_section


def test_deadlift_is_tagged_for_lower_back_safety() -> None:
    exercise = {
        "id": "test_deadlift",
        "name": "Barbell Deadlift",
        "force": "pull",
        "level": "intermediate",
        "mechanic": "compound",
        "equipment": "barbell",
        "category": "strength",
        "primaryMuscles": ["hamstrings"],
        "secondaryMuscles": ["lower back", "glutes"],
        "instructions": ["Hinge at the hips and lift the barbell from the floor."],
    }
    tags = set(tag_movement_patterns(exercise))
    assert {"hip_hinge", "spinal_loading"} <= tags
