"""RAG chunk r gistry.

Each chunk is a dict with:
- doc_type: CORE/RULE/CATALOG
- topic: retrieval topic
- priority: higher = more important
- role: router/support/static
- data: short embedded routing summary (what gets embedded)
- text: full reference text (not embedded)

NOTE: Only `data` should be embedded for vector search.
"""
PROMPT_ACTION_EVENTS_BUILTIN_FILTERING = {
    "doc_type": "RULE",
    "topic": "actions_builtin_filtering",
    "priority": 120,
    "role": "router",
"data": """
ROUTER.RULE.actions_builtin_filtering | doc_type=RULE | role=router | priority=120
Signature: WHERE_SELECTION_PREDICATE; ROW_MATCHING; TARGET_ROWS

where <predicate>; when <predicate>; only rows where; records with <field=value>
filter rows; matching records; select matching entries; apply to records where
status=; amount>; date between; tag=; archived=true
update records where; delete records where; create record where; duplicate record where; restore record where
update record where status is active; update record where department is Science

ref:actions_builtin_filtering#router

""",
    "text": """SIMPLE WHERE FILTER RULE (NO CONDITIONS):
- If the query uses "where/when" only to identify which records to act on (e.g., "where status is active"),
  treat it as built-in filtering and DO NOT add any CNDN_*.
- Only use CNDN_* when the query requires branching decisions (if/else) or multiple logical paths.
"""
}

# PROMPT_ACTION_EVENTS_BUILTIN_FILTERING = {
#     "doc_type": "RULE",
#     "topic": "actions_builtin_filtering",
#     "priority": 120,
#     "role": "router",
#     "data": """
# ROUTER.RULE.actions_builtin_filtering
# Intent: update/modify records/entities/forms/tasks/workflow fields (NON-user-account).
# + Intent: NON-USER workflow / task / form / record state updates.

# ACTION-INTENT REQUIREMENT (to avoid stealing notification triggers):
# This topic MUST ONLY be selected when the user is asking the system to PERFORM an update/change operation.
# It must contain an explicit action verb like:
# - update / change / set / modify / mark / move / close / complete

# If the query is phrased as "email/sms/notify/alert WHEN/IF a record is updated/edited/changed"
# (without asking to update anything), that is NOT an action request. Route to notifications_intent.


# Objects this topic applies to:
# - task
# - task status
# - task completion form
# - workflow step
# - workflow state
# - process stage
# - record status field

# Strong matches (notification-first trigger phrasing):
# - "email/sms/notify/alert when a record is updated/edited/changed"
# - "sms the admin when status changes"
# - "notify when form is submitted"
# These are notifications_intent even though they mention "updated/edited/changed".

# MUST MATCH (positive intent signals):
# - update a record/entity/form/task
# - change status/stage/state/field value
# - mark as done/completed/cancelled/closed
# - workflow state/status update
# - form submission/status update
# - task lifecycle status update

# High-confidence matches:
# - change the status of Task completed to Done
# - change the status of Task completed to Done in task completion form
# - when someone moves to another task, set previous task to Done
# - update task completion form status when moving to another task
# - mark previous task as Done after workflow progresses
# - update workflow task status field to Done


# FILTERING (selection, not user-account mgmt):
# - update WHERE moved_to_another_task = true
# - update WHEN moved_to_another_task = true
# - update records matching condition (built-in filtering)

# HARD EXCLUSIONS (route away):
# - Any request whose primary intent is sending a message/notification (email/sms/notify/alert/push/webhook)
#   in response to a record/task/form/status change.
#   Route those to notifications_intent.


# - Notification-first phrasing (route away to notifications_intent):
#   If the query STARTS with or is primarily about sending a message:
#   "email ...", "sms ...", "notify ...", "send alert ..."
#   AND the rest of the query describes a trigger like:
#   "when a record is updated/edited/changed", "when status changes"
#   THEN this is notifications_intent (NOT actions_builtin_filtering).

# Examples (must route away):
# - "sms the admin when a record is updated"
# - "email when the data in the record is edited"
# - "notify me when record status changes"
# - "send an alert when a form is submitted"


# DISAMBIGUATION:
# - If the object being updated is a TASK/FORM/RECORD/WORKFLOW status → actions_builtin_filtering.
# - Only choose user_mgmt if the object is explicitly a USER ACCOUNT.

# Anti-pattern clarification:
# - The word "user" appearing in context (e.g., "when user moves to another task")
#   does NOT imply user account management.
# - This topic applies when the UPDATED OBJECT is a task, form, or workflow,
#   NOT when updating a user account/profile.

# MIXED ACTION + NOTIFICATION (allow BOTH topics ONLY when BOTH intents are explicit):

# Do NOT invent an update such as "set status to done" unless the user explicitly asked for that field/value change.

# ✅ Must contain BOTH:
# A) an explicit action instruction to update/change/set/mark something
# AND
# B) a notification instruction (email/sms/notify/alert)

# Examples:
# - "update the record status to done and email the admin"
# - "change status to done then send mail"
# - "set task to completed and notify by SMS"

# Non-examples (notification-only; DO NOT include this topic):
# - "sms the admin when a record is updated"
# - "email when the data in the record is edited"



# Output: EVNT_RCRD_UPDT / EVNT_RCRD_* action events (built-in filtering).
# """,

#     "text": """SIMPLE WHERE FILTER RULE (NO CONDITIONS):
# - If the query uses "where/when" only to identify which records to act on (e.g., "where status is active"),
#   treat it as built-in filtering and DO NOT add any CNDN_*.
# - Only use CNDN_* when the query requires branching decisions (if/else) or multiple logical paths.

# CONDITIONS matches:
# - if moved to another task then update status to done else end
# - if condition then update record else end

# NEAR-MISS VARIANTS:
# - if moved to another task then update status to done else end
# - if condition then update record else end
# - if moved to another task then update status to done else end
# - if condition then update record else end
# """
# }

PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_SUPPORT = {

    "doc_type": "RULE",
    "topic": "actions_builtin_filtering",
    "priority": 90,
    "role": "support",
"data": """
SUPPORT.RULE.actions_builtin_filtering | doc_type=RULE | role=support | priority=90
Signature: DIRECT_RECORD_ACTION; BUILTIN_WHERE_FILTER; NO_EXTRA_FILTER_STEP

Purpose:
Map user phrasing to direct record action events that include internal record selection via where/when predicates.

Primary outputs (direct action events):
EVNT_RCRD_ADD (create record)
EVNT_RCRD_UPDT (update/modify record)
EVNT_RCRD_DEL (delete/remove record)
EVNT_RCRD_DUP (duplicate/copy record)
EVNT_RCRD_REST (restore/unarchive record)

Key constraint:
- These events include built-in record filtering; do not pair with EVNT_RCRD_INFO or EVNT_FLTR.
- Prefer emitting ONLY the action event when the request is a direct record action over selected rows.
- If static keywords are present (role/department), use the _STC variants of these actions.

Action detection triggers (safe):
create record; add record; new record; insert record
update record; modify record; change field; set status
delete record; remove record
duplicate record; copy record; clone record
restore record; unarchive record

Where/when usage:
- Patterns: "ACTION ... where <predicate>" / "ACTION ... when <predicate>" / "ACTION ... for rows where <predicate>"
- Predicate applies to selecting target rows for the action.
- IMPORTANT: If the query says "update record(s) where ...", the correct output is EVNT_RCRD_UPDT (not EVNT_FLTR).

Create-vs-update disambiguation (high-signal):
If query starts with "create" OR contains "create a record" → ALWAYS EVNT_RCRD_ADD (never EVNT_RCRD_UPDT), even if phrasing contains "to".

Masked mixed-intent note (no competitor tokens):
If query combines a record action AND an outbound-message intent → allow SECONDARY topic = notifications_intent.
Use label: OUTBOUND_MESSAGE_INTENT (do not key on channel words here).

Examples (kept channel-neutral):
- "create a record in <entity> where fee charged between 2500 and 3000" → EVNT_RCRD_ADD
- "delete records where status = expired" → EVNT_RCRD_DEL
- "duplicate records where value > 100" → EVNT_RCRD_DUP
- "update records where tier = gold; set status = done" → EVNT_RCRD_UPDT
- "update record where status is active" → EVNT_RCRD_UPDT
- "duplicate the record where department is management" → EVNT_RCRD_DUP_STC
- "update status and perform OUTBOUND_MESSAGE_INTENT" → action event + allow notifications_intent secondary

ref:actions_builtin_filtering#support
"""
,

    "text": """CRITICAL: Action Events with Built-in Filtering

Use Direct Action Events (NO additional retrieve/filter needed) for:

EVNT_RCRD_ADD (Create a Record):
- Keywords: "create a record", "add a record", "create record of [entity]"
- Pattern: "create [a] record of [entity] where [conditions]"
- Examples:
  - "create a record in enrollment tracking where fee charged is 2500 to fee charged 3000" → EVNT_RCRD_ADD ONLY

EVNT_RCRD_DUP (Duplicate a Record):
- Keywords: "duplicate the record", "duplicate record of [entity]"
- Pattern: "duplicate [the] record of [entity] where [conditions]"
- Has BUILT-IN filtering - directly duplicates matching record
- Examples:
  - "duplicate the record of Enrollment Tracking where Title is Enrollment 1 and status is enrolled" → EVNT_RCRD_DUP ONLY
  - "duplicate a record when value is greater than 100" → EVNT_RCRD_DUP ONLY (built-in condition handling)
  - If role/department is mentioned, use EVNT_RCRD_DUP_STC

EVNT_RCRD_REST (Restore a Record):
- Keywords: "restore the record", "restore record of [entity]"
- Pattern: "restore [the] record of [entity] where [conditions]"
- Has BUILT-IN filtering - directly restores matching record
- Examples:
  - "restore the record of Enrollment Tracking where Title is Enrollment 1 and status is enrolled" → EVNT_RCRD_REST ONLY

EVNT_RCRD_DEL (Delete a Record):
- Keywords: "delete the record", "delete record of [entity]", "remove the record"
- Pattern: "delete [the] record of [entity] where [conditions]"
- Has BUILT-IN filtering - directly deletes matching record
- Examples:
  - "delete the record of Enrollment Tracking where Title is Enrollment 1 and status is enrolled" → EVNT_RCRD_DEL ONLY
  - "delete a record when status is expired" → EVNT_RCRD_DEL ONLY

EVNT_RCRD_UPDT (Update a Record):
- Keywords: "update the record", "update record of [entity]", "modify the record"
- Pattern: "update [the] record of [entity]"
- Examples:
  - "update a record in enrollment tracking where fee charged is 2500 to fee charged 3000" → EVNT_RCRD_UPDT ONLY

MIXED ACTION + NOTIFICATION (include BOTH topics):
- update the record status to done and email the admin
- update status and notify by email
- change status then send mail
- modify record and send an alert
Rule: when a query contains BOTH an action (update/change/set status) AND a message intent (email/sms/notify/alert),
the router should allow notifications_intent as a secondary topic.

⚠️ CRITICAL RULE:
- DO NOT combine these action events with EVNT_RCRD_INFO, EVNT_FLTR, or CNDN_BIN
- Each action event handles its own record selection and filtering internally
- Use ONLY the action event when the query is a direct action on records

CRITICAL ACTION DETECTION RULE:
If a query starts with "create" or contains "create a record", it is ALWAYS a CREATE operation (EVNT_RCRD_ADD), never an UPDATE operation, regardless of other words like "to" in the query.
"""
}

