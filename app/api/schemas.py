from __future__ import annotations

from pydantic import BaseModel, Field


class InjuryInput(BaseModel):
    injury_code: str
    severity: str = "moderate"
    notes: str | None = None


class ExclusionInput(BaseModel):
    exercise_id: str
    reason: str | None = None


class UserCreate(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    level: str
    goal: str
    days_per_week: int = Field(ge=2, le=6)
    minutes_per_session: int = Field(gt=0)
    equipment: list[str] = Field(default_factory=lambda: ["body only"])
    injuries: list[InjuryInput] = Field(default_factory=list)
    exclusions: list[ExclusionInput] = Field(default_factory=list)


class PlanGenerateRequest(BaseModel):
    user_id: int
    week_index: int = 1


class SwapRequest(BaseModel):
    exercise_id: str


class SessionLogRequest(BaseModel):
    plan_day_id: int
    rpe: int = Field(ge=1, le=10)
    completed_slot_ids: list[int] = Field(default_factory=list)
    skipped_slot_ids: list[int] = Field(default_factory=list)
    duration_min: int | None = None
    notes: str | None = None


class IntakeTextRequest(BaseModel):
    text: str


class CoachChatRequest(BaseModel):
    user_id: int
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
