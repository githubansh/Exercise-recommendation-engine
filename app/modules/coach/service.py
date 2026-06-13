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
        red_flag = self.medical_red_flag(message)
        if red_flag:
            return {
                "message": red_flag,
                "tool_results": [],
            }
        if self.is_rpe_question(message):
            return {
                "message": "RPE means Rate of Perceived Exertion: 1 is very easy, 10 is maximum effort. RPE 7 means challenging but controlled, with a few reps left.",
                "tool_results": [],
            }
        if self.is_swap_help(message):
            return {
                "message": "To swap, open Today or Plan, pick the exercise, then use its Swap button. FitEngine will only show alternatives that match your equipment and safety rules.",
                "tool_results": [],
            }

        tool_call = self.suggest_tool_call(db, user_id, message, history)
        if tool_call is None:
            answer = self.chat_answer(db, user, message, history)
            return {"message": answer["message"], "source": answer["source"], "tool_results": []}
        result = self.execute_tool(db, user_id, tool_call["name"], tool_call.get("arguments", {}))
        return {"message": self.summarize_tool_result(tool_call["name"], result), "tool_results": [{"tool": tool_call["name"], "result": result}]}

    def chat_answer(self, db: Session, user: User, message: str, history: list[dict[str, str]]) -> dict:
        messages = self.sanitize_history(history)[-8:] + [{"role": "user", "content": message}]
        try:
            message_text = get_llm_client().chat(
                self.chat_system_prompt(db, user),
                messages,
                temperature=0.45,
            )
            return {"message": message_text, "source": "llm"}
        except Exception:
            return {"message": self.fallback_chat_response(message), "source": "fallback"}

    def sanitize_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        clean = []
        for item in history:
            role = item.get("role", "user")
            if role == "coach":
                role = "assistant"
            if role not in {"user", "assistant"}:
                role = "user"
            content = str(item.get("content", "")).strip()
            if content:
                clean.append({"role": role, "content": content[:1200]})
        return clean

    def chat_system_prompt(self, db: Session, user: User) -> str:
        plan = self.get_current_plan(db, user.id)
        plan_summary = self.compact_plan_summary(plan)
        return (
            "You are FitEngine Coach, a friendly exercise recommendation assistant inside a fitness planning app. "
            "You can chat naturally, but keep answers short and practical. "
            "Do not invent exercises outside the provided current plan context. "
            "For app-changing actions, tell the user which UI action to use or ask for the missing detail. "
            "Never give medical clearance; for serious pain or injury tell the user to rest and consult a doctor.\n\n"
            f"User profile: level={user.level}, goal={user.goal}, days_per_week={user.days_per_week}, "
            f"minutes_per_session={user.minutes_per_session}, equipment={user.equipment}.\n"
            f"Current plan summary: {plan_summary}"
        )

    def compact_plan_summary(self, plan: dict) -> str:
        days = plan.get("days") or []
        if not days:
            return "No active plan."
        parts = []
        for day in days[:6]:
            exercises = [
                (slot.get("exercise") or {}).get("name", slot.get("exercise_id", "exercise"))
                for slot in day.get("slots", [])[:5]
            ]
            parts.append(f"Day {day.get('day_index')} {day.get('focus')}: {', '.join(exercises)}")
        return " | ".join(parts)

    def fallback_chat_response(self, message: str) -> str:
        text = message.lower().strip()
        if any(greeting in text for greeting in ["hi", "hello", "hey", "hii"]):
            return "Hey. I am here to help with your workout plan, swaps, time limits, and exercise questions. What do you want to change today?"
        if "what are you doing" in text or "who are you" in text:
            return "I am your FitEngine coach. I read your current plan and help you make small safe changes without rebuilding everything manually."
        if "help" in text:
            return "Tell me what feels hard: time, pain, equipment, a confusing exercise, or motivation. I can guide you to Today, Swap, Progress, or Profile."
        if "thank" in text:
            return "Anytime. Keep it simple: finish what you can, log how hard it felt, and FitEngine will adapt."
        return "I can help, but I need one detail: do you want to change time, swap an exercise, understand an exercise, or update an injury/equipment detail?"

    def suggest_tool_call(
        self,
        db: Session,
        user_id: int,
        message: str,
        history: list[dict[str, str]],
    ) -> dict | None:
        deterministic = self.deterministic_tool_call(message, default_day_id=self.current_plan_day_id(db, user_id))
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
            if tool_call and tool_call.get("name") in self.allowed_tool_names() and self.tool_matches_message(tool_call["name"], message):
                return tool_call
        except Exception:
            return None
        return None

    def deterministic_tool_call(self, message: str, default_day_id: int | None = None) -> dict | None:
        text = message.lower()
        slot_id = self.extract_int_after(text, "slot")
        day_id = self.extract_int_after(text, "day")

        if "explain" in text and slot_id:
            return {"name": "explain_slot", "arguments": {"slot_id": slot_id}}
        if ("alternative" in text or "swap option" in text) and slot_id:
            return {"name": "get_alternatives", "arguments": {"slot_id": slot_id}}
        if "swap" in text and slot_id:
            exercise_id = self.extract_exercise_id(message)
            if exercise_id:
                return {"name": "swap_exercise", "arguments": {"slot_id": slot_id, "exercise_id": exercise_id}}
            return {"name": "get_alternatives", "arguments": {"slot_id": slot_id}}
        if any(term in text for term in ["minute", "minutes", "less time", "shorter", "only have"]):
            minutes = self.extract_int_before(text, "minute") or self.extract_first_int(text)
            target_day_id = day_id or default_day_id
            if minutes and target_day_id:
                return {"name": "replan_session", "arguments": {"plan_day_id": target_day_id, "available_minutes": minutes}}
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
        if ("current" in text) or ("plan" in text and "generate" not in text):
            return {"name": "get_current_plan", "arguments": {}}
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

    def current_plan_day_id(self, db: Session, user_id: int) -> int | None:
        plan = db.scalar(
            select(Plan)
            .where(Plan.user_id == user_id, Plan.status == "active")
            .order_by(Plan.week_index.desc(), Plan.id.desc())
        )
        if plan is None or not plan.days:
            return None
        return plan.days[0].id

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
            slot.status = "deferred"
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
            days = result.get("days") or []
            if not days:
                return "I could not find an active plan yet. Create a plan from setup first."
            return f"Your active plan is Week {result.get('week_index', 1)} with {len(days)} training days. Open Plan or Today to review it."
        if tool_name == "explain_slot":
            slot = result.get("slot", {})
            exercise = (slot.get("exercise") or {}).get("name", "this exercise")
            return f"{exercise}: {result.get('rationale', 'This slot was selected by your plan rules.')}"
        if tool_name == "get_alternatives":
            count = len(result.get("alternatives", []))
            return f"I found {count} safe alternatives. Open the swap screen to choose one."
        if tool_name == "swap_exercise":
            exercise = (result.get("exercise") or {}).get("name", "the selected exercise")
            return f"Swap completed. Today now uses {exercise}."
        if tool_name == "replan_session":
            return f"I updated today's workout to fit about {result.get('available_minutes')} minutes. Open Today to see the changed plan."
        if tool_name == "log_feedback":
            return "Workout feedback logged. Open Progress to see what FitEngine learned."
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

    def tool_matches_message(self, tool_name: str, message: str) -> bool:
        text = message.lower()
        if tool_name == "get_current_plan":
            return any(term in text for term in ["plan", "today", "week", "workout", "exercise"])
        if tool_name in {"explain_slot", "get_alternatives", "swap_exercise"}:
            return any(term in text for term in ["slot", "exercise", "swap", "alternative", "why"])
        if tool_name == "replan_session":
            return any(term in text for term in ["minute", "minutes", "time", "shorter", "only have"])
        if tool_name == "log_feedback":
            return any(term in text for term in ["log", "rpe", "completed", "skipped", "done"])
        return True

    def medical_red_flag(self, message: str) -> str | None:
        text = message.lower()
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
        if any(term in text for term in ["diagnose", "doctor", "medical advice", "is it safe with pain"]):
            return "I cannot give medical clearance. Please consult a qualified medical professional before training with pain or injury."
        return None

    def is_rpe_question(self, message: str) -> bool:
        text = message.lower()
        return "rpe" in text and not any(term in text for term in ["log", "logged", "completed", "skipped"])

    def is_swap_help(self, message: str) -> bool:
        text = message.lower()
        return "swap" in text and "slot" not in text

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
