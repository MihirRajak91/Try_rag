# scripts/run_planner_agent.py
import json
from planner.compiler_with_crew import compile_with_crew

def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    plan, judge = compile_with_crew(q, max_iters=2, verbose=True)

    print("\n=== PLAN ===\n")
    print(plan)

    print("\n=== JUDGE ===\n")
    print(json.dumps(judge, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