PROMPT_NOTIFICATIONS_INTENT = {
    "doc_type": "RULE",
    "topic": "notifications_intent",
    "priority": 140,
    "role": "router",
"data": """
ROUTER.RULE.notifications_intent | doc_type=RULE | role=router | priority=140
Signature: OUTBOUND_MESSAGE; SEND_MESSAGE; NOTIFICATION_CHANNELS

notify; notification; alert; message; send message
email; mail; sms; text; ping; remind; dm
slack; teams; whatsapp; webhook; push

ref:notifications_intent#router
"""

,
    "text": """Use when the user request is primarily about sending a notification/message.
Do not use for record CRUD, loops, or computations.

- If the prompt mentions a record being created/edited/updated ONLY as a trigger/context (e.g., "when a record is edited"), do NOT add any EVNT_RCRD_* action steps unless the user explicitly asks to create/update/delete/restore/duplicate a record."""
}



PROMPT_NOTIFICATIONS_SUPPORT = {
    "doc_type": "RULE",
    "topic": "notifications_intent",
    "priority": 140,
    "role": "support",
"data": """
SUPPORT.RULE.notifications_intent | doc_type=RULE | role=support | priority=140
Signature: OUTBOUND_MESSAGE_INTENT; CHANNEL_TO_EVENT_MAPPING; EVNT_NOTI_*

Task:
Map an outbound message/notification request to the correct EVNT_NOTI_* event and fill required slots.

Channel mapping keywords → event:
EMAIL_CHANNEL → EVNT_NOTI_MAIL
SMS_CHANNEL → EVNT_NOTI_SMS
SYSTEM_NOTIFICATION_CHANNEL → EVNT_NOTI_NOTI
PUSH_CHANNEL → EVNT_NOTI_PUSH
WEBHOOK_CHANNEL → EVNT_NOTI_WBH

Canonical channel tokens (only these):
EMAIL_CHANNEL: email, mail, gmail
SMS_CHANNEL: sms, text message, txt
SYSTEM_NOTIFICATION_CHANNEL: system notification, in-app notification
PUSH_CHANNEL: push notification
WEBHOOK_CHANNEL: webhook, callback url, http endpoint

Required fields:
recipient (or resolve step); message content (subject/body/message); optional trigger phrase (when/on/if)

Missing-info rules:
- If recipient missing → add RESOLVE_RECIPIENT (name→user lookup) or placeholder recipient
- If content missing → add placeholders for subject/body/message
 - If no channel is specified, default to SYSTEM_NOTIFICATION_CHANNEL → EVNT_NOTI_NOTI
 - Use ONLY ONE EVNT_NOTI_* unless the user explicitly asks for multiple channels

ref:notifications_intent#support
"""

,
    "text": """Use when the user request is primarily about sending a notification/message.
Map intent to the correct EVNT_NOTI_* event:
- Email → EVNT_NOTI_MAIL
- SMS/Text → EVNT_NOTI_SMS
- System notification → EVNT_NOTI_NOTI
- Push → EVNT_NOTI_PUSH
- Webhook → EVNT_NOTI_WBH

Do not use for record CRUD, loops, or computations.

- if recipient email isn’t given → add a “resolve recipient” step OR treat “anish” as user record lookup
- if subject/body not given → include placeholders
- Webhook notifications (EVNT_NOTI_WBH) are actions, not triggers; default Trigger remains TRG_DB unless the user explicitly requests an incoming webhook trigger.
"""
}


PROMPT_DATA_OPS_RULES = {

    "doc_type": "RULE",
    "topic": "data_ops_rules",
    "priority": 80,
    "role": "router",
"data": """
ROUTER.RULE.data_ops_rules | doc_type=RULE | role=router | priority=80
Signature: EVNT_DATA_OPR; DATA_TRANSFORM; FORMULA_CALC; FIELD_DERIVATION

Select when:
User intent is to compute/derive/transform values (numbers, text, dates) or generate values, i.e., a formula-like operation.

Core operations (high-signal, low-leak):
- arithmetic: calculate, compute, total, sum, percentage, multiply, divide, difference
- string ops: lowercase, uppercase, trim, concatenate, split, replace, extract, regex
- date/time ops: format date, add/subtract days, weekday, timezone conversion
- generation: random value, uuid, sequence, otp/code
- normalization: round, type conversion, clean/format

Output:
EVNT_DATA_OPR

Notes (kept embedding-safe):
- This rule is about value transformation/derivation, not selecting records via where/when.
- Use when a field/value must be computed before storing/using it.

ref:data_ops_rules#router
"""
,

    "text": """STEP X: Formula / Calculation Detection (EVNT_DATA_OPR)
Use EVNT_DATA_OPR when the user wants to:
- Perform any calculation: add, subtract, multiply, divide, power, percentage, etc.
- Manipulate strings: uppercase, lowercase, concatenate, extract, replace, split, regex
- Work with dates: format, add/subtract days, get weekday, convert timezone
- Generate random values, UUIDs, sequences
- Derive/compute a field value before creating/updating a record
- Clean/format data (trim, round, type conversion)
- Complex conditional value assignment that goes beyond simple field mapping

Keywords/phrases that trigger EVNT_DATA_OPR:
"calculate", "compute", "add ... and ...", "subtract", "multiply", "divide", "total", "sum", "difference",
"uppercase", "lowercase", "capitalize", "concatenate", "join", "split", "extract", "replace",
"format date", "add days", "current date", "today + 7", "weekday", "convert timezone",
"round", "absolute", "generate random", "if ... then ... else" (for value assignment, not branching)

Examples – ALWAYS use EVNT_DATA_OPR:
- "create a record where full_name is first_name + last_name" → EVNT_DATA_OPR (concat) + EVNT_RCRD_ADD
- "set expiry_date to today + 30 days" → EVNT_DATA_OPR (add_timedelta) + EVNT_RCRD_ADD/_UPDT
- "calculate total_amount = quantity * price" → EVNT_DATA_OPR
- "make email lowercase before saving" → EVNT_DATA_OPR (lower)
- "extract phone number using regex" → EVNT_DATA_OPR (findall/sub)
- "generate a random 8-digit OTP" → EVNT_DATA_OPR
- "set status to 'Overdue' if due_date < today" → EVNT_DATA_OPR + CNDN_BIN if branching needed

DO NOT use CNDN_BIN just for value assignment – use EVNT_DATA_OPR for computed fields.

HARD BAN (trigger-only record mentions):
- If the query mentions a record being created/edited/updated ONLY as a trigger or context
  (e.g., "when a record is edited", "on record update"),
  DO NOT output any EVNT_RCRD_* steps.

- Output EVNT_RCRD_* steps ONLY when the user explicitly requests a record action
  using verbs such as:
  create, add, update, modify, delete, remove, restore, duplicate, set status.

Only use CNDN_BIN when the entire action branches (e.g., create vs update, send email or not).

The workflow plan is NOT JSON.
It should describe:
- Workflow name & description
- Trigger details (type code)
- Events & actions (event codes, purpose)
- Conditions / logic steps (include ONLY for conditional actions, not data filtering)
- Flow sequence (ordered steps from trigger to end)

Stick strictly to the user's request. Do not add extra actions, events, or features such as notifications, emails, or any other outputs unless explicitly mentioned in the query. For example, if the user asks to retrieve or filter records, do not add sending notifications.

"""
}

PROMPT_DATA_OPS_SUPPORT = {

    "doc_type": "RULE",
    "topic": "data_ops_rules",
    "priority": 80,
    "role": "support",
"data": """
SUPPORT.RULE.data_ops_rules | doc_type=RULE | role=support | priority=80
Signature: EVNT_DATA_OPR; VALUE_DERIVATION; TRANSFORM_FUNCTIONS; FORMULA_ENGINE

Task:
When intent is value computation/transformation, emit EVNT_DATA_OPR and describe the operation(s) as functions.

Operation families (high-signal):
- numeric: add, subtract, multiply, divide, power, percent, sum/total, difference, round, abs
- string: lowercase, uppercase, capitalize, trim, concatenate/join, split, replace, extract, regex
- date/time: parse/format date, add/subtract days, weekday, timezone convert
- generation: random number/string, uuid, sequence, code/otp
- type/cleaning: cast/convert type, normalize, sanitize

Expected EVNT_DATA_OPR slots:
- inputs: source fields/values
- ops: ordered list of transforms (function names + parameters)
- output: target field/value name

Guidance:
- Use EVNT_DATA_OPR for computed/derived values and normalization.
- Keep this event scoped to value transformation; avoid adding unrelated event families unless explicitly requested.

ref:data_ops_rules#support
"""
,

    "text": """STEP X: Formula / Calculation Detection (EVNT_DATA_OPR)
Use EVNT_DATA_OPR when the user wants to:
- Perform any calculation: add, subtract, multiply, divide, power, percentage, etc.
- Manipulate strings: uppercase, lowercase, concatenate, extract, replace, split, regex
- Work with dates: format, add/subtract days, get weekday, convert timezone
- Generate random values, UUIDs, sequences
- Derive/compute a field value before creating/updating a record
- Clean/format data (trim, round, type conversion)
- Complex conditional value assignment that goes beyond simple field mapping

Keywords/phrases that trigger EVNT_DATA_OPR:
"calculate", "compute", "add ... and ...", "subtract", "multiply", "divide", "total", "sum", "difference",
"uppercase", "lowercase", "capitalize", "concatenate", "join", "split", "extract", "replace",
"format date", "add days", "current date", "today + 7", "weekday", "convert timezone",
"round", "absolute", "generate random", "if ... then ... else" (for value assignment, not branching)

Examples – ALWAYS use EVNT_DATA_OPR:
- "create a record where full_name is first_name + last_name" → EVNT_DATA_OPR (concat) + EVNT_RCRD_ADD
- "set expiry_date to today + 30 days" → EVNT_DATA_OPR (add_timedelta) + EVNT_RCRD_ADD/_UPDT
- "calculate total_amount = quantity * price" → EVNT_DATA_OPR
- "make email lowercase before saving" → EVNT_DATA_OPR (lower)
- "extract phone number using regex" → EVNT_DATA_OPR (findall/sub)
- "generate a random 8-digit OTP" → EVNT_DATA_OPR
- "set status to 'Overdue' if due_date < today" → EVNT_DATA_OPR + CNDN_BIN if branching needed

DO NOT use CNDN_BIN just for value assignment – use EVNT_DATA_OPR for computed fields.
Only use CNDN_BIN when the entire action branches (e.g., create vs update, send email or not).

The workflow plan is NOT JSON.
It should describe:
- Workflow name & description
- Trigger details (type code)
- Events & actions (event codes, purpose)
- Conditions / logic steps (include ONLY for conditional actions, not data filtering)
- Flow sequence (ordered steps from trigger to end)

Stick strictly to the user's request. Do not add extra actions, events, or features such as notifications, emails, or any other outputs unless explicitly mentioned in the query. For example, if the user asks to retrieve or filter records, do not add sending notifications.

"""
}

