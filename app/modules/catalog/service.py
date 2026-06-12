from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.models import Exercise, ExerciseEmbedding
from app.modules.catalog.constants import LEVEL_ORDER
from app.modules.catalog.utils import level_allowed, query_similarity


class CatalogService:
    def get_exercise(self, db: Session, exercise_id: str) -> Exercise | None:
        return db.get(Exercise, exercise_id)

    def list_by_filters(
        self,
        db: Session,
        *,
        max_level: str | None = None,
        equipment: set[str] | None = None,
        category: str | None = None,
        categories: set[str] | None = None,
        muscle_group: str | None = None,
        allow_one_above: bool = False,
    ) -> list[Exercise]:
        stmt: Select[tuple[Exercise]] = select(Exercise)
        if equipment is not None:
            stmt = stmt.where(Exercise.equipment.in_(sorted(equipment)))
        if category is not None:
            stmt = stmt.where(Exercise.category == category)
        if categories is not None:
            stmt = stmt.where(Exercise.category.in_(sorted(categories)))
        if muscle_group is not None:
            stmt = stmt.where(Exercise.muscle_groups.any(muscle_group))

        rows = list(db.scalars(stmt).all())
        if max_level is None:
            return rows
        return [exercise for exercise in rows if level_allowed(exercise.level, max_level, allow_one_above)]

    def semantic_search(
        self,
        db: Session,
        query_text: str,
        *,
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[Exercise]:
        filters = filters or {}
        candidates = self.list_by_filters(
            db,
            max_level=filters.get("max_level"),
            equipment=set(filters["equipment"]) if filters.get("equipment") else None,
            category=filters.get("category"),
            categories=set(filters["categories"]) if filters.get("categories") else None,
            muscle_group=filters.get("muscle_group"),
            allow_one_above=filters.get("allow_one_above", False),
        )
        vector_results = self._vector_search(db, query_text, candidates, k)
        if vector_results is not None:
            return vector_results
        return sorted(candidates, key=lambda item: query_similarity(query_text, item), reverse=True)[:k]

    def similar_exercises(
        self,
        db: Session,
        exercise_id: str,
        *,
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[Exercise]:
        base = self.get_exercise(db, exercise_id)
        if base is None:
            return []
        query_text = f"{base.name}. {' '.join(base.primary_muscles)}. {' '.join(base.instructions[:2])}"
        return [item for item in self.semantic_search(db, query_text, k=k + 1, filters=filters) if item.id != exercise_id][:k]

    def _vector_search(
        self,
        db: Session,
        query_text: str,
        candidates: list[Exercise],
        k: int,
    ) -> list[Exercise] | None:
        if not candidates:
            return []
        try:
            query_vector = embed_text(query_text)
            distance_expr = ExerciseEmbedding.embedding.cosine_distance(query_vector).label("distance")
            candidate_limit = min(len(candidates), max(k * 5, 100))
            stmt = (
                select(Exercise, distance_expr)
                .join(ExerciseEmbedding, ExerciseEmbedding.exercise_id == Exercise.id)
                .where(Exercise.id.in_([item.id for item in candidates]))
                .order_by(distance_expr)
                .limit(candidate_limit)
            )
            rows = list(db.execute(stmt).all())
            scored = [
                (
                    (0.70 * (1.0 - float(distance)))
                    + (0.30 * query_similarity(query_text, exercise))
                    + exact_name_boost(query_text, exercise.name),
                    exercise,
                )
                for exercise, distance in rows
            ]
            return [exercise for _score, exercise in sorted(scored, key=lambda item: (-item[0], item[1].id))[:k]]
        except Exception:
            return None


@lru_cache(maxsize=1)
def _embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name)


def embed_text(text: str) -> list[float]:
    vector = _embedding_model().encode([text], normalize_embeddings=True)[0]
    return vector.tolist()


catalog_service = CatalogService()


def exact_name_boost(query_text: str, exercise_name: str) -> float:
    query = "".join(ch for ch in query_text.lower() if ch.isalnum())
    name = "".join(ch for ch in exercise_name.lower() if ch.isalnum())
    if query == name:
        return 0.5
    if query and query in name:
        return 0.15
    return 0.0
