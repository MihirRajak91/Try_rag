# scripts/run_planner_agent.py
import json
from planner.compiler_with_crew import compile_with_crew
from planner.simple_logger import SimpleRunLogger
import uuid
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    run_id = str(uuid.uuid4())[:8]
    logger = SimpleRunLogger(run_id)

    logger.log("START")
    plan, judge = compile_with_crew(q, enable_validation=False,verbose=False)

    print("\n=== PLAN ===\n")
    print(plan)

    print("\n=== JUDGE ===\n")
    print(json.dumps(judge, indent=2, ensure_ascii=False))

    logger.log("END")
    logger.finish()

if __name__ == "__main__":
    main()
