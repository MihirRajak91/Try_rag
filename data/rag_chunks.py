"""
rag_chunks_data.py  (CLEAN VERSION)

Principles:
- Only `data` is used for embeddings/RAG retrieval.
- `text` is stored for prompt assembly (comes from planner.py full prompt strings).
- CORE/static pieces are NOT embedded; they are always injected at runtime.
- No duplicate variable names. No circular references.
"""

# -------------------------------------------------------------------
# LAYER 1: CORE (static, always injected) — NOT FOR EMBEDDING
# -------------------------------------------------------------------

PROMPT_CORE_INTRO_CHUNK = {
    "doc_type": "CORE",
    "topic": "core_intro",
    "priority": 999,
    "role": "static",
    "data": """CORE.INTRO
Intent: base planner role + output expectation.
Output: always include as system framing (not retrieved).
""",
    "text": """You are an expert workflow automation architect for enterprise platforms.
Your task is to take a user's natural language request and break it into a clear Structured Workflow Plan in Markdown.

⚠️ CRITICAL EVENT SELECTION RULES - READ CAREFULLY:
""",
}

CORE_STATIC_CHUNKS = [
    PROMPT_CORE_INTRO_CHUNK,
]


# -------------------------------------------------------------------
# LAYER 2: STOP-EARLY PRIORITY GATES (router + optional support)
# -------------------------------------------------------------------

PROMPT_STEP_NEG1_USER_MGMT_ROUTER = {
    "doc_type": "RULE",
    "topic": "user_mgmt",
    "priority": 110,
    "role": "router",
    "data": """ROUTER.RULE.user_mgmt
Priority: HIGHEST (stop-early).
Intent: user management actions (create/update/deactivate/activate/assign/extend).
Signals: user/users, permission(s), access, role assignment, assign role, grant/revoke, extend responsibility, head of.
Output: EVNT_USER_MGMT_ADD / EVNT_USER_MGMT_UPDT / EVNT_USER_MGMT_DEACT / EVNT_USER_MGMT_ASSIGN / EVNT_USER_MGMT_EXTND.
Stop-early: If main action is user management, do not route to other topics.
Special: retrieving user info -> EVNT_RCRD_INFO_STC.
""",
    "text": PROMPT_STEP_NEG1_USER_MGMT,  # from planner.py
}

PROMPT_STEP_NEG1_USER_MGMT_SUPPORT = {
    "doc_type": "RULE",
    "topic": "user_mgmt",
    "priority": 110,
    "role": "support",
    "data": """SUPPORT.RULE.user_mgmt
Use when full user-management detection rules + examples are needed.
""",
    "text": PROMPT_STEP_NEG1_USER_MGMT,  # from planner.py
}

PROMPT_STEP0_STATIC_VS_DYNAMIC_ROUTER = {
    "doc_type": "RULE",
    "topic": "static_vs_dynamic",
    "priority": 105,
    "role": "router",
    "data": """ROUTER.RULE.static_vs_dynamic
Priority: very high (stop-early after user_mgmt).
Intent: decide static vs dynamic record family.
Signals: role/roles, department/departments (static system tables).
Output: use *_STC record events only when static keywords present.
Stop-early: If static detected, do not route to dynamic CRUD/data extraction topics.
""",
    "text": PROMPT_STEP0_STATIC_VS_DYNAMIC,  # from planner.py
}

PROMPT_STEP0_STATIC_VS_DYNAMIC_SUPPORT = {
    "doc_type": "RULE",
    "topic": "static_vs_dynamic",
    "priority": 105,
    "role": "support",
    "data": """SUPPORT.RULE.static_vs_dynamic
Use when full static vs dynamic classification rules + examples are needed.
""",
    "text": PROMPT_STEP0_STATIC_VS_DYNAMIC,  # from planner.py
}

