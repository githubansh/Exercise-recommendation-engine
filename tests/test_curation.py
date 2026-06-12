from seeds.curation import apply_data_corrections, curated_exercise


def test_data_corrections_override_equipment_and_force() -> None:
    raw = [
        {
            "id": "Chin-Up",
            "name": "Chin-Up",
            "force": None,
            "level": "beginner",
            "mechanic": "compound",
            "equipment": "body only",
            "primaryMuscles": ["lats"],
            "secondaryMuscles": ["biceps"],
            "instructions": ["Pull up."],
            "category": "strength",
            "images": [],
        }
    ]
    corrected = apply_data_corrections(
        raw,
        {"equipment_overrides": {"Chin-Up": "pull-up bar"}, "force_overrides": {"Chin-Up": "pull"}},
    )
    exercise = curated_exercise(corrected[0])
    assert exercise["equipment"] == "pull-up bar"
    assert exercise["force"] == "pull"


def test_instruction_backfill_is_flagged() -> None:
    raw = [
        {
            "id": "Side_Bridge",
            "name": "Side Bridge",
            "force": None,
            "level": "beginner",
            "mechanic": "compound",
            "equipment": "body only",
            "primaryMuscles": ["abdominals"],
            "secondaryMuscles": [],
            "instructions": [],
            "category": "strength",
            "images": [],
        }
    ]
    corrected = apply_data_corrections(
        raw,
        {"instruction_backfills": {"Side_Bridge": ["Hold a side bridge."]}},
    )
    exercise = curated_exercise(corrected[0])
    assert exercise["instructions"] == ["Hold a side bridge."]
    assert exercise["instructions_generated"] is True
