# planner/model_config.py
import os

# Judge model (cheap + consistent)
JUDGE_MODEL = os.getenv("JUDGE_MODEL")

# (Optional later) Planner model if you want to configure it too
PLANNER_MODEL = os.getenv("PLANNER_MODEL")
