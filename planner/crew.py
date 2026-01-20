# planner/crew.py
from crewai import Agent, Task, Crew, Process
from planner.tools import AssemblePromptTool, ValidatePlanTool

assemble_tool = AssemblePromptTool()
validate_tool = ValidatePlanTool()

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
    role="Workflow Plan Validator Agent",
    goal="Validate the drafted workflow plan and report errors/warnings as JSON.",
    backstory="You enforce the output contract. Use the validate_plan tool.",
    tools=[validate_tool],
    verbose=True,
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
        "Validate the drafted Markdown plan from the previous task using the validate_plan tool.\n"
        "Return ONLY the raw JSON result from the tool (ok/errors/warnings). Do not add commentary."
    ),
    agent=validator_agent,
    expected_output="JSON string: { ok: bool, errors: [...], warnings: [...] }",
)

t4_repair_if_needed = Task(
    description=(
        "You will receive:\n"
        "A) The drafted Markdown plan from Task 2\n"
        "B) The validation JSON from Task 3\n\n"
        "If validation ok=true: return the original plan unchanged.\n"
        "If ok=false: minimally edit the plan to fix ALL errors. Keep content minimal.\n"
        "Output ONLY the final Markdown workflow plan."
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