PROMPT_USER_MGMT_STOP_EARLY_SUPPORT = {
    "doc_type": "RULE",
    "topic": "user_mgmt.stop",
    "priority": 108,
    "role": "support",
    "data": """SUPPORT.RULE.user_mgmt.stop
Purpose: micro stop-early reminder for user management.
""",
    "text": """If main action is on users (create/update/deactivate/activate/assign/extend), ALWAYS use EVNT_USER_MGMT_* and STOP.
Only user retrieval uses EVNT_RCRD_INFO_STC.""",
}

PROMPT_STATIC_STOP_EARLY_SUPPORT = {
    "doc_type": "RULE",
    "topic": "static_vs_dynamic.stop",
    "priority": 103,
    "role": "support",
    "data": """SUPPORT.RULE.static_vs_dynamic.stop
Purpose: micro stop-early reminder for static entities.
""",
    "text": """If query mentions role/department (static keywords), ALWAYS use *_STC events and STOP (never dynamic).""",
}

LAYER2_CHUNK_DATA = [
    PROMPT_STEP_NEG1_USER_MGMT_ROUTER,
    PROMPT_STEP_NEG1_USER_MGMT_SUPPORT,
    PROMPT_USER_MGMT_STOP_EARLY_SUPPORT,
    PROMPT_STEP0_STATIC_VS_DYNAMIC_ROUTER,
    PROMPT_STEP0_STATIC_VS_DYNAMIC_SUPPORT,
    PROMPT_STATIC_STOP_EARLY_SUPPORT,
]


# -------------------------------------------------------------------
# LAYER 3: DATA EXTRACTION (EVNT_JMES / EVNT_FLTR / EVNT_RCRD_INFO)
# -------------------------------------------------------------------

PROMPT_DATA_EXTRACTION_ROUTER = {
    "doc_type": "RULE",
    "topic": "data_extraction",
    "priority": 95,
    "role": "router",
    "data": """ROUTER.RULE.data_extraction
Intent: retrieve/extract data from records (NOT CRUD action).
Outputs (choose ONE primary):
- EVNT_JMES: field extraction OR limited/positional selection (first/last/top/N).
- EVNT_FLTR: multiple/all complete records (no explicit limit).
- EVNT_RCRD_INFO: one complete record ("a/the record").
Guardrail: do NOT use CNDN_* for simple "where" retrieval filters; handled by extraction events.
""",
    "text": (
        PROMPT_DATA_EXTRACTION_JMES
        + "\n\n" + PROMPT_DATA_EXTRACTION_FLTR
        + "\n\n" + PROMPT_DATA_EXTRACTION_RCRD_INFO
    ),  # from planner.py
}

PROMPT_DATA_JMES_ROUTER = {
    "doc_type": "RULE",
    "topic": "data_extraction.jmes",
    "priority": 93,
    "role": "router",
    "data": """ROUTER.RULE.data_extraction.jmes
Intent: extract specific fields OR positional/limited record request.
Signals: field names (id/name/status/email/qty), first/last/top, get N records.
Output: EVNT_JMES only.
""",
    "text": PROMPT_DATA_EXTRACTION_JMES,
}

PROMPT_DATA_FLTR_ROUTER = {
    "doc_type": "RULE",
    "topic": "data_extraction.fltr",
    "priority": 93,
    "role": "router",
    "data": """ROUTER.RULE.data_extraction.fltr
Intent: retrieve multiple/all complete records with criteria (no explicit limit).
Signals: get records, retrieve all, show all, filter records (without N/first/last/top).
Output: EVNT_FLTR only.
""",
    "text": PROMPT_DATA_EXTRACTION_FLTR,
}

PROMPT_DATA_RCRD_INFO_ROUTER = {
    "doc_type": "RULE",
    "topic": "data_extraction.rcrd_info",
    "priority": 93,
    "role": "router",
    "data": """ROUTER.RULE.data_extraction.rcrd_info
Intent: retrieve ONE complete record.
Signals: "a record", "the record", "retrieve the record", "get a record".
Output: EVNT_RCRD_INFO only (built-in filtering; do NOT pair with EVNT_FLTR).
""",
    "text": PROMPT_DATA_EXTRACTION_RCRD_INFO,
}

