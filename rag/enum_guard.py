# rag/enum_guard.py
from typing import Dict, List
from rag.enums import TRIGGERS, EVENTS, CONDITIONS, LOOPS


class EnumValidationError(ValueError):
    pass


def validate_judge_output(judge_json: Dict) -> None:
    """
    Hard validation of enums.
    Raises EnumValidationError on any invalid enum usage.
    """

    errors: List[str] = []

    # ---- Trigger ----
    for side in ("expected", "actual"):
        trigger = judge_json.get(side, {}).get("trigger")
        if trigger and trigger not in TRIGGERS:
            errors.append(f"{side}.trigger invalid: {trigger}")

    # ---- Events ----
    for side in ("expected", "actual"):
        events = judge_json.get(side, {}).get("events", [])
        if events is None:
            events = []
        if not isinstance(events, list):
            errors.append(f"{side}.events must be a list")
            events = []
        for ev in events:
            if ev not in EVENTS:
                errors.append(f"{side}.event invalid: {ev}")

    # ---- Conditions ----
    for side in ("expected", "actual"):
        cond = judge_json.get(side, {}).get("conditions", {}) or {}
        if not isinstance(cond, dict):
            errors.append(f"{side}.conditions must be an object")
            cond = {}
        ctype = cond.get("type")
        if ctype and ctype not in CONDITIONS:
            errors.append(f"{side}.condition invalid: {ctype}")

    # ---- Loops ----
    for side in ("expected", "actual"):
        loop = judge_json.get(side, {}).get("loops", {}) or {}
        if not isinstance(loop, dict):
            errors.append(f"{side}.loops must be an object")
            loop = {}
        ltype = loop.get("type")
        if ltype and ltype not in LOOPS:
            errors.append(f"{side}.loop invalid: {ltype}")

    if errors:
        raise EnumValidationError(
            "Enum validation failed:\n" + "\n".join(errors)
        )
