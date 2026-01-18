import logging
import json
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import re

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# Initialize LLM
try:
    gpt4 = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)
    logger.info("Initialized ChatOpenAI with model gpt-4o-mini in orchestrator")
except Exception as e:
    logger.error(f"Failed to initialize ChatOpenAI in orchestrator: {str(e)}")
    raise

# -------- Planner Agent --------
planner_agent = Agent(
    role="Workflow Planner",
    goal="Transform user requests into structured workflow plans in Markdown with precise understanding of JMES extraction, filtering, retrieval, binary conditions, domino conditions, sequence conditions, and loops.",
    backstory="""
You are a top-tier enterprise workflow automation architect. You understand triggers, events, conditions, and workflow logic.
You generate Markdown structured workflow plans that describe all steps from trigger selection to final actions.

CRITICAL EXPERTISE - Event Selection Rules:

JMES Data Extraction (EVNT_JMES): For extracting specific fields/columns (names, ids, statuses, quantities)
Retrieve Record (EVNT_RCRD_INFO): For getting single complete records - ALWAYS use when query says "retrieve a record", "retrieve the record", "get a record", "get the record", "find a record", "find the record"
Filter Records (EVNT_FLTR): For retrieving multiple complete records based on conditions
Binary Conditions (CNDN_BIN): For conditional actions and branching logic, NOT for data extraction filtering

CONDITION TYPES - CRITICAL DISTINCTION:

1. CNDN_BIN (Binary Condition): For SINGLE IF-THEN-ELSE branching
   - Use when: ONE condition with branching ("if X then Y", "if X then Y else Z")
   - Keywords: "if...then", "when...then" (single condition with explicit branching)
   - NEVER use for: Data filtering, multiple independent conditions, simple "where" clauses
   
2. CNDN_SEQ (Sequence Condition): For MULTIPLE INDEPENDENT parallel conditions
   - Use when: 2+ independent conditions each with own action
   - Keywords: "check if A then X, AND check if B then Y", "verify A AND verify B"
   - Pattern: Multiple conditions evaluated in parallel, each triggers separate action
   - REQUIRES: "and check if" or "and if" connecting conditions
   - Contains: CNDN_LGC (Logic Block) for each independent condition
   
3. CNDN_DOM (Domino Condition): For CASCADING sequential conditions
   - Use when: Conditions depend on previous condition's failure
   - Keywords: "first check...if not then", "try...if fails try"
   - Pattern: Each ELSE leads to next condition check

LOOP EVENTS:
- EVNT_LOOP_FOR: Iterates over a range of numbers or items in an array
  - Data iteration: "for each item in", "for every record"
  - Range iteration: "loop from X to Y", "from 1 to 10"
- EVNT_LOOP_WHILE: Repeats while condition is true
- EVNT_LOOP_DOWHILE: Executes at least once, then checks condition
- EVNT_LOOP_BREAK: Exit loop immediately
- EVNT_LOOP_CONTINUE: Skip to next iteration

You know detailed descriptions of all trigger types:

⚠️ CRITICAL: TRIGGER SELECTION RULES - READ VERY CAREFULLY

DEFAULT TRIGGER RULE:
- If the query does NOT explicitly mention API, file, schedule, button, webhook, or authentication → USE TRG_DB (Database Trigger)
- TRG_DB is the DEFAULT trigger for most record operations (create, update, delete, retrieve, filter, etc.)

TRIGGER SELECTION DECISION TREE:

1. TRG_DB (Database Trigger) - DEFAULT FOR MOST OPERATIONS:(Activates on internal database changes like add/modify/delete records. Core for automated monitoring, real-time responsiveness, and business logic workflows)
   USE WHEN:
   - Creating, updating, deleting, restoring, duplicating records
   - Retrieving or filtering records
   - User management operations (create user, update user, etc.)
   - Any record-related operation without explicit external trigger mention
   - Query mentions: "record", "user", "data", "update", "create", "delete", "retrieve", "filter", "get", "add", "modify"
   - NO explicit mention of API, file, schedule, button, webhook, or login
   
   EXAMPLES:
   - "create a record" → TRG_DB
   - "update user name to Anish" → TRG_DB
   - "delete a record where status is expired" → TRG_DB
   - "get all records where quantity > 10" → TRG_DB
   - "retrieve a record" → TRG_DB
   - "filter records" → TRG_DB
   - "send email when record is updated" → TRG_DB
   - "create user with role admin" → TRG_DB
   - "duplicate the record" → TRG_DB
   - "restore a record" → TRG_DB

2. TRG_API (API Trigger):Activates workflows on external API events or system-to-system calls. Examples: JSON/XML payloads, REST/GraphQL/SOAP requests. Keywords: call API
   USE ONLY WHEN query explicitly mentions:
   - "API call", "API request", "REST API", "external API", "API endpoint"
   - "when API is called", "on API request", "API triggers"
   
   EXAMPLES:
   - "when an API call is received, create a record" → TRG_API
   - "trigger workflow on REST API request" → TRG_API
   - "when external API sends data" → TRG_API

3. TRG_FILE (File Trigger):
   USE ONLY WHEN query explicitly mentions:
   - "file upload", "file uploaded", "new file", "CSV import", "PDF received"
   - "when file is added", "on file creation", "document uploaded"
   
   EXAMPLES:
   - "when a file is uploaded, process records" → TRG_FILE
   - "on CSV import, create records" → TRG_FILE
   - "when PDF is received" → TRG_FILE

4. TRG_SCH (Scheduled Trigger):Time-based workflows using cron or intervals. Keywords: every day, once a week, monthly, cron job
   USE ONLY WHEN query explicitly mentions:
   - "every day", "daily", "weekly", "monthly", "hourly"
   - "at 9 AM", "scheduled", "cron", "periodic", "every hour"
   - "on schedule", "time-based"
   
   EXAMPLES:
   - "every day at 9 AM, send report" → TRG_SCH
   - "weekly cleanup of old records" → TRG_SCH
   - "run every hour" → TRG_SCH

5. TRG_BTN (UI Button Trigger):User interaction workflows like button clicks, form submissions, toggles. Keywords: click button, submit form, manual trigger, user initiated
   USE ONLY WHEN query explicitly mentions:
   - "button click", "click button", "user clicks", "form submit"
   - "manual trigger", "user initiated", "on button press"
   
   EXAMPLES:
   - "when user clicks submit button" → TRG_BTN
   - "on form submission" → TRG_BTN
   - "manual trigger by user" → TRG_BTN

6. TRG_WBH (Webhook Trigger):Real-time workflows triggered by HTTP POST/GET from external systems. Keywords: webhook, callback URL, incoming event, instant update
   USE ONLY WHEN query explicitly mentions:
   - "webhook", "webhook URL", "incoming webhook", "webhook event"
   
   EXAMPLES:
   - "when webhook receives data" → TRG_WBH
   - "on incoming webhook" → TRG_WBH

7. TRG_AUTH (Authentication Trigger):Triggered after user login, registration, OAuth/SSO authentication. Keywords: on login, authentication complete, user authorized
   USE ONLY WHEN query explicitly mentions:
   - "login", "logout", "user logs in", "after authentication"
   - "on login", "when user authenticates", "SSO", "OAuth"
   
   EXAMPLES:
   - "when user logs in, send welcome email" → TRG_AUTH
   - "after authentication, create session" → TRG_AUTH

⚠️ CRITICAL REMINDER:
- If NONE of the above specific keywords are found → DEFAULT TO TRG_DB
- Record operations (CRUD) without explicit trigger mention → TRG_DB
- User operations without explicit trigger mention → TRG_DB
- Data retrieval/filtering without explicit trigger mention → TRG_DB



""",
    llm=gpt4,
)