PROMPT_DATA_EXTRACTION_SUPPORT = {
    "doc_type": "RULE",
    "topic": "data_extraction",
    "priority": 90,
    "role": "support",
    "data": """SUPPORT.RULE.data_extraction
Use when full retrieval/extraction guidance is needed (JMES vs FLTR vs RCRD_INFO).
""",
    "text": (
        PROMPT_DATA_EXTRACTION_JMES
        + "\n\n" + PROMPT_DATA_EXTRACTION_FLTR
        + "\n\n" + PROMPT_DATA_EXTRACTION_RCRD_INFO
    ),
}

LAYER3_CHUNK_DATA = [
    PROMPT_DATA_EXTRACTION_ROUTER,
    PROMPT_DATA_EXTRACTION_SUPPORT,
    PROMPT_DATA_JMES_ROUTER,
    PROMPT_DATA_FLTR_ROUTER,
    PROMPT_DATA_RCRD_INFO_ROUTER,
]


# -------------------------------------------------------------------
# LAYER 4: DIRECT ACTION EVENTS (CRUD with built-in filtering)
# -------------------------------------------------------------------

PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering",
    "priority": 96,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering
Intent: CRUD action on records (create/update/delete/duplicate/restore).
Signals: create/add, update/modify, delete/remove, duplicate/clone, restore/recover + record/entity/window.
Output: EVNT_RCRD_ADD / EVNT_RCRD_UPDT / EVNT_RCRD_DEL / EVNT_RCRD_DUP / EVNT_RCRD_REST.
Guardrails:
- Action events handle record selection internally; do NOT combine with EVNT_RCRD_INFO/EVNT_FLTR/EVNT_JMES.
- Do NOT add CNDN_* for delete/duplicate/restore/update "where/when" (built-in filtering).
- Exception: CREATE with truly complex branching may require CNDN_* + EVNT_RCRD_ADD.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,  # from planner.py
}

PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_SUPPORT = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering",
    "priority": 92,
    "role": "support",
    "data": """SUPPORT.RULE.actions_builtin_filtering
Use when full CRUD built-in filtering rules + examples are needed.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

# Optional micro-routers (keep minimal, but no duplicates)
PROMPT_ACTION_CREATE_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering.create",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering.create
Intent: create/add a record.
Signals: create a record, add a record, create record in [entity/window].
Output: EVNT_RCRD_ADD (or *_STC if static gate matched earlier).
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

PROMPT_ACTION_UPDATE_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering.update",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering.update
Intent: update/modify a record (built-in selection).
Output: EVNT_RCRD_UPDT only. No extraction events. No CNDN_*.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

PROMPT_ACTION_DELETE_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering.delete",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering.delete
Intent: delete/remove a record (built-in selection).
Output: EVNT_RCRD_DEL only. No extraction events. No CNDN_*.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

PROMPT_ACTION_DUPLICATE_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering.duplicate",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering.duplicate
Intent: duplicate/clone a record (built-in selection).
Output: EVNT_RCRD_DUP only. No extraction events. No CNDN_*.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

PROMPT_ACTION_RESTORE_ROUTER = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering.restore",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.actions_builtin_filtering.restore
Intent: restore/recover a record (built-in selection).
Output: EVNT_RCRD_REST only. No extraction events. No CNDN_*.
""",
    "text": PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
}

LAYER4_CHUNK_DATA = [
    PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_ROUTER,
    PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_SUPPORT,
    PROMPT_ACTION_CREATE_ROUTER,
    PROMPT_ACTION_UPDATE_ROUTER,
    PROMPT_ACTION_DELETE_ROUTER,
    PROMPT_ACTION_DUPLICATE_ROUTER,
    PROMPT_ACTION_RESTORE_ROUTER,
]


