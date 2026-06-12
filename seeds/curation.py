from __future__ import annotations

from collections.abc import Iterable
from typing import Any

LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "expert": 2}
SEVERITY_ORDER = {"mild": 0, "moderate": 1, "severe": 2}

MUSCLE_GROUP_MAP = {
    "chest": "chest",
    "lats": "back",
    "middle back": "back",
    "traps": "back",
    "lower back": "lower_back",
    "shoulders": "shoulders",
    "neck": "shoulders",
    "biceps": "biceps",
    "triceps": "triceps",
    "forearms": "triceps",
    "quadriceps": "quads",
    "adductors": "quads",
    "hamstrings": "posterior_chain",
    "glutes": "posterior_chain",
    "abductors": "posterior_chain",
    "calves": "calves",
    "abdominals": "abs",
}

TRAINABLE_GROUPS = [
    "chest",
    "back",
    "lower_back",
    "shoulders",
    "biceps",
    "triceps",
    "quads",
    "posterior_chain",
    "calves",
    "abs",
]

MOVEMENT_PATTERNS = [
    "squat_pattern",
    "hip_hinge",
    "lunge_pattern",
    "horizontal_push",
    "vertical_push",
    "horizontal_pull",
    "vertical_pull",
    "spinal_flexion",
    "spinal_loading",
    "rotation",
    "deep_knee_flexion",
    "high_impact",
    "overhead_position",
    "wrist_loading",
    "carry",
]

PULLUP_BAR_HINTS = [
    "pull-up",
    "pullup",
    "chin-up",
    "chinup",
    "muscle up",
    "toes-to-bar",
    "hanging",
]


def normalize_equipment(exercise: dict[str, Any]) -> str:
    equipment = exercise.get("equipment") or "body only"
    name = exercise.get("name", "").lower()
    if any(hint in name for hint in PULLUP_BAR_HINTS) and equipment == "body only":
        return "pull-up bar"
    return equipment


def normalize_mechanic(exercise: dict[str, Any]) -> str:
    return exercise.get("mechanic") or "isolation"


def normalize_force(exercise: dict[str, Any]) -> str | None:
    force = exercise.get("force")
    if force:
        return force
    text = exercise_text(exercise)
    if any(word in text for word in ["hold", "stretch", "plank", "isometric"]):
        return "static"
    if any(word in text for word in ["row", "curl", "pull", "chin", "raise", "deadlift"]):
        return "pull"
    if any(word in text for word in ["press", "push", "squat", "lunge", "dip", "extension"]):
        return "push"
    return None


def cleaned_instructions(exercise: dict[str, Any]) -> tuple[list[str], bool]:
    instructions = [str(item).strip() for item in exercise.get("instructions", []) if str(item).strip()]
    if instructions:
        return instructions, False
    name = exercise.get("name", "this exercise")
    return [
        f"Set up for {name} with a controlled, pain-free range of motion.",
        "Move slowly, keep your breathing steady, and stop if you feel sharp pain.",
        "Use a light effort until a coach or reliable reference confirms your form.",
    ], True


def derive_muscle_groups(primary_muscles: Iterable[str], secondary_muscles: Iterable[str] = ()) -> list[str]:
    groups = {MUSCLE_GROUP_MAP[m] for m in list(primary_muscles) + list(secondary_muscles) if m in MUSCLE_GROUP_MAP}
    return sorted(groups)


def primary_group(exercise: dict[str, Any]) -> str | None:
    for muscle in exercise.get("primaryMuscles", []) or exercise.get("primary_muscles", []):
        if muscle in MUSCLE_GROUP_MAP:
            return MUSCLE_GROUP_MAP[muscle]
    groups = exercise.get("muscle_groups", [])
    return groups[0] if groups else None


def exercise_text(exercise: dict[str, Any]) -> str:
    parts = [
        exercise.get("name", ""),
        exercise.get("category", ""),
        exercise.get("force") or "",
        exercise.get("mechanic") or "",
        exercise.get("equipment") or "",
        " ".join(exercise.get("primaryMuscles", []) or exercise.get("primary_muscles", [])),
        " ".join(exercise.get("secondaryMuscles", []) or exercise.get("secondary_muscles", [])),
        " ".join(exercise.get("instructions", [])),
    ]
    return " ".join(parts).lower()


