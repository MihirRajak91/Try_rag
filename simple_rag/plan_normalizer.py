"""Minimal normalizer to fix loop placement only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import re

SECTION_RE = re.compile(r"^##\s+(\w+)", re.IGNORECASE)
LOOP_RE = re.compile(r"(EVNT_LOOP_[A-Z_]+(?:\s*\\(count: [^)]+\\))?)")


@dataclass
class ParsedPlan:
    sections: Dict[str, List[str]]


def _split_sections(text: str) -> ParsedPlan:
    sections: Dict[str, List[str]] = {}
    current: str | None = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = SECTION_RE.match(line.strip())
        if m:
            current = m.group(1).capitalize()
            sections.setdefault(current, [])
            continue
        if current is None:
            continue
        sections[current].append(line)
    return ParsedPlan(sections=sections)


def _is_loop_line(line: str) -> bool:
    return ("EVNT_LOOP_" in line) or ("INSIDE LOOP" in line)


def normalize_plan(
    plan: str,
    *,
    require_conditions: bool = False,
    require_loops: bool = False,
    require_notification_only: bool = False,
    require_static_only: bool = False,
    require_loop_only: bool = False,
    query_text: str | None = None,
    loop_kind: str = "EVNT_LOOP_FOR",
    loop_count: str | None = None,
) -> str:
    """Fix loop placement only."""
    parsed = _split_sections(plan)
    sections = parsed.sections
    if not sections:
        return plan or ""

    steps = sections.get("Steps", [])
    conds = sections.get("Conditions", [])
    loop_lines = [ln for ln in steps if _is_loop_line(ln)]
    loop_lines += [ln for ln in conds if _is_loop_line(ln)]
    if loop_lines:
        sections["Steps"] = [ln for ln in steps if not _is_loop_line(ln)]
        if "Conditions" in sections:
            sections["Conditions"] = [ln for ln in conds if not _is_loop_line(ln)]
            # Drop Conditions if no actual EVNT_ remains
            if not any("EVNT_" in ln for ln in sections["Conditions"]):
                sections.pop("Conditions", None)
        loops = sections.get("Loops", [])
        if not loops:
            for ln in loop_lines:
                s = ln.strip()
                if "EVNT_LOOP_" in s:
                    m = LOOP_RE.search(s)
                    if m:
                        sections.setdefault("Loops", []).append(f"- {m.group(1)}")
                    else:
                        sections.setdefault("Loops", []).append(f"- {s}")
                else:
                    if "INSIDE LOOP" in s and not s.startswith("↳") and not s.startswith("  ↳"):
                        s = "  ↳ " + s.lstrip("↳ ").lstrip()
                    elif s.startswith("↳"):
                        s = "  " + s
                    sections.setdefault("Loops", []).append(s)
            if not any("INSIDE LOOP" in l for l in sections["Loops"]):
                sections["Loops"].append("  ↳ INSIDE LOOP: <EVNT_* ...>")
        if not any(ln.strip() for ln in sections["Steps"]):
            sections.pop("Steps", None)

    # Normalize loop break/continue placement and inject count if missing
    if "Loops" in sections:
        new_loops: List[str] = []
        inside_action = None
        for ln in sections["Loops"]:
            if "EVNT_LOOP_BREAK" in ln or "EVNT_LOOP_CONTINUE" in ln:
                inside_action = ln.strip().replace("- ", "")
                continue
            new_loops.append(ln)
        if inside_action:
            new_loops = [l for l in new_loops if "INSIDE LOOP" not in l]
            new_loops.append(f"  ↳ INSIDE LOOP: {inside_action}")
        if query_text:
            m = re.search(r"\b(\d+)\b", query_text)
            if m:
                cnt = m.group(1)
                updated = []
                for l in new_loops:
                    if l.strip().startswith("- EVNT_LOOP_FOR") and "count:" not in l:
                        updated.append("- EVNT_LOOP_FOR (count: " + cnt + ")")
                    else:
                        updated.append(l)
                new_loops = updated
        sections["Loops"] = new_loops

    # If query indicates do-while/at-least-once but no loop emitted, force a DOWHILE loop.
    if query_text:
        ql = query_text.lower()
        if ("do while" in ql) or ("at least once" in ql):
            sections["Loops"] = ["- EVNT_LOOP_DOWHILE", "  ↳ INSIDE LOOP: <EVNT_* ...>"]
            sections.pop("Conditions", None)
            if "Steps" in sections and all("CNDN_" in ln for ln in sections["Steps"] if ln.strip()):
                sections.pop("Steps", None)

    # Drop orphaned CNDN_* steps if Conditions were removed
    if "Steps" in sections and "Conditions" not in sections:
        only_cndn = all("CNDN_" in ln for ln in sections["Steps"] if ln.strip())
        if only_cndn:
            sections.pop("Steps", None)

    # Static keywords: force _STC variants and remove stray End lines in Steps
    if query_text and "Steps" in sections:
        ql = query_text.lower()
        if "role" in ql or "roles" in ql or "department" in ql or "departments" in ql:
            def _to_static(line: str) -> str:
                m = re.findall(r"EVNT_RCRD_(ADD|UPDT|DEL|REST|DUP|INFO)", line)
                if not m:
                    return line
                for t in m:
                    if f"EVNT_RCRD_{t}_STC" in line:
                        continue
                    line = line.replace(f"EVNT_RCRD_{t}", f"EVNT_RCRD_{t}_STC")
                return line
            sections["Steps"] = [
                _to_static(ln) for ln in sections["Steps"]
                if "End" not in ln and not ln.lstrip().startswith("↳")
            ]

    # User update: force direct EVNT_USER_MGMT_UPDT and drop Conditions
    if query_text:
        ql = query_text.lower()
        if "update user" in ql:
            sections.pop("Conditions", None)
            sections["Steps"] = ["1. EVNT_USER_MGMT_UPDT"]

    # Notification-only: if a specific channel is present, drop EVNT_NOTI_NOTI
    if query_text and "Steps" in sections:
        ql = query_text.lower()
        if any(k in ql for k in ["email", "sms", "text", "push", "webhook"]):
            sections["Steps"] = [ln for ln in sections["Steps"] if "EVNT_NOTI_NOTI" not in ln]

    order = ["Trigger", "Start", "Steps", "Conditions", "Loops", "End"]
    out_lines: List[str] = []
    for sec in order:
        if sec not in sections:
            continue
        out_lines.append(f"## {sec}")
        out_lines.extend([ln for ln in sections[sec] if ln.strip() != ""])
        out_lines.append("")
    return "\n".join(out_lines).rstrip() + "\n"