# -------------------------------------------------------------------
# LAYER 5: CONDITIONS (CNDN_BIN / CNDN_SEQ / CNDN_DOM)
# -------------------------------------------------------------------

PROMPT_CONDITIONS_ROUTER = {
    "doc_type": "RULE",
    "topic": "conditions",
    "priority": 97,
    "role": "router",
    "data": """ROUTER.RULE.conditions
Intent: conditional branching / decision logic.
Signals: if/else, when/then, otherwise, unless, first check, if not, else check, AND check if, and check if.
Output: choose CNDN_BIN / CNDN_SEQ / CNDN_DOM (always explicit TRUE + FALSE paths).
Guardrails:
- Do NOT use conditions for simple retrieval "where" filters (handled by EVNT_JMES/EVNT_FLTR/EVNT_RCRD_INFO).
- Do NOT use conditions for built-in CRUD filters (delete/duplicate/restore/update with where/when).
""",
    "text": PROMPT_COND_OVERVIEW_AND_PATTERNS,  # from planner.py
}

PROMPT_CONDITIONS_SUPPORT = {
    "doc_type": "RULE",
    "topic": "conditions",
    "priority": 92,
    "role": "support",
    "data": """SUPPORT.RULE.conditions
Use when full condition patterns + examples are needed.
""",
    "text": (
        PROMPT_COND_OVERVIEW_AND_PATTERNS
        + "\n\n" + PROMPT_COND_DOM
        + "\n\n" + PROMPT_COND_SEQ
        + "\n\n" + PROMPT_COND_BIN
        + "\n\n" + PROMPT_COND_DISTINCTION_TABLE_AND_DECISION
        + "\n\n" + PROMPT_COND_DECISION_RULES
        + "\n\n" + PROMPT_COND_DO_NOT_USE
        + "\n\n" + PROMPT_COND_DISTINCTION_NOTES
    ),  # all from planner.py
}

PROMPT_COND_BIN_ROUTER = {
    "doc_type": "RULE",
    "topic": "conditions.bin",
    "priority": 95,
    "role": "router",
    "data": """ROUTER.RULE.conditions.bin
Intent: single branching decision (true/false).
Signals: if X then Y, when X then Y, if X then Y else Z.
Output: CNDN_BIN. ALWAYS specify both branches (FALSE may route to END).
""",
    "text": PROMPT_COND_BIN,
}

PROMPT_COND_SEQ_ROUTER = {
    "doc_type": "RULE",
    "topic": "conditions.seq",
    "priority": 95,
    "role": "router",
    "data": """ROUTER.RULE.conditions.seq
Intent: multiple independent checks evaluated separately.
Signals: AND check if, and check if, and verify if, and if (independent clauses).
Output: CNDN_SEQ with one CNDN_LGC per independent check/action.
""",
    "text": PROMPT_COND_SEQ,
}

PROMPT_COND_DOM_ROUTER = {
    "doc_type": "RULE",
    "topic": "conditions.dom",
    "priority": 95,
    "role": "router",
    "data": """ROUTER.RULE.conditions.dom
Intent: cascading / fallback checks (domino).
Signals: first check..., if not then..., else check if..., if fails try....
Output: CNDN_DOM with CNDN_LGC_DOM containers; ELSE routes to next container or END.
""",
    "text": PROMPT_COND_DOM,
}

# Optional support micro-chunks (small retrievable helpers)
PROMPT_COND_DISTINCTION_TABLE_SUPPORT = {
    "doc_type": "RULE",
    "topic": "conditions.distinction_table",
    "priority": 85,
    "role": "support",
    "data": """SUPPORT.RULE.conditions.distinction_table
Use for pattern-to-condition mapping table and decision checklist.
""",
    "text": PROMPT_COND_DISTINCTION_TABLE_AND_DECISION,
}

