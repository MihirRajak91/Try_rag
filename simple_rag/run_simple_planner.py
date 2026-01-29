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
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))


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
        "## End with exactly '- End' (the bullet line is required; do not leave End blank). "
        "## Steps must be a numbered list (1., 2., 3., ...), no bullet lists. "
        "If the prompt includes CONDITIONS ENFORCEMENT, then ## Steps must be exactly: "
        "1. CNDN_BIN or 1. CNDN_SEQ or 1. CNDN_DOM, and MUST NOT list any EVNT_* steps. "
        "If conditions are present, EVNT_* must appear only inside ## Conditions. "
        "Only include a ## Conditions section (and any CNDN_*) if the prompt explicitly requires it. "
        "Only include a ## Loops section if the prompt explicitly requires it. "
        "If loops are required, put loop content ONLY inside ## Loops and do NOT add 'Loop End'. "
        "When ## Loops is required, format it as: "
        "a bullet line '- EVNT_LOOP_*' (or '- EVNT_LOOP_FOR (count: N)') followed by "
        "a line starting with '↳ INSIDE LOOP: <EVNT_* ...>'. "
        "If the query says 'at least once', use EVNT_LOOP_DOWHILE in ## Loops (not Conditions). "
        "If the query says 'do while', use EVNT_LOOP_DOWHILE in ## Loops (not Conditions). "
        "If LOOP_ONLY is required, omit ## Steps entirely and use only ## Loops. "
        "NEVER put EVNT_LOOP_* inside ## Steps. Loop content must appear only under ## Loops. "
        "Do NOT use ## Loops unless the query explicitly mentions repetition (e.g., 'times', 'repeat', 'loop', "
        "'for each', 'for every', 'from X to Y'). "
        "Never infer loops from words like 'when' or 'if'. If there is no explicit repetition, "
        "do NOT use EVNT_LOOP_* and do NOT include ## Loops. "
        "Do NOT wrap CRUD actions (EVNT_RCRD_*) in loops unless the query explicitly asks for repetition. "
        "If no notification channel is specified, choose ONLY EVNT_NOTI_NOTI (system notification). "
        "If the query explicitly mentions a channel, you MUST use the matching event: "
        "webhook→EVNT_NOTI_WBH, push→EVNT_NOTI_PUSH, in-app/system notification→EVNT_NOTI_NOTI, "
        "email→EVNT_NOTI_MAIL, sms/text→EVNT_NOTI_SMS. "
        "Do NOT include EVNT_RCRD_* actions when the record change is only the trigger for a notification. "
        "If the request is notification-only, include ONLY EVNT_NOTI_* steps. "
        "If multiple channels are requested, include each as its own step in order. "
        "If the request is retrieval-only (list/get/search/filter/select fields), "
        "do NOT include ## Loops or ## Conditions; use only EVNT_RCRD_INFO / EVNT_FLTR / EVNT_JMES in ## Steps. "
        "Always include the ## End section as the final section with exactly two lines:\n"
        "## End\n- End\n"
        "Never output a bare '- End' line unless it is directly under a '## End' header. "
        "Never put '- End' outside ## End. "
        "The line '## End' must appear immediately before the '- End' line. "
        "Include exactly ONE '## End' header. "
        "Never output a bare 'Start' line; it must be exactly '- Start' under ## Start. "
        "Use ## Conditions only when the user explicitly asks for branching or mutually exclusive outcomes. "
        "If you include ## Conditions, then ## Steps MUST be exactly one line: '1. CNDN_BIN' or '1. CNDN_SEQ' or '1. CNDN_DOM'. "
        "When ## Conditions is present, do NOT list any EVNT_* steps in ## Steps. "
        "If the request is notification-only, use EVNT_NOTI_* events only. "
        "If a specific channel is mentioned, output ONLY that channel (do NOT add EVNT_NOTI_NOTI). "
        "If the user asks for multiple notification channels (e.g., email + sms), "
        "include each channel as its own step under ## Steps. "
        "If META.STATIC_ONLY appears in the prompt, you MUST use ONLY _STC events and must NOT use dynamic EVNT_RCRD_* events. "
        "If the query mentions role/roles/department/departments, use ONLY _STC events (static), "
        "e.g., EVNT_RCRD_DUP_STC / EVNT_RCRD_DEL_STC / EVNT_RCRD_UPDT_STC / EVNT_RCRD_ADD_STC / EVNT_RCRD_REST_STC. "
        "When using _STC actions, do NOT add EVNT_FLTR or any sub-bullets under ## Steps. "
        "User management updates (e.g., update user email/name/role) must be a direct EVNT_USER_MGMT_UPDT step, "
        "not a condition or branch. "
        "If the query mentions updating a user, you MUST NOT output any CNDN_* or ## Conditions. "
        "## Steps must be numbered single-line items only; do NOT add sub-bullets under Steps. "
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

    normalized = normalize_plan(raw_plan, query_text=q)

    print("\n=== PLANNER OUTPUT ===\n")
    print(normalized)


if __name__ == "__main__":
    main()