def tag_movement_patterns(exercise: dict[str, Any]) -> list[str]:
    text = exercise_text(exercise)
    name = exercise.get("name", "").lower()
    primary = set(exercise.get("primaryMuscles", []) or exercise.get("primary_muscles", []))
    secondary = set(exercise.get("secondaryMuscles", []) or exercise.get("secondary_muscles", []))
    equipment = normalize_equipment(exercise)
    category = exercise.get("category", "")
    force = normalize_force(exercise)
    tags: set[str] = set()

    if any(word in text for word in ["squat", "leg press", "wall sit"]):
        tags.update(["squat_pattern", "deep_knee_flexion"])
    if any(word in text for word in ["lunge", "split squat", "step-up", "step up", "pistol"]):
        tags.update(["lunge_pattern", "deep_knee_flexion"])
    if any(word in text for word in ["deadlift", "good morning", "hip hinge", "pull-through", "pull through", "hip thrust", "glute bridge", "swing"]):
        tags.add("hip_hinge")
    if any(word in text for word in ["clean", "snatch", "jerk"]):
        tags.update(["hip_hinge", "spinal_loading", "overhead_position"])
    if "calf raise" in text:
        tags.add("deep_knee_flexion")

    if category == "plyometrics" or any(word in text for word in ["jump", "bound", "burpee", "sprint", "running", "run ", "hop", "leap"]):
        tags.add("high_impact")

    if any(word in text for word in ["crunch", "sit-up", "sit up", "jackknife", "knee raise", "leg raise", "toe touch", "v-up", "v up"]):
        tags.add("spinal_flexion")
    if any(word in text for word in ["twist", "rotation", "rotational", "russian", "woodchop", "windmill", "side bend"]):
        tags.add("rotation")

    if any(word in text for word in ["overhead", "military press", "shoulder press", "arnold", "handstand", "jerk", "snatch"]):
        tags.add("overhead_position")
    if force == "push" and "shoulders" in primary:
        tags.update(["vertical_push", "overhead_position"])
    if force == "push" and ("chest" in primary or any(word in name for word in ["bench", "push-up", "pushup", "dip", "fly"])):
        tags.add("horizontal_push")
    if any(word in name for word in ["push-up", "pushup", "plank", "handstand", "burpee", "mountain climber", "bear crawl"]):
        tags.add("wrist_loading")

    if any(word in name for word in ["pull-up", "pullup", "chin-up", "chinup", "pulldown", "pull down"]):
        tags.add("vertical_pull")
    if "row" in name or "middle back" in primary or ("lats" in primary and "pulldown" not in name):
        tags.add("horizontal_pull")
    if force == "pull" and "biceps" in primary:
        tags.add("horizontal_pull")

    if any(word in text for word in ["carry", "farmer", "suitcase walk", "walking"]):
        tags.add("carry")
    if equipment in {"barbell", "kettlebells", "machine"} and (
        "squat_pattern" in tags
        or "hip_hinge" in tags
        or any(word in text for word in ["shoulder press", "overhead", "clean", "snatch", "good morning"])
    ):
        tags.add("spinal_loading")
    if "lower back" in primary or "lower back" in secondary:
        tags.add("spinal_loading")

    return sorted(tags)


def curated_exercise(raw: dict[str, Any]) -> dict[str, Any]:
    instructions, instructions_generated = cleaned_instructions(raw)
    instructions_generated = bool(raw.get("instructions_generated", instructions_generated))
    primary = raw.get("primaryMuscles", [])
    secondary = raw.get("secondaryMuscles", [])
    return {
        "id": raw["id"],
        "name": raw["name"],
        "level": raw["level"],
        "force": normalize_force(raw),
        "mechanic": normalize_mechanic(raw),
        "equipment": normalize_equipment(raw),
        "category": raw["category"],
        "primary_muscles": primary,
        "secondary_muscles": secondary,
        "instructions": instructions,
        "instructions_generated": instructions_generated,
        "images": raw.get("images", []),
        "muscle_groups": derive_muscle_groups(primary, secondary),
    }


def apply_data_corrections(raw_exercises: list[dict[str, Any]], corrections: dict[str, Any]) -> list[dict[str, Any]]:
    equipment_overrides = corrections.get("equipment_overrides", {})
    force_overrides = corrections.get("force_overrides", {})
    instruction_backfills = corrections.get("instruction_backfills", {})
    corrected = []
    for raw in raw_exercises:
        item = dict(raw)
        exercise_id = item["id"]
        if exercise_id in equipment_overrides:
            item["equipment"] = equipment_overrides[exercise_id]
        if exercise_id in force_overrides:
            item["force"] = force_overrides[exercise_id]
        if exercise_id in instruction_backfills and not item.get("instructions"):
            item["instructions"] = instruction_backfills[exercise_id]
            item["instructions_generated"] = True
        corrected.append(item)
    return corrected
