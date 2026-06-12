from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.models import Contraindication, Exercise, ExerciseEmbedding, ExercisePattern, InjuryProfile
from app.core.config import settings
from seeds.curation import apply_data_corrections, curated_exercise

ROOT = Path(__file__).resolve().parent


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def embedding_text(exercise: dict) -> str:
    first_instructions = " ".join(exercise["instructions"][:2])
    return (
        f"{exercise['name']}. Level: {exercise['level']}. "
        f"{exercise['mechanic']} {exercise.get('force') or ''} exercise using {exercise['equipment']}. "
        f"Targets: {', '.join(exercise['primary_muscles'])}. {first_instructions}"
    )


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embedding_model_name)
    vectors = model.encode(texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def upsert_exercises(db: Session, raw_exercises: list[dict]) -> list[dict]:
    curated = [curated_exercise(item) for item in raw_exercises]
    for exercise in curated:
        stmt = insert(Exercise).values(**exercise)
        update = {key: getattr(stmt.excluded, key) for key in exercise if key != "id"}
        db.execute(stmt.on_conflict_do_update(index_elements=[Exercise.id], set_=update))
    return curated


def replace_patterns(db: Session, patterns: dict[str, list[str] | None]) -> None:
    db.query(ExercisePattern).delete()
    rows = [
        ExercisePattern(exercise_id=exercise_id, pattern=pattern)
        for exercise_id, tags in patterns.items()
        for pattern in (tags or [])
    ]
    db.add_all(rows)


def replace_injury_profiles(db: Session, profiles: dict) -> None:
    db.query(Contraindication).delete()
    db.query(InjuryProfile).delete()
    for code, profile in profiles.items():
        db.add(
            InjuryProfile(
                code=code,
                display_name=profile["display_name"],
                description=profile["description"],
            )
        )
    db.flush()
    for code, profile in profiles.items():
        for block in profile.get("blocks", []):
            db.add(
                Contraindication(
                    injury_code=code,
                    pattern=block["pattern"],
                    min_severity=block.get("min_severity", "mild"),
                )
            )


def replace_embeddings(db: Session, exercises: list[dict]) -> None:
    db.query(ExerciseEmbedding).delete()
    texts = [embedding_text(exercise) for exercise in exercises]
    for exercise, vector in zip(exercises, compute_embeddings(texts), strict=True):
        db.add(ExerciseEmbedding(exercise_id=exercise["id"], embedding=vector))


def main() -> None:
    raw_exercises = json.loads((ROOT / "exercises.json").read_text(encoding="utf-8"))
    corrections = load_yaml(ROOT / "data_corrections.yaml") if (ROOT / "data_corrections.yaml").exists() else {}
    raw_exercises = apply_data_corrections(raw_exercises, corrections)
    patterns_path = ROOT / "movement_patterns.yaml"
    if not patterns_path.exists():
        raise RuntimeError("Run `python -m seeds.build_movement_patterns` before loading seeds.")

    with SessionLocal() as db:
        exercises = upsert_exercises(db, raw_exercises)
        replace_patterns(db, load_yaml(patterns_path))
        replace_injury_profiles(db, load_yaml(ROOT / "injury_profiles.yaml"))
        replace_embeddings(db, exercises)
        db.commit()

    print(f"loaded {len(raw_exercises)} exercises and embeddings")


if __name__ == "__main__":
    main()