PROMPT_COND_OVERVIEW_AND_PATTERNS = {

    "doc_type": "RULE",
    "topic": "conditions",
    "priority": 100,
    "role": "router",
"data": """
ROUTER.RULE.conditions | doc_type=RULE | role=router | priority=100
Signature: CONDITION_BRANCHING; CNDN_BIN; CNDN_SEQ; CNDN_DOM

Select when:
User intent includes conditional decision logic with different paths or multiple conditional checks.

Do NOT select for:
- where/when record filtering (built-in action filtering)
- create/update/delete/duplicate/restore records with simple where predicates
- data retrieval filtering (JMES/Filter)
- sequential actions without branching

Condition type patterns (router cues only):
CNDN_DOM (cascading / fallback chain):
- cues: if not then; else check if; if fails; first check ... if not; try X then Y then Z (fallback)

CNDN_SEQ (multiple independent checks in one request):
- cues: AND check if; and verify if; verify A AND verify B; multiple checks each tied to its own outcome

CNDN_BIN (single binary decision):
- cues: if X then Y; if X then Y else Z; when X then Y (single check with true/false outcome)
Examples (signals):
- if status is approved send email else send notification
- if X then email else notify

Output:
Choose one of: CNDN_BIN / CNDN_SEQ / CNDN_DOM (and associated logic blocks)

Notes:
This rule is about branching/conditional logic patterns, not value computation and not record selection predicates.

ref:conditions#router
"""
,

    "text": """⚠️⚠️⚠️ CRITICAL: CONDITION TYPE DETECTION ⚠️⚠️⚠️

STEP A: CONDITION PATTERN ANALYSIS

Read the query carefully and look for these EXACT patterns:

PATTERN 1 - CNDN_DOM (Domino/Cascading Condition):
Keywords: "if not then", "else check if", "if fails", "first check...if not"
Meaning: CASCADING conditions where each condition depends on the previous one's failure.

Structure in Flow Sequence: #condition containeer may varies according to the user query
  ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Domino Condition (CNDN_DOM) 
      ↳ Container 1 (CNDN_LGC_DOM)
         → IF: Check status is Low → Send Email (EVNT_NOTI_MAIL)
         → ELSE: Route to Container 2
      ↳ Container 2 (CNDN_LGC_DOM)
         → IF: Check status is Medium → Send Alert (EVNT_NOTI_NOTI)
         → ELSE: Route to END
   4. End

Examples that MUST use CNDN_DOM:
- "First check if X then A, if not then check if Y then B" → CNDN_DOM ✓
- "Check if status is Low then email, if not then check if status is Medium then alert" → CNDN_DOM ✓
- "Try X, if fails try Y, if fails try Z" → CNDN_DOM ✓

PATTERN 2 - CNDN_SEQ (Sequence/Parallel Condition):
Keywords: "AND check if", "and check if", "and verify if", "and if"
Meaning: INDEPENDENT parallel conditions that are ALL evaluated simultaneously.

Structure in Flow Sequence:
    ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Sequence Condition (CNDN_SEQ)
      ↳ Logic Block 1 (CNDN_LGC): Check if status is approved → Send Email (EVNT_NOTI_MAIL)
      ↳ Logic Block 2 (CNDN_LGC): Check if amount > 1000 → Send Alert (EVNT_NOTI_NOTI)
   4. End

Examples that MUST use CNDN_SEQ:
- "Check if A then X, AND check if B then Y" → CNDN_SEQ ✓
- "Check if status is approved then send email, and check if amount > 1000 then send alert" → CNDN_SEQ ✓
- "Verify status AND verify amount AND verify date" → CNDN_SEQ ✓

PATTERN 3 - CNDN_BIN (Binary Condition):
Keywords: "if X then Y", "if X then Y else Z", "when X then Y"
Meaning: Single condition with two possible paths (TRUE/FALSE), no cascading, no parallel.

⚠️ CRITICAL: CNDN_BIN ELSE BRANCH SPECIFICATION
- Always explicitly specify BOTH branches in your workflow plan
- Structure must show what happens in BOTH IF TRUE and IF FALSE cases

Structure in Flow Sequence:( ALWAYS SHOW BOTH BRANCHES:)
   ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Binary Condition (CNDN_BIN)
      ↳ IF TRUE: Send Email (EVNT_NOTI_MAIL) → END
      ↳ IF FALSE: Send Notification (EVNT_NOTI_NOTI) → END
   4. End

  CRITICAL RULES:
   - ALWAYS show both IF TRUE and IF FALSE paths
   - If no explicit ELSE action in query, write: "↳ IF FALSE: route to END"
   - Each branch MUST show the event code in parentheses: (EVNT_XXX)
   - Always include → END at the end of each branch path

Examples that MUST use CNDN_BIN:
- "If quantity > 100 send email, else send notification"
  → CNDN_BIN
  → IF TRUE: Send Email (EVNT_NOTI_MAIL)
  → IF FALSE: Send Notification (EVNT_NOTI_NOTI)

- "If status is active update record, else delete record"
  → CNDN_BIN
  → IF TRUE: Update Record (EVNT_RCRD_UPDT)
  → IF FALSE: Delete Record (EVNT_RCRD_DEL)

- "If user exists create record" (no else specified)
  → CNDN_BIN
  → IF TRUE: Create Record (EVNT_RCRD_ADD)
  → IF FALSE: do nothing (route to END)

- "Send email when status = approved" (implicit single-branch)
  → CNDN_BIN
  → IF TRUE: Send Email (EVNT_NOTI_MAIL)
  → IF FALSE: do nothing (route to END)

CRITICAL DISTINCTION TABLE:

| Query Pattern | Condition Type | Reason |
|--------------|----------------|--------|
| "if not then check" | CNDN_DOM | Cascading - second check only if first fails |
| "else check if" | CNDN_DOM | Cascading - each else leads to next check |
| "first check...if not" | CNDN_DOM | Cascading - sequential with fallback |
| "AND check if" | CNDN_SEQ | Parallel - all conditions evaluated independently |
| "and check if" | CNDN_SEQ | Parallel - all conditions evaluated independently |
| Single "if X then Y" | CNDN_BIN | Simple binary - one condition with implicit ELSE to END |
| "if X then Y else Z" | CNDN_BIN | Simple binary - one condition with explicit ELSE |
| Single "when X" | CNDN_BIN | Simple binary - one condition with implicit ELSE to END |


⚠️ CONDITION TYPE DECISION PROCESS:

STEP A: Count the conditions in the query
- How many "if" statements are there?
- How many "check if" statements are there?
- Are they connected by "and" or are they cascading with "if not/else"?

STEP B: Apply these rules:

CNDN_BIN (Binary Condition) - Use for SINGLE IF-THEN branching:
- ONE condition with IF-THEN-ELSE logic (explicit or implicit ELSE)
- Keywords: "if X then do Y", "if X then create else update", "when X then Y", "send email if X"
- ALWAYS specify in Flow Sequence:
  * What happens when TRUE
  * What happens when FALSE (even if it's "route to END")
- Examples:
  - "If value > 100 create a record" 
    → Flow: IF TRUE: Create, IF FALSE: END
  - "Send email if status is pending" 
    → Flow: IF TRUE: Send Email, IF FALSE: END
  - "If quantity < 50 then update record else delete record" 
    → Flow: IF TRUE: Update, IF FALSE: Delete

CNDN_SEQ (Sequence Condition) - Use for MULTIPLE INDEPENDENT parallel conditions:
- 2+ independent conditions, each with its own separate action
- Keywords: "check if A then X, AND check if B then Y", "verify if A AND verify if B"
- REQUIRES: "and check if" or "and if" connecting independent conditions
- Each condition is evaluated independently (parallel, not cascading)
- Contains CNDN_LGC (Logic Block) for each independent condition
- Examples:
  - "Check if status is approved then send email, AND check if amount > 1000 then send alert" 
    → CNDN_SEQ with 2 CNDN_LGC blocks
  - "Verify if user exists then log, AND verify if email is valid then proceed" 
    → CNDN_SEQ with 2 CNDN_LGC blocks

CNDN_DOM (Domino Condition) - Use for CASCADING sequential conditions:
- Conditions where each ELSE leads to the next condition check
- Keywords: "first check X, if not then check Y", "try X, if fails try Y"
- Each condition depends on previous condition's failure
- Examples:
  - "First check if user exists, if not then check permissions, if not then check quota" 
    → CNDN_DOM with 3 containers
  - "Try premium service, if fails try standard, if fails try basic" 
    → CNDN_DOM with 3 containers

DO NOT include ANY condition (CNDN_BIN, CNDN_SEQ, CNDN_DOM) for:
- Simple data extraction with filtering conditions (JMES/Filter handle conditions internally)
- Direct action events with built-in conditions (duplicate/restore/delete/update handle "where/when" conditions internally)
- Sequential actions without conditional branching ("do A then do B then do C")
- Examples:
  - "Get names where salary > 50000" → EVNT_JMES ONLY (no CNDN_BIN)
  - "Get records where status = 'active'" → EVNT_FLTR ONLY (no CNDN_BIN)
  - "duplicate the record where id = 5" → EVNT_RCRD_DUP ONLY (no CNDN_BIN)
  - "delete a record when status is expired" → EVNT_RCRD_DEL ONLY (no CNDN_BIN)
  - "Send email" → EVNT_NOTI_MAIL ONLY (no condition)
  - "Create a record" → EVNT_RCRD_ADD ONLY (no condition)

⚠️ CRITICAL DISTINCTION:
- "but X be Y" = Field specification (set X to Y) → NO condition needed
- "if X then Y" = Conditional branching (check X, decide action) → USE appropriate condition
- "then" connecting sequential actions = Simple sequence → NO condition needed
- "then" after "if" = Conditional branch → USE appropriate condition
- "where" in data queries = Filter criteria → NO condition needed (handled by event)
- "when" in direct actions (delete when, update when) = Built-in filter → NO condition needed



"""
}