PROMPT_COND_GUARDRAILS_SUPPORT = {
    "doc_type": "RULE",
    "topic": "conditions.guardrails",
    "priority": 85,
    "role": "support",
    "data": """SUPPORT.RULE.conditions.guardrails
Use for guardrails on when NOT to add conditions.
""",
    "text": PROMPT_COND_DO_NOT_USE + "\n\n" + PROMPT_COND_DISTINCTION_NOTES,
}

LAYER5_CHUNK_DATA = [
    PROMPT_CONDITIONS_ROUTER,
    PROMPT_CONDITIONS_SUPPORT,
    PROMPT_COND_BIN_ROUTER,
    PROMPT_COND_SEQ_ROUTER,
    PROMPT_COND_DOM_ROUTER,
    PROMPT_COND_DISTINCTION_TABLE_SUPPORT,
    PROMPT_COND_GUARDRAILS_SUPPORT,
]


# -------------------------------------------------------------------
# LAYER 6: NOTIFICATIONS (EVNT_NOTI_*)
# -------------------------------------------------------------------

PROMPT_NOTIFICATIONS_ROUTER = {
    "doc_type": "RULE",
    "topic": "notifications",
    "priority": 94,
    "role": "router",
    "data": """ROUTER.RULE.notifications
Intent: send a notification/message.
Signals: email, mail, notify, notification, alert, sms, text message, push, webhook.
Output: choose EVNT_NOTI_* family.
Guardrail: if query contains branching (if/else/first check/etc.), also retrieve conditions topic.
Guardrail: if query contains repetition (repeat/times/loop/etc.), also retrieve loops topic.
""",
    "text": PROMPT_NOTIFICATIONS_SUPPORT_TEXT,  # use a single notifications section string from planner.py
}

PROMPT_NOTIFICATIONS_EVENT_MAPPING_SUPPORT = {
    "doc_type": "RULE",
    "topic": "notifications.map",
    "priority": 88,
    "role": "support",
    "data": """SUPPORT.RULE.notifications.map
Purpose: quick mapping from intent to EVNT_NOTI_* code.
""",
    "text": """Map notification intent to the correct EVNT_NOTI_* event:
- Email → EVNT_NOTI_MAIL
- SMS/Text → EVNT_NOTI_SMS
- System notification/alert → EVNT_NOTI_NOTI
- Push → EVNT_NOTI_PUSH
- Webhook → EVNT_NOTI_WBH
""",
}

LAYER6_CHUNK_DATA = [
    PROMPT_NOTIFICATIONS_ROUTER,
    PROMPT_NOTIFICATIONS_EVENT_MAPPING_SUPPORT,
]


# -------------------------------------------------------------------
# LAYER 7: LOOPS + FLOW FORMATTING RULES
# -------------------------------------------------------------------

PROMPT_LOOPS_ROUTER = {
    "doc_type": "RULE",
    "topic": "loops",
    "priority": 88,
    "role": "router",
    "data": """ROUTER.RULE.loops
Intent: repetition/iteration.
Signals: repeat, times, for each, for every, loop, iterate, from X to Y, while, until, do while, break, continue.
Output: EVNT_LOOP_FOR / EVNT_LOOP_WHILE / EVNT_LOOP_DOWHILE (+ BREAK/CONTINUE if requested).
Rule: if BOTH condition + repetition exist, loop goes INSIDE condition branch (not after).
""",
    "text": PROMPT_LOOPS_TYPES,  # from planner.py
}

PROMPT_FLOW_FORMATTING_SUPPORT = {
    "doc_type": "RULE",
    "topic": "flow_formatting",
    "priority": 80,
    "role": "support",
    "data": """SUPPORT.RULE.flow_formatting
Purpose: strict Flow Sequence formatting rules (numbering + ↳ branches + INSIDE LOOP).
Use when workflow contains CNDN_* or EVNT_LOOP_*.
""",
    "text": (
        PROMPT_FLOW_FORMATTING_RULES
        + "\n\n" + PROMPT_FLOW_FORMATTING_RULES_DETAILED
        + "\n\n" + PROMPT_FLOW_EXAMPLES_CORRECT
        + "\n\n" + PROMPT_FLOW_EXAMPLES_WRONG
        + "\n\n" + PROMPT_FLOW_APPLICABILITY_AND_CHECKLIST
    ),  # from planner.py
}

