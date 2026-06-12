from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm import get_llm_client
from app.core.config import settings
from app.core.models import Exercise, InjuryProfile, User, UserExclusion, UserInjury
from app.modules.catalog.service import catalog_service
from app.modules.catalog.utils import query_similarity


SEVERITIES = {"mild", "moderate", "severe"}


class ParsedInjury(BaseModel):
    code: str
    severity: Literal["mild", "moderate", "severe"] = "moderate"
    notes: str | None = None


class ParsedIntake(BaseModel):
    injuries: list[ParsedInjury] = Field(default_factory=list)
    exclusions_by_name: list[str] = Field(default_factory=list)
    preferences_text: str = ""

    @field_validator("exclusions_by_name")
    @classmethod
    def clean_names(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ProfileService:
    def create_user(self, db: Session, payload: dict) -> User:
        injuries = payload.pop("injuries", [])
        exclusions = payload.pop("exclusions", [])
        user = User(**payload)
        db.add(user)
        db.flush()
        for injury in injuries:
            db.add(
                UserInjury(
                    user_id=user.id,
                    injury_code=injury["injury_code"],
                    severity=injury.get("severity", "moderate"),
                    notes=injury.get("notes"),
                )
            )
        for exclusion in exclusions:
            db.add(
                UserExclusion(
                    user_id=user.id,
                    exercise_id=exclusion["exercise_id"],
                    reason=exclusion.get("reason"),
                )
            )
        db.commit()
        db.refresh(user)
        return user

    def get_user(self, db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    def parse_intake_text(self, db: Session, user_id: int, free_text: str) -> dict:
        user = self.get_user(db, user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")

        valid_codes = set(db.scalars(select(InjuryProfile.code)).all())
        parsed, source = self.parse_with_llm_or_fallback(free_text, valid_codes)
        if source == "structured_form_required":
            return {
                "source": source,
                "requires_structured_form": True,
                "injuries": [],
                "exclusions": [],
                "unresolved_exclusions_by_name": [],
                "preferences_text": "",
            }
        saved_injuries = self.persist_injuries(db, user_id, parsed, valid_codes)
        saved_exclusions, unresolved_exclusions = self.persist_exclusions(db, user_id, parsed.exclusions_by_name)
        db.commit()
        return {
            "source": source,
            "injuries": saved_injuries,
            "exclusions": saved_exclusions,
            "unresolved_exclusions_by_name": unresolved_exclusions,
            "preferences_text": parsed.preferences_text,
        }

    def parse_with_llm_or_fallback(self, free_text: str, valid_codes: set[str]) -> tuple[ParsedIntake, str]:
        schema = ParsedIntake.model_json_schema()
        system_prompt = (
            "Extract exercise intake details. Return data only. "
            f"Valid injury codes: {', '.join(sorted(valid_codes))}. "
            "Use moderate severity when the user is vague. Do not invent injury codes."
        )
        llm = get_llm_client()
        try:
            raw = llm.structured_json(system_prompt, free_text, schema, temperature=0)
            parsed = ParsedIntake.model_validate(raw)
            self.validate_injury_codes(parsed, valid_codes)
            return parsed, "llm"
        except Exception as first_error:
            try:
                retry_prompt = f"{free_text}\n\nPrevious validation error: {first_error}"
                raw = llm.structured_json(system_prompt, retry_prompt, schema, temperature=0)
                parsed = ParsedIntake.model_validate(raw)
                self.validate_injury_codes(parsed, valid_codes)
                return parsed, "llm_retry"
            except Exception:
                if settings.gemini_api_key:
                    return ParsedIntake(), "structured_form_required"
                return self.deterministic_parse(free_text), "deterministic_fallback"

    def validate_injury_codes(self, parsed: ParsedIntake, valid_codes: set[str]) -> None:
        invalid = [injury.code for injury in parsed.injuries if injury.code not in valid_codes]
        if invalid:
            raise ValueError(f"Invalid injury codes: {invalid}")

    def deterministic_parse(self, free_text: str) -> ParsedIntake:
        text = free_text.lower()
        severity = self.detect_severity(text)
        injuries: list[ParsedInjury] = []
        injury_terms = {
            "knee_pain": ["knee", "knees", "squat deep", "deep squat"],
            "lower_back_pain": ["lower back", "back pain", "lumbar", "deadlift hurts"],
            "shoulder_impingement": ["shoulder", "impingement", "overhead hurts"],
            "wrist_pain": ["wrist", "wrists"],
            "elbow_tendinitis": ["elbow", "tennis elbow", "tendinitis", "tendonitis"],
            "ankle_instability": ["ankle", "ankles"],
            "hip_pain": ["hip", "hips"],
            "neck_pain": ["neck"],
            "hernia_recovery": ["hernia"],
            "hamstring_strain": ["hamstring"],
        }
        for code, terms in injury_terms.items():
            if any(term in text for term in terms):
                injuries.append(ParsedInjury(code=code, severity=severity, notes=free_text))

        exclusions = self.extract_exclusion_names(text)
        preference_text = self.extract_preferences(free_text)
        return ParsedIntake(injuries=injuries, exclusions_by_name=exclusions, preferences_text=preference_text)

    def detect_severity(self, text: str) -> str:
        if any(word in text for word in ["severe", "sharp", "intense", "serious", "bad pain"]):
            return "severe"
        if any(word in text for word in ["mild", "slight", "minor"]):
            return "mild"
        return "moderate"

    def extract_exclusion_names(self, text: str) -> list[str]:
        names: list[str] = []
        direct_phrases = re.findall(r"(?:hate|dislike|avoid|can't stand|do not want|don't want|no)\s+([a-z0-9 \-_/]+)", text)
        for phrase in direct_phrases:
            phrase = re.split(r"\b(?:and|but|because|with|due|when|while)\b|[,.]", phrase)[0].strip()
            if phrase:
                names.append(phrase)
        if "burpee" in text and "burpee" not in names:
            names.append("burpee")
        return names[:10]

    def extract_preferences(self, free_text: str) -> str:
        matches = re.findall(r"\b(?:like|prefer|love)\b\s+([^,.]+)", free_text, flags=re.IGNORECASE)
        return "; ".join(match.strip() for match in matches)

    def persist_injuries(
        self,
        db: Session,
        user_id: int,
        parsed: ParsedIntake,
        valid_codes: set[str],
    ) -> list[dict]:
        saved = []
        for injury in parsed.injuries:
            if injury.code not in valid_codes:
                continue
            row = UserInjury(
                user_id=user_id,
                injury_code=injury.code,
                severity=injury.severity,
                notes=injury.notes,
            )
            db.merge(row)
            saved.append(row_to_injury_dict(row))
        return saved

    def persist_exclusions(self, db: Session, user_id: int, names: list[str]) -> tuple[list[dict], list[str]]:
        saved = []
        unresolved = []
        for name in names:
            match = self.resolve_exclusion_name(db, name)
            if match is None:
                unresolved.append(name)
                continue
            db.merge(UserExclusion(user_id=user_id, exercise_id=match.id, reason=f"intake text: {name}"))
            saved.append({"exercise_id": match.id, "name": match.name, "reason": f"intake text: {name}"})
        return saved, unresolved

    def resolve_exclusion_name(self, db: Session, name: str):
        normalized = normalize_exclusion_name(name)
        all_exercises = db.scalars(select(Exercise)).all()
        for exercise in all_exercises:
            if normalize_exclusion_name(exercise.name) == normalized:
                return exercise
        singular = normalized[:-1] if normalized.endswith("s") else normalized
        for exercise in all_exercises:
            if normalize_exclusion_name(exercise.name) == singular:
                return exercise
        results = catalog_service.semantic_search(db, name, k=5, filters={})
        if not results:
            return None
        exact = next((exercise for exercise in results if exercise.name.lower() == name.lower()), None)
        if exact:
            return exact
        best = max(results, key=lambda exercise: query_similarity(name, exercise))
        return best if query_similarity(name, best) > 0.45 else None


def row_to_injury_dict(row: UserInjury) -> dict:
    return {"injury_code": row.injury_code, "severity": row.severity, "notes": row.notes}


def normalize_exclusion_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


profile_service = ProfileService()