PROMPT_CONDITIONS_SUPPORT = {

    "doc_type": "RULE",
    "topic": "conditions",
    "priority": 100,
    "role": "support",
"data": """
SUPPORT.RULE.conditions | doc_type=RULE | role=support | priority=100
Signature: CNDN_BIN; CNDN_SEQ; CNDN_DOM; FLOW_SEQUENCE_FORMAT; CONDITION_CONTAINERS

Task:
When a condition type is chosen, describe the workflow plan structure and required branches/blocks for that condition.

Outputs:
CNDN_BIN / CNDN_SEQ / CNDN_DOM
Logic blocks: CNDN_LGC (for BIN/SEQ), CNDN_LGC_DOM (for DOM containers)

Minimal pattern cues (no examples, no other event families):
- CNDN_BIN: single conditional check with TRUE/FALSE outcomes (explicit or implicit else-to-end)
- CNDN_SEQ: 2+ independent checks connected as parallel/sequence checks, each in its own logic block
- CNDN_DOM: cascading fallback chain where a failed check routes to the next container

Flow Sequence requirements:
- Always include both branches for CNDN_BIN:
  IF TRUE: <action placeholder> → END
  IF FALSE: <action placeholder or route to END> → END
- For CNDN_SEQ: include N logic blocks; each block is an independent check → its outcome
- For CNDN_DOM: include ordered containers; each container routes to next on failure; final failure routes to END

Formatting constraints:
- The workflow plan is NOT JSON.
- Show ordered steps: Trigger → Start → Condition → End.
- Use placeholders for actions/events inside branches if action details come from other topics.

ref:conditions#support
"""
,

    "text": """⚠️⚠️⚠️ CRITICAL: CONDITION TYPE DETECTION ⚠️⚠️⚠️

STEP A: CONDITION PATTERN ANALYSIS

Read the query carefully and look for these EXACT patterns:

PATTERN 1 - CNDN_DOM (Domino/Cascading Condition):
Keywords: "if not then", "else check if", "if fails", "first check...if not"
Meaning: CASCADING conditions where each condition depends on the previous one's failure.

Structure in Flow Sequence: #condition containeer may varies according to the user query
  ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Domino Condition (CNDN_DOM) 
      ↳ Container 1 (CNDN_LGC_DOM)
         → IF: Check status is Low → Send Email (EVNT_NOTI_MAIL)
         → ELSE: Route to Container 2
      ↳ Container 2 (CNDN_LGC_DOM)
         → IF: Check status is Medium → Send Alert (EVNT_NOTI_NOTI)
         → ELSE: Route to END
   4. End

Examples that MUST use CNDN_DOM:
- "First check if X then A, if not then check if Y then B" → CNDN_DOM ✓
- "Check if status is Low then email, if not then check if status is Medium then alert" → CNDN_DOM ✓
- "Try X, if fails try Y, if fails try Z" → CNDN_DOM ✓

PATTERN 2 - CNDN_SEQ (Sequence/Parallel Condition):
Keywords: "AND check if", "and check if", "and verify if", "and if"
Meaning: INDEPENDENT parallel conditions that are ALL evaluated simultaneously.

Structure in Flow Sequence:
    ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Sequence Condition (CNDN_SEQ)
      ↳ Logic Block 1 (CNDN_LGC): Check if status is approved → Send Email (EVNT_NOTI_MAIL)
      ↳ Logic Block 2 (CNDN_LGC): Check if amount > 1000 → Send Alert (EVNT_NOTI_NOTI)
   4. End

Examples that MUST use CNDN_SEQ:
- "Check if A then X, AND check if B then Y" → CNDN_SEQ ✓
- "Check if status is approved then send email, and check if amount > 1000 then send alert" → CNDN_SEQ ✓
- "Verify status AND verify amount AND verify date" → CNDN_SEQ ✓

PATTERN 3 - CNDN_BIN (Binary Condition):
Keywords: "if X then Y", "if X then Y else Z", "when X then Y"
Meaning: Single condition with two possible paths (TRUE/FALSE), no cascading, no parallel.

⚠️ CRITICAL: CNDN_BIN ELSE BRANCH SPECIFICATION
- Always explicitly specify BOTH branches in your workflow plan
- Structure must show what happens in BOTH IF TRUE and IF FALSE cases

Structure in Flow Sequence:( ALWAYS SHOW BOTH BRANCHES:)
   ##Flow Sequence
   1. Trigger (TRG_DB)
   2. Start
   3. Binary Condition (CNDN_BIN)
      ↳ IF TRUE: Send Email (EVNT_NOTI_MAIL) → END
      ↳ IF FALSE: Send Notification (EVNT_NOTI_NOTI) → END
   4. End

  CRITICAL RULES:
   - ALWAYS show both IF TRUE and IF FALSE paths
   - If no explicit ELSE action in query, write: "↳ IF FALSE: route to END"
   - Each branch MUST show the event code in parentheses: (EVNT_XXX)
   - Always include → END at the end of each branch path

Examples that MUST use CNDN_BIN:
- "If quantity > 100 send email, else send notification"
  → CNDN_BIN
  → IF TRUE: Send Email (EVNT_NOTI_MAIL)
  → IF FALSE: Send Notification (EVNT_NOTI_NOTI)

- "If status is active update record, else delete record"
  → CNDN_BIN
  → IF TRUE: Update Record (EVNT_RCRD_UPDT)
  → IF FALSE: Delete Record (EVNT_RCRD_DEL)

- "If user exists create record" (no else specified)
  → CNDN_BIN
  → IF TRUE: Create Record (EVNT_RCRD_ADD)
  → IF FALSE: do nothing (route to END)

- "Send email when status = approved" (implicit single-branch)
  → CNDN_BIN
  → IF TRUE: Send Email (EVNT_NOTI_MAIL)
  → IF FALSE: do nothing (route to END)

CRITICAL DISTINCTION TABLE:

| Query Pattern | Condition Type | Reason |
|--------------|----------------|--------|
| "if not then check" | CNDN_DOM | Cascading - second check only if first fails |
| "else check if" | CNDN_DOM | Cascading - each else leads to next check |
| "first check...if not" | CNDN_DOM | Cascading - sequential with fallback |
| "AND check if" | CNDN_SEQ | Parallel - all conditions evaluated independently |
| "and check if" | CNDN_SEQ | Parallel - all conditions evaluated independently |
| Single "if X then Y" | CNDN_BIN | Simple binary - one condition with implicit ELSE to END |
| "if X then Y else Z" | CNDN_BIN | Simple binary - one condition with explicit ELSE |
| Single "when X" | CNDN_BIN | Simple binary - one condition with implicit ELSE to END |


⚠️ CONDITION TYPE DECISION PROCESS:

STEP A: Count the conditions in the query
- How many "if" statements are there?
- How many "check if" statements are there?
- Are they connected by "and" or are they cascading with "if not/else"?

STEP B: Apply these rules:

CNDN_BIN (Binary Condition) - Use for SINGLE IF-THEN branching:
- ONE condition with IF-THEN-ELSE logic (explicit or implicit ELSE)
- Keywords: "if X then do Y", "if X then create else update", "when X then Y", "send email if X"
- ALWAYS specify in Flow Sequence:
  * What happens when TRUE
  * What happens when FALSE (even if it's "route to END")
- Examples:
  - "If value > 100 create a record" 
    → Flow: IF TRUE: Create, IF FALSE: END
  - "Send email if status is pending" 
    → Flow: IF TRUE: Send Email, IF FALSE: END
  - "If quantity < 50 then update record else delete record" 
    → Flow: IF TRUE: Update, IF FALSE: Delete

CNDN_SEQ (Sequence Condition) - Use for MULTIPLE INDEPENDENT parallel conditions:
- 2+ independent conditions, each with its own separate action
- Keywords: "check if A then X, AND check if B then Y", "verify if A AND verify if B"
- REQUIRES: "and check if" or "and if" connecting independent conditions
- Each condition is evaluated independently (parallel, not cascading)
- Contains CNDN_LGC (Logic Block) for each independent condition
- Examples:
  - "Check if status is approved then send email, AND check if amount > 1000 then send alert" 
    → CNDN_SEQ with 2 CNDN_LGC blocks
  - "Verify if user exists then log, AND verify if email is valid then proceed" 
    → CNDN_SEQ with 2 CNDN_LGC blocks

CNDN_DOM (Domino Condition) - Use for CASCADING sequential conditions:
- Conditions where each ELSE leads to the next condition check
- Keywords: "first check X, if not then check Y", "try X, if fails try Y"
- Each condition depends on previous condition's failure
- Examples:
  - "First check if user exists, if not then check permissions, if not then check quota" 
    → CNDN_DOM with 3 containers
  - "Try premium service, if fails try standard, if fails try basic" 
    → CNDN_DOM with 3 containers

DO NOT include ANY condition (CNDN_BIN, CNDN_SEQ, CNDN_DOM) for:
- Simple data extraction with filtering conditions (JMES/Filter handle conditions internally)
- Direct action events with built-in conditions (duplicate/restore/delete/update handle "where/when" conditions internally)
- Sequential actions without conditional branching ("do A then do B then do C")
- Examples:
  - "Get names where salary > 50000" → EVNT_JMES ONLY (no CNDN_BIN)
  - "Get records where status = 'active'" → EVNT_FLTR ONLY (no CNDN_BIN)
  - "duplicate the record where id = 5" → EVNT_RCRD_DUP ONLY (no CNDN_BIN)
  - "delete a record when status is expired" → EVNT_RCRD_DEL ONLY (no CNDN_BIN)
  - "Send email" → EVNT_NOTI_MAIL ONLY (no condition)
  - "Create a record" → EVNT_RCRD_ADD ONLY (no condition)

⚠️ CRITICAL DISTINCTION:
- "but X be Y" = Field specification (set X to Y) → NO condition needed
- "if X then Y" = Conditional branching (check X, decide action) → USE appropriate condition
- "then" connecting sequential actions = Simple sequence → NO condition needed
- "then" after "if" = Conditional branch → USE appropriate condition
- "where" in data queries = Filter criteria → NO condition needed (handled by event)
- "when" in direct actions (delete when, update when) = Built-in filter → NO condition needed

"""
}