LAYER7_CHUNK_DATA = [
    PROMPT_LOOPS_ROUTER,
    PROMPT_FLOW_FORMATTING_SUPPORT,
]


# -------------------------------------------------------------------
# LAYER 8: DATA OPS / FORMULA (EVNT_DATA_OPR)
# -------------------------------------------------------------------

PROMPT_DATA_OPS_ROUTER = {
    "doc_type": "RULE",
    "topic": "data_ops",
    "priority": 85,
    "role": "router",
    "data": """ROUTER.RULE.data_ops
Intent: compute/transform/derive values (math/string/date/regex/uuid/random).
Signals: calculate, compute, sum, total, percentage, concat, uppercase/lowercase, split, replace, regex,
format date, add days, round, uuid, random.
Output: EVNT_DATA_OPR.
Guardrail: do NOT use CNDN_BIN just for value assignment.
""",
    "text": PROMPT_FORMULA_DETECTION,  # from planner.py
}

PROMPT_DATA_OPS_GUARDRAIL_SUPPORT = {
    "doc_type": "RULE",
    "topic": "data_ops.guardrails",
    "priority": 75,
    "role": "support",
    "data": """SUPPORT.RULE.data_ops.guardrails
Purpose: prevent condition misuse for computed assignments.
""",
    "text": """DO NOT use CNDN_BIN just for value assignment – use EVNT_DATA_OPR for computed fields.
Only use CNDN_BIN when the entire action branches (e.g., send email or not, create vs delete).""",
}

LAYER8_CHUNK_DATA = [
    PROMPT_DATA_OPS_ROUTER,
    PROMPT_DATA_OPS_GUARDRAIL_SUPPORT,
]


# -------------------------------------------------------------------
# LAYER 9: OUTPUT CONTRACT / PLANNER POLICY (support-only)
# -------------------------------------------------------------------

PROMPT_PLANNER_POLICY_SUPPORT = {
    "doc_type": "RULE",
    "topic": "planner_policy",
    "priority": 80,
    "role": "support",
    "data": """SUPPORT.RULE.planner_policy
Intent: output format + plan writing constraints (Markdown sections, omit unused sections, numbering, branch formatting).
Output: formatting policy only (not event selection).
""",
    "text": (
        PROMPT_PLANNER_POLICY
        + "\n\n" + PROMPT_OUTPUT_CONTRACT
        + "\n\n" + PROMPT_EXAMPLES
    ),  # from planner.py
}

PROMPT_OUTPUT_CONTRACT_MINI_SUPPORT = {
    "doc_type": "RULE",
    "topic": "output_contract",
    "priority": 60,
    "role": "support",
    "data": """SUPPORT.RULE.output_contract
Purpose: minimal output guardrails (Markdown plan only, omit unused sections).
""",
    "text": PROMPT_OUTPUT_CONTRACT,  # from planner.py
}

LAYER9_CHUNK_DATA = [
    PROMPT_PLANNER_POLICY_SUPPORT,
    PROMPT_OUTPUT_CONTRACT_MINI_SUPPORT,
]


# -------------------------------------------------------------------
# FINAL: CHUNKS FOR EMBEDDING (EXCLUDES CORE STATIC)
# -------------------------------------------------------------------

CHUNKS_FOR_EMBEDDING = (
    LAYER2_CHUNK_DATA
    + LAYER3_CHUNK_DATA
    + LAYER4_CHUNK_DATA
    + LAYER5_CHUNK_DATA
    + LAYER6_CHUNK_DATA
    + LAYER7_CHUNK_DATA
    + LAYER8_CHUNK_DATA
    + LAYER9_CHUNK_DATA
)
