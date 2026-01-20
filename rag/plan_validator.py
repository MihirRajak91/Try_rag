# rag/plan_validator.py
import re
from typing import List, Dict

SECTION_ORDER = ["## Trigger", "## Start", "## Steps", "## End"]

TRG_RE = re.compile(r"^\s*-\s*(TRG_[A-Z_]+)\s*$", re.MULTILINE)
EVNT_RE = re.compile(r"\bEVNT_[A-Z0-9_]+\b")

def validate_plan_output(plan_md: str) -> Dict:
    """
    Validates the LLM output (Markdown workflow plan) against basic contract rules.
    Returns a dict:
      { "ok": bool, "errors": [..], "warnings": [..] }
    """
    errors: List[str] = []
    warnings: List[str] = []
    text = (plan_md or "").strip()

    if not text:
        return {"ok": False, "errors": ["Output is empty."], "warnings": []}

    # Must be Markdown with at least Trigger/Steps
    if "## Trigger" not in text:
        errors.append("Missing section: ## Trigger")
    if "## Steps" not in text:
        errors.append("Missing section: ## Steps")
    if "## End" not in text:
        errors.append("Missing section: ## End")

    # Section order check (only for those present)
    positions = []
    for s in SECTION_ORDER:
        idx = text.find(s)
        if idx != -1:
            positions.append((s, idx))
    if positions:
        sorted_positions = sorted(positions, key=lambda x: x[1])
        if [s for s, _ in sorted_positions] != [s for s, _ in positions]:
            errors.append("Sections are out of order. Expected: Trigger → Start → Steps → End.")

    # Trigger must include TRG_*
    if "## Trigger" in text:
        m = TRG_RE.search(text)
        if not m:
            errors.append("Trigger section must include a line like: - TRG_DB (or another TRG_*)")

    # Steps must be numbered and include at least one EVNT_*
    if "## Steps" in text:
        # basic numbered steps
        step_lines = re.findall(r"^\s*\d+\.\s+.+$", text, flags=re.MULTILINE)
        if not step_lines:
            errors.append("Steps section must contain numbered steps like: 1. EVNT_* ...")

        # EVNT presence
        if not EVNT_RE.search(text):
            errors.append("No EVNT_* event found. Steps must include at least one EVNT_* code.")

    # If Conditions section exists, enforce TRUE/FALSE blocks (binary contract)
    if "## Conditions" in text:
        if "IF TRUE" not in text or "IF FALSE" not in text:
            errors.append("Conditions section must include both IF TRUE and IF FALSE blocks.")

    # Light safety: discourage tool/meta chatter
    forbidden_phrases = ["json", "tool", "Action:", "Thought:", "Observation:"]
    if any(p.lower() in text.lower() for p in forbidden_phrases):
        warnings.append("Output contains meta/tooling text. Should be pure Markdown workflow plan.")

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings}