PROMPT_LOOPS_TYPES = {

    "doc_type": "RULE",
    "topic": "loops",
    "priority": 70,
    "role": "support",
"data": """
SUPPORT.RULE.loops | doc_type=RULE | role=support | priority=70
Signature: EVNT_LOOP_FOR; EVNT_LOOP_WHILE; EVNT_LOOP_DOWHILE; LOOP_CONTROL; LOOP_FORMAT

Task:
Detect explicit repetition/iteration intent and map to correct loop event type; format loop blocks in the workflow plan.

Use ONLY when the query explicitly asks for repetition (e.g., "repeat", "N times", "loop", "iterate", "for each", "for every", "from X to Y").
Do NOT use for CRUD actions unless explicit repetition is stated.

Loop type mapping:
- EVNT_LOOP_FOR: iterate over a collection OR repeat N times / range iteration
  cues: for each; for every; iterate; process all; loop from X to Y; repeat N times; repeat 3 times; run N times
- EVNT_LOOP_WHILE: pre-check loop (condition evaluated before each iteration)
  cues: while; as long as; until <state changes> (pre-check phrasing)
- EVNT_LOOP_DOWHILE: post-check loop (executes at least once then checks)
  cues: do while; do once then check; execute at least once; run then verify; at least once
- EVNT_LOOP_BREAK: exit loop early
  cues: break; stop loop; exit loop
- EVNT_LOOP_CONTINUE: skip iteration
  cues: skip this; continue; next iteration

Formatting rules (loops-only):
- Top-level: Trigger → Start → Loop Start (EVNT_LOOP_*) → Loop End → End
- Loop internals: use "↳ INSIDE LOOP:" lines (never numbered)
- Never number items inside a loop.
- Loop End is a top-level numbered step.

Nesting rule (placeholder-safe):
- If repetition appears inside a branch block, the loop must be nested inside that branch (not as a separate top-level step).

Not loops:
- Numeric comparisons or filters (e.g., value > 100, amount <= 50, where status = active)
- Thresholds or ranges used to select items

ref:loops#support
"""

,
    "text": """
3. Loop Events (EVNT_LOOP_FOR, EVNT_LOOP_WHILE, EVNT_LOOP_DOWHILE):

Use EVNT_LOOP_FOR when:
- Iterating over data collections: "for each item in", "for every item", "process all items"
- Iterating over numeric ranges: "loop from X to Y", "from 1 to 10", "repeat 5 times"

Use EVNT_LOOP_WHILE when:
- Condition checked BEFORE each iteration
- Keywords: "while X is true", "as long as", "until X becomes"

Use EVNT_LOOP_DOWHILE when:
- Action executes at least ONCE, then condition checked
- Keywords: "do while", "do X at least once", "execute then check", "at least once"

Use EVNT_LOOP_BREAK when:
- Need to exit loop immediately based on condition
- Keywords: "break when", "exit loop if", "stop loop when"

Use EVNT_LOOP_CONTINUE when:
- Need to skip current iteration
- Keywords: "skip if", "continue to next if"

⚠️⚠️⚠️ CRITICAL: QUERY INTERPRETATION - WHEN TO USE LOOPS ⚠️⚠️⚠️

PATTERN 1: LOOP INSIDE CONDITION (Query has BOTH condition AND repetition)
Query pattern: "When [condition], [action] N times"
Examples:
- "When status is approved, send 10 emails"
- "If amount > 1000, create 5 records"
- "When user is active, notify 3 times"

Structure:
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: For Loop (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: <Action> (<EVENT_CODE>)
   ↳ IF FALSE: Route to END
4. End

Flow visualization:
START → Binary Condition → IF TRUE → Loop → Loop Start → Action (inside loop) → Loop End → END
                        └→ IF FALSE → END

PATTERN 2: STANDALONE LOOP (Query has ONLY repetition, NO condition)
Query pattern: "[Action] N times" (no "when" or "if")
Examples:
- "Send email 10 times"
- "Loop through all items and update them"

Structure:
3. Loop Start (EVNT_LOOP_FOR)
   ↳ INSIDE LOOP: <Action> (<EVENT_CODE>)
4. Loop End
5. End

Flow visualization:
START → Loop Start → Action (inside loop) → Loop End → END

DECISION TREE - Which pattern to use?
1. Does query have condition keywords ("when", "if", "whenever")?
   YES → Check for repetition
         Has repetition ("N times", "repeat", "loop")? 
         YES → Use PATTERN 1 (Loop INSIDE condition)
         NO  → Use simple binary condition (no loop)
   NO  → Check for repetition
         Has repetition ("N times", "repeat", "loop")?
         YES → Use PATTERN 2 (Standalone loop)
         NO  → Use simple event (no condition, no loop)

⚠️⚠️⚠️ CRITICAL: UNIVERSAL FORMATTING RULES FOR BINARY CONDITIONS ⚠️⚠️⚠️

When ANY event appears inside a Binary Condition (CNDN_BIN) branch, follow these rules:

CORE PRINCIPLE:
- Events inside conditional branches are NOT numbered
- Events inside conditional branches use ↳ arrow notation
- Event codes MUST appear on the same line as the branch indicator (IF TRUE/IF FALSE)

STRUCTURE PATTERN FOR CONDITIONS:

## Flow Sequence
1. Trigger (...)
2. Start
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: <Description> (<EVENT_CODE>)
      [↳ nested content if event has sub-items]
   ↳ IF FALSE: <Description> (<EVENT_CODE>) OR Route to END
4. End

STRUCTURE PATTERN FOR STANDALONE LOOPS:

## Flow Sequence
1. Trigger (...)
2. Start
3. Loop Start (<EVNT_LOOP_XXX>)
   ↳ INSIDE LOOP: <Action> (<EVENT_CODE>)
4. Loop End
5. End

FORMATTING RULES:

Rule 1: BRANCH EVENT PLACEMENT (For conditions)
✅ Correct: ↳ IF TRUE: <Action Description> (<EVENT_CODE>)
❌ Wrong:   ↳ IF TRUE: <Some text> → 
            4. <Action Description> (<EVENT_CODE>)

Rule 2: NUMBERING
- Only number: Trigger, Start, top-level Conditions/Events/Loops, Loop End, End
- Never number: Anything inside a conditional branch
- Never number: Anything inside a loop (use ↳ INSIDE LOOP)
- Inside branches: Use ↳ exclusively

Rule 3: EVENT CODE INCLUSION
- ALWAYS include event codes in parentheses: (EVNT_XXX)
- Event code appears on the SAME LINE as the branch (IF TRUE/IF FALSE)
- If branch has multiple events, repeat the branch indicator for each

Rule 4: BRANCH COMPLETENESS (For conditions)
- ALWAYS specify both IF TRUE and IF FALSE
- If a branch has no action: write "Route to END"

Rule 5: NESTED CONTENT (For loops)
- Loop internals ALWAYS use "INSIDE LOOP:" prefix
- Use ↳ indentation for items inside loops
- Never number items inside loops

Rule 6: MULTIPLE EVENTS IN ONE BRANCH
- Repeat the branch indicator (↳ IF TRUE or ↳ IF FALSE) for each event
- Each event gets its own line with its event code

COMPLETE EXAMPLES:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example 1: Loop INSIDE condition (PATTERN 1)
Query: "When application status changes to Approved, send 10 times email notifications to anish@gmail.com"

## Flow Sequence
1. Trigger (TRG_DB)
2. Start
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: For Loop (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: Send Email Notification (EVNT_NOTI_MAIL)
   ↳ IF FALSE: Route to END
4. End

Why this structure:
- Query has condition: "When status changes to Approved" → Binary Condition needed
- Query has repetition: "send 10 times" → Loop needed
- Both present → Loop goes INSIDE the IF TRUE branch
- Email event goes INSIDE the loop
- No numbered items inside the condition
- No numbered items inside the loop

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example 2: Standalone loop (PATTERN 2)
Query: "Send email to anish@gmail.com 10 times"

## Flow Sequence
1. Trigger (TRG_DB)
2. Start
3. Loop Start (EVNT_LOOP_FOR)
   ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)
4. Loop End
5. End

Why this structure:
- Query has NO condition (no "when", "if")
- Query has repetition: "10 times" → Loop needed
- No condition → Loop is standalone (numbered as step 3)
- Email event goes INSIDE the loop
- Loop End is numbered (step 4)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example 3: Condition WITHOUT loop
Query: "When status is approved, send email to anish@gmail.com"

## Flow Sequence
1. Trigger (TRG_DB)
2. Start
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: Send Email (EVNT_NOTI_MAIL)
   ↳ IF FALSE: Route to END
4. End

Why this structure:
- Query has condition: "When status is approved" → Binary Condition needed
- Query has NO repetition (no "N times") → No loop needed
- Email event goes directly in IF TRUE branch

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example 4: Multiple events in loop inside condition
Query: "When quantity > 100, loop 5 times and create record then send email each time"

## Flow Sequence
1. Trigger (TRG_DB)
2. Start
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: For Loop (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: Create Record (EVNT_RCRD_ADD)
      ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)
   ↳ IF FALSE: Route to END
4. End

Why this structure:
- Condition + repetition → Loop inside IF TRUE
- Multiple actions per iteration → Multiple "INSIDE LOOP" items
- Both events execute on each loop iteration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example 5: Nested loops (loop inside loop) - standalone
Query: "Loop 3 times, and in each iteration loop 5 times to send email"

## Flow Sequence
1. Trigger (TRG_DB)
2. Start
3. Outer Loop Start (EVNT_LOOP_FOR)
   ↳ INSIDE LOOP: Inner Loop Start (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)
4. Outer Loop End
5. End

Why this structure:
- No condition → Standalone loops
- Nested loops → Inner loop is INSIDE outer loop
- Email is INSIDE the inner loop

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WRONG PATTERNS - NEVER DO THESE:

❌ WRONG Pattern 1: Loop as separate numbered step after condition
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: Send Email (EVNT_NOTI_MAIL)
   ↳ IF FALSE: Route to END
4. Loop Start (EVNT_LOOP_FOR)
   ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)

Why wrong: Loop executes AFTER condition completes, not inside IF TRUE

❌ WRONG Pattern 2: Numbered items inside condition
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: Loop Started
   4. Loop (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)

Why wrong: Cannot number items inside a conditional branch

❌ WRONG Pattern 3: Event before loop in same branch
3. Binary Condition (CNDN_BIN)
   ↳ IF TRUE: Send Email (EVNT_NOTI_MAIL)
   ↳ IF TRUE: For Loop (EVNT_LOOP_FOR)
      ↳ INSIDE LOOP: Send Email (EVNT_NOTI_MAIL)

Why wrong: If query says "send N times", there should be ONLY the loop, not a separate email before it

APPLICABILITY:
These rules apply to ALL event types:
- Loops (EVNT_LOOP_*)
- Notifications (EVNT_NOTI_*)
- Record operations (EVNT_RCRD_*)
- User management (EVNT_USER_*)
- Formulas (EVNT_FRMLA_*)
- Static record operations (EVNT_STC_RCRD_*)
- Any other event type

CRITICAL DON'TS:
❌ DO NOT create numbered items inside conditional branches
❌ DO NOT create numbered items inside loops
❌ DO NOT put event codes on separate lines from branch indicators
❌ DO NOT omit the IF FALSE branch (always specify it)
❌ DO NOT use → for flow continuation within branches (use ↳ only)
❌ DO NOT mix numbered and ↳ notation within the same conditional block

CRITICAL DO's:
✅ DO use ↳ for all items inside conditional branches
✅ DO use ↳ for all items inside loops with "INSIDE LOOP:" prefix
✅ DO include event code on same line as IF TRUE/IF FALSE
✅ DO specify both branches (IF TRUE and IF FALSE)
✅ DO use "Route to END" for branches with no action
✅ DO nest sub-items with additional ↳ indentation
✅ DO number only top-level flow steps (Trigger, Start, Condition, Loop Start, Loop End, End)
✅ DO mark loop internals with "INSIDE LOOP:"

LOOP TYPE IDENTIFICATION:
- DATA ITERATION LOOP: "for each item in", "for every record", "process all items", "each record"
- RANGE ITERATION LOOP: "from X to Y", "loop from A to B", "1 to 10", "repeat N times", "send X times"
```
"""
}