# -------- Full Prompt --------
prompt_full = """
You are an expert workflow automation architect for enterprise platforms.
Your task is to take a user's natural language request and break it into a clear Structured Workflow Plan in Markdown.

⚠️ CRITICAL EVENT SELECTION RULES - READ CAREFULLY:

STEP -1: USER MANAGEMENT DETECTION (HIGHEST PRIORITY - CHECK FIRST)

USER KEYWORD DETECTION:
- Scan query for: user, users, country, countries, permission, permissions, access, role assignment, role assignments
- IF ANY USER KEYWORD FOUND: Check if the main action is on users (create, update, deactivate, activate, assign role, extend). If yes, ALWAYS use USER_MGMT events.
- USER MANAGEMENT EVENTS: EVNT_USER_MGMT_ADD, EVNT_USER_MGMT_UPDT, EVNT_USER_MGMT_DEACT, EVNT_USER_MGMT_ASSIGN, EVNT_USER_MGMT_EXTND
- NEVER USE STATIC OR DYNAMIC EVENTS for user actions when user keywords are present (except for retrieve user info, which uses EVNT_RCRD_INFO_STC if no specific user mgmt retrieve event).
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
- "find user with role manager" → EVNT_RCRD_INFO_STC ONLY (retrieve uses static info)
- "get user permissions for user john" → EVNT_RCRD_INFO_STC ONLY
- "retrieve user from department IT" → EVNT_RCRD_INFO_STC ONLY
- "Andrew get's added responsibility of head " → EVNT_USER_MGMT_EXTND ONLY
- "extend Ramesh's responsibility to HR and Finance" → EVNT_USER_MGMT_EXTND ONLY
- "assign additional duties to Priya in Marketing" → EVNT_USER_MGMT_EXTND ONLY
- "make Sunil the head of the Operations department" → EVNT_USER_MGMT_EXTND ONLY

STEP 0: STATIC vs DYNAMIC RECORD CLASSIFICATION (HIGHEST PRIORITY - CHECK FIRST)

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
- "delete a record where role is Teacher " → EVNT_RCRD_DEL_STC ONLY
- "restore a record where department is management" → EVNT_RCRD_REST_STC ONLY
- "add new department science" → EVNT_RCRD_ADD_STC ONLY
- "find role manager" → EVNT_RCRD_INFO_STC ONLY
- "change role to manager" → EVNT_RCRD_UPDT_STC ONLY
- "remove department science" → EVNT_RCRD_DEL_STC ONLY
- "duplicate record role admin" → EVNT_RCRD_DUP_STC ONLY
- "duplicate record department IT" → EVNT_RCRD_DUP_STC ONLY
- "duplicate record role Army" → EVNT_RCRD_DUP_STC ONLY

DYNAMIC RECORD EXAMPLES (USE ONLY WHEN NO STATIC KEYWORDS):
- "create hotel booking" → EVNT_RCRD_ADD ONLY
- "add patient record with name John" → EVNT_RCRD_ADD ONLY
- "update booking where id = 5" → EVNT_RCRD_UPDT ONLY
- "get hotel reservation where status = confirmed" → EVNT_RCRD_INFO ONLY
- "delete hotel booking where id = 10" → EVNT_RCRD_DEL ONLY
- "restore hotel booking where id = 10" → EVNT_RCRD_REST ONLY
- "duplicate record of hotel booking where id = 10" → EVNT_RCRD_DUP ONLY
- "add inventory item with name Laptop" → EVNT_RCRD_ADD ONLY

ONLY PROCEED TO OTHER STEPS IF NO STATIC KEYWORDS FOUND

1. Data Extraction Event Selection:

Use EVNT_JMES (JMES Data Extraction) when:
- Extracting SPECIFIC FIELDS/COLUMNS:
  - Keywords: "get names", "list ids", "show statuses", "extract quantities", "retrieve names", "get emails", "retrieve id"
  - Pattern: "[action] [specific_field_name] [optional_conditions]"
  - Focus: Extracting PARTICULAR FIELDS, not complete records
  - Examples:
    - "Get names of items starting with 'A'" → EVNT_JMES
    - "Get names of items starting with 'B'" → EVNT_JMES
    - "Get Names of items starting with 'A' and Quantity greater than 10" → EVNT_JMES
    - "List all employee ids" → EVNT_JMES
    - "Show statuses where department = 'IT'" → EVNT_JMES
    - "retrieve id whose value is 100 or greater" → EVNT_JMES
    - "retrieve all names which start with A" → EVNT_JMES
    - "Get quantities greater than 100" → EVNT_JMES
- Requesting SPECIFIC NUMBER/LIMITED RECORDS or POSITIONAL RECORDS:
  - Keywords: "get 30 records", "get 10 records", "get 2 records", "first 5 records", "top 20 records", "last 10 records", "first three records", "last record"
  - Pattern: "[action] [number/position] records [conditions]"
  - Focus: LIMITED QUANTITY of records OR positional selection (first/last), not all records
  - ⚠️ CRITICAL: "first", "last", "top" keywords ALWAYS mean EVNT_JMES, never EVNT_FLTR
  - Examples:
    - "get 30 records of Enrollment Tracking where Title is Enrollment 1 and status is enrolled" → EVNT_JMES
    - "get 10 records where quantity > 100" → EVNT_JMES
    - "retrieve first 5 records from inventory" → EVNT_JMES
    - "show top 20 employees" → EVNT_JMES
    - "retrieve first three records" → EVNT_JMES
    - "get last 10 records" → EVNT_JMES
    - "show first record" → EVNT_JMES
    - "retrieve last five records" → EVNT_JMES

Use EVNT_FLTR (Filter Records) when retrieving ALL/MULTIPLE COMPLETE RECORDS:
- Keywords: "get all records", "retrieve all records", "fetch all records", "show all records", "filter records" (without number limit)
- Pattern: "[action] all records [conditions]" or "[action] records [conditions]" (without specific number)
- Focus: ALL MATCHING RECORDS/ROWS with all fields, no limit specified
- Examples:
  - "Get all records where name starts with 'A'" → EVNT_FLTR
  - "Retrieve all records where quantity > 100" → EVNT_FLTR
  - "Show all employee records" → EVNT_FLTR
  - "Get records where status = active" → EVNT_FLTR (no "all" but no limit specified)

Use EVNT_RCRD_INFO (Retrieve a Record) when retrieving ONE COMPLETE RECORD:
- Keywords: "retrieve a record", "retrieve the record", "get a record", "get the record", "find a record", "find the record", "get record of [entity]", "retrieve record of [entity]"
- Pattern: "[action] a/the record [condition]" OR "[action] record of [entity] where [condition]"
- Focus: ONE COMPLETE RECORD/ROW with built-in filtering
- ⚠️ CRITICAL: Has BUILT-IN filtering - no need for separate EVNT_FLTR
- ⚠️ IMPORTANT: "retrieve a record" or "get a record" (with indefinite article "a") ALWAYS means EVNT_RCRD_INFO, NOT EVNT_FLTR
- Examples:
  - "retrieve a record where fee charged > 500" → EVNT_RCRD_INFO
  - "Get a record with id = 5" → EVNT_RCRD_INFO
  - "Retrieve the record where email = 'john@company.com'" → EVNT_RCRD_INFO

CRITICAL: Action Events with Built-in Filtering

Use Direct Action Events (NO additional retrieve/filter needed) for:

EVNT_RCRD_ADD (Create a Record):
- Keywords: "create a record", "add a record", "create record of [entity]"
- Pattern: "create [a] record of [entity] where [conditions]"
- For complex create operations with conditions, use CNDN_BIN + EVNT_RCRD_ADD
- Examples:
  - "create a record in enrollment tracking where fee charged is 2500 to fee charged 3000" → CNDN_BIN + EVNT_RCRD_ADD (binary condition evaluates the complex fee logic)

EVNT_RCRD_DUP (Duplicate a Record):
- Keywords: "duplicate the record", "duplicate record of [entity]"
- Pattern: "duplicate [the] record of [entity] where [conditions]"
- Has BUILT-IN filtering - directly duplicates matching record
- Examples:
  - "duplicate the record of Enrollment Tracking where Title is Enrollment 1 and status is enrolled" → EVNT_RCRD_DUP ONLY
  - "duplicate a record when value is greater than 100" → EVNT_RCRD_DUP ONLY (built-in condition handling)

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
- For update operations with conditions, use CNDN_BIN + EVNT_RCRD_UPDT
- Examples:
  - "update a record in enrollment tracking where fee charged is 2500 to fee charged 3000" → CNDN_BIN + EVNT_RCRD_UPDT (binary condition evaluates "where fee charged is 2500")

⚠️ CRITICAL RULE:
- DO NOT combine these action events with EVNT_RCRD_INFO, EVNT_FLTR, or CNDN_BIN (except for complex create operations)
- Each action event handles its own record selection and filtering internally
- Use ONLY the action event when the query is a direct action on records
- CREATE operations with complex conditions may need CNDN_BIN, CNDN_SEQ, CNDN_DOM for condition evaluation

CRITICAL ACTION DETECTION RULE:
If a query starts with "create" or contains "create a record", it is ALWAYS a CREATE operation (EVNT_RCRD_ADD), never an UPDATE operation, regardless of other words like "to" in the query.

2. Condition Selection (CNDN_BIN, CNDN_SEQ, CNDN_DOM) - CRITICAL RULES:


⚠️⚠️⚠️ CRITICAL: CONDITION TYPE DETECTION ⚠️⚠️⚠️

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

3. Loop Events (EVNT_LOOP_FOR, EVNT_LOOP_WHILE, EVNT_LOOP_DOWHILE):

Use EVNT_LOOP_FOR when:
- Iterating over data collections: "for each item in", "for every record", "process all items"
- Iterating over numeric ranges: "loop from X to Y", "from 1 to 10", "repeat 5 times"

Use EVNT_LOOP_WHILE when:
- Condition checked BEFORE each iteration
- Keywords: "while X is true", "as long as", "until X becomes"

Use EVNT_LOOP_DOWHILE when:
- Action executes at least ONCE, then condition checked
- Keywords: "do X at least once", "execute then check"

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
- "Create 5 records"
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

4. Key Decision Process - REFINED LOGIC:

STEP 0: STATIC KEYWORD DETECTION (HIGHEST PRIORITY)
- Scan query for: role, roles, department, departments, country, countries, user permission, user permissions
- IF ANY STATIC KEYWORD FOUND: Use STATIC events (_STC) ONLY - Stop here
- IF NO STATIC KEYWORDS: Proceed to Step 1

STEP 1: NUMBER/QUANTITY DETECTION (HIGH PRIORITY)
- Scan query for specific numbers/quantities OR positional keywords: "get 30 records", "get 10 records", "first 5 records", "top 20 records", "last 10 records", "first three", "last record"
- If specific number OR positional keyword found: Use EVNT_JMES ONLY - Stop here
- If no specific number or positional keyword found: Proceed to Step 2

STEP 2: FIELD NAME DETECTION
- Scan query for specific field names: "id/ids", "name/names", "status/statuses", "quantity/quantities", "email/emails", etc.
- If field name found: Use EVNT_JMES ONLY - Stop here
- If no field name found: Proceed to Step 3

STEP 3: ENTITY TYPE IDENTIFICATION
- Complete Records: "get records", "retrieve records", "show all employees", "fetch user data"
→ Use EVNT_FLTR (multiple records) or EVNT_RCRD_INFO (single record)
- Direct Actions: "duplicate/restore/delete/update the record"
→ Use direct action event ONLY (EVNT_RCRD_DUP/REST/DEL/UPDT)
- Conditional Actions: "if X then Y", "create if", "send email if"
→ Use appropriate condition + action events

STEP 4: LOOP DETECTION
- Scan for loop keywords: "for each", "loop through", "iterate", "from X to Y", "repeat", "while", "each item", "every record"
- If loop detected: Include appropriate loop event and mark internal events with "(INSIDE LOOP)"

STEP 5: CONDITION TYPE DETECTION
- Count conditions and check connection type:
- 1 condition with branching → CNDN_BIN
- 2+ independent conditions with "and check if" or "and if" → CNDN_SEQ (with CNDN_LGC for each)
- Cascading "if not/else" conditions → CNDN_DOM
- No branching logic → NO condition needed

STEP 6: COMMON MISTAKE PREVENTION
- NEVER combine EVNT_FLTR + EVNT_JMES for field extraction
- NEVER use EVNT_FLTR when a field name is mentioned in the query
- NEVER combine action events (DUP/REST/DEL/UPDT) with retrieve/filter events
- ALWAYS use EVNT_JMES for any field extraction, regardless of complexity
- NEVER use CNDN_BIN for simple "where" clauses in data queries
- NEVER use conditions for direct action events that have built-in filtering

EXAMPLES OF CORRECT IDENTIFICATION:

Static/Dynamic Records:
- "create a record with role: admin, department: science" → EVNT_RCRD_ADD_STC ONLY
- "add user with role manager and department IT" → EVNT_RCRD_ADD_STC ONLY
- "update role from admin to user" → EVNT_RCRD_UPDT_STC ONLY
- "get all departments" → EVNT_RCRD_INFO_STC ONLY
- "restore role admin" → EVNT_RCRD_REST_STC ONLY
- "create user permission for admin" → EVNT_RCRD_ADD_STC ONLY
- "get user permissions for department IT" → EVNT_RCRD_INFO_STC ONLY

Conditional Actions (USE conditions):
- "create a record in enrollment tracking where fee charged is 2500 to fee charged 3000" → CNDN_BIN + EVNT_RCRD_ADD (CREATE operation with complex condition)
- "if value > 100 then create record" → CNDN_BIN + EVNT_RCRD_ADD (conditional action)
- "Check if status is approved then send email, AND check if amount > 1000 then send alert" → CNDN_SEQ (with 2 CNDN_LGC) + EVNT_NOTI_MAIL + EVNT_NOTI_NOTI
- "If quantity < 50 then update record else delete record" → CNDN_BIN + EVNT_RCRD_UPDT + EVNT_RCRD_DEL

Direct Actions (NO conditions needed):
- "duplicate a record when value is greater than 100" → EVNT_RCRD_DUP ONLY (built-in condition handling)
- "delete a record when status is expired" → EVNT_RCRD_DEL ONLY (built-in condition handling)
- "update a record where fee charged is 2500" → EVNT_RCRD_UPDT ONLY (built-in filtering)
- "restore the record where id = 10" → EVNT_RCRD_REST ONLY

Data Extraction (NO conditions needed):
- "retrieve all id of records where Quantity > 10" → EVNT_JMES ONLY (field: "id")
- "get names from employees where dept = IT" → EVNT_JMES ONLY (field: "names")
- "show status of active users" → EVNT_JMES ONLY (field: "status")
- "get all records where quantity > 10" → EVNT_FLTR (no field specified, wants complete records)

Sequential Actions (NO conditions needed):
- "create a record with status active then send notification" → EVNT_RCRD_ADD + EVNT_NOTI_NOTI ONLY (no condition - sequential actions)
- "add a record but keep quantity 100 then update another record" → EVNT_RCRD_ADD + EVNT_RCRD_UPDT ONLY (no condition - field specification)

Positional Selection:
- "retrieve first three records" → EVNT_JMES ONLY (positional selection: first)
- "get last 10 records" → EVNT_JMES ONLY (positional selection: last)
- "show first record from enrollment tracking" → EVNT_JMES ONLY (positional selection: first)
- "retrieve last five records where status is active" → EVNT_JMES ONLY (positional selection: last with condition)

Loop Examples:
- "For each record, send email notification" → EVNT_LOOP_FOR + EVNT_NOTI_MAIL (INSIDE LOOP)
- "Loop from 1 to 10 and create a record each time" → EVNT_LOOP_FOR + EVNT_RCRD_ADD (INSIDE LOOP)
- "Process all items in the list and update their status" → EVNT_LOOP_FOR + EVNT_RCRD_UPDT (INSIDE LOOP)
- "Loop through numbers 1 to 10 and for each iteration, send email" → EVNT_LOOP_FOR (range_iteration_loop) + EVNT_NOTI_MAIL (INSIDE LOOP)

CRITICAL RULE: The presence of words like "records" doesn't matter - if a FIELD NAME is mentioned, use EVNT_JMES exclusively. If it's a direct action (duplicate/restore/delete/update), use ONLY the action event. CREATE operations with complex conditions use CNDN_BIN + EVNT_RCRD_ADD.

STEP X: Formula / Calculation Detection (EVNT_DATA_OPR)
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

EVENTS LIST WITH DESCRIPTIONS
"EVNT_NOTI_MAIL": "Email Notification - Email Events in the Workflow Builder module allow automated sending of emails based on workflow triggers. Users can configure emails with static values or dynamic content, including recipients, subject, body, and attachments. These events ensure timely and consistent communication by automatically sending emails when specific conditions or schedules are met.",
"EVNT_NOTI_SMS": "SMS Notification - SMS Notifications enable automated text messaging through services like Twilio based on workflow triggers. Users can configure provider credentials, specify recipients and message content, and validate settings to ensure proper delivery. These notifications streamline timely communication by automatically sending SMS messages when workflow conditions are met.",
"EVNT_NOTI_NOTI": "System Notification - Notification Events allow automated alerts to be sent to recipients based on specific workflow triggers. Users can configure the title, recipients, subject, and message content, ensuring that important updates reach the right stakeholders. This feature helps keep teams informed and ensures timely communication when predefined conditions are met.",
"EVNT_NOTI_PUSH": "Push Notification - Push Notification Events allow automated alerts to be sent to mobile devices based on specific workflow triggers. Users can configure the title, recipients, subject, and message content to ensure timely updates. This feature keeps stakeholders informed in real-time and ensures important notifications are delivered promptly when predefined conditions are met.",
"EVNT_UX_ALRT": "Alert Message - The Alert Message Event allows users to configure and display notifications within the system. Users can set the position on the screen, choose the alert type (default, success, error), specify an autoclose delay, and provide the message content. When triggered, the alert appears according to the configured settings, providing timely feedback or notifications to users.",
"EVNT_RCRD_ADD": "Create A Dynamic Record - Automates creation of application-specific records within customizable windows (e.g., hotel bookings, patient records, inventory items). Supports field configuration using static data, workflow variables, previous node outputs, or user input. Enables bulk creation for scalable industry-specific data management.",
"EVNT_RCRD_INFO": "Retrieve a Dynamic Record - Fetches specific application records from configurable system windows for processing, validation, or reference. Uses constants, workflow data, or filters to retrieve industry-specific data like military equipment, hotel reservations, or library transactions.",
"EVNT_RCRD_UPDT": "Update A Dynamic Record - Modifies existing application records by selecting from dynamic system windows. Fields can be auto-filled with previous data and updated using static values, workflow variables, or user input for real-time application data maintenance across different domains.",
"EVNT_RCRD_DEL": "Delete A Dynamic Record - Enables automated removal of application-specific records from dynamic windows based on predefined conditions. Uses constants, workflow data, or filters for precise deletion of industry-specific records like hospital appointments or military personnel data.",
"EVNT_RCRD_REST": "Restore A Dynamic Record - Recovers previously deleted application records from dynamic system windows based on predefined conditions. Enables automatic restoration of domain-specific data across various business systems.",
"EVNT_RCRD_DUP": "Duplicate A Dynamic Record - Creates exact copies of application records from dynamic system windows based on predefined conditions. Enables automatic duplication of industry-specific records with configurable field values for hotel room types, medical procedures, or library resources.",
"EVNT_RCRD_ADD_STC": "Create A Static Record - Automates creation of system-level static records for user management, role assignments, department setup, and other standardized system configurations. Supports consistent field mapping across all applications and domains.",
"EVNT_RCRD_INFO_STC": "Retrieve a Static Record - Fetches system-level static records from predefined tables for user authentication, role verification, department lookup, and other standardized system references that remain consistent regardless of application domain.",
"EVNT_RCRD_UPDT_STC": "Update A Static Record - Modifies existing system-level static records for user profile updates, role changes, department modifications, and other standardized system maintenance tasks that apply universally across all systems.",
"EVNT_RCRD_DEL_STC": "Delete A Static Record - Enables removal of system-level static records from predefined tables for user deactivation, role removal, or department cleanup following standardized system protocols applicable to all business domains.",
"EVNT_RCRD_REST_STC": "Restore A Static Record - Recovers previously deleted system-level static records from predefined tables for user reactivation, role restoration, or department recovery using consistent system-wide standards.",
"EVNT_RCRD_DUP_STC": "Duplicate A Static Record - Creates exact copies of system-level static records from predefined tables for role duplication, department cloning, or other standardized system configurations.",
"EVNT_DATA_OPR": "Calculation - The Formula Event allows users to perform dynamic computations and data transformations within workflows using predefined formulas. Users can define formula rows with static values, workflow variables, or outputs from previous events. Available formula categories include String, Arithmetic, Statistics, DateTime, Array, Dictionary, Regex, Math, Digital Logic, and Utility functions.",
"EVNT_FLTR": "Filter Records - The Filter Event allows users to retrieve multiple records from dynamic windows based on specific conditions. Users can define filtering criteria using field comparisons, logical operators, or workflow data to automatically select matching records. This event streamlines data retrieval.",
"EVNT_JMES": "JMES Data Extraction - The JMESPath Data Extraction Event enables users to transform and extract specific elements from JSON data using JMESPath queries. Input JSON can come from static sources or previous workflow steps, and queries allow filtering, restructuring, and generating new JSON outputs.",
"EVNT_JSON_CNTRCT": "JSON Contract Validation - The JSON Contract Validation Event enables users to validate JSON data against a predefined schema or contract. Acting as a quality gate in workflows, it ensures that data meets the required structure and constraints before proceeding.",
"EVNT_LGR": "Workflow Logger - The Workflow Logger Event records key workflow activities, errors, and events for monitoring, debugging, and auditing. It supports configurable logging levels (Info, Error, Access, Security, Performance), structured JSON log formats, and conditional logging.",
"EVNT_USER_MGMT_ADD": "Create a User - The Create User Event automates the creation of new users in the system by defining user details such as name, email, country, department, role, password, and creator. It supports specifying a logged-in or a static user as the creator.",
"EVNT_USER_MGMT_UPDT": "Update a User - The Update User Event automates modifying existing user details in the system, such as name, email, country, department, and role. It allows selecting a specific user, configuring update parameters, and triggering the event to apply changes.",
"EVNT_USER_MGMT_DEACT": "Deactivate / Activate a User - This event automates changing user statuses to 'Active' or 'Inactive.' Users can configure it for specific users via dropdown selection or for multiple users based on conditions (e.g., department).",
"EVNT_USER_MGMT_ASSIGN": "Assign a Role - This event automates assigning roles to users. Roles can be assigned to specific users via dropdown selection or through a designated user performing the assignment.",
"EVNT_USER_MGMT_EXTND": "Extend User to Another System - This event automates granting a user access to additional systems. Administrators select the user, choose the target system(s), and assign roles.",
"EVNT_ROLE_PRMSSN": "Assign or Remove Permissions - Event for managing role permissions within the system.",
"EVNT_PBL_RGSTN": "Public Registration - This event enables administrators to create a public registration link and send it via email. Configurations include link expiry, usage limits, department and role assignment, and customizable email content.",
"EVNT_INVC_ADD": "Generate Invoice - Event for creating invoices within the system.",
"EVNT_INVC_UPDT": "Update Invoice - Event for modifying existing invoices.",
"EVNT_INVC_SEND": "Send Invoice - Event for sending invoices to recipients.",
"EVNT_RPRT_PDF": "Report in PDF - This event enables automated report generation based on selected menus, windows, and templates. Users can configure input types and specify who updates the report.",
"EVNT_SPRT_TKT": "Support Ticket - Event for managing support ticket operations.",
"EVNT_RCRD_DUMP": "Generate Data Link - Event for creating data export links.",
"EVNT_EXT_API": "External API Event - This event automates interactions with external APIs by configuring HTTP requests, including method, URL, headers, and query parameters.",
"EVNT_NOTI_WBH": "Webhook - This event sends real-time notifications to external systems via a configured webhook URL. Users can set the URL, authentication credentials, payload, and notification settings.",
"EVNT_CHATGPT": "AI-Powered Event - This event integrates OpenAI's ChatGPT into workflows to automate conversational tasks, text processing, and intelligent responses. Users configure a prompt and authenticate with an OpenAI API token.",
"EVNT_EXT_DB": "External Database Integration - This event allows workflows to connect to external databases (PostgreSQL, MySQL, Oracle), execute SQL queries, and retrieve results in JSON format.",
"EVNT_VAR_ADD": "Create a variable - This event allows users to define and store variables for use in workflows. Users can specify the variable name, type, and input source.",
"EVNT_VAR_INFO": "Retrieve a variable - This event enables users to fetch previously stored variables for use in workflows. Users select the record ID to retrieve.",
"EVNT_VAR_UPDT": "Update a variable - This event allows users to modify previously stored variables for use in workflows. Users select the record ID to update.",
"EVNT_VAR_DEL": "Delete a variable - This event allows users to permanently remove stored variables. Users select the record ID to delete.",
"EVNT_UX_RDRCT": "Redirect (URL) - The Redirect URL Event allows users to automate redirection to specific URLs, supporting both local and external destinations.",
"EVNT_ACT_DYN_REQ": "Request an Approval - This event allows users to configure approval requests for specific records or processes. Users define the title, description, menu, window, and record setup.",
"EVNT_ACT_DYN_MOD": "Modify a Request - This event allows users to modify existing approval requests by configuring the title, description, menu, window, record field, default values, and the assigned user.",
"EVNT_ACT_VIEW": "View Data - Event for viewing specific data records.",
"EVNT_ACT_BULK_VIEW": "View Bulk Data - Event for viewing multiple data records.",
"EVNT_ACT_SHR": "Share - Event for sharing data or records.",
"EVNT_ACT_QR": "QR Code Generation - Event for generating QR codes.",
"EVNT_ACT_DWLND": "Download - Event for downloading data or files.",
"EVNT_ACT_CPY_RW": "Copy Row - Event for copying table rows.",
"EVNT_ACT_CPYDATA": "Copy Data - Event for copying data between fields or records.",
"EVNT_ACT_DISC_FM": "Discussion Forum - Event for forum discussions.",
"EVNT_ACT_MNG_SCH": "Manage Schedule - Event for schedule management.",
"EVNT_ACT_VRFY": "Verify - Event for verification operations.",
"EVNT_ACT_CMMNT": "Comment - Event for adding comments.",
"EVNT_LOOP_FOR": "For Loop - Iterates over a range of numbers or items in an array. It runs a defined workflow for each item or value in the sequence. Ideal for automating repetitive batch tasks like processing lists or sending bulk notifications.",
"EVNT_LOOP_WHILE": "While Loop - Repeats a workflow as long as a condition is true, checked before each iteration. Ideal for dynamic scenarios where the number of iterations is unknown and depends on changing data.",
"EVNT_LOOP_DOWHILE": "Do While Loop - Executes its workflow at least once. The condition to continue is checked after each iteration. Ideal for ensuring an action runs before checking if it needs to repeat.",
"EVNT_LOOP_BREAK": "Break Loop - This block is used to immediately exit a loop when a specified condition becomes true. It halts all further iterations, moving the workflow directly to the next step. This prevents unnecessary operations and optimizes efficiency.",
"EVNT_LOOP_CONTINUE": "Continue Loop - Skips the current loop iteration when a condition is met. Proceeds directly to the next cycle, bypassing any remaining steps. This prevents redundant actions and improves loop efficiency."

CONDITIONS LIST WITH DESCRIPTIONS
Include conditions ONLY if the workflow requires separate logical checks beyond inherent event logic (e.g., do not include for simple filters where the filter event already handles the criteria). Examples:
- Field value comparisons with branching: if quantity > 100 then X, else Y
- Boolean logic with branching: AND, OR, NOT
- Range checks with branching: if 10 <= age <= 50 then X

NEVER include CRUD actions (add_record, mod_record, delete_record, etc.) in conditions.
If no separate logical conditions are required, skip the Conditions section entirely.

CNDN_BIN = "Binary Condition - Binary Conditions in Workflow Management trigger actions based on true/false logic evaluations. A basic setup includes a logic block, an If block for true actions, and an Else block for false actions. Complex conditions can combine multiple criteria using AND/OR operators. Always validate and test conditions to ensure workflows run as expected."

CNDN_SEQ = "Sequential Condition - Sequential Conditions let you run logical checks in a set order, executing the first matching condition's action and skipping the rest. A basic setup handles simple scenarios, while complex setups use logical operators for multi-criteria conditions. Always validate and test to ensure correct actions trigger based on different sequential checks. Use with CNDN_LGC for each independent logic block."

CNDN_LGC = "Logic Block - Used within CNDN_SEQ to represent individual independent condition checks. Each CNDN_LGC contains one condition and its associated action."

CNDN_DOM = "Domino Condition - Domino Conditions enable sequential logical evaluations in workflows, triggering specific actions in order until a match is found, with fallback options for unmatched scenarios. A basic setup defines multiple conditions with corresponding actions, while complex conditions use logical operators (AND/OR) for advanced logic. Always validate and test conditions to ensure accurate execution across all scenarios."

CNDN_LGC_DOM = "Logic Domino Condition - Advanced domino conditions using logical operators (AND/OR) for complex multi-criteria evaluations in sequential order."

IMPORTANT INSTRUCTIONS:
- Analyze the user request thoroughly to identify all required components
- Create a comprehensive workflow plan that includes all necessary events, conditions, and loops
- Use appropriate triggers based on the request context
- Include conditions only when separate logical checks with branching are needed beyond event-inherent logic
- Use loops when repetitive actions are required (for each, loop from X to Y, etc.)
- Structure the workflow in a logical sequence from trigger to completion
- Make sure to use the correct event codes and descriptions
- Do not infer or add any extra steps, such as notifications or additional actions, unless explicitly stated in the user request
- For loops, mark events inside the loop with "(INSIDE LOOP)" notation
- For CNDN_SEQ, include CNDN_LGC for each independent logic block

Examples:

Simple action workflow (no conditions):
- Trigger: Database add_record
- Action: Send email notification
- No Conditions section included

Conditional workflow (CNDN_BIN - single condition):
- Trigger: Database update_record
- Condition: if status == "approved" then send email, else do nothing
- Action: Send email notification

Multiple independent conditions (CNDN_SEQ with CNDN_LGC):
- Trigger: Database add_record  
- Condition: CNDN_SEQ containing:
- CNDN_LGC: Check if risk = High then alert
- CNDN_LGC: Check if type = Permit then assign
- Actions: Send alert, Assign to team

Cascading conditions (CNDN_DOM):
- Trigger: API call
- Condition: CNDN_DOM - First check user exists, if not check permissions, if not check quota
- Actions: Based on which condition matches

Loop workflow:
- Trigger: File upload
- For Loop: Process each record in the file (EVNT_LOOP_FOR - data_iteration_loop)
- Action: Create record for each item (INSIDE LOOP)

Range Loop workflow:
- Trigger: UI Button click
- For Loop: Loop from 1 to 10 (EVNT_LOOP_FOR - range_iteration_loop)
- Action: Send email (INSIDE LOOP)

Filter workflow (no separate conditions or extra actions):
- Trigger: Database mod_record
- Action: Filter records where quantity > 90
- No Conditions section, no notifications

OUTPUT: Markdown Structured Workflow Plan ONLY.
- Include the Conditions / logic steps section only if applicable (actual branching logic needed).
- If the workflow is a simple action (e.g., add record, send email, SMS, push) or simple filter/retrieve, omit the Conditions section.
- Include loops when repetitive processing is needed.
- Mark loop internal events with "(INSIDE LOOP)" notation.
- For CNDN_SEQ, show each CNDN_LGC logic block.
"""
logger.debug("Defined full prompt for planner_agent")



