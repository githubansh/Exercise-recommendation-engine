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

PRIMARY_VOLUME_GROUPS = ["chest", "back", "shoulders", "quads", "posterior_chain"]
HALF_VOLUME_GROUPS = ["biceps", "triceps", "abs", "calves"]

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

GOALS = ["strength", "hypertrophy", "fat_loss", "endurance", "mobility"]

EQUIPMENT_VALUES = {
    "body only",
    "dumbbell",
    "barbell",
    "cable",
    "machine",
    "kettlebells",
    "bands",
    "medicine ball",
    "exercise ball",
    "foam roll",
    "e-z curl bar",
    "pull-up bar",
    "other",
}

PRESCRIPTIONS = {
    "strength": {"sets": 4, "reps": "4-6", "rest_sec": 180, "rpe_target": 8},
    "hypertrophy": {"sets": 3, "reps": "8-12", "rest_sec": 90, "rpe_target": 8},
    "fat_loss": {"sets": 3, "reps": "10-15", "rest_sec": 60, "rpe_target": 7},
    "endurance": {"sets": 3, "reps": "15-20", "rest_sec": 45, "rpe_target": 6},
    "mobility": {"sets": 2, "reps": "30-45s holds", "rest_sec": 30, "rpe_target": 4},
}

STRETCH_PRESCRIPTION = {"sets": 2, "reps": "30s", "rest_sec": 30, "rpe_target": 4}

VOLUME_TARGETS = {
    "beginner": {
        "strength": (6, 10),
        "hypertrophy": (8, 12),
        "fat_loss": (8, 12),
        "endurance": (8, 12),
    },
    "intermediate": {
        "strength": (8, 14),
        "hypertrophy": (10, 16),
        "fat_loss": (10, 14),
        "endurance": (10, 14),
    },
    "expert": {
        "strength": (10, 16),
        "hypertrophy": (12, 20),
        "fat_loss": (12, 16),
        "endurance": (12, 16),
    },
}

FOCUS_GROUPS = {
    "full": set(TRAINABLE_GROUPS),
    "upper": {"chest", "back", "shoulders", "biceps", "triceps", "abs"},
    "lower": {"quads", "posterior_chain", "calves", "lower_back", "abs"},
    "push": {"chest", "shoulders", "triceps"},
    "pull": {"back", "biceps", "lower_back"},
    "legs": {"quads", "posterior_chain", "calves", "abs"},
}

SIBLING_GROUP = {
    "calves": "quads",
    "biceps": "back",
    "triceps": "chest",
    "lower_back": "posterior_chain",
}
