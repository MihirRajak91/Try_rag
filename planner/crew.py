# planner/crew.py
from crewai import Agent, Task, Crew, Process
from planner.tools import AssemblePromptTool, JudgePlanTool

from planner.judge_context import (
    TRIGGERS_ENUMS, EVENT_ENUMS, CONDITION_ENUMS, LOOP_ENUMS, JUDGE_RULES
)


assemble_tool = AssemblePromptTool()
judge_tool = JudgePlanTool()

assembler_agent = Agent(
    role="Prompt Assembler Agent",
    goal="Assemble the final planner prompt JSON using the internal RAG pipeline.",
    backstory="You only assemble prompts using tools. Return tool output exactly.",
    tools=[assemble_tool],
    verbose=True,
)

planner_agent = Agent(
    role="Workflow Planner Agent",
    goal="Generate a correct workflow plan in Markdown for enterprise automation.",
    backstory="Follow the provided prompt strictly. No tools available.",
    tools=[],  # hard guarantee: no tool calls
    verbose=True,
)

validator_agent = Agent(
    role="Workflow Plan Judge",
    goal="Decide whether the workflow plan is correct for the given user query.",
    backstory=(
        "You are a strict judge. You do not rewrite plans. "
        "You compare expected vs actual usage of triggers, events, conditions, and loops. "
        "You return JSON only."
    ),
    tools=[judge_tool],
    verbose=True,
    temperature=0,
)


refiner_agent = Agent(
    role="Workflow Plan Refiner Agent",
    goal="If validation fails, minimally repair the plan to satisfy the contract; otherwise return it unchanged.",
    backstory="You only output the final corrected Markdown workflow plan. No tools available.",
    tools=[],  # hard guarantee: no tool calls
    verbose=True,
)

t1_assemble = Task(
    description=(
        "Call the tool assemble_prompt with this exact user query:\n\n"
        "{query}\n\n"
        "Return ONLY the raw JSON string from the tool. Do NOT wrap it in code fences."
    ),
    agent=assembler_agent,
    expected_output="JSON string with at least: prompt, routing, manifest_path, audit.",
)

t2_draft = Task(
    description=(
        "Use ONLY the JSON output from the previous task.\n"
        "1) Parse the JSON.\n"
        "2) Extract `prompt`.\n"
        "3) Follow that prompt and generate the workflow plan in Markdown.\n"
        "Do not mention JSON. Output ONLY the Markdown plan."
    ),
    agent=planner_agent,
    expected_output="Markdown workflow plan.",
)

t3_validate = Task(
    description=(
        "You must call the tool: judge_plan.\n\n"
        "ABSOLUTE RULES:\n"
        "1) Call judge_plan exactly ONCE.\n"
        "2) Use the inputs below EXACTLY. Every value must be a plain string.\n"
        "3) Your final output MUST be exactly the tool's raw JSON output string.\n"
        "   - No extra text.\n"
        "   - No code fences.\n"
        "   - No Thought/Action formatting.\n"
        "   - Do not rephrase, summarize, or add keys.\n\n"
        "INPUTS (plain strings):\n"
        "query: {query}\n\n"
        "plan_markdown:\n{plan_markdown}\n\n"
        f"triggers: {TRIGGERS_ENUMS}\n\n"
        f"events: {EVENT_ENUMS}\n\n"
        f"conditions: {CONDITION_ENUMS}\n\n"
        f"loops: {LOOP_ENUMS}\n\n"
        f"rules:\n{JUDGE_RULES}\n\n"
        "IMPORTANT:\n"
        "- Do NOT pass objects like {\"description\": ..., \"type\": ...}.\n"
        "- Do NOT change the trigger list or enums.\n"
        "- Return ONLY the tool output."
    ),
    agent=validator_agent,
    expected_output="Raw JSON string from judge_plan (no extra text).",
)

t4_repair_if_needed = Task(
    description=(
        "You will receive:\n"
        "A) Drafted workflow plan in Markdown:\n\n"
        "{plan_markdown}\n\n"
        "B) Judge JSON (a JSON object):\n\n"
        "{judge_json}\n\n"
        "IMPORTANT:\n"
        "- Treat B as JSON and read ONLY these keys: B.ok (boolean) and B.fix_instructions (list of strings).\n"
        "- Consider B.fix_instructions EMPTY if it is missing, null, an empty list, or contains only 'None'/'null'/empty strings.\n"
        "- Do NOT guess missing instructions.\n\n"
        "RULES:\n"
        "1) If B.ok=true: return A exactly unchanged.\n"
        "2) If B.ok=false:\n"
        "   - If B.fix_instructions is EMPTY (per definition above): return A exactly unchanged.\n"
        "   - Else: you are a PATCHER. Apply B.fix_instructions as literal edits to A.\n"
        "     - Prefer replacements over additions.\n"
        "     - Only change the minimum text necessary to resolve EVERY error.\n"
        "     - Do NOT add new steps unless fix_instructions explicitly requires it.\n"
        "     - Do NOT invent new enums. Only use enums listed in the plan/judge context.\n"
        "     - If the plan contains an invalid enum (not in allowed list), replace it with the expected enum.\n\n"
        "EDIT OPERATIONS ALLOWED:\n"
        "- Replace invalid/incorrect TRG_* with the expected TRG_*.\n"
        "- Replace incorrect EVNT_* with expected EVNT_*.\n"
        "- Remove extra EVNT_*/CNDN_*/EVNT_LOOP_* sections if not required.\n"
        "- Add a missing required section ONLY if judge says it is missing.\n\n"
        "OUTPUT:\n"
        "- Output ONLY the final Markdown workflow plan.\n"
        "- No JSON, no commentary, no code fences.\n"
    ),
    agent=refiner_agent,
    expected_output="Final Markdown workflow plan (valid).",
)





def build_crew() -> Crew:
    return Crew(
        agents=[assembler_agent, planner_agent, validator_agent, refiner_agent],
        tasks=[t1_assemble, t2_draft, t3_validate, t4_repair_if_needed],
        process=Process.sequential,
        verbose=True,
    )
