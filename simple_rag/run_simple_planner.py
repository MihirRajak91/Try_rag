# simple_rag/run_simple_planner.py
import os
import sys
from pathlib import Path
import re
from dotenv import load_dotenv
from openai import OpenAI

# Ensure project root is on sys.path when running as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simple_rag.simple_assembler import build_prompt  # noqa: E402
from simple_rag.plan_normalizer import normalize_plan  # noqa: E402

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))


def main() -> None:
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    prompt = build_prompt(q)
    require_conditions = "CONDITIONS ENFORCEMENT (HARD RULES)" in prompt
    ql_for_conditions = f" {q.lower()} "
    if (" if " in ql_for_conditions) and (" else " in ql_for_conditions or " otherwise " in ql_for_conditions):
        require_conditions = True
    require_loops = "LOOPS ENFORCEMENT (HARD RULES)" in prompt
    require_notification_only = "META.NOTIFICATION_ONLY" in prompt
    require_static_only = "META.STATIC_ONLY" in prompt
    require_loop_only = "META.LOOP_ONLY" in prompt

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_msg = (
        "You are a precise workflow planner. Output Markdown only. "
        "You MUST follow the prompt exactly and comply with format rules. "
        "If sections are required, use exact headers and bullets: "
        "## Trigger with exactly one bullet '- TRG_*', "
        "## Start with exactly '- Start', "
        "## End with exactly '- End'. "
        "## Steps must be a numbered list (1., 2., 3., ...), no bullet lists. "
        "If the prompt includes CONDITIONS ENFORCEMENT, then ## Steps must be exactly: "
        "1. CNDN_BIN or 1. CNDN_SEQ or 1. CNDN_DOM, and MUST NOT list any EVNT_* steps. "
        "If conditions are present, EVNT_* must appear only inside ## Conditions. "
        "Only include a ## Conditions section (and any CNDN_*) if the prompt explicitly requires it. "
        "Only include a ## Loops section if the prompt explicitly requires it. "
        "If loops are required, put loop content ONLY inside ## Loops and do NOT add 'Loop End'. "
        "If no notification channel is specified, choose ONLY EVNT_NOTI_NOTI (system notification). "
        "If the query explicitly mentions a channel, you MUST use the matching event: "
        "webhook→EVNT_NOTI_WBH, push→EVNT_NOTI_PUSH, in-app/system notification→EVNT_NOTI_NOTI, "
        "email→EVNT_NOTI_MAIL, sms/text→EVNT_NOTI_SMS. "
        "Do NOT include EVNT_RCRD_* actions when the record change is only the trigger for a notification. "
        "Do not add extra text outside required sections."
    )

    resp = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
    )

    raw_plan = resp.choices[0].message.content
    loop_count = None
    loop_kind = "EVNT_LOOP_FOR"
    if require_loops:
        ql = q.lower()
        if "at least once" in ql or "do once" in ql:
            loop_kind = "EVNT_LOOP_DOWHILE"
        elif "while " in ql or ql.startswith("while"):
            loop_kind = "EVNT_LOOP_WHILE"
        elif "do while" in ql or ("do " in ql and " while " in ql):
            loop_kind = "EVNT_LOOP_DOWHILE"
        m = re.search(r"\b(\d+)\b", q)
        if m:
            loop_count = m.group(1)

    normalized = normalize_plan(
        raw_plan,
        require_conditions=require_conditions,
        require_loops=require_loops,
        require_notification_only=require_notification_only,
        require_static_only=require_static_only,
        require_loop_only=require_loop_only,
        query_text=q,
        loop_kind=loop_kind,
        loop_count=loop_count,
    )

    print("\n=== PLANNER OUTPUT ===\n")
    print(normalized)


if __name__ == "__main__":
    main()