PROMPT_OUTPUT_CONTRACT = {
    "doc_type": "RULE",
    "topic": "output_contract",
    "priority": 90,      # below triggers_rules, above planner_policy
    "role": "support",
"data": """
SUPPORT.RULE.output_contract | doc_type=RULE | role=support | priority=90
Signature: MARKDOWN_OUTPUT_CONTRACT; STRUCTURED_TEMPLATE; SECTION_HEADERS; NUMBERED_STEPS

Purpose:
Enforce the output format contract: produce a structured workflow plan as raw Markdown, not JSON.

Format triggers:
workflow plan template; output format; structured plan; markdown sections; section headers; formatting rules; numbered steps; no code fences; no JSON

Trigger format (required):
## Trigger must include exactly one bullet line: "- TRG_*" (default TRG_DB if not explicitly specified)

Start format (required):
## Start must include exactly one bullet line: "- Start"

End format (required):
## End must include exactly one bullet line: "- End"

Loops format (required when loops are required):
- Include a ## Loops section only when repetition is required.
- The first line under ## Loops must be a bullet with EVNT_LOOP_* (e.g., "- EVNT_LOOP_FOR" or "- EVNT_LOOP_FOR (count: N)").
- The next line must be "↳ INSIDE LOOP: <EVNT_* ...>" (or the specific action).
- If the prompt declares LOOP_ONLY, omit ## Steps entirely and use only ## Loops for the action.
- Do NOT use ## Loops unless the query explicitly mentions repetition (e.g., "times", "repeat", "loop", "for each", "for every", "from X to Y").
- Never infer loops from words like "when" or "if". If there is no explicit repetition, do NOT use EVNT_LOOP_* and do NOT include ## Loops.
- Do NOT wrap CRUD actions (EVNT_RCRD_*) in loops unless the query explicitly asks for repetition.
- Never place EVNT_LOOP_* inside ## Steps; loop content must appear only under ## Loops.
- If the query says "at least once", use EVNT_LOOP_DOWHILE in ## Loops (not Conditions).
- If the query says "do while", use EVNT_LOOP_DOWHILE in ## Loops (not Conditions).

Conditions format (required when conditions are required):
- Include a ## Conditions section only when branching is required.
- The first line under ## Conditions must be a subheader: "### CNDN_BIN" or "### CNDN_SEQ" or "### CNDN_DOM".
- If conditions are required, ## Steps must be exactly one line: "1. CNDN_BIN" (or CNDN_SEQ/CNDN_DOM).
- When conditions are required, do NOT put any EVNT_* in ## Steps.
- Do NOT include ## Conditions unless the user explicitly asks for branching or mutually exclusive outcomes.
 - If ## Conditions is present, ## Steps must be exactly one line: "1. CNDN_BIN" or "1. CNDN_SEQ" or "1. CNDN_DOM".

Notification channel rules (required when notifications are requested):
- If the query mentions a notification channel, use the matching EVNT_NOTI_*:
  email → EVNT_NOTI_MAIL, sms/text → EVNT_NOTI_SMS, push → EVNT_NOTI_PUSH,
  webhook → EVNT_NOTI_WBH, in-app/system notification → EVNT_NOTI_NOTI.
- If no channel is specified but notification intent exists, default to EVNT_NOTI_NOTI.
- Do not include non-notification EVNT_* steps when the request is notification-only.
- If multiple channels are requested, list each channel as its own step and do NOT add ## Conditions.
- Never use ## Conditions to represent multiple notification channels.
- If the request is notification-only, use only EVNT_NOTI_* events.
- If a specific channel is mentioned, output ONLY that channel (do NOT add EVNT_NOTI_NOTI).
- If a notification uses a simple "when/if" trigger with no explicit else/otherwise, do NOT use ## Conditions; output the EVNT_NOTI_* steps directly.

Retrieval-only rules (required when user only wants to read/filter/project data):
- Do NOT use ## Conditions or ## Loops.
- Steps should include only EVNT_RCRD_INFO / EVNT_FLTR / EVNT_JMES as applicable.
- If filters/field selection are requested without actions, avoid EVNT_RCRD_* actions.
- If a filter is present and it already implies the record set, EVNT_FLTR alone is acceptable (EVNT_RCRD_INFO may be omitted).

Static-only rules (required when prompt declares STATIC_ONLY):
- Use EVNT_RCRD_*_STC variants for record CRUD and info (ADD/UPDT/DEL/REST/DUP/INFO).
- When static-only add/create is requested (e.g., department/role), use EVNT_RCRD_ADD_STC and avoid Conditions.

Template shape (header-only):
## Trigger
## Start
## Steps
## Conditions
## Loops
## End

Step-line constraints (token-neutral):
- Steps are numbered, single-line items only.
- No freeform branching sentences inside Steps.
- Conditional logic and repetition details belong in their dedicated sections, not in Steps.

ref:output_contract#support
"""
,
    "text": """
OUTPUT CONTRACT (STRUCTURED WORKFLOW PLAN TEMPLATE)

Your output MUST be a Markdown Structured Workflow Plan (NOT JSON) using only the sections required.

HARD FORMAT RULES (non-negotiable):
- ## Trigger must contain EXACTLY one bullet line in the format: "- TRG_*".
- If no explicit trigger is mentioned in the query, default to "- TRG_DB".
- ## Start must contain EXACTLY one bullet line: "- Start".
- ## End must contain EXACTLY one bullet line: "- End".
- Do NOT place "- End" anywhere except under ## End.
- Always include the ## End section as the final section in the plan.
- Never output a bare "- End" line unless it is directly under a "## End" header.
- The "## End" header must appear immediately before the "- End" line.
- Include exactly ONE "## End" header.
- The ## End section must be exactly two lines:
  ## End
  - End
- CRUD actions (EVNT_RCRD_ADD/UPDT/DEL/REST/DUP) must NOT be placed inside ## Loops unless the query explicitly requests repetition.
- Never output a bare "Start" line; it must be exactly "- Start" under ## Start.
- If static add/create is requested (departments/roles), do NOT include ## Conditions; output only EVNT_RCRD_ADD_STC.
- If the query mentions role/roles/department/departments, use ONLY _STC events for record CRUD.
- When using _STC actions, do NOT add EVNT_FLTR; the action already targets the static record set.
- When loops are required, ## Loops must include:
  - a single EVNT_LOOP_* bullet line
  - a following "↳ INSIDE LOOP: ..." line describing the loop action
- When conditions are required:
  - ## Steps must be exactly one line: "1. CNDN_BIN" or "1. CNDN_SEQ" or "1. CNDN_DOM"
  - ## Conditions must include a matching "### CNDN_*" subheader
  - No EVNT_* lines are allowed inside ## Steps
- When notification intent is present:
  - Use ONLY EVNT_NOTI_* steps (no EVNT_RCRD_*, EVNT_FLTR, EVNT_JMES, etc.)
  - If a channel is explicitly mentioned, it must be used
  - If multiple channels are requested, include each as its own step
- When retrieval-only intent is present:
  - Use ONLY EVNT_RCRD_INFO / EVNT_FLTR / EVNT_JMES steps
  - Do NOT include ## Conditions or ## Loops
- -If an EVNT_* appears inside ## Conditions → ### CNDN_BIN, it MUST NOT appear anywhere in ## Steps.

- NEVER write freeform "IF ... THEN ..." lines inside ## Steps.

-## Steps must contain ONLY numbered, single-line codes.
-## Steps must contain ONLY numbered, single-line codes.
-## Steps must contain ONLY numbered, single-line codes.
-Do NOT add sub-bullets under ## Steps.

    - If "conditions" topic is selected: Steps MUST be exactly: 1. CNDN_BIN or 1. CNDN_SEQ or 1. CNDN_DOM
      and MUST NOT list any EVNT_* steps.
    - Otherwise: Steps contains EVNT_* codes only (single-line each).

- Each numbered line in ## Steps MUST be a single line item.
  (No nested bullets, no multiline blocks, no IF/ELSE content.)

- If the query requires branching, use ONLY the ## Conditions section
  with ### CNDN_BIN / ### CNDN_SEQ / ### CNDN_DOM as appropriate.

- MUST: Never place CNDN_* (or any IF TRUE / IF FALSE blocks)
  inside ## Steps.

- Use ## Conditions ONLY when there are mutually exclusive TRUE vs FALSE paths (if/else).

- If the query uses "if / when / where" ONLY to select which records to act on
  (filtering, matching, constraints),
  DO NOT use ## Conditions.
  Encode filtering inside the EVNT_* parameters instead.

- Inside ### CNDN_BIN, the labels MUST be EXACTLY:
  - IF TRUE:
  - IF FALSE:
  (Do NOT write "IF email succeeds", "IF success", or similar.)

-If an EVNT_* appears inside ## Conditions → ### CNDN_BIN, it MUST NOT appear anywhere in ## Steps.
- When ## Conditions exists, ## Steps must include ONLY the unconditional events that occur BEFORE the branch decision.
- All conditional-path events must appear ONLY under ## Conditions.
- In ### CNDN_BIN, IF TRUE / IF FALSE refers to the success/failure of the most recent EVNT_ step in ## Steps immediately before the Conditions section.*

HARD BAN (Trigger-only mention): If the query mentions a record being created/edited/updated ONLY as the trigger/context (e.g., “when a record is edited in the UI”), DO NOT output any EVNT_RCRD_* steps.

-Only output EVNT_RCRD_* when the user explicitly requests record CRUD actions using verbs like: create/add/update/modify/delete/restore/duplicate/set status.

LOOP DEDUPE RULE:
- If the workflow includes a ## Loops section, do NOT repeat the looped action in ## Steps.
- ## Steps should only list top-level events that are NOT inside loops.

Use this template (omit sections that are not needed):

## Trigger

<TRG_*>

## Start

<brief start>
## Steps

If "conditions" topic is selected:

## CNDN_BIN OR 1. CNDN_SEQ OR 1. CNDN_DOM

Otherwise:

<EVNT_* ...>

<EVNT_* ...>

Conditions (ONLY if branching/conditional logic is required)
## CNDN_BIN / CNDN_SEQ / CNDN_DOM

<condition logic + branch/blocks>
↳ <EVNT_* ...>

Loops (ONLY if repetition is required)

<FOR/WHILE/DO-WHILE ...>
INSIDE LOOP:
↳ <EVNT_* ...>

## End

- DO NOT wrap the output in triple backticks (no ```markdown fences). Output raw Markdown only.

-ENFORCEMENT (no post-branch steps):
- If ## Conditions exists, ## Steps must include ONLY the unconditional EVNT_* steps that occur BEFORE branching.
- Therefore, ANY EVNT_* that occurs only on a TRUE/FALSE path (e.g., SMS after email success) MUST appear ONLY under ## Conditions → ### CNDN_BIN and MUST NOT appear in ## Steps.
- In other words: when branching exists, do NOT list “next” actions in ## Steps. Put them only in the branch path.
- When Conditions exist, Steps must NOT include any EVNT that is referenced in either branch.
- “If the query is ‘A; if A succeeds then B’, Steps must contain only A, and B must appear only under IF TRUE.”

"""
}


PROMPT_TRIGGERS_CATALOG = {

    "doc_type": "CATALOG",
    "topic": "triggers_catalog",
    "priority": 40,
    "role": "support",
"data": """
SUPPORT.CATALOG.triggers_catalog | doc_type=CATALOG | role=support | priority=40
Signature: TRIGGER_CODE_LOOKUP; TRG_*; TRIGGER_TYPES

Purpose:
Lookup and select the correct TRG_* trigger code from common trigger phrasing.

Trigger codes + aliases:
TRG_API: api trigger, api call, endpoint hit
TRG_DB: database trigger, record change, db event
TRG_FILE: file trigger, file uploaded, file created
TRG_SCH: scheduled trigger, cron, time-based, daily/weekly
TRG_BTN: ui trigger, button click
TRG_WBH: webhook trigger, incoming webhook
TRG_AUTH: authentication trigger, login/logout/password
TRG_APRVL: approval trigger, ui approval
TRG_FLD: field entry trigger, form field input
TRG_OUT: timeout trigger, process timeout

ref:triggers_catalog#support
"""
,

    "text": """
TRIGGERS LIST
TRG_API = "API Trigger"
TRG_DB = "Database Trigger"
TRG_FILE = "File Trigger"
TRG_SCH = "Scheduled Trigger"
TRG_BTN = "UI Trigger"
TRG_WBH = "Webhook Trigger"
TRG_AUTH = "Authentication Trigger"
TRG_APRVL = "UI Approval Trigger"
TRG_FLD = "UI Field Entry Trigger"
TRG_OUT = "Process Timeout Trigger"

TRIGGER METHODS
["pwd_reset","login","logout","cng_pwd","add_helpdesk","mod_helpdesk","delete_helpdesk",
"restore_helpdesk","add_form","mod_form","del_form","add_record","mod_record",
"restore_record","del_record","add_user","del_user","mod_user","restore_user",
"approved_public_registration","rejected_public_registration","add_department","mod_department",
"del_department","restore_department","add_role","mod_role","delete_role","restore_role",
"{method.lower()}_{str(status_code).lower()}"]

"""
}

