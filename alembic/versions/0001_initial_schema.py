"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE exercises (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          level TEXT NOT NULL,
          force TEXT,
          mechanic TEXT NOT NULL DEFAULT 'isolation',
          equipment TEXT NOT NULL DEFAULT 'body only',
          category TEXT NOT NULL,
          primary_muscles TEXT[] NOT NULL,
          secondary_muscles TEXT[] NOT NULL,
          instructions TEXT[] NOT NULL,
          instructions_generated BOOLEAN NOT NULL DEFAULT FALSE,
          images TEXT[] NOT NULL,
          muscle_groups TEXT[] NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE exercise_patterns (
          exercise_id TEXT REFERENCES exercises(id) ON DELETE CASCADE,
          pattern TEXT NOT NULL,
          PRIMARY KEY (exercise_id, pattern)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE exercise_embeddings (
          exercise_id TEXT PRIMARY KEY REFERENCES exercises(id) ON DELETE CASCADE,
          embedding vector(384) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_exercise_embeddings_cosine ON exercise_embeddings USING ivfflat (embedding vector_cosine_ops)")
    op.execute(
        """
        CREATE TABLE users (
          id SERIAL PRIMARY KEY,
          name TEXT,
          age INT,
          sex TEXT,
          height_cm INT,
          weight_kg INT,
          level TEXT NOT NULL,
          goal TEXT NOT NULL,
          days_per_week INT NOT NULL CHECK (days_per_week BETWEEN 2 AND 6),
          minutes_per_session INT NOT NULL,
          equipment TEXT[] NOT NULL,
          created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_injuries (
          user_id INT REFERENCES users(id) ON DELETE CASCADE,
          injury_code TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'moderate',
          notes TEXT,
          PRIMARY KEY (user_id, injury_code)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_exclusions (
          user_id INT REFERENCES users(id) ON DELETE CASCADE,
          exercise_id TEXT REFERENCES exercises(id) ON DELETE CASCADE,
          reason TEXT,
          PRIMARY KEY (user_id, exercise_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE injury_profiles (
          code TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          description TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE contraindications (
          injury_code TEXT REFERENCES injury_profiles(code) ON DELETE CASCADE,
          pattern TEXT NOT NULL,
          min_severity TEXT NOT NULL DEFAULT 'mild',
          PRIMARY KEY (injury_code, pattern, min_severity)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE preference_scores (
          user_id INT REFERENCES users(id) ON DELETE CASCADE,
          exercise_id TEXT REFERENCES exercises(id) ON DELETE CASCADE,
          score REAL NOT NULL DEFAULT 0.5,
          pulls INT NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ DEFAULT now(),
          PRIMARY KEY (user_id, exercise_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE plans (
          id SERIAL PRIMARY KEY,
          user_id INT REFERENCES users(id) ON DELETE CASCADE,
          week_index INT NOT NULL DEFAULT 1,
          split TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          params JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE plan_days (
          id SERIAL PRIMARY KEY,
          plan_id INT REFERENCES plans(id) ON DELETE CASCADE,
          day_index INT NOT NULL,
          focus TEXT NOT NULL,
          UNIQUE (plan_id, day_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE plan_slots (
          id SERIAL PRIMARY KEY,
          plan_day_id INT REFERENCES plan_days(id) ON DELETE CASCADE,
          slot_index INT NOT NULL,
          exercise_id TEXT REFERENCES exercises(id),
          sets INT NOT NULL,
          reps TEXT NOT NULL,
          rest_sec INT NOT NULL,
          rpe_target INT NOT NULL DEFAULT 8,
          rationale TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'planned',
          UNIQUE (plan_day_id, slot_index)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE session_logs (
          id SERIAL PRIMARY KEY,
          plan_day_id INT REFERENCES plan_days(id) ON DELETE CASCADE,
          completed_at TIMESTAMPTZ DEFAULT now(),
          rpe INT CHECK (rpe BETWEEN 1 AND 10),
          duration_min INT,
          notes TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE slot_feedback (
          id SERIAL PRIMARY KEY,
          session_log_id INT REFERENCES session_logs(id) ON DELETE CASCADE,
          plan_slot_id INT REFERENCES plan_slots(id) ON DELETE CASCADE,
          status TEXT NOT NULL,
          reward REAL NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE swap_events (
          id SERIAL PRIMARY KEY,
          plan_slot_id INT REFERENCES plan_slots(id) ON DELETE CASCADE,
          from_exercise TEXT,
          to_exercise TEXT,
          reason TEXT,
          created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    for table in [
        "swap_events",
        "slot_feedback",
        "session_logs",
        "plan_slots",
        "plan_days",
        "plans",
        "preference_scores",
        "contraindications",
        "injury_profiles",
        "user_exclusions",
        "user_injuries",
        "users",
        "exercise_embeddings",
        "exercise_patterns",
        "exercises",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
