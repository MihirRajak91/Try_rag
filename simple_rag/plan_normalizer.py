"""Normalize planner output to enforce the minimal output contract."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

SECTION_RE = re.compile(r"^##\s+(\w+)", re.IGNORECASE)


@dataclass
class ParsedPlan:
    sections: Dict[str, List[str]]  # section -> lines (without section header)
    order: List[str]


def _split_sections(text: str) -> ParsedPlan:
    sections: Dict[str, List[str]] = {}
    order: List[str] = []

    current = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = SECTION_RE.match(line.strip())
        if m:
            current = m.group(1).capitalize()
            if current not in sections:
                sections[current] = []
                order.append(current)
            continue
        if current is None:
            continue
        sections[current].append(line)

    return ParsedPlan(sections=sections, order=order)


def _ensure_single_bullet(line: str) -> str:
    s = line.strip()
    if s.startswith("-"):
        return "- " + s.lstrip("- ")
    return "- " + s


def _normalize_trigger(lines: List[str]) -> List[str]:
    # Always return exactly one bullet for TRG_DB if anything is missing/invalid.
    for ln in lines:
        if "TRG_" in ln:
            token = ln.strip().lstrip("- ").split()[0]
            return [_ensure_single_bullet(token)]
    return ["- TRG_DB"]


def _normalize_start(lines: List[str]) -> List[str]:
    return ["- Start"]


def _normalize_end(lines: List[str]) -> List[str]:
    return ["- End"]


def _detect_cndn_type(conditions_lines: List[str]) -> str:
    # Prefer explicit CNDN_* markers if present.
    joined = "\n".join(conditions_lines)
    for t in ("CNDN_BIN", "CNDN_SEQ", "CNDN_DOM"):
        if t in joined:
            return t
    return "CNDN_BIN"


def _strip_evnt_lines(lines: List[str]) -> List[str]:
    return [ln for ln in lines if "EVNT_" not in ln]


def _normalize_steps_for_conditions(cndn_type: str) -> List[str]:
    return [f"1. {cndn_type}"]


def _extract_loop_block(text: str) -> List[str]:
    # Best-effort: pull any lines containing EVNT_LOOP or INSIDE LOOP.
    out = []
    for ln in text.splitlines():
        if "EVNT_LOOP" in ln or "INSIDE LOOP" in ln:
            out.append(ln.strip())
    return out


def _normalize_loops(loop_lines: List[str], *, loop_kind: str = "EVNT_LOOP_FOR", count: str | None = None) -> List[str]:
    # Ensure bullet format with EVNT_LOOP_*.
    count_txt = f" (count: {count})" if (count and loop_kind == "EVNT_LOOP_FOR") else ""
    out = [f"- {loop_kind}{count_txt}"]
    # Preserve any INSIDE LOOP action if present.
    inside = None
    for ln in loop_lines:
        if "INSIDE LOOP" in ln:
            inside = ln.strip()
            break
    if not inside:
        inside = "↳ INSIDE LOOP: <EVNT_* ...>"
    out.append(inside)
    return out


def normalize_plan(
    plan: str,
    *,
    require_conditions: bool = False,
    require_loops: bool = False,
    require_notification_only: bool = False,
    require_static_only: bool = False,
    loop_kind: str = "EVNT_LOOP_FOR",
    loop_count: str | None = None,
) -> str:
    parsed = _split_sections(plan)
    sections = parsed.sections

    # Normalize Trigger/Start/End always
    sections["Trigger"] = _normalize_trigger(sections.get("Trigger", []))
    sections["Start"] = _normalize_start(sections.get("Start", []))
    sections["End"] = _normalize_end(sections.get("End", []))

    # If conditions required, enforce Steps = CNDN_* and remove EVNT from Steps
    if require_conditions:
        cndn_type = _detect_cndn_type(sections.get("Conditions", []))
        sections["Steps"] = _normalize_steps_for_conditions(cndn_type)
        # Ensure Conditions header exists
        if "Conditions" not in sections:
            sections["Conditions"] = [f"### {cndn_type}", "- IF TRUE:", "  ↳ <EVNT_* ...>", "- IF FALSE:", "  ↳ Route to END"]
    else:
        # If not required, strip accidental Conditions section
        if "Conditions" in sections:
            sections.pop("Conditions", None)

    # If notification-only, remove non-notification EVNT_* steps
    if require_notification_only and "Steps" in sections:
        kept = []
        for ln in sections["Steps"]:
            if "EVNT_NOTI_" in ln:
                kept.append(ln)
        if kept:
            sections["Steps"] = kept

    # If user info is requested, prefer EVNT_USER_MGMT_INFO over record info
    if "Steps" in sections:
        has_user_info = any("EVNT_RCRD_INFO_STC" in ln for ln in sections["Steps"])
        if has_user_info:
            sections["Steps"] = [
                ("1. EVNT_USER_MGMT_INFO" if "EVNT_RCRD_INFO_STC" in ln else ln)
                for ln in sections["Steps"]
            ]

    # Clean stray End lines from Steps
    if "Steps" in sections:
        sections["Steps"] = [ln for ln in sections["Steps"] if "End" not in ln]

    # If EVNT_FLTR is present, drop EVNT_RCRD_INFO to avoid redundant retrieval steps
    if "Steps" in sections:
        has_fltr = any("EVNT_FLTR" in ln for ln in sections["Steps"])
        if has_fltr:
            sections["Steps"] = [ln for ln in sections["Steps"] if "EVNT_RCRD_INFO" not in ln]

    # If webhook notification is an action, force TRG_DB (webhook is not a trigger here)
    def _has_webhook_action() -> bool:
        for sec in ("Steps", "Conditions", "Loops"):
            for ln in sections.get(sec, []):
                if "EVNT_NOTI_WBH" in ln:
                    return True
        return False

    if _has_webhook_action():
        sections["Trigger"] = ["- TRG_DB"]

    # If static-only, rewrite EVNT_RCRD_* to EVNT_RCRD_*_STC
    if require_static_only:
        def _to_static(line: str) -> str:
            m = re.findall(r"EVNT_RCRD_(ADD|UPDT|DEL|REST|DUP|INFO)", line)
            if not m:
                return line
            for t in m:
                if f"EVNT_RCRD_{t}_STC" in line:
                    continue
                line = line.replace(f"EVNT_RCRD_{t}", f"EVNT_RCRD_{t}_STC")
            return line

        for sec in ("Steps", "Conditions", "Loops"):
            if sec in sections:
                sections[sec] = [_to_static(ln) for ln in sections[sec]]

    # If loops required, enforce Loops section and remove Steps if no other steps
    if require_loops:
        loop_lines = sections.get("Loops", [])
        # Try to recover loop lines from Steps if needed
        if not loop_lines:
            loop_lines = _extract_loop_block("\n".join(sections.get("Steps", [])))
        sections["Loops"] = _normalize_loops(loop_lines, loop_kind=loop_kind, count=loop_count)
        # Remove steps if they only contain loop info
        steps = sections.get("Steps", [])
        steps = [ln for ln in steps if "EVNT_LOOP" not in ln and "Loop End" not in ln]
        if not steps:
            sections.pop("Steps", None)
        else:
            sections["Steps"] = steps
    else:
        if "Loops" in sections:
            sections.pop("Loops", None)

    # Rebuild output in canonical order
    order = ["Trigger", "Start", "Steps", "Conditions", "Loops", "End"]
    out_lines: List[str] = []
    for sec in order:
        if sec not in sections:
            continue
        out_lines.append(f"## {sec}")
        out_lines.extend([ln for ln in sections[sec] if ln.strip() != ""])
        out_lines.append("")

    return "\n".join(out_lines).rstrip() + "\n"