PROMPT_PLANNER_POLICY = {

    "doc_type": "RULE",
    "topic": "planner_policy",
    "priority": 80,
    "role": "support",
"data": """
SUPPORT.RULE.planner_policy | doc_type=RULE | role=support | priority=80
Signature: PLANNER_OUTPUT_POLICY; FORMAT_GUIDELINES; MARKDOWN_ONLY; NO_EXTRA_COMMENTARY

Purpose:
Enforce planner output constraints (format + minimality).

Rules:
- Output only the structured workflow plan in raw Markdown (no extra commentary).
- Include only applicable sections; omit unused sections.
- Maintain sequence order: Trigger → Start → Steps → End.
- When the query implies alternative paths, include both outcomes in the dedicated logic section.
- When repetition is required, label repeated execution clearly inside the repetition block.
- Do not invent additional capabilities beyond what the user asked.

ref:planner_policy#support
"""
,
  "text": """
  PLANNER OUTPUT POLICY (FORMAT ONLY)

  - Output MUST be a Markdown Structured Workflow Plan only (no extra commentary).
  - Include only the sections that are applicable to the user request; omit unused sections entirely.
  - Keep the workflow sequence ordered from Trigger → Start → Steps → End.
  - For branching logic: show both TRUE and FALSE paths when an ELSE exists or is implied.
  - For loops: clearly mark any events inside loops with “(INSIDE LOOP)”.
  - Do not infer extra steps (notifications, records, conditions, loops) unless explicitly required by the query.
  """

}

PROMPT_TRIGGERS_RULES = {
    "doc_type": "RULE",
    "topic": "triggers_rules",
    "priority": 95,
    "role": "support",
"data": """
SUPPORT.RULE.triggers_rules | doc_type=RULE | role=support | priority=95
Signature: TRIGGER_SELECTION; DEFAULT_TRIGGER; TRG_DB_FALLBACK

default trigger; choose trigger; trigger rules
TRG_DB default; api trigger; file trigger; schedule trigger
ui button trigger; field entry trigger; webhook trigger; auth trigger; approval trigger; timeout trigger

ref:triggers_rules#support
""",

    "text": """
TRIGGER SELECTION RULES (DEFAULT + DECISION TREE)

- Default: If the user does NOT explicitly mention API/file/schedule/button/webhook/auth/approval/ui/field-entry/field/timeout,
  use TRG_DB.

- Use TRG_API only when the query explicitly mentions API call/request/endpoint/integration.
- Use TRG_FILE only when the query explicitly mentions file upload/import/export/CSV/Excel.
- Use TRG_SCH only when the query explicitly mentions time/schedule/daily/weekly/cron.

- Use TRG_BTN only when the query explicitly mentions clicking a button / UI action (explicit button click).
  Examples: "on button click", "when user clicks submit", "UI button pressed"

- Use TRG_FLD for UI field entry/update events (UI edit implies field update).
  Treat these as TRG_FLD (even if the query uses loose wording):
  - "UI triggered"
  - "triggered from UI"
  - "edited in UI"
  - "record edited from UI"
  - "UI field updated"
  - "form field changed"
  - "user edits record data"
MUST RULE: If the query contains "UI triggered" / "triggered from UI" / "edited in UI" / "record is edited" / "user edits record data" → TRG_FLD (do NOT default to TRG_DB).

- Use TRG_WBH only when the query explicitly mentions an incoming webhook.
- Use TRG_AUTH only for login/logout/password reset/change.
- Use TRG_APRVL only for approval events.
- Use TRG_OUT only for timeouts/expiry.

TRG_NOTI is NOT a valid trigger. Do not invent triggers. For notifications, use EVNT_NOTI_ events and TRG_DB by default unless the user explicitly indicates another trigger type (API/file/schedule/button/webhook/auth/approval/field/timeout).
"""
}


PROMPT_DATA_RETRIEVAL_ROUTER = {
  "doc_type": "RULE",
  "topic": "data_retrieval_filtering",
  "priority": 105,   # bump priority above 98 and 100, because it's a core router
  "role": "router",
"data": """
ROUTER.RULE.data_retrieval_filtering | doc_type=RULE | role=router | priority=105
Signature: LIST_QUERY_SEARCH; READ_RETRIEVE; WHERE_FILTERING; FIELD_SELECTION

get records; list records; show records; fetch records; retrieve records; search records; find records; query records
where filter; filter records; criteria; constraints; match records; records with field=value; records where field>value
select fields; return only fields; extract columns; projection; show only column; pick fields
count records; sort by; order by; group by; aggregate
ref:data_retrieval_filtering#router
"""
,

  "text": """
Use when the user wants to retrieve/list/search records and/or apply WHERE-style filtering,
or extract specific fields from records.
Do not use for create/update/delete actions.
"""
}

PROMPT_DATA_RETRIEVAL_SUPPORT = {
    "doc_type": "RULE",
    "topic": "data_retrieval_filtering",
    "priority": 110,
    "role": "support",
 "data": """
SUPPORT.RULE.data_retrieval_filtering | doc_type=RULE | role=support | priority=110
Signature: EVNT_RCRD_INFO; EVNT_FLTR; EVNT_JMES; READ_QUERY_PIPELINE

Goal:
Map read-only record retrieval requests to the correct retrieval events and their typical composition.

Event mapping:
- EVNT_RCRD_INFO: retrieve/list/show/fetch records from an entity/table
- EVNT_FLTR: apply where-style filtering criteria to a record set
- EVNT_JMES: select/extract/project fields/columns from records (field selection)

Common retrieval pipeline (composition):
EVNT_RCRD_INFO → EVNT_FLTR → EVNT_JMES
(omit steps that are not requested; for simple filtered retrievals, EVNT_FLTR alone is acceptable)
If both filtering and field selection are requested, include BOTH EVNT_FLTR and EVNT_JMES (in that order).

Keywords (retrieval-only):
get/list/show/retrieve/search/query records; where filter; criteria; constraints; matching; select fields; extract columns; projection; names/emails/ids

ref:data_retrieval_filtering#support
"""

,
    "text": """
DATA RETRIEVAL & FILTERING RULES

Use EVNT_RCRD_INFO for:
- "get records", "list records", "show records", "retrieve records" from a table/entity.

Use EVNT_FLTR for:
- "where ..." filtering on record sets (status=..., date between..., amount>...)
- IMPORTANT: filters do NOT require CNDN_* (filter is built into EVNT_FLTR)

Use EVNT_JMES for:
- extracting fields from retrieved records (e.g., "get names and emails where ...")
- JMES is for projection/field selection, not branching logic.

Never use CNDN_* for simple WHERE filtering.
Only use CNDN_* when the workflow branches into different actions (if/else).
If both a filter and specific fields are requested (e.g., "names/emails where ..."), output BOTH EVNT_FLTR and EVNT_JMES.
"""
}

PROMPT_DATA_RETRIEVAL_NO_LOOPS = {
    "doc_type": "RULE",
    "topic": "data_retrieval_filtering",
    "priority": 140,
    "role": "support",
"data": """
SUPPORT.RULE.data_retrieval_no_loops | doc_type=RULE | role=support | priority=140
Signature: RETRIEVAL_NO_LOOPS; READ_ONLY; NO_CONDITIONS_NO_LOOPS

Purpose:
When the user only wants to retrieve/list/filter/project data, do NOT use loops or conditions.

Rules:
- Do NOT include ## Loops
- Do NOT include ## Conditions
- Use ONLY EVNT_RCRD_INFO / EVNT_FLTR / EVNT_JMES in ## Steps
- Do NOT use EVNT_RCRD_ADD/UPDT/DEL/REST/DUP for read-only requests

ref:data_retrieval_no_loops#support
"""
,
    "text": """
RETRIEVAL-ONLY: NO LOOPS / NO CONDITIONS

If the user is only retrieving or filtering data:
- Never add ## Loops or ## Conditions.
- Steps should include only EVNT_RCRD_INFO / EVNT_FLTR / EVNT_JMES.
- Do not add any EVNT_RCRD_* action events.
"""
}

PROMPT_USER_MGMT_ROUTER = {
  "doc_type": "RULE",
  "topic": "user_mgmt",
  "priority": 150,
  "role": "router",
  "data": """
ROUTER.RULE.user_mgmt | doc_type=RULE | role=router | priority=150
Signature: USER_ACCOUNT_OBJECT; USER_ACCESS_PERMISSIONS; EVNT_USER_MGMT_*

Select when:
Primary object is a user account / user profile / user access / user permissions / role assignment.

Account actions (high-signal):
create user; add user; register user; update user details; update user profile
activate user; deactivate user; enable user; disable user
grant permission; revoke permission; user access; remove access
assign role to user; change user role; role assignment
extend responsibility; add responsibility; assign additional duties; make head of

Output family:
EVNT_USER_MGMT_ADD; EVNT_USER_MGMT_UPDT; EVNT_USER_MGMT_DEACT; EVNT_USER_MGMT_ASSIGN; EVNT_USER_MGMT_EXTND

ref:user_mgmt#router
"""
,

  "text": """
STOP-EARLY.
Intent: actions on a USER ACCOUNT OBJECT ONLY.
This topic applies ONLY when the PRIMARY OBJECT being changed is a user account.

MUST MATCH (the OBJECT is a USER ACCOUNT):
- explicit user account object: "user account", "user profile", "user details", "user permissions", "user access"
AND
- an account action:
  - create/add/register user account
  - update user profile/details
  - activate/deactivate user account
  - grant/revoke permissions for a user
  - assign role TO a user account
  - extend user responsibility/coverage

HIGH-CONFIDENCE POSITIVE EXAMPLES (user account mgmt):
- create a user with role admin
- update user details for John
- deactivate user account
- grant permissions to a user
- revoke user access
- assign role editor to user Alice
- extend user responsibility to HR system

HARD NEGATIVE (NOT user_mgmt; route away):
- task status update (done/completed/in progress)
- task completion form updates
- workflow state/status changes
- process step moved / moved to another task
- form status updates
- record/entity/table updates
- "change status to done"
- "mark as done"
- "task completed to done"
- "moved to another task"

DISAMBIGUATION RULE:
- If the updated object is a TASK/FORM/RECORD/WORKFLOW → NOT user_mgmt.
- Choose user_mgmt ONLY when the updated object is explicitly a USER ACCOUNT.

This topic does NOT apply to:
- tasks
- task status
- task completion forms
- workflow states
- workflow steps
- process stages
- record/entity updates
- form status updates

Output: EVNT_USER_MGMT_* family ONLY.

STEP -1: USER MANAGEMENT DETECTION (HIGHEST PRIORITY - CHECK FIRST)

USER KEYWORD DETECTION:
- Scan query for: user, users, country, countries, permission, permissions, access, role assignment, role assignments
- IF ANY USER KEYWORD FOUND: Check if the main action is on users (create, update, deactivate, activate, assign role, extend). If yes, ALWAYS use USER_MGMT events.
- USER MANAGEMENT EVENTS: EVNT_USER_MGMT_ADD, EVNT_USER_MGMT_UPDT, EVNT_USER_MGMT_DEACT, EVNT_USER_MGMT_ASSIGN, EVNT_USER_MGMT_EXTND
 - NEVER USE STATIC OR DYNAMIC EVENTS for user actions when user keywords are present.
 - For user info retrieval, use EVNT_USER_MGMT_INFO (user-specific retrieval).
- ONLY PROCEED TO OTHER STEPS IF NOT USER MANAGEMENT RELATED

SPECIAL CASES:
- If the query mentions assigning a role or granting permissions, use EVNT_USER_MGMT_ASSIGN ONLY.
- If the query mentions adding responsibility, extending responsibility, assigning additional duties, or making someone head, use EVNT_USER_MGMT_EXTND ONLY.
- If both assigning and extending actions appear together, prioritize EVNT_USER_MGMT_EXTND ONLY.

USER MANAGEMENT EXAMPLES:
- "create a user with role: admin, department: science" → EVNT_USER_MGMT_ADD ONLY
- "create a user with name :Abishek ,role:System Head, department: IT" → EVNT_USER_MGMT_ADD ONLY
- "add user with role manager and department IT" → EVNT_USER_MGMT_ADD ONLY
- "update user details" → EVNT_USER_MGMT_UPDT ONLY
- "update user email to alice@example.com" → EVNT_USER_MGMT_UPDT ONLY
- For any "update user ..." request, do NOT use CNDN_*; output a single EVNT_USER_MGMT_UPDT step.
- "change user role to manager" → EVNT_USER_MGMT_UPDT ONLY
- "deactivate user" → EVNT_USER_MGMT_DEACT ONLY
- "activate user" → EVNT_USER_MGMT_DEACT ONLY
- "assign role to user" → EVNT_USER_MGMT_ASSIGN ONLY
- "extend user to another system" → EVNT_USER_MGMT_EXTND ONLY
- "remove user access" → EVNT_USER_MGMT_DEACT ONLY
- "revoke user permissions" → EVNT_USER_MGMT_DEACT ONLY
- "grant user permissions" → EVNT_USER_MGMT_ASSIGN ONLY
- "add user access to system" → EVNT_USER_MGMT_EXTND ONLY
- "create user john with role admin" → EVNT_USER_MGMT_ADD ONLY
- "activate user jane" → EVNT_USER_MGMT_DEACT ONLY
- "deactivate user mike" → EVNT_USER_MGMT_DEACT ONLY
- "assign role editor to user alice" → EVNT_USER_MGMT_ASSIGN ONLY
- "extend user bob to system HR" → EVNT_USER_MGMT_EXTND ONLY
- "create user in department IT with role manager" → EVNT_USER_MGMT_ADD ONLY
- "update user john to role admin" → EVNT_USER_MGMT_UPDT ONLY
- "find user with role manager" → EVNT_USER_MGMT_INFO ONLY
- "get user permissions for user john" → EVNT_USER_MGMT_INFO ONLY
- "retrieve user from department IT" → EVNT_USER_MGMT_INFO ONLY
- "get user info" → EVNT_USER_MGMT_INFO ONLY
- "show user profile" → EVNT_USER_MGMT_INFO ONLY
- "Andrew get's added responsibility of head " → EVNT_USER_MGMT_EXTND ONLY
- "extend Ramesh's responsibility to HR and Finance" → EVNT_USER_MGMT_EXTND ONLY
- "assign additional duties to Priya in Marketing" → EVNT_USER_MGMT_EXTND ONLY
- "make Sunil the head of the Operations department" → EVNT_USER_MGMT_EXTND ONLY
""",
}

