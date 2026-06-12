from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import exercise_dict, plan_dict, slot_dict
from app.core.llm import get_llm_client
from app.core.models import Plan, PlanDay, PlanSlot, User
from app.modules.feedback.service import feedback_service
from app.modules.substitution.service import substitution_service


class CoachService:
    def chat(self, db: Session, *, user_id: int, message: str, history: list[dict[str, str]]) -> dict:
        user = db.get(User, user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")
        if self.is_medical_question(message):
            return {
                "message": "I can explain plan safety rules, but pain or injury decisions need a qualified medical professional.",
                "tool_results": [],
            }

        tool_call = self.suggest_tool_call(db, user_id, message, history)
        if tool_call is None:
            plan = self.get_current_plan(db, user_id)
            return {
                "message": "I can help with your current plan, slot explanations, safe alternatives, swaps, time rebudgeting, and feedback logging.",
                "tool_results": [{"tool": "get_current_plan", "result": plan}],
            }
        result = self.execute_tool(db, user_id, tool_call["name"], tool_call.get("arguments", {}))
        return {"message": self.summarize_tool_result(tool_call["name"], result), "tool_results": [{"tool": tool_call["name"], "result": result}]}

    def suggest_tool_call(
        self,
        db: Session,
        user_id: int,
        message: str,
        history: list[dict[str, str]],
    ) -> dict | None:
        deterministic = self.deterministic_tool_call(message)
        if deterministic:
            return deterministic

        try:
            response = get_llm_client().chat_with_tools(
                self.system_prompt(),
                history + [{"role": "user", "content": message}],
                self.tool_definitions(),
                max_tool_calls=1,
            )
            tool_call = response.get("tool_call")
            if tool_call and tool_call.get("name") in self.allowed_tool_names():
                return tool_call
        except Exception:
            return None
        return None

    def deterministic_tool_call(self, message: str) -> dict | None:
        text = message.lower()
        slot_id = self.extract_int_after(text, "slot")
        day_id = self.extract_int_after(text, "day")
        if "current" in text or "plan" in text and "generate" not in text:
            return {"name": "get_current_plan", "arguments": {}}
        if "explain" in text and slot_id:
            return {"name": "explain_slot", "arguments": {"slot_id": slot_id}}
        if ("alternative" in text or "swap option" in text) and slot_id:
            return {"name": "get_alternatives", "arguments": {"slot_id": slot_id}}
        if "swap" in text and slot_id:
            exercise_id = self.extract_exercise_id(message)
            if exercise_id:
                return {"name": "swap_exercise", "arguments": {"slot_id": slot_id, "exercise_id": exercise_id}}
            return {"name": "get_alternatives", "arguments": {"slot_id": slot_id}}
        if "minute" in text and day_id:
            minutes = self.extract_int_before(text, "minute") or self.extract_first_int(text)
            if minutes:
                return {"name": "replan_session", "arguments": {"plan_day_id": day_id, "available_minutes": minutes}}
        if ("log" in text or "rpe" in text) and day_id:
            rpe = self.extract_int_after(text, "rpe") or self.extract_first_int(text) or 7
            completed = self.extract_ids_after(message, "completed")
            skipped = self.extract_ids_after(message, "skipped")
            return {
                "name": "log_feedback",
                "arguments": {
                    "plan_day_id": day_id,
                    "rpe": rpe,
                    "completed": completed,
                    "skipped": skipped,
                },
            }
        return None

    def execute_tool(self, db: Session, user_id: int, name: str, arguments: dict[str, Any]) -> dict:
        if name == "get_current_plan":
            return self.get_current_plan(db, user_id)
        if name == "explain_slot":
            return self.explain_slot(db, int(arguments["slot_id"]))
        if name == "get_alternatives":
            return self.get_alternatives(db, int(arguments["slot_id"]))
        if name == "swap_exercise":
            return self.swap_exercise(db, int(arguments["slot_id"]), str(arguments["exercise_id"]))
        if name == "replan_session":
            return self.replan_session(db, int(arguments["plan_day_id"]), int(arguments["available_minutes"]))
        if name == "log_feedback":
            return self.log_feedback(
                db,
                int(arguments["plan_day_id"]),
                int(arguments["rpe"]),
                list(arguments.get("completed", [])),
                list(arguments.get("skipped", [])),
            )
        raise ValueError(f"Unsupported tool: {name}")

    def get_current_plan(self, db: Session, user_id: int) -> dict:
        plan = db.scalar(
            select(Plan)
            .where(Plan.user_id == user_id, Plan.status == "active")
            .order_by(Plan.week_index.desc(), Plan.id.desc())
        )
        if plan is None:
            return {"plan": None}
        return plan_dict(plan)

    def explain_slot(self, db: Session, slot_id: int) -> dict:
        slot = db.get(PlanSlot, slot_id)
        if slot is None:
            raise ValueError(f"Slot {slot_id} does not exist")
        return {
            "slot": slot_dict(slot),
            "rationale": slot.rationale,
            "instructions": slot.exercise.instructions if slot.exercise else [],
        }

    def get_alternatives(self, db: Session, slot_id: int) -> dict:
        alternatives = substitution_service.alternatives(db, slot_id, k=5)
        return {
            "slot_id": slot_id,
            "alternatives": [
                {
                    "exercise": exercise_dict(item["exercise"]),
                    "score": item["score"],
                    "similarity": item["similarity"],
                    "utility": item["utility"],
                }
                for item in alternatives
            ],
        }

    def swap_exercise(self, db: Session, slot_id: int, exercise_id: str) -> dict:
        allowed_ids = {item["exercise"].id for item in substitution_service.alternatives(db, slot_id, k=20)}
        if exercise_id not in allowed_ids:
            raise ValueError("Exercise must come from the current safe alternatives list.")
        return slot_dict(substitution_service.swap(db, slot_id, exercise_id))

    def replan_session(self, db: Session, plan_day_id: int, available_minutes: int) -> dict:
        day = db.get(PlanDay, plan_day_id)
        if day is None:
            raise ValueError(f"Plan day {plan_day_id} does not exist")
        kept: list[PlanSlot] = []
        elapsed = 8.0
        for slot in sorted(day.slots, key=lambda item: item.slot_index):
            minutes_per_set = 4.0 if slot.exercise and slot.exercise.mechanic == "compound" else 3.0
            estimate = slot.sets * minutes_per_set
            remaining = available_minutes - elapsed
            if estimate <= remaining:
                slot.status = "planned"
                kept.append(slot)
                elapsed += estimate
                continue
            reduced_sets = int(remaining // minutes_per_set)
            if reduced_sets >= 1:
                slot.sets = reduced_sets
                slot.status = "planned"
                slot.rationale = f"{slot.rationale} | reduced to fit {available_minutes} minutes"
                kept.append(slot)
                elapsed += reduced_sets * minutes_per_set
                continue
            slot.status = "skipped"
        db.commit()
        return {
            "plan_day_id": plan_day_id,
            "available_minutes": available_minutes,
            "estimated_minutes": round(elapsed, 1),
            "kept_slots": [slot_dict(slot) for slot in kept],
        }

    def log_feedback(self, db: Session, plan_day_id: int, rpe: int, completed: list[int], skipped: list[int]) -> dict:
        log = feedback_service.log_session(
            db,
            plan_day_id=plan_day_id,
            rpe=rpe,
            completed_slot_ids=[int(item) for item in completed],
            skipped_slot_ids=[int(item) for item in skipped],
        )
        return {"session_log_id": log.id, "plan_day_id": log.plan_day_id, "rpe": log.rpe}

    def summarize_tool_result(self, tool_name: str, result: dict) -> str:
        if tool_name == "get_current_plan":
            return "Here is the current active plan from the engine."
        if tool_name == "explain_slot":
            return "Here is the slot rationale and exercise instruction set."
        if tool_name == "get_alternatives":
            return "Here are safe alternatives from the engine."
        if tool_name == "swap_exercise":
            return "Swap completed after validating the alternative against safety and equipment rules."
        if tool_name == "replan_session":
            return "Session rebudgeted for the available time."
        if tool_name == "log_feedback":
            return "Feedback logged and preference scores updated."
        return "Tool completed."

    def system_prompt(self) -> str:
        return (
            "You are FitEngine coach. Use only tool results. Never invent exercises. "
            "Do not provide medical advice; recommend a qualified professional for pain or injury questions."
        )

    def tool_definitions(self) -> list[dict]:
        return [
            {"name": "get_current_plan", "description": "Read the user's active plan.", "parameters": {}},
            {"name": "explain_slot", "parameters": {"slot_id": "int"}},
            {"name": "get_alternatives", "parameters": {"slot_id": "int"}},
            {"name": "swap_exercise", "parameters": {"slot_id": "int", "exercise_id": "str"}},
            {"name": "replan_session", "parameters": {"plan_day_id": "int", "available_minutes": "int"}},
            {"name": "log_feedback", "parameters": {"plan_day_id": "int", "rpe": "int", "completed": "list[int]", "skipped": "list[int]"}},
        ]

    def allowed_tool_names(self) -> set[str]:
        return {tool["name"] for tool in self.tool_definitions()}

    def is_medical_question(self, message: str) -> bool:
        text = message.lower()
        return any(term in text for term in ["diagnose", "doctor", "medical advice", "is it safe with pain", "sharp pain"])

    def extract_int_after(self, text: str, label: str) -> int | None:
        match = re.search(rf"{re.escape(label)}\s*#?:?\s*(\d+)", text)
        return int(match.group(1)) if match else None

    def extract_int_before(self, text: str, label: str) -> int | None:
        match = re.search(rf"(\d+)\s*{re.escape(label)}", text)
        return int(match.group(1)) if match else None

    def extract_first_int(self, text: str) -> int | None:
        match = re.search(r"\d+", text)
        return int(match.group(0)) if match else None

    def extract_ids_after(self, message: str, label: str) -> list[int]:
        match = re.search(rf"{re.escape(label)}\s*:?\s*([0-9,\s]+)", message, re.IGNORECASE)
        if not match:
            return []
        return [int(item) for item in re.findall(r"\d+", match.group(1))]

    def extract_exercise_id(self, message: str) -> str | None:
        match = re.search(r"\b([A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)+)\b", message)
        return match.group(1) if match else None


coach_service = CoachService()
