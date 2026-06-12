from seeds.curation import apply_data_corrections, curated_exercise, tag_movement_patterns


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


def test_data_corrections_cover_hanging_and_decline_bench_gaps() -> None:
    raw = [
        {
            "id": "Wind_Sprints",
            "name": "Wind Sprints",
            "force": None,
            "level": "beginner",
            "mechanic": None,
            "equipment": "body only",
            "primaryMuscles": ["abdominals"],
            "secondaryMuscles": [],
            "instructions": ["Hang from a pull-up bar."],
            "category": "strength",
            "images": [],
        },
        {
            "id": "Decline_Crunch",
            "name": "Decline Crunch",
            "force": None,
            "level": "beginner",
            "mechanic": "isolation",
            "equipment": "body only",
            "primaryMuscles": ["abdominals"],
            "secondaryMuscles": [],
            "instructions": ["Lie on a decline bench."],
            "category": "strength",
            "images": [],
        },
    ]

    corrected = apply_data_corrections(
        raw,
        {"equipment_overrides": {"Wind_Sprints": "pull-up bar", "Decline_Crunch": "other"}},
    )

    assert curated_exercise(corrected[0])["equipment"] == "pull-up bar"
    assert curated_exercise(corrected[1])["equipment"] == "other"


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


def test_calf_raises_are_not_deep_knee_flexion() -> None:
    exercise = {
        "id": "Standing_Calf_Raise",
        "name": "Standing Calf Raise",
        "force": "push",
        "level": "beginner",
        "mechanic": "isolation",
        "equipment": "machine",
        "primaryMuscles": ["calves"],
        "secondaryMuscles": [],
        "instructions": ["Set a barbell on a squat rack and raise your heels under control."],
        "category": "strength",
    }

    assert "deep_knee_flexion" not in tag_movement_patterns(exercise)


def test_walking_lunge_is_not_tagged_as_carry() -> None:
    exercise = {
        "id": "Bodyweight_Walking_Lunge",
        "name": "Bodyweight Walking Lunge",
        "force": "push",
        "level": "beginner",
        "mechanic": "compound",
        "equipment": "body only",
        "primaryMuscles": ["quadriceps"],
        "secondaryMuscles": ["glutes"],
        "instructions": ["Step forward into a lunge and alternate legs."],
        "category": "strength",
    }

    tags = set(tag_movement_patterns(exercise))
    assert "lunge_pattern" in tags
    assert "carry" not in tags