PROMPT_STATIC_VS_DYNAMIC_ROUTER = {
  "doc_type": "RULE",
  "topic": "static_vs_dynamic",
  "priority": 130,
  "role": "router",
 "data": """
ROUTER.RULE.static_vs_dynamic | doc_type=RULE | role=router | priority=130
Signature: STATIC_DIMENSIONS; ROLE_DEPARTMENT; USE_STC_SUFFIX

Select when:
Query targets static reference dimensions such as roles or departments (static catalogs).

High-signal static cues:
role; roles; department; departments

Examples:
- update record where department is Science
- delete a record where role is Teacher

Not static (dynamic):
- status is active/inactive
- date, amount, tag, archived

Output rule:
Use _STC event family (static record operations) when static cues are present.

Static event family tokens:
EVNT_RCRD_ADD_STC; EVNT_RCRD_INFO_STC; EVNT_RCRD_UPDT_STC; EVNT_RCRD_DEL_STC; EVNT_RCRD_REST_STC; EVNT_RCRD_DUP_STC

ref:static_vs_dynamic#router
"""


,
    "text": """STEP 0: STATIC vs DYNAMIC RECORD CLASSIFICATION (HIGHEST PRIORITY - CHECK FIRST)

STATIC KEYWORD DETECTION:
- Scan query for: role, roles, department, departments
- IF ANY STATIC KEYWORD FOUND: ALWAYS use STATIC events (_STC suffix)
- STATIC EVENTS: EVNT_RCRD_ADD_STC, EVNT_RCRD_INFO_STC, EVNT_RCRD_UPDT_STC, EVNT_RCRD_DEL_STC, EVNT_RCRD_REST_STC, EVNT_RCRD_DUP_STC
- NEVER USE DYNAMIC EVENTS when static keywords are present

STATIC RECORD EXAMPLES:
- "create a record with role admin" → EVNT_RCRD_ADD_STC ONLY
- "add department IT" → EVNT_RCRD_ADD_STC ONLY
- "update role from admin to user" → EVNT_RCRD_UPDT_STC ONLY
- "get all departments" → EVNT_RCRD_INFO_STC ONLY
- "delete a record with department system head" → EVNT_RCRD_DEL_STC ONLY
- "restore role admin" → EVNT_RCRD_REST_STC ONLY
- "get user permissions for department IT" → EVNT_RCRD_INFO_STC ONLY
- "update record where department is Science" → EVNT_RCRD_UPDT_STC ONLY
- "delete a record where role is Teacher" → EVNT_RCRD_DEL_STC ONLY
- "restore a record where department is management" → EVNT_RCRD_REST_STC ONLY
- "duplicate the record where department is management" → EVNT_RCRD_DUP_STC ONLY
- "add new department science" → EVNT_RCRD_ADD_STC ONLY
- "find role manager" → EVNT_RCRD_INFO_STC ONLY
- "change role to manager" → EVNT_RCRD_UPDT_STC ONLY
- "remove department science" → EVNT_RCRD_DEL_STC ONLY
""",
}

# PROMPT_ROUTER_DISAMBIGUATION = {
#     "doc_type": "RULE",
#     "topic": "router_disambiguation",
#     "priority": 130,   # higher than everything else
#     "role": "router",
# "data": """
# ROUTER.RULE.router_disambiguation | doc_type=RULE | role=router | priority=130
# Signature: ROUTER_TIEBREAK_RULES; USER_MGMT_VS_STATIC

# ref:router_disambiguation#router
# """


# PROMPT_LOOPS_ROUTER = {
#     "doc_type": "RULE",
#     "topic": "loops",
#     "priority": 90,
#     "role": "router",
#     "data": """

# """,
#     "text": """Use when query requires repetition. Use EVNT_LOOP_* and put actions INSIDE LOOP."""
# }

PROMPT_CONDITIONS_ROUTER_STRONG = {
  "doc_type": "RULE",
  "topic": "conditions",
  "priority": 160,
  "role": "router",
"data": """
ROUTER.RULE.conditions_strong | doc_type=RULE | role=router | priority=160
Signature: BRANCH_DECISION; IF_ELSE_LOGIC; CNDN_BIN; CNDN_SEQ; CNDN_DOM

if else; else; otherwise
if not then; else check if; fallback; fails then
and check if; and verify if; parallel checks; multiple checks
if status is approved then send email else send notification
if X then email else notify
if condition then send email, otherwise send notification

NOT for: where/when filtering; record CRUD with predicates; data retrieval filtering

Outputs:
CNDN_BIN; CNDN_SEQ; CNDN_DOM

ref:conditions#router_strong
"""
,
  "text":   "Intent: explicit TRUE/FALSE branching decisions.\n"
  "Triggers: IF/ELSE, fallback, parallel checks.\n"
  + PROMPT_COND_OVERVIEW_AND_PATTERNS["text"]  # <— reuse existing full rules
}

PROMPT_LOOPS_NO_INFERENCE = {
  "doc_type": "RULE",
  "topic": "loops",
  "priority": 160,
  "role": "router",
"data": """
ROUTER.RULE.loops_no_inference | doc_type=RULE | role=router | priority=160
Signature: NO_IMPLICIT_LOOPS; REQUIRE_REPETITION_TERMS; WHEN_IF_NOT_LOOP

Purpose:
Prevent loop selection unless the query explicitly requests repetition.

Rules:
- Do NOT select loops for queries that only use conditional wording ("when", "if", "whenever") without repetition.
- Only select loops when explicit repetition is present (e.g., "times", "repeat", "loop", "for each", "for every", "from X to Y", "iterate").
- Treat "do while" and "at least once" as explicit loop intent (use EVNT_LOOP_DOWHILE).

ref:loops_no_inference#router
"""
,
  "text": "Do NOT use loops unless the user explicitly asks for repetition. "
  "Words like 'when' or 'if' alone do NOT imply loops. "
  "Treat 'do while' and 'at least once' as loop intent (EVNT_LOOP_DOWHILE)."
}







# -----------------
# Layer grouping
# -----------------

LAYER0_STOP_EARLY_ROUTING = [
    PROMPT_USER_MGMT_ROUTER,
    PROMPT_STATIC_VS_DYNAMIC_ROUTER,
]



LAYER3_DATA_OPS = [
    PROMPT_DATA_OPS_RULES,
    PROMPT_DATA_OPS_SUPPORT,
]
LAYER3_DATA_RETRIEVAL = [
    PROMPT_DATA_RETRIEVAL_ROUTER,
    PROMPT_DATA_RETRIEVAL_SUPPORT,
    PROMPT_DATA_RETRIEVAL_NO_LOOPS,
]


LAYER4_ACTIONS_BUILTIN_FILTERING = [
    PROMPT_ACTION_EVENTS_BUILTIN_FILTERING,
    PROMPT_ACTION_EVENTS_BUILTIN_FILTERING_SUPPORT,
]

LAYER5_CONDITIONS = [
    PROMPT_COND_OVERVIEW_AND_PATTERNS,
    PROMPT_CONDITIONS_SUPPORT,
    PROMPT_CONDITIONS_ROUTER_STRONG,
]

LAYER6_NOTIFICATIONS = [
    PROMPT_NOTIFICATIONS_INTENT,
    PROMPT_NOTIFICATIONS_SUPPORT,
]

LAYER7_LOOPS = [
    #PROMPT_LOOPS_ROUTER,
    PROMPT_LOOPS_NO_INFERENCE,
    PROMPT_LOOPS_TYPES,
]


LAYER8_TRIGGER_CATALOG = [
    PROMPT_TRIGGERS_CATALOG,
    PROMPT_TRIGGERS_RULES,
]

LAYER9_PLANNER_POLICY = [
    PROMPT_PLANNER_POLICY,
    PROMPT_OUTPUT_CONTRACT,
]

# Flat list used by embedding + retrieval.
chunk_data = (
    LAYER0_STOP_EARLY_ROUTING
    + LAYER4_ACTIONS_BUILTIN_FILTERING
    + LAYER6_NOTIFICATIONS
    + LAYER3_DATA_OPS
    + LAYER3_DATA_RETRIEVAL
    + LAYER5_CONDITIONS
    + LAYER7_LOOPS
    + LAYER8_TRIGGER_CATALOG
    + LAYER9_PLANNER_POLICY
)


__all__ = [
    'chunk_data',
    'LAYER0_STOP_EARLY_ROUTING',
    'LAYER3_DATA_OPS',
    'LAYER4_ACTIONS_BUILTIN_FILTERING',
    'LAYER5_CONDITIONS',
    'LAYER6_NOTIFICATIONS',
    'LAYER7_LOOPS',
    'LAYER8_TRIGGER_CATALOG',
    'LAYER9_PLANNER_POLICY',
]
