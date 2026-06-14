import os

import pytest
from sqlalchemy import select

from app.api.exercises import search_exercises
from app.core.db import SessionLocal
from app.core.models import Exercise

pytestmark = pytest.mark.integration

requires_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs seeded PostgreSQL")


@requires_db
def test_search_level_filter_is_exact_for_explore_api() -> None:
    with SessionLocal() as db:
        if not db.scalar(select(Exercise.id).where(Exercise.level == "expert").limit(1)):
            pytest.skip("seeded exercise catalog required")

        results = search_exercises(q="", equipment=None, level="expert", db=db)

        assert results
        assert {item["level"] for item in results} == {"expert"}