def plan_workflow(user_input: str):
    logger.info(f"Generating workflow plan for user input: {user_input}")
    task = Task(
        description=f"User Query: {user_input}\n{prompt_full}",
        agent=planner_agent,
        expected_output="Markdown structured workflow plan with explicit trigger_code, code, and code for each component.",
    )
    crew = Crew(agents=[planner_agent], tasks=[task])
    try:
        result = crew.kickoff()
        workflow_plan = result.output if hasattr(result, "output") else str(result)
        logger.debug(f"Generated workflow plan:\n{workflow_plan}")
        
        # Extract codes and flow sequence from the workflow plan
        trigger = None
        events = []
        conditions = []
        flow_sequence = []
        
        # Enhanced regex patterns
        flow_sequence_pattern = r"^\s*\d+\.\s*([^\(]+?)\s*\((\w+)\)\s*$"
        code_pattern = r"(?i)(?:code|trigger_code|event_code|condition_code)?:\s*([A-Za-z0-9_]+)"
        
        # Exact patterns from original code
        standalone_event_pattern = r"\b(EVNT_[A-Z_]+)\b"
        standalone_trigger_pattern = r"\b(TRG_[A-Z_]+)\b"
        standalone_condition_pattern = r"\b(CNDN_[A-Z_]+|cndn_[a-z_]+)\b"
        
        current_section = None
        lines = workflow_plan.split("\n")
        
        for line in lines:
            line = line.strip()
            

            if line.startswith("#"):
                line_lower = line.lower()

                if "trigger" in line_lower and "detail" not in line_lower:
                    current_section = "Trigger"

                elif "events" in line_lower or "actions" in line_lower:
                    current_section = "Events"

                # ✅ PATCH: treat Conditions / Logic Steps as Flow Sequence
                elif "condition" in line_lower and "flow" not in line_lower:
                    current_section = "Flow Sequence"

                elif "flow" in line_lower and "sequence" in line_lower:
                    current_section = "Flow Sequence"

            
        
            code_matches = re.findall(code_pattern, line)
            for code in code_matches:
                if current_section == "Trigger" and not trigger:
                    if re.match(r"TRG_[A-Z_]+", code):
                        trigger = code
                        logger.debug(f"  Found trigger: {code}")
                elif current_section == "Events":
                    if re.match(r"EVNT_[A-Z_]+", code) and code not in events:
                        events.append(code)
                        logger.debug(f"  Found event: {code}")
                elif current_section == "Conditions":
                    if re.match(r"(CNDN_[A-Z_]+)", code) and code not in conditions:
                        conditions.append(code)
                        logger.debug(f"  Found condition: {code}")

            # Standalone codes (UNCHANGED)
            if current_section == "Events":
                standalone_events = re.findall(standalone_event_pattern, line)
                for event in standalone_events:
                    if event not in events:
                        events.append(event)
                        logger.debug(f"  Found standalone event: {event}")
            elif current_section == "Trigger" and not trigger:
                standalone_triggers = re.findall(standalone_trigger_pattern, line)
                if standalone_triggers:
                    trigger = standalone_triggers[0]
                    logger.debug(f"  Found standalone trigger: {trigger}")
            elif current_section == "Conditions":
                standalone_conditions = re.findall(standalone_condition_pattern, line)
                for condition in standalone_conditions:
                    condition_upper = condition.upper()
                    if condition_upper not in conditions:
                        conditions.append(condition_upper)
                        logger.debug(f"  Found standalone condition: {condition_upper}")

            if current_section in ["Events", "Conditions"] or "CNDN_BIN" in line or "cndn_bin" in line.lower():
                line_conditions = re.findall(standalone_condition_pattern, line)
                for condition in line_conditions:
                    condition_upper = condition.upper()
                    if condition_upper not in conditions:
                        conditions.append(condition_upper)
            
            if current_section is None:
                # Check if line looks like a numbered flow item: "1. Something (CODE)"
                if re.match(r"^\s*\d+\.\s*.+\([A-Z_]+\)", line):
                    current_section = "Flow Sequence"
                    logger.debug(f"✅ Auto-detected Flow Sequence from numbered item: {line}")
                # Also check for branch lines that indicate we're in flow sequence
                elif re.match(r"^\s*↳\s*(IF TRUE|IF FALSE|INSIDE LOOP|Logic Block|Container)", line):
                    current_section = "Flow Sequence"
                    logger.debug(f"✅ Auto-detected Flow Sequence from branch line: {line}")

       
            if current_section == "Flow Sequence":
                logger.debug(f"[FLOW SEQ] Processing: {line}")
                
                # Main flow items (numbered) - UNCHANGED
                main_flow_match = re.match(flow_sequence_pattern, line)
                if main_flow_match:
                    description, code = main_flow_match.groups()
                    logger.debug(f"  Main flow match: {description} ({code})")
                    
                    # Validation
                    is_valid_trigger = re.match(r"TRG_[A-Z_]+", code)
                    is_valid_event = re.match(r"EVNT_[A-Z_]+", code)
                    is_valid_condition = re.match(r"CNDN_[A-Z_]+", code.upper())
                    
                    if is_valid_trigger or is_valid_event or is_valid_condition:
                        flow_item = {
                            "step": description.strip(),
                            "code": code,
                            "branches": {}
                        }
                        flow_sequence.append(flow_item)
                        logger.debug(f"  ✅ Added to flow_sequence: {code}")
                        
                        # Populate main lists
                        if is_valid_trigger and not trigger:
                            trigger = code
                        elif is_valid_event and code not in events:
                            events.append(code)
                        elif is_valid_condition:
                            code_upper = code.upper()
                            if code_upper not in conditions:
                                conditions.append(code_upper)
                    continue
                
                

            
                branch_match = re.match(
                    r"^\s*↳\s*(IF TRUE|IF FALSE|INSIDE LOOP|Logic Block \d+|Container \d+)\s*(?:\(([A-Z_]+)\))?:\s*(.+?)(?:\s*→\s*(.+))?$",
                    line
                )
                
                if branch_match:
                    if not flow_sequence:
                        logger.warning(f"  ⚠️ Branch found but flow_sequence is empty: {line}")
                        continue
                    
                    branch_type, condition_code, description, flow_dest = branch_match.groups()
                    logger.debug(f"  Branch match: type={branch_type}, condition={condition_code}, desc={description}, dest={flow_dest}")
                    

                    event_code = None
                    if flow_dest:
                        event_match = re.search(r"\(([A-Z_]+)\)$", flow_dest)
                        if event_match:
                            event_code = event_match.group(1)
                            logger.debug(f"    Extracted event code from flow_dest: {event_code}")
                    
                    # Fallback: if condition_code is actually an event code (starts with EVNT_)
                    if not event_code and condition_code and condition_code.startswith("EVNT_"):
                        event_code = condition_code
                        logger.debug(f"    Using condition_code as event: {event_code}")
                    
                    # Get the last main flow item
                    last_item = flow_sequence[-1]

                    # For Logic Blocks, find the CNDN_SEQ parent
                    if "Logic Block" in branch_type:
                        for item in reversed(flow_sequence):
                            if item.get("code") == "CNDN_SEQ":
                                last_item = item
                                break

                    # Extract event code if present
                    if event_code:
                        # Add to events list if not already present
                        if event_code not in events:
                            events.append(event_code)
                            logger.debug(f"    Added event from branch: {event_code}")
                        
                        # ========================================================
                        # Store in branches based on type
                        # ========================================================
                        if branch_type == "IF TRUE":
                            last_item["branches"]["if_true"] = event_code
                            last_item["branches"]["if_true_desc"] = description.strip()
                            logger.debug(f"    ✅ Set IF TRUE: {event_code}")
                            
                        elif branch_type == "IF FALSE":
                            last_item["branches"]["if_false"] = event_code
                            last_item["branches"]["if_false_desc"] = description.strip()
                            logger.debug(f"    ✅ Set IF FALSE: {event_code} (explicit action)")
                                
                        elif branch_type == "INSIDE LOOP":
                            if "loop_internal" not in last_item["branches"]:
                                last_item["branches"]["loop_internal"] = []
                            last_item["branches"]["loop_internal"].append({
                                "event": event_code,
                                "description": description.strip()
                            })
                            logger.debug(f"    ✅ Added to loop_internal: {event_code}")
                            
                        elif "Logic Block" in branch_type:
                            if "logic_blocks" not in last_item["branches"]:
                                last_item["branches"]["logic_blocks"] = []
                            last_item["branches"]["logic_blocks"].append({
                                "event": event_code,
                                "description": description.strip() + (" → " + flow_dest if flow_dest else "")
                            })
                            logger.debug(f"    ✅ Added to logic_blocks: {event_code}")
                            
                        elif "Container" in branch_type:
                            if "containers" not in last_item["branches"]:
                                last_item["branches"]["containers"] = []
                            last_item["branches"]["containers"].append({
                                "event": event_code,
                                "description": description.strip()
                            })
                            logger.debug(f"    ✅ Added to containers: {event_code}")
                    
                    else:
                        # No event code found - check if it's "route to END"
                        description_lower = description.lower() if description else ""
                        flow_dest_upper = flow_dest.upper() if flow_dest else ""
                        
                        if "route to end" in description_lower or "END" in flow_dest_upper:
                            if branch_type == "IF FALSE":
                                last_item["branches"]["if_false"] = "END"
                                last_item["branches"]["if_false_desc"] = "Route to END"
                                logger.debug(f"    ✅ Set IF FALSE: END (implicit - no event code)")
                            elif branch_type == "IF TRUE":
                                last_item["branches"]["if_true"] = "END"
                                last_item["branches"]["if_true_desc"] = "Route to END"
                                logger.debug(f"    ✅ Set IF TRUE: END (implicit - no event code)")
                        
                        # For Logic Blocks without event code in flow_dest, try to extract from description
                        elif "Logic Block" in branch_type:
                            # Try to find event code anywhere in the line
                            full_line_event = re.search(r"\(EVNT_[A-Z_]+\)", line)
                            if full_line_event:
                                extracted_event = full_line_event.group(0)[1:-1]  # Remove parentheses
                                if extracted_event not in events:
                                    events.append(extracted_event)
                                if "logic_blocks" not in last_item["branches"]:
                                    last_item["branches"]["logic_blocks"] = []
                                last_item["branches"]["logic_blocks"].append({
                                    "event": extracted_event,
                                    "description": description.strip() + (" → " + flow_dest if flow_dest else "")
                                })
                                logger.debug(f"    ✅ Added to logic_blocks (full line search): {extracted_event}")
                    
                    continue

        
                nested_match = re.match(
                    r"^\s*→\s*(IF|ELSE):\s*(.+?)(?:\s*\(([A-Z_]+)\))?(?:\s*→\s*(.+))?",
                    line
                )
                if nested_match and flow_sequence:
                    branch_type, description, event_code, flow_dest = nested_match.groups()
                    
                    last_item = flow_sequence[-1]
                    if "containers" in last_item["branches"] and last_item["branches"]["containers"]:
                        last_container = last_item["branches"]["containers"][-1]
                        
                        if "nested" not in last_container:
                            last_container["nested"] = []
                        
                        nested_item = {
                            "branch_type": branch_type.strip(),
                            "description": description.strip(),
                            "event": event_code if event_code else None,
                            "flow_dest": flow_dest.strip() if flow_dest else None
                        }
                        last_container["nested"].append(nested_item)
                        
                        # Add event to main list if present
                        if event_code and event_code not in events:
                            events.append(event_code)
                            logger.debug(f"    Added nested event: {event_code}")
        
       
        if not flow_sequence:
            logger.warning("Flow sequence is empty, constructing from collected components")
            if trigger:
                flow_sequence.append({
                    "step": f"Trigger on {trigger.lower().replace('_', ' ')}",
                    "code": trigger,
                    "branches": {}
                })
            for condition in conditions:
                flow_sequence.append({
                    "step": f"Evaluate condition {condition}",
                    "code": condition,
                    "branches": {}
                })
            for event in events:
                flow_sequence.append({
                    "step": f"Execute event {event}",
                    "code": event,
                    "branches": {}
                })
       
        binary_branches = {}
        sequence_logic_blocks = []
        domino_containers = []
        loop_internal_events = []
        
        for step in flow_sequence:
            code = step.get("code", "")
            branches = step.get("branches", {})
            
            # Binary condition branches
            if code == "CNDN_BIN":
                if_branch = branches.get("if_true")
                else_branch = branches.get("if_false")
                
                # Determine if else is explicit
                has_explicit_else = else_branch is not None and else_branch != "END"
                
                binary_branches = {
                    "if_branch": if_branch,
                    "else_branch": else_branch,
                    "has_explicit_else": has_explicit_else,
                    "if_branch_desc": branches.get("if_true_desc", ""),
                    "else_branch_desc": branches.get("if_false_desc", "")
                }
                logger.info(f"✅ Extracted binary branches: {binary_branches}")
            
            # Sequence condition logic blocks
            # elif code == "CNDN_SEQ":
            #     logic_blocks = branches.get("logic_blocks", [])
            #     sequence_logic_blocks = [lb["event"] for lb in logic_blocks if "event" in lb]
            #     logger.info(f"✅ Extracted sequence logic blocks: {sequence_logic_blocks}")

            elif code == "CNDN_SEQ":
                logic_blocks = branches.get("logic_blocks", [])
                sequence_logic_blocks = []

                for idx, lb in enumerate(logic_blocks, start=1):
                    event = lb.get("event")
                    sequence_logic_blocks.append({
                        "logic_id": f"logic_{idx}",
                        "description": lb.get("description"),
                        "event": event,
                        "next": "END"
                    })

                    # ✅ push events immediately, safely
                    if event and event not in events:
                        events.append(event)

                logger.info(f"✅ Extracted sequence logic blocks: {sequence_logic_blocks}")


            # Domino condition containers
            elif code == "CNDN_DOM":
                containers = branches.get("containers", [])
                domino_containers = [c["event"] for c in containers if "event" in c]
                logger.info(f" Extracted domino containers: {domino_containers}")
            
            # Loop internal events
            elif code == "EVNT_LOOP_FOR":
                loop_events = branches.get("loop_internal", [])
                loop_internal_events = [le["event"] for le in loop_events if "event" in le]
                logger.info(f"Extracted loop internal events: {loop_internal_events}")
        
    
        codes_output = {
            "trigger": trigger or "UNKNOWN",
            "events": events,
            "conditions": conditions,
            "flow_sequence": flow_sequence,
            "binary_branches": binary_branches,
            "sequence_logic_blocks": sequence_logic_blocks,
            "domino_containers": domino_containers,
            "loop_internal_events": loop_internal_events
        }
        
        logger.info(f" Final extraction summary:")
        logger.info(f"  Trigger: {trigger}")
        logger.info(f"  Events: {events}")
        logger.info(f"  Conditions: {conditions}")
        logger.info(f"  Flow sequence items: {len(flow_sequence)}")
        logger.info(f"  Binary branches: {binary_branches}")
        
        # try:
        #     with open("codes.json", "w") as f:
        #         json.dump(codes_output, f, indent=2)
        #     logger.info(" Saved extracted codes and flow sequence to codes.json")
        # except Exception as e:
        #     logger.error(f"Failed to save codes to codes.json: {str(e)}")
        #     raise
        
        return workflow_plan, codes_output
    except Exception as e:
        logger.error(f"Error in plan_workflow: {str(e)}")
        raise




