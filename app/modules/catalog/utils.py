from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Protocol

from app.modules.catalog.constants import LEVEL_ORDER, MUSCLE_GROUP_MAP


class ExerciseLike(Protocol):
    id: str
    name: str
    level: str
    mechanic: str
    equipment: str
    category: str
    primary_muscles: list[str]
    secondary_muscles: list[str]
    muscle_groups: list[str]
    instructions: list[str]


def level_allowed(exercise_level: str, user_level: str, allow_one_above: bool = False) -> bool:
    exercise_rank = LEVEL_ORDER[exercise_level]
    user_rank = LEVEL_ORDER[user_level]
    if exercise_rank <= user_rank:
        return True
    return allow_one_above and exercise_rank == user_rank + 1 and user_rank >= LEVEL_ORDER["intermediate"]


def primary_group(exercise: ExerciseLike) -> str | None:
    for muscle in exercise.primary_muscles:
        group = MUSCLE_GROUP_MAP.get(muscle)
        if group:
            return group
    return exercise.muscle_groups[0] if exercise.muscle_groups else None


def mapped_groups(muscles: Iterable[str]) -> set[str]:
    return {MUSCLE_GROUP_MAP[muscle] for muscle in muscles if muscle in MUSCLE_GROUP_MAP}


def text_for_similarity(exercise: ExerciseLike) -> str:
    return " ".join(
        [
            exercise.name,
            exercise.level,
            exercise.mechanic,
            exercise.equipment,
            exercise.category,
            " ".join(exercise.primary_muscles),
            " ".join(exercise.secondary_muscles),
            " ".join(exercise.instructions[:2]),
        ]
    ).lower()


def lexical_similarity(left: ExerciseLike, right: ExerciseLike) -> float:
    return SequenceMatcher(a=text_for_similarity(left), b=text_for_similarity(right)).ratio()


def query_similarity(query: str, exercise: ExerciseLike) -> float:
    text = text_for_similarity(exercise)
    query = query.lower().strip()
    if not query:
        return 0
    ratio = SequenceMatcher(a=query, b=text).ratio()
    token_hits = sum(1 for token in query.split() if token in text)
    return min(1.0, ratio + (token_hits / max(len(query.split()), 1)) * 0.6)
