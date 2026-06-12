from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - import depends on optional package install.
    Vector = None


class Base(DeclarativeBase):
    pass


StringArray = ARRAY(String)
Vector384 = Vector(384) if Vector is not None else JSONB


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    force: Mapped[str | None] = mapped_column(Text)
    mechanic: Mapped[str] = mapped_column(Text, nullable=False, default="isolation")
    equipment: Mapped[str] = mapped_column(Text, nullable=False, default="body only")
    category: Mapped[str] = mapped_column(Text, nullable=False)
    primary_muscles: Mapped[list[str]] = mapped_column(StringArray, nullable=False)
    secondary_muscles: Mapped[list[str]] = mapped_column(StringArray, nullable=False)
    instructions: Mapped[list[str]] = mapped_column(StringArray, nullable=False)
    instructions_generated: Mapped[bool] = mapped_column(nullable=False, default=False)
    images: Mapped[list[str]] = mapped_column(StringArray, nullable=False)
    muscle_groups: Mapped[list[str]] = mapped_column(StringArray, nullable=False)

    patterns: Mapped[list["ExercisePattern"]] = relationship(back_populates="exercise", cascade="all, delete-orphan")
    embedding: Mapped["ExerciseEmbedding"] = relationship(back_populates="exercise", cascade="all, delete-orphan")


class ExercisePattern(Base):
    __tablename__ = "exercise_patterns"

    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    pattern: Mapped[str] = mapped_column(Text, primary_key=True)

    exercise: Mapped[Exercise] = relationship(back_populates="patterns")


class ExerciseEmbedding(Base):
    __tablename__ = "exercise_embeddings"

    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[Any] = mapped_column(Vector384, nullable=False)

    exercise: Mapped[Exercise] = relationship(back_populates="embedding")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None]
    sex: Mapped[str | None] = mapped_column(Text)
    height_cm: Mapped[int | None]
    weight_kg: Mapped[int | None]
    level: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    days_per_week: Mapped[int] = mapped_column(nullable=False)
    minutes_per_session: Mapped[int] = mapped_column(nullable=False)
    equipment: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (CheckConstraint("days_per_week BETWEEN 2 AND 6", name="ck_users_days_per_week"),)

    injuries: Mapped[list["UserInjury"]] = relationship(cascade="all, delete-orphan")
    exclusions: Mapped[list["UserExclusion"]] = relationship(cascade="all, delete-orphan")


class UserInjury(Base):
    __tablename__ = "user_injuries"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    injury_code: Mapped[str] = mapped_column(Text, primary_key=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="moderate")
    notes: Mapped[str | None] = mapped_column(Text)


class UserExclusion(Base):
    __tablename__ = "user_exclusions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)


class InjuryProfile(Base):
    __tablename__ = "injury_profiles"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Contraindication(Base):
    __tablename__ = "contraindications"

    injury_code: Mapped[str] = mapped_column(ForeignKey("injury_profiles.code", ondelete="CASCADE"), primary_key=True)
    pattern: Mapped[str] = mapped_column(Text, primary_key=True)
    min_severity: Mapped[str] = mapped_column(Text, primary_key=True, default="mild")


class PreferenceScore(Base):
    __tablename__ = "preference_scores"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float] = mapped_column(nullable=False, default=0.5)
    pulls: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_index: Mapped[int] = mapped_column(nullable=False, default=1)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    days: Mapped[list["PlanDay"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="PlanDay.day_index")


class PlanDay(Base):
    __tablename__ = "plan_days"
    __table_args__ = (UniqueConstraint("plan_id", "day_index", name="uq_plan_days_plan_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    day_index: Mapped[int] = mapped_column(nullable=False)
    focus: Mapped[str] = mapped_column(Text, nullable=False)

    plan: Mapped[Plan] = relationship(back_populates="days")
    slots: Mapped[list["PlanSlot"]] = relationship(back_populates="plan_day", cascade="all, delete-orphan", order_by="PlanSlot.slot_index")


class PlanSlot(Base):
    __tablename__ = "plan_slots"
    __table_args__ = (UniqueConstraint("plan_day_id", "slot_index", name="uq_plan_slots_day_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(ForeignKey("plan_days.id", ondelete="CASCADE"))
    slot_index: Mapped[int] = mapped_column(nullable=False)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"))
    sets: Mapped[int] = mapped_column(nullable=False)
    reps: Mapped[str] = mapped_column(Text, nullable=False)
    rest_sec: Mapped[int] = mapped_column(nullable=False)
    rpe_target: Mapped[int] = mapped_column(nullable=False, default=8)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")

    plan_day: Mapped[PlanDay] = relationship(back_populates="slots")
    exercise: Mapped[Exercise] = relationship()


class SessionLog(Base):
    __tablename__ = "session_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_day_id: Mapped[int] = mapped_column(ForeignKey("plan_days.id", ondelete="CASCADE"))
    completed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    rpe: Mapped[int | None]
    duration_min: Mapped[int | None]
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (CheckConstraint("rpe BETWEEN 1 AND 10", name="ck_session_logs_rpe"),)


class SlotFeedback(Base):
    __tablename__ = "slot_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_log_id: Mapped[int] = mapped_column(ForeignKey("session_logs.id", ondelete="CASCADE"))
    plan_slot_id: Mapped[int] = mapped_column(ForeignKey("plan_slots.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reward: Mapped[float] = mapped_column(nullable=False)


class SwapEvent(Base):
    __tablename__ = "swap_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_slot_id: Mapped[int] = mapped_column(ForeignKey("plan_slots.id", ondelete="CASCADE"))
    from_exercise: Mapped[str | None] = mapped_column(Text)
    to_exercise: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
