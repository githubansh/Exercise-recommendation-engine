from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm import get_llm_client
from app.core.config import settings
from app.core.models import Exercise, InjuryProfile, User, UserExclusion, UserInjury
from app.modules.catalog.constants import EQUIPMENT_VALUES, GOALS, LEVEL_ORDER
from app.modules.catalog.service import catalog_service
from app.modules.catalog.utils import query_similarity


SEVERITIES = {"mild", "moderate", "severe"}
USER_UPDATE_FIELDS = {
    "name",
    "age",
    "sex",
    "height_cm",
    "weight_kg",
    "level",
    "goal",
    "days_per_week",
    "minutes_per_session",
    "equipment",
}


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
        payload = dict(payload)
        injuries = payload.pop("injuries", [])
        exclusions = payload.pop("exclusions", [])
        self.validate_create_payload(db, payload, injuries, exclusions)
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

    def validate_create_payload(self, db: Session, payload: dict, injuries: list[dict], exclusions: list[dict]) -> None:
        level = payload.get("level")
        if level not in LEVEL_ORDER:
            raise ValueError(f"Unknown level: {level}. Allowed: {sorted(LEVEL_ORDER)}")
        goal = payload.get("goal")
        if goal not in GOALS:
            raise ValueError(f"Unknown goal: {goal}. Allowed: {GOALS}")
        equipment = set(payload.get("equipment") or [])
        unknown_equipment = sorted(equipment - EQUIPMENT_VALUES)
        if unknown_equipment:
            raise ValueError(f"Unknown equipment: {unknown_equipment}. Allowed: {sorted(EQUIPMENT_VALUES)}")

        valid_codes = set(db.scalars(select(InjuryProfile.code)).all())
        invalid_codes = sorted({injury["injury_code"] for injury in injuries if injury["injury_code"] not in valid_codes})
        if invalid_codes:
            raise ValueError(f"Invalid injury codes: {invalid_codes}. Allowed: {sorted(valid_codes)}")
        invalid_severities = sorted(
            {injury.get("severity", "moderate") for injury in injuries if injury.get("severity", "moderate") not in SEVERITIES}
        )
        if invalid_severities:
            raise ValueError(f"Invalid injury severities: {invalid_severities}. Allowed: {sorted(SEVERITIES)}")

        exclusion_ids = {exclusion["exercise_id"] for exclusion in exclusions}
        if exclusion_ids:
            found_ids = set(db.scalars(select(Exercise.id).where(Exercise.id.in_(exclusion_ids))).all())
            missing_ids = sorted(exclusion_ids - found_ids)
            if missing_ids:
                raise ValueError(f"Invalid exclusion exercise ids: {missing_ids}")

    def get_user(self, db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    def update_user(self, db: Session, user_id: int, payload: dict) -> User:
        user = self.get_user(db, user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")
        updates = {key: value for key, value in payload.items() if key in USER_UPDATE_FIELDS}
        candidate = {
            "level": updates.get("level", user.level),
            "goal": updates.get("goal", user.goal),
            "equipment": updates.get("equipment", user.equipment),
        }
        if "days_per_week" in updates:
            candidate["days_per_week"] = updates["days_per_week"]
        else:
            candidate["days_per_week"] = user.days_per_week
        self.validate_create_payload(db, candidate, [], [])
        for key, value in updates.items():
            setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return user

    def parse_intake_text(self, db: Session, user_id: int, free_text: str) -> dict:
        user = self.get_user(db, user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")
        warning = self.medical_red_flag_warning(free_text)
        if warning:
            return self.medical_red_flag_response(warning)

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
            "requires_structured_form": False,
            "injuries": saved_injuries,
            "exclusions": saved_exclusions,
            "unresolved_exclusions_by_name": unresolved_exclusions,
            "preferences_text": parsed.preferences_text,
        }

    def preview_intake_text(self, db: Session, free_text: str) -> dict:
        warning = self.medical_red_flag_warning(free_text)
        if warning:
            return self.medical_red_flag_response(warning)
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
        exclusions, unresolved = self.preview_exclusions(db, parsed.exclusions_by_name)
        return {
            "source": source,
            "requires_structured_form": False,
            "injuries": [
                {"injury_code": injury.code, "severity": injury.severity, "notes": injury.notes}
                for injury in parsed.injuries
            ],
            "exclusions": exclusions,
            "unresolved_exclusions_by_name": unresolved,
            "preferences_text": parsed.preferences_text,
        }

    def medical_red_flag_warning(self, free_text: str) -> str | None:
        text = free_text.lower()
        red_flags = [
            "head injury",
            "concussion",
            "hit my head",
            "head trauma",
            "loss of consciousness",
            "blacked out",
            "fainted",
            "dizzy",
            "chest pain",
            "trouble breathing",
            "shortness of breath",
            "numbness",
            "severe pain",
            "sharp pain",
        ]
        if any(term in text for term in red_flags):
            return (
                "Do not train right now. Rest and consult a doctor or urgent medical professional before exercising, "
                "especially with head injury, dizziness, chest pain, numbness, or severe/sharp pain."
            )
        return None

    def medical_red_flag_response(self, warning: str) -> dict:
        return {
            "source": "medical_red_flag",
            "requires_structured_form": True,
            "medical_warning": warning,
            "injuries": [],
            "exclusions": [],
            "unresolved_exclusions_by_name": [],
            "preferences_text": "",
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
                deterministic = self.deterministic_parse(free_text)
                if deterministic.injuries or deterministic.exclusions_by_name or deterministic.preferences_text:
                    return deterministic, "deterministic_fallback"
                if settings.gemini_api_key:
                    return ParsedIntake(), "structured_form_required"
                return deterministic, "deterministic_fallback"

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

    def preview_exclusions(self, db: Session, names: list[str]) -> tuple[list[dict], list[str]]:
        resolved = []
        unresolved = []
        for name in names:
            match = self.resolve_exclusion_name(db, name)
            if match is None:
                unresolved.append(name)
                continue
            resolved.append({"exercise_id": match.id, "name": match.name, "reason": f"intake text: {name}"})
        return resolved, unresolved

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
