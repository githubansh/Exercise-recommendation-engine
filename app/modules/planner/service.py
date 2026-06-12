from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.models import Exercise, Plan, PlanDay, PlanSlot, User
from app.modules.catalog.constants import (
    FOCUS_GROUPS,
    HALF_VOLUME_GROUPS,
    PRESCRIPTIONS,
    PRIMARY_VOLUME_GROUPS,
    SIBLING_GROUP,
    STRETCH_PRESCRIPTION,
    TRAINABLE_GROUPS,
    VOLUME_TARGETS,
)
from app.modules.catalog.service import catalog_service
from app.modules.catalog.utils import lexical_similarity, mapped_groups, primary_group
from app.modules.safety.service import safety_service
from app.modules.scoring.service import scoring_service


@dataclass(frozen=True)
class Candidate:
    exercise: Exercise
    score: float


@dataclass
class SlotDraft:
    exercise: Exercise
    group: str
    sets: int
    reps: str
    rest_sec: int
    rpe_target: int
    score: float
    rationale_note: str = ""


class PlannerService:
    def generate_plan(
        self,
        db: Session,
        user_id: int,
        *,
        week_index: int = 1,
        days_override: int | None = None,
        mode_note: str | None = None,
        allow_progression: bool = False,
        deload: bool = False,
    ) -> Plan:
        user = db.get(User, user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")

        days_per_week = max(2, min(6, days_override or user.days_per_week))
        split, focuses = self.split_for_days(days_per_week)
        targets = self.volume_targets(user.level, user.goal)
        blocked_ids = safety_service.blocked_exercise_ids(db, user.id)
        candidates = self.candidate_pool(db, user, blocked_ids, allow_one_above=allow_progression)
        targets, aliases, feasibility_notes = self.apply_feasibility_ladder(targets, candidates)
        if mode_note:
            feasibility_notes.append(mode_note)

        prescription = dict(PRESCRIPTIONS[user.goal])
        if deload and prescription["sets"] > 2:
            prescription["sets"] -= 1

        planned_days: list[list[SlotDraft]] = []
        weekly_sets: dict[str, float] = {group: 0.0 for group in TRAINABLE_GROUPS}
        used_exercise_ids: set[str] = set()
        previous_groups: set[str] = set()

        for day_index, focus in enumerate(focuses, start=1):
            focus_groups = FOCUS_GROUPS[focus]
            slot_count = self.slots_for_session(user.minutes_per_session, prescription["sets"])
            day_slots: list[SlotDraft] = []
            day_group_counts: dict[str, int] = {}

            for _slot in range(slot_count):
                candidate = self.choose_candidate(
                    candidates,
                    focus_groups=focus_groups,
                    aliases=aliases,
                    weekly_sets=weekly_sets,
                    targets=targets,
                    used_exercise_ids=used_exercise_ids,
                    day_slots=day_slots,
                    day_group_counts=day_group_counts,
                    previous_groups=previous_groups,
                    full_body=(split == "full_body"),
                    prescription_sets=prescription["sets"],
                )
                if candidate is None:
                    candidate = self.choose_candidate(
                        candidates,
                        focus_groups=focus_groups,
                        aliases=aliases,
                        weekly_sets=weekly_sets,
                        targets=targets,
                        used_exercise_ids=used_exercise_ids,
                        day_slots=day_slots,
                        day_group_counts=day_group_counts,
                        previous_groups=set(),
                        full_body=True,
                        prescription_sets=prescription["sets"],
                        relax_volume=True,
                        relax_similarity=True,
                    )
                if candidate is None:
                    break
                group = self.planning_group(candidate.exercise, focus_groups, aliases)
                draft = SlotDraft(
                    exercise=candidate.exercise,
                    group=group,
                    sets=prescription["sets"],
                    reps=prescription["reps"],
                    rest_sec=prescription["rest_sec"],
                    rpe_target=prescription["rpe_target"],
                    score=candidate.score,
                    rationale_note="challenging - go slow" if allow_progression else "",
                )
                day_slots.append(draft)
                used_exercise_ids.add(candidate.exercise.id)
                self.add_contributions(weekly_sets, draft, aliases)
                day_group_counts[group] = day_group_counts.get(group, 0) + 1

            if user.goal != "mobility":
                self.append_stretch_if_time(candidates, focus_groups, aliases, day_slots, used_exercise_ids)
            self.sort_day_slots(day_slots)
            planned_days.append(day_slots)
            previous_groups = {slot.group for slot in day_slots}

        self.repair_volume(planned_days, targets, aliases, feasibility_notes)
        if allow_progression:
            self.apply_progression_sets(planned_days)
        plan = self.persist_plan(
            db,
            user=user,
            week_index=week_index,
            split=split,
            focuses=focuses,
            planned_days=planned_days,
            targets=targets,
            feasibility_notes=feasibility_notes,
            days_override=days_override,
            allow_progression=allow_progression,
            deload=deload,
        )
        db.commit()
        db.refresh(plan)
        return plan

    def split_for_days(self, days_per_week: int) -> tuple[str, list[str]]:
        if days_per_week <= 3:
            return "full_body", ["full"] * days_per_week
        if days_per_week == 4:
            return "upper_lower", ["upper", "lower", "upper", "lower"]
        sequence = ["push", "pull", "legs", "push", "pull", "legs"]
        return "ppl", sequence[:days_per_week]

    def volume_targets(self, level: str, goal: str) -> dict[str, tuple[int, int]]:
        if goal == "mobility":
            return {group: (0, 99) for group in TRAINABLE_GROUPS}
        base_min, base_max = VOLUME_TARGETS[level][goal]
        targets: dict[str, tuple[int, int]] = {}
        for group in PRIMARY_VOLUME_GROUPS:
            targets[group] = (base_min, base_max)
        for group in HALF_VOLUME_GROUPS:
            targets[group] = (ceil(base_min / 2), ceil(base_max / 2))
        targets["lower_back"] = (4, 6)
        return targets

    def candidate_pool(
        self,
        db: Session,
        user: User,
        blocked_ids: set[str],
        *,
        allow_one_above: bool = False,
    ) -> list[Candidate]:
        equipment = set(user.equipment or []) | {"body only"}
        categories = {"stretching"} if user.goal == "mobility" else {
            "strength",
            "plyometrics",
            "powerlifting",
            "olympic weightlifting",
            "strongman",
            "cardio",
        }
        exercises = catalog_service.list_by_filters(
            db,
            max_level=user.level,
            equipment=equipment,
            categories=categories,
            allow_one_above=allow_one_above,
        )
        candidates = [
            Candidate(exercise=exercise, score=scoring_service.utility(db, user, exercise, allow_one_above=allow_one_above))
            for exercise in exercises
            if exercise.id not in blocked_ids and exercise.muscle_groups
        ]
        return sorted(candidates, key=lambda item: (-item.score, item.exercise.id))

    def apply_feasibility_ladder(
        self,
        targets: dict[str, tuple[int, int]],
        candidates: list[Candidate],
    ) -> tuple[dict[str, tuple[int, int]], dict[str, str], list[str]]:
        targets = dict(targets)
        aliases: dict[str, str] = {}
        notes: list[str] = []
        primary_available = {group: 0 for group in TRAINABLE_GROUPS}
        secondary_available = {group: 0 for group in TRAINABLE_GROUPS}
        for candidate in candidates:
            exercise = candidate.exercise
            primary = primary_group(exercise)
            if primary:
                primary_available[primary] = primary_available.get(primary, 0) + 1
            for group in mapped_groups(exercise.secondary_muscles):
                secondary_available[group] = secondary_available.get(group, 0) + 1

        for group, (minimum, maximum) in list(targets.items()):
            if minimum <= 0:
                continue
            if primary_available.get(group, 0) > 0:
                achievable = primary_available[group] * PRESCRIPTIONS["hypertrophy"]["sets"]
                if achievable < minimum:
                    degraded = max(0, achievable)
                    targets[group] = (degraded, max(degraded, min(maximum, achievable)))
                    notes.append(f"Limited {group} options; target reduced to achievable {degraded} sets.")
                continue
            if secondary_available.get(group, 0) > 0:
                degraded = max(1, min(minimum, floor(secondary_available[group] * 0.5)))
                targets[group] = (degraded, max(degraded, min(maximum, degraded + 2)))
                notes.append(f"{group} will use secondary-muscle credit because no direct options are available.")
                continue
            sibling = SIBLING_GROUP.get(group)
            if sibling:
                aliases[group] = sibling
                targets[group] = (0, 0)
                notes.append(f"No direct {group} options available; folded into {sibling} for this plan.")
            else:
                targets[group] = (0, 0)
                notes.append(f"No safe/equipment-valid {group} options available; target lowered to 0.")
        return targets, aliases, notes

    def slots_for_session(self, minutes: int, sets: int) -> int:
        available = max(0, minutes - 8)
        avg_slot_minutes = sets * 3.5
        return max(2, min(8, floor(available / avg_slot_minutes)))

    def choose_candidate(
        self,
        candidates: list[Candidate],
        *,
        focus_groups: set[str],
        aliases: dict[str, str],
        weekly_sets: dict[str, float],
        targets: dict[str, tuple[int, int]],
        used_exercise_ids: set[str],
        day_slots: list[SlotDraft],
        day_group_counts: dict[str, int],
        previous_groups: set[str],
        full_body: bool,
        prescription_sets: int,
        relax_volume: bool = False,
        relax_similarity: bool = False,
    ) -> Candidate | None:
        eligible: list[tuple[float, float, int, Candidate]] = []
        for candidate in candidates:
            exercise = candidate.exercise
            if exercise.id in used_exercise_ids:
                continue
            group = self.planning_group(exercise, focus_groups, aliases)
            if group not in focus_groups:
                continue
            if day_group_counts.get(group, 0) >= 2:
                continue
            if previous_groups and self.violates_recovery(group, exercise, previous_groups, full_body):
                continue
            if not relax_similarity and any(lexical_similarity(exercise, slot.exercise) >= 0.80 for slot in day_slots):
                continue
            _minimum, maximum = targets.get(group, (0, 99))
            if not relax_volume and weekly_sets.get(group, 0) + prescription_sets > maximum:
                continue
            current = weekly_sets.get(group, 0.0)
            deficit = max(0, _minimum - current)
            relative_deficit = deficit / max(_minimum, 1)
            compound_bonus = 1 if exercise.mechanic == "compound" else 0
            eligible.append((relative_deficit, candidate.score, compound_bonus, candidate))
        if not eligible:
            return None
        return sorted(eligible, key=lambda item: (-item[0], -item[1], -item[2], item[3].exercise.id))[0][3]

    def slot_contributions(self, slot: SlotDraft, aliases: dict[str, str]) -> dict[str, float]:
        contributions: dict[str, float] = {slot.group: float(slot.sets)}
        for group in mapped_groups(slot.exercise.secondary_muscles):
            group = aliases.get(group, group)
            if group != slot.group:
                contributions[group] = contributions.get(group, 0.0) + slot.sets * 0.5
        return contributions

    def add_contributions(self, weekly_sets: dict[str, float], slot: SlotDraft, aliases: dict[str, str]) -> None:
        for group, sets in self.slot_contributions(slot, aliases).items():
            weekly_sets[group] = weekly_sets.get(group, 0.0) + sets

    def compute_weekly_sets(self, planned_days: list[list[SlotDraft]], aliases: dict[str, str]) -> dict[str, float]:
        weekly_sets: dict[str, float] = {group: 0.0 for group in TRAINABLE_GROUPS}
        for day in planned_days:
            for slot in day:
                self.add_contributions(weekly_sets, slot, aliases)
        return weekly_sets

    def planning_group(self, exercise: Exercise, focus_groups: set[str], aliases: dict[str, str]) -> str:
        primary = primary_group(exercise)
        if primary:
            primary = aliases.get(primary, primary)
        if primary in focus_groups:
            return primary
        for group in sorted(mapped_groups(exercise.secondary_muscles)):
            group = aliases.get(group, group)
            if group in focus_groups:
                return group
        return primary or (exercise.muscle_groups[0] if exercise.muscle_groups else "abs")

    def violates_recovery(self, group: str, exercise: Exercise, previous_groups: set[str], full_body: bool) -> bool:
        if full_body:
            return group in previous_groups and primary_group(exercise) == group
        return group in previous_groups

    def append_stretch_if_time(
        self,
        candidates: list[Candidate],
        focus_groups: set[str],
        aliases: dict[str, str],
        day_slots: list[SlotDraft],
        used_exercise_ids: set[str],
    ) -> None:
        if len(day_slots) >= 8:
            return
        for candidate in candidates:
            exercise = candidate.exercise
            if exercise.category != "stretching" or exercise.id in used_exercise_ids:
                continue
            group = self.planning_group(exercise, focus_groups, aliases)
            if group not in focus_groups:
                continue
            day_slots.append(
                SlotDraft(
                    exercise=exercise,
                    group=group,
                    sets=STRETCH_PRESCRIPTION["sets"],
                    reps=STRETCH_PRESCRIPTION["reps"],
                    rest_sec=STRETCH_PRESCRIPTION["rest_sec"],
                    rpe_target=STRETCH_PRESCRIPTION["rpe_target"],
                    score=candidate.score,
                    rationale_note="mobility finisher",
                )
            )
            used_exercise_ids.add(exercise.id)
            return

    def sort_day_slots(self, slots: list[SlotDraft]) -> None:
        slots.sort(key=lambda slot: (slot.exercise.mechanic != "compound", slot.exercise.category == "stretching", -slot.score, slot.exercise.id))

    def repair_volume(
        self,
        planned_days: list[list[SlotDraft]],
        targets: dict[str, tuple[int, int]],
        aliases: dict[str, str],
        notes: list[str],
    ) -> None:
        for _ in range(10):
            weekly_sets = self.compute_weekly_sets(planned_days, aliases)
            changed = False
            for group, (minimum, maximum) in targets.items():
                if maximum == 0:
                    continue
                current = weekly_sets.get(group, 0)
                if current < minimum:
                    slot = self.find_slot_for_group(planned_days, group, prefer_low_sets=True)
                    if slot and slot.sets < 5:
                        slot.sets += 1
                        changed = True
                elif current > maximum:
                    slot = self.find_slot_for_group(planned_days, group, prefer_low_sets=False)
                    if slot and slot.sets > 1:
                        slot.sets -= 1
                        changed = True
            if not changed:
                break

        weekly_sets = self.compute_weekly_sets(planned_days, aliases)
        for group, (minimum, _maximum) in targets.items():
            if minimum > 0 and weekly_sets.get(group, 0) < minimum:
                actual = round(weekly_sets.get(group, 0), 1)
                notes.append(f"Unmet {group} volume: {actual}/{minimum} sets after repair.")

    def apply_progression_sets(self, planned_days: list[list[SlotDraft]]) -> None:
        compounds = [
            slot
            for day in planned_days
            for slot in day
            if slot.exercise.mechanic == "compound" and slot.sets < 5
        ]
        for slot in sorted(compounds, key=lambda item: (-item.score, item.exercise.id))[:2]:
            slot.sets += 1
            slot.rationale_note = f"{slot.rationale_note}, progressed +1 set".strip(", ")

    def find_slot_for_group(
        self,
        planned_days: list[list[SlotDraft]],
        group: str,
        *,
        prefer_low_sets: bool,
    ) -> SlotDraft | None:
        slots = [slot for day in planned_days for slot in day if slot.group == group]
        if not slots:
            return None
        return sorted(slots, key=lambda slot: (slot.sets, slot.score), reverse=not prefer_low_sets)[0]

    def persist_plan(
        self,
        db: Session,
        *,
        user: User,
        week_index: int,
        split: str,
        focuses: list[str],
        planned_days: list[list[SlotDraft]],
        targets: dict[str, tuple[int, int]],
        feasibility_notes: list[str],
        days_override: int | None,
        allow_progression: bool,
        deload: bool,
    ) -> Plan:
        params = {
            "seed": settings.random_seed,
            "targets": {group: {"min": values[0], "max": values[1]} for group, values in targets.items()},
            "feasibility_notes": feasibility_notes,
            "days_override": days_override,
            "allow_progression": allow_progression,
            "deload": deload,
            "disclaimer": "Not medical advice - consult a qualified professional for injuries or pain.",
        }
        if user.goal in {"fat_loss", "endurance"}:
            params["conditioning_blocks"] = self.conditioning_blocks(user.goal, user.minutes_per_session)
        db.query(Plan).filter(Plan.user_id == user.id, Plan.status == "active").update({"status": "replaced"})
        plan = Plan(user_id=user.id, week_index=week_index, split=split, params=params)
        db.add(plan)
        db.flush()
        for day_index, (focus, slots) in enumerate(zip(focuses, planned_days, strict=True), start=1):
            day = PlanDay(plan_id=plan.id, day_index=day_index, focus=focus)
            db.add(day)
            db.flush()
            for slot_index, slot in enumerate(slots, start=1):
                target = targets.get(slot.group, (0, 0))
                note = f", {slot.rationale_note}" if slot.rationale_note else ""
                rationale = (
                    f"{slot.exercise.name}: targets {slot.group} "
                    f"({slot.sets}/{target[0]} minimum weekly sets), "
                    f"{slot.exercise.level} level matches you, {slot.exercise.equipment} available{note}"
                )
                db.add(
                    PlanSlot(
                        plan_day_id=day.id,
                        slot_index=slot_index,
                        exercise_id=slot.exercise.id,
                        sets=slot.sets,
                        reps=slot.reps,
                        rest_sec=slot.rest_sec,
                        rpe_target=slot.rpe_target,
                        rationale=rationale,
                    )
                )
        return plan

    def conditioning_blocks(self, goal: str, minutes_per_session: int) -> list[dict[str, str | int]]:
        if goal == "fat_loss":
            return [
                {
                    "type": "intervals",
                    "description": "8 rounds of 30s brisk effort / 60s easy recovery after strength work.",
                    "minutes": min(16, max(8, minutes_per_session // 3)),
                }
            ]
        if goal == "endurance":
            return [
                {
                    "type": "liss",
                    "description": "Conversational-pace walking, cycling, or rowing block.",
                    "minutes": min(30, max(12, minutes_per_session // 2)),
                }
            ]
        return []


planner_service = PlannerService()
