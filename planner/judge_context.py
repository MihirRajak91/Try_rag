# planner/judge_context.py

TRIGGERS_ENUMS = """TRG_API, TRG_DB, TRG_FILE, TRG_SCH, TRG_BTN, TRG_WBH, TRG_AUTH, TRG_APRVL, TRG_FLD, TRG_OUT"""

# Keep this as just the codes (not long descriptions)
EVENT_ENUMS = """EVNT_NOTI_MAIL, EVNT_NOTI_SMS, EVNT_NOTI_NOTI, EVNT_NOTI_PUSH, EVNT_NOTI_WBH, EVNT_UX_ALRT,
EVNT_RCRD_ADD, EVNT_RCRD_INFO, EVNT_RCRD_UPDT, EVNT_RCRD_DEL, EVNT_RCRD_REST, EVNT_RCRD_DUP,
EVNT_RCRD_ADD_STC, EVNT_RCRD_INFO_STC, EVNT_RCRD_UPDT_STC, EVNT_RCRD_DEL_STC, EVNT_RCRD_REST_STC, EVNT_RCRD_DUP_STC,
EVNT_FLTR, EVNT_JMES, EVNT_DATA_OPR, EVNT_JSON_CNTRCT, EVNT_LGR,
EVNT_USER_MGMT_ADD, EVNT_USER_MGMT_UPDT, EVNT_USER_MGMT_DEACT, EVNT_USER_MGMT_ASSIGN, EVNT_USER_MGMT_EXTND,
EVNT_EXT_API, EVNT_EXT_DB,
EVNT_VAR_ADD, EVNT_VAR_INFO, EVNT_VAR_UPDT, EVNT_VAR_DEL,
EVNT_LOOP_FOR, EVNT_LOOP_WHILE, EVNT_LOOP_DOWHILE, EVNT_LOOP_BREAK, EVNT_LOOP_CONTINUE
"""

CONDITION_ENUMS = """CNDN_BIN, CNDN_SEQ, CNDN_LGC, CNDN_DOM, CNDN_LGC_DOM"""

LOOP_ENUMS = """EVNT_LOOP_FOR, EVNT_LOOP_WHILE, EVNT_LOOP_DOWHILE"""

# Rules: keep only decision rules, not catalogs/descriptions
JUDGE_RULES = """
- Default trigger is TRG_DB.
- Use TRG_APRVL ONLY if user explicitly mentions approval / approve button / request approval.
- Conditions allowed ONLY when explicit branching is requested (if/else/otherwise).
- Loops allowed ONLY when repetition is explicitly requested (for each/iterate/loop).
- CRUD with built-in filtering: "Delete record ... where ..." => EVNT_RCRD_DEL, NO Conditions.
- Retrieval:
  - "Get records from X" => EVNT_RCRD_INFO
  - "Get records from X where ..." => EVNT_FLTR
"""
