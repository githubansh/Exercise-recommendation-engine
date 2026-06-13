from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.models import Contraindication, Exercise, ExerciseEmbedding, ExercisePattern, InjuryProfile
from seeds import load_seeds

TRUE_VALUES = {"1", "true", "yes", "on"}


def env_enabled(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in TRUE_VALUES


def row_count(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def seed_status(db: Session) -> dict[str, int]:
    return {
        "exercises": row_count(db, Exercise),
        "embeddings": row_count(db, ExerciseEmbedding),
        "patterns": row_count(db, ExercisePattern),
        "injury_profiles": row_count(db, InjuryProfile),
        "contraindications": row_count(db, Contraindication),
    }


def missing_seed_parts(counts: dict[str, int]) -> list[str]:
    missing = [name for name, count in counts.items() if count == 0]
    if 0 < counts["embeddings"] < counts["exercises"]:
        missing.append("embedding coverage")
    return missing


def main() -> None:
    with SessionLocal() as db:
        counts = seed_status(db)

    force = env_enabled("FORCE_SEED_DATA")
    missing = missing_seed_parts(counts)

    if force or missing:
        reason = "FORCE_SEED_DATA=true" if force else f"missing {', '.join(missing)}"
        print(f"seed data: loading catalog because {reason}")
        load_seeds.main()
        return

    print(
        "seed data: already loaded "
        f"({counts['exercises']} exercises, {counts['embeddings']} embeddings)"
    )


if __name__ == "__main__":
    main()
